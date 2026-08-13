from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    EventConfirmForbiddenError,
    EventNotFoundError,
    EventSelectionConflictError,
    EventStateConflictError,
    GroupNotFoundError,
    HangoutNotFoundError,
    ProposalNotFoundError,
    TimeOptionNotFoundError,
)
from app.models.enums import GroupMemberRole, HangoutStatus
from app.models.event import Event
from app.models.user import User
from app.repositories.event import EventRepository


class EventService:
    """Apply event visibility/confirmation rules and own confirmation transactions."""

    def __init__(
        self,
        *,
        repository: EventRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._events = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    async def read_event(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
    ) -> Event:
        membership = await self._events.get_active_membership(
            group_id=group_id,
            user_id=current_user.id,
        )
        if membership is None:
            raise GroupNotFoundError
        hangout = await self._events.get_hangout(
            group_id=group_id,
            hangout_id=hangout_id,
        )
        if hangout is None:
            raise HangoutNotFoundError
        event = await self._events.get_by_hangout(hangout_id=hangout.id)
        if event is None:
            raise EventNotFoundError
        return event

    async def confirm_event(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
        proposal_id: UUID,
        time_option_id: UUID,
    ) -> Event:
        try:
            membership = await self._events.get_active_membership_for_update(
                group_id=group_id,
                user_id=current_user.id,
            )
            if membership is None:
                raise GroupNotFoundError
            hangout = await self._events.get_hangout_for_update(
                group_id=group_id,
                hangout_id=hangout_id,
            )
            if hangout is None:
                raise HangoutNotFoundError
            if (
                hangout.created_by_user_id != current_user.id
                and membership.role != GroupMemberRole.OWNER
            ):
                raise EventConfirmForbiddenError

            existing = await self._events.get_by_hangout(hangout_id=hangout.id)
            if existing is not None:
                if hangout.status != HangoutStatus.CONFIRMED:
                    raise EventStateConflictError
                if existing.proposal_id != proposal_id or existing.time_option_id != time_option_id:
                    raise EventSelectionConflictError
                await self._events.commit()
                return existing

            if hangout.status != HangoutStatus.VOTING:
                raise EventStateConflictError
            proposal = await self._events.get_proposal(
                hangout_id=hangout.id,
                proposal_id=proposal_id,
            )
            if proposal is None:
                raise ProposalNotFoundError
            time_option = await self._events.get_time_option(
                hangout_id=hangout.id,
                time_option_id=time_option_id,
            )
            if time_option is None:
                raise TimeOptionNotFoundError

            event = await self._events.confirm(
                hangout,
                proposal=proposal,
                time_option=time_option,
                confirmed_by_user_id=current_user.id,
                confirmed_at=self._clock().astimezone(UTC),
            )
            await self._events.commit()
        except IntegrityError as exc:
            await self._events.rollback()
            raise EventStateConflictError from exc
        except Exception:
            await self._events.rollback()
            raise
        return event
