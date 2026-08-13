from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    GroupNotFoundError,
    HangoutEditForbiddenError,
    HangoutNotFoundError,
    HangoutProposalRequiredError,
    HangoutStateConflictError,
    HangoutTimeOptionRequiredError,
    HangoutVotingDeadlineElapsedError,
    HangoutVotingForbiddenError,
)
from app.core.group_security import HangoutPageCursor, SignedCursorCodec
from app.models.enums import GroupMemberRole, HangoutStatus
from app.models.hangout import Hangout
from app.models.user import User
from app.repositories.hangout import HangoutRepository


@dataclass(frozen=True, slots=True)
class HangoutPage:
    items: list[Hangout]
    next_cursor: str | None
    has_more: bool


class HangoutService:
    """Apply hangout membership/editing rules and own write transactions."""

    def __init__(
        self,
        *,
        repository: HangoutRepository,
        cursors: SignedCursorCodec,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._hangouts = repository
        self._cursors = cursors
        self._clock = clock or (lambda: datetime.now(UTC))

    async def create_hangout(
        self,
        current_user: User,
        *,
        group_id: UUID,
        title: str,
        description: str | None,
        voting_deadline: datetime | None,
    ) -> Hangout:
        try:
            membership = await self._hangouts.get_active_membership_for_update(
                group_id=group_id,
                user_id=current_user.id,
            )
            if membership is None:
                raise GroupNotFoundError
            hangout = await self._hangouts.create(
                group_id=group_id,
                created_by_user_id=current_user.id,
                title=title.strip(),
                description=self._normalize_description(description),
                voting_deadline=self._normalize_deadline(voting_deadline),
            )
            await self._hangouts.commit()
        except IntegrityError as exc:
            await self._hangouts.rollback()
            raise HangoutStateConflictError from exc
        except Exception:
            await self._hangouts.rollback()
            raise
        return hangout

    async def list_hangouts(
        self,
        current_user: User,
        *,
        group_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> HangoutPage:
        await self._require_active_membership(current_user, group_id=group_id)
        scope = f"group:{group_id}"
        after = (
            cast(
                HangoutPageCursor,
                self._cursors.decode(cursor, kind="hangout_list", scope=scope),
            )
            if cursor is not None
            else None
        )
        rows = await self._hangouts.list_in_group(
            group_id=group_id,
            after=after,
            limit=limit + 1,
        )
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = self._cursors.encode(
                HangoutPageCursor(created_at=last.created_at, hangout_id=last.id),
                kind="hangout_list",
                scope=scope,
            )
        return HangoutPage(items=items, next_cursor=next_cursor, has_more=has_more)

    async def read_hangout(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
    ) -> Hangout:
        await self._require_active_membership(current_user, group_id=group_id)
        hangout = await self._hangouts.get_in_group(
            group_id=group_id,
            hangout_id=hangout_id,
        )
        if hangout is None:
            raise HangoutNotFoundError
        return hangout

    async def update_hangout(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
        title: str,
        description: str | None,
        voting_deadline: datetime | None,
    ) -> Hangout:
        try:
            membership = await self._hangouts.get_active_membership_for_update(
                group_id=group_id,
                user_id=current_user.id,
            )
            if membership is None:
                raise GroupNotFoundError
            hangout = await self._hangouts.get_in_group_for_update(
                group_id=group_id,
                hangout_id=hangout_id,
            )
            if hangout is None:
                raise HangoutNotFoundError
            if (
                hangout.created_by_user_id != current_user.id
                and membership.role != GroupMemberRole.OWNER
            ):
                raise HangoutEditForbiddenError
            if hangout.status != HangoutStatus.DRAFT:
                raise HangoutStateConflictError
            updated = await self._hangouts.update(
                hangout,
                title=title.strip(),
                description=self._normalize_description(description),
                voting_deadline=self._normalize_deadline(voting_deadline),
            )
            await self._hangouts.commit()
        except IntegrityError as exc:
            await self._hangouts.rollback()
            raise HangoutStateConflictError from exc
        except Exception:
            await self._hangouts.rollback()
            raise
        return updated

    async def start_voting(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
    ) -> Hangout:
        try:
            membership = await self._hangouts.get_active_membership_for_update(
                group_id=group_id,
                user_id=current_user.id,
            )
            if membership is None:
                raise GroupNotFoundError
            hangout = await self._hangouts.get_in_group_for_update(
                group_id=group_id,
                hangout_id=hangout_id,
            )
            if hangout is None:
                raise HangoutNotFoundError
            if (
                hangout.created_by_user_id != current_user.id
                and membership.role != GroupMemberRole.OWNER
            ):
                raise HangoutVotingForbiddenError
            if hangout.status != HangoutStatus.DRAFT:
                raise HangoutStateConflictError
            if hangout.voting_deadline is not None and (
                hangout.voting_deadline.astimezone(UTC) <= self._clock().astimezone(UTC)
            ):
                raise HangoutVotingDeadlineElapsedError
            if await self._hangouts.count_proposals(hangout_id=hangout.id) < 1:
                raise HangoutProposalRequiredError
            if await self._hangouts.count_time_options(hangout_id=hangout.id) < 1:
                raise HangoutTimeOptionRequiredError
            voting_hangout = await self._hangouts.start_voting(hangout)
            await self._hangouts.commit()
        except IntegrityError as exc:
            await self._hangouts.rollback()
            raise HangoutStateConflictError from exc
        except Exception:
            await self._hangouts.rollback()
            raise
        return voting_hangout

    async def _require_active_membership(self, current_user: User, *, group_id: UUID) -> None:
        membership = await self._hangouts.get_active_membership(
            group_id=group_id,
            user_id=current_user.id,
        )
        if membership is None:
            raise GroupNotFoundError

    @staticmethod
    def _normalize_description(description: str | None) -> str | None:
        if description is None:
            return None
        normalized = description.strip()
        return normalized or None

    @staticmethod
    def _normalize_deadline(voting_deadline: datetime | None) -> datetime | None:
        if voting_deadline is None:
            return None
        return voting_deadline.astimezone(UTC)
