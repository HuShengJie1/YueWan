from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    GroupNotFoundError,
    HangoutNotFoundError,
    InvalidTimeOptionError,
    TimeOptionManageForbiddenError,
    TimeOptionNotFoundError,
    TimeOptionStateConflictError,
)
from app.core.group_security import SignedCursorCodec, TimeOptionPageCursor
from app.models.enums import GroupMemberRole, HangoutStatus
from app.models.group import GroupMember
from app.models.hangout import Hangout
from app.models.time_option import TimeOption
from app.models.user import User
from app.repositories.time_option import TimeOptionRepository


@dataclass(frozen=True, slots=True)
class ManagedTimeOption:
    time_option: TimeOption
    can_manage: bool


@dataclass(frozen=True, slots=True)
class TimeOptionPage:
    items: list[ManagedTimeOption]
    next_cursor: str | None
    has_more: bool


class TimeOptionService:
    """Apply time-option visibility/management rules and own write transactions."""

    def __init__(
        self,
        *,
        repository: TimeOptionRepository,
        cursors: SignedCursorCodec,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._time_options = repository
        self._cursors = cursors
        self._clock = clock or (lambda: datetime.now(UTC))

    async def create_time_option(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
        starts_at: datetime,
        ends_at: datetime | None,
        display_label: str | None,
    ) -> ManagedTimeOption:
        try:
            membership = await self._time_options.get_active_membership_for_update(
                group_id=group_id,
                user_id=current_user.id,
            )
            if membership is None:
                raise GroupNotFoundError
            hangout = await self._time_options.get_hangout_for_update(
                group_id=group_id,
                hangout_id=hangout_id,
            )
            if hangout is None:
                raise HangoutNotFoundError
            self._require_draft(hangout)
            normalized_start, normalized_end = self._normalize_time_range(
                starts_at=starts_at,
                ends_at=ends_at,
            )
            time_option = await self._time_options.create(
                hangout_id=hangout_id,
                created_by_user_id=current_user.id,
                starts_at=normalized_start,
                ends_at=normalized_end,
                display_label=self._normalize_display_label(display_label),
            )
            await self._time_options.commit()
        except IntegrityError as exc:
            await self._time_options.rollback()
            raise TimeOptionStateConflictError from exc
        except Exception:
            await self._time_options.rollback()
            raise
        return ManagedTimeOption(time_option=time_option, can_manage=True)

    async def list_time_options(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> TimeOptionPage:
        membership, hangout = await self._require_read_context(
            current_user,
            group_id=group_id,
            hangout_id=hangout_id,
        )
        scope = self._cursor_scope(group_id=group_id, hangout_id=hangout_id)
        after = (
            cast(
                TimeOptionPageCursor,
                self._cursors.decode(cursor, kind="time_option_list", scope=scope),
            )
            if cursor is not None
            else None
        )
        rows = await self._time_options.list_in_hangout(
            hangout_id=hangout_id,
            after=after,
            limit=limit + 1,
        )
        has_more = len(rows) > limit
        time_options = rows[:limit]
        items = [
            ManagedTimeOption(
                time_option=time_option,
                can_manage=self._can_manage(
                    current_user=current_user,
                    membership=membership,
                    hangout=hangout,
                    time_option=time_option,
                ),
            )
            for time_option in time_options
        ]
        next_cursor = None
        if has_more and time_options:
            last = time_options[-1]
            next_cursor = self._cursors.encode(
                TimeOptionPageCursor(starts_at=last.starts_at, time_option_id=last.id),
                kind="time_option_list",
                scope=scope,
            )
        return TimeOptionPage(items=items, next_cursor=next_cursor, has_more=has_more)

    async def update_time_option(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
        time_option_id: UUID,
        starts_at: datetime,
        ends_at: datetime | None,
        display_label: str | None,
    ) -> ManagedTimeOption:
        try:
            membership, hangout, time_option = await self._lock_write_context(
                current_user,
                group_id=group_id,
                hangout_id=hangout_id,
                time_option_id=time_option_id,
            )
            self._require_draft(hangout)
            self._require_manage_permission(
                current_user=current_user,
                membership=membership,
                hangout=hangout,
                time_option=time_option,
            )
            normalized_start, normalized_end = self._normalize_time_range(
                starts_at=starts_at,
                ends_at=ends_at,
            )
            updated = await self._time_options.update(
                time_option,
                starts_at=normalized_start,
                ends_at=normalized_end,
                display_label=self._normalize_display_label(display_label),
            )
            await self._time_options.commit()
        except IntegrityError as exc:
            await self._time_options.rollback()
            raise TimeOptionStateConflictError from exc
        except Exception:
            await self._time_options.rollback()
            raise
        return ManagedTimeOption(time_option=updated, can_manage=True)

    async def delete_time_option(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
        time_option_id: UUID,
    ) -> None:
        try:
            membership, hangout, time_option = await self._lock_write_context(
                current_user,
                group_id=group_id,
                hangout_id=hangout_id,
                time_option_id=time_option_id,
            )
            self._require_draft(hangout)
            self._require_manage_permission(
                current_user=current_user,
                membership=membership,
                hangout=hangout,
                time_option=time_option,
            )
            await self._time_options.delete(time_option)
            await self._time_options.commit()
        except IntegrityError as exc:
            await self._time_options.rollback()
            raise TimeOptionStateConflictError from exc
        except Exception:
            await self._time_options.rollback()
            raise

    async def _require_read_context(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
    ) -> tuple[GroupMember, Hangout]:
        membership = await self._time_options.get_active_membership(
            group_id=group_id,
            user_id=current_user.id,
        )
        if membership is None:
            raise GroupNotFoundError
        hangout = await self._time_options.get_hangout(
            group_id=group_id,
            hangout_id=hangout_id,
        )
        if hangout is None:
            raise HangoutNotFoundError
        return membership, hangout

    async def _lock_write_context(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
        time_option_id: UUID,
    ) -> tuple[GroupMember, Hangout, TimeOption]:
        membership = await self._time_options.get_active_membership_for_update(
            group_id=group_id,
            user_id=current_user.id,
        )
        if membership is None:
            raise GroupNotFoundError
        hangout = await self._time_options.get_hangout_for_update(
            group_id=group_id,
            hangout_id=hangout_id,
        )
        if hangout is None:
            raise HangoutNotFoundError
        time_option = await self._time_options.get_in_hangout_for_update(
            hangout_id=hangout_id,
            time_option_id=time_option_id,
        )
        if time_option is None:
            raise TimeOptionNotFoundError
        return membership, hangout, time_option

    @staticmethod
    def _can_manage(
        *,
        current_user: User,
        membership: GroupMember,
        hangout: Hangout,
        time_option: TimeOption,
    ) -> bool:
        return hangout.status == HangoutStatus.DRAFT and TimeOptionService._has_manage_permission(
            current_user=current_user,
            membership=membership,
            hangout=hangout,
            time_option=time_option,
        )

    @staticmethod
    def _has_manage_permission(
        *,
        current_user: User,
        membership: GroupMember,
        hangout: Hangout,
        time_option: TimeOption,
    ) -> bool:
        return (
            time_option.created_by_user_id == current_user.id
            or hangout.created_by_user_id == current_user.id
            or membership.role == GroupMemberRole.OWNER
        )

    @classmethod
    def _require_manage_permission(
        cls,
        *,
        current_user: User,
        membership: GroupMember,
        hangout: Hangout,
        time_option: TimeOption,
    ) -> None:
        if not cls._has_manage_permission(
            current_user=current_user,
            membership=membership,
            hangout=hangout,
            time_option=time_option,
        ):
            raise TimeOptionManageForbiddenError

    @staticmethod
    def _require_draft(hangout: Hangout) -> None:
        if hangout.status != HangoutStatus.DRAFT:
            raise TimeOptionStateConflictError

    def _normalize_time_range(
        self,
        *,
        starts_at: datetime,
        ends_at: datetime | None,
    ) -> tuple[datetime, datetime | None]:
        if starts_at.tzinfo is None or starts_at.utcoffset() is None:
            raise InvalidTimeOptionError
        normalized_start = starts_at.astimezone(UTC)
        if normalized_start <= self._clock().astimezone(UTC):
            raise InvalidTimeOptionError
        normalized_end = None
        if ends_at is not None:
            if ends_at.tzinfo is None or ends_at.utcoffset() is None:
                raise InvalidTimeOptionError
            normalized_end = ends_at.astimezone(UTC)
            if normalized_end <= normalized_start:
                raise InvalidTimeOptionError
        return normalized_start, normalized_end

    @staticmethod
    def _normalize_display_label(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _cursor_scope(*, group_id: UUID, hangout_id: UUID) -> str:
        return f"group:{group_id}:hangout:{hangout_id}"
