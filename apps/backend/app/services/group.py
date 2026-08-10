from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    GroupConfirmationNameMismatchError,
    GroupNotFoundError,
    GroupOwnerRequiredError,
    GroupStateConflictError,
)
from app.core.group_security import (
    CursorKind,
    GroupInviteTokenService,
    IssuedGroupInviteToken,
    PageCursor,
    SignedCursorCodec,
)
from app.models.enums import GroupMemberRole
from app.models.user import User
from app.repositories.group import GroupMemberSummary, GroupRepository, GroupSummary


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: list[T]
    next_cursor: str | None
    has_more: bool


class GroupService:
    """Apply group membership rules and own group transaction boundaries."""

    def __init__(
        self,
        *,
        repository: GroupRepository,
        invite_tokens: GroupInviteTokenService,
        cursors: SignedCursorCodec,
    ) -> None:
        self._groups = repository
        self._invite_tokens = invite_tokens
        self._cursors = cursors

    async def create_group(
        self,
        current_user: User,
        *,
        name: str,
        description: str | None,
    ) -> GroupSummary:
        try:
            group = await self._groups.create_with_owner(
                user_id=current_user.id,
                name=name.strip(),
                description=self._normalize_description(description),
            )
            await self._groups.commit()
        except IntegrityError as exc:
            await self._groups.rollback()
            raise GroupStateConflictError from exc
        except Exception:
            await self._groups.rollback()
            raise
        return group

    async def list_groups(
        self,
        current_user: User,
        *,
        cursor: str | None,
        limit: int,
    ) -> Page[GroupSummary]:
        scope = f"user:{current_user.id}"
        after = (
            self._cursors.decode(cursor, kind="group_list", scope=scope)
            if cursor is not None
            else None
        )
        rows = await self._groups.list_active_groups(
            user_id=current_user.id,
            after=after,
            limit=limit + 1,
        )
        return self._group_page(rows, limit=limit, kind="group_list", scope=scope)

    async def read_group(self, current_user: User, *, group_id: UUID) -> GroupSummary:
        group = await self._groups.get_active_group(
            group_id=group_id,
            user_id=current_user.id,
        )
        if group is None:
            raise GroupNotFoundError
        return group

    async def list_members(
        self,
        current_user: User,
        *,
        group_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> Page[GroupMemberSummary]:
        await self.read_group(current_user, group_id=group_id)
        scope = f"group:{group_id}"
        after = (
            self._cursors.decode(cursor, kind="group_member_list", scope=scope)
            if cursor is not None
            else None
        )
        rows = await self._groups.list_active_members(
            group_id=group_id,
            after=after,
            limit=limit + 1,
        )
        return self._member_page(rows, limit=limit, scope=scope)

    async def create_invite_token(
        self,
        current_user: User,
        *,
        group_id: UUID,
    ) -> IssuedGroupInviteToken:
        await self.read_group(current_user, group_id=group_id)
        return self._invite_tokens.issue(group_id)

    async def join_group(
        self,
        current_user: User,
        *,
        group_id: UUID,
        invite_token: str,
    ) -> GroupSummary:
        self._invite_tokens.verify(invite_token, expected_group_id=group_id)
        try:
            if not await self._groups.group_exists(group_id):
                raise GroupNotFoundError
            await self._groups.join_group(group_id=group_id, user_id=current_user.id)
            group = await self._groups.get_active_group(
                group_id=group_id,
                user_id=current_user.id,
            )
            if group is None:
                raise GroupStateConflictError
            await self._groups.commit()
        except IntegrityError as exc:
            await self._groups.rollback()
            raise GroupStateConflictError from exc
        except Exception:
            await self._groups.rollback()
            raise
        return group

    async def delete_group(
        self,
        current_user: User,
        *,
        group_id: UUID,
        confirmation_name: str,
    ) -> None:
        try:
            target = await self._groups.get_active_group_for_update(
                group_id=group_id,
                user_id=current_user.id,
            )
            if target is None:
                raise GroupNotFoundError
            if target.current_user_role != GroupMemberRole.OWNER:
                raise GroupOwnerRequiredError
            if confirmation_name.strip() != target.group.name:
                raise GroupConfirmationNameMismatchError
            await self._groups.delete_group(target.group)
            await self._groups.commit()
        except IntegrityError as exc:
            await self._groups.rollback()
            raise GroupStateConflictError from exc
        except Exception:
            await self._groups.rollback()
            raise

    def _group_page(
        self,
        rows: list[GroupSummary],
        *,
        limit: int,
        kind: CursorKind,
        scope: str,
    ) -> Page[GroupSummary]:
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = self._cursors.encode(
                PageCursor(joined_at=last.joined_at, membership_id=last.membership_id),
                kind=kind,
                scope=scope,
            )
        return Page(items=items, next_cursor=next_cursor, has_more=has_more)

    def _member_page(
        self,
        rows: list[GroupMemberSummary],
        *,
        limit: int,
        scope: str,
    ) -> Page[GroupMemberSummary]:
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = self._cursors.encode(
                PageCursor(joined_at=last.joined_at, membership_id=last.membership_id),
                kind="group_member_list",
                scope=scope,
            )
        return Page(items=items, next_cursor=next_cursor, has_more=has_more)

    @staticmethod
    def _normalize_description(description: str | None) -> str | None:
        if description is None:
            return None
        normalized = description.strip()
        return normalized or None
