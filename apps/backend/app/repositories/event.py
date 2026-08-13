from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import GroupMemberStatus, HangoutStatus
from app.models.event import Event
from app.models.group import GroupMember
from app.models.hangout import Hangout
from app.models.proposal import Proposal
from app.models.time_option import TimeOption


class EventRepository:
    """Persist confirmed events and execute group/hangout-scoped queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_membership(
        self,
        *,
        group_id: UUID,
        user_id: UUID,
    ) -> GroupMember | None:
        statement = select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id,
            GroupMember.status == GroupMemberStatus.ACTIVE,
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def get_active_membership_for_update(
        self,
        *,
        group_id: UUID,
        user_id: UUID,
    ) -> GroupMember | None:
        statement = (
            select(GroupMember)
            .where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
                GroupMember.status == GroupMemberStatus.ACTIVE,
            )
            .with_for_update()
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def get_hangout(
        self,
        *,
        group_id: UUID,
        hangout_id: UUID,
    ) -> Hangout | None:
        statement = select(Hangout).where(
            Hangout.id == hangout_id,
            Hangout.group_id == group_id,
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def get_hangout_for_update(
        self,
        *,
        group_id: UUID,
        hangout_id: UUID,
    ) -> Hangout | None:
        statement = (
            select(Hangout)
            .where(
                Hangout.id == hangout_id,
                Hangout.group_id == group_id,
            )
            .with_for_update()
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def get_by_hangout(self, *, hangout_id: UUID) -> Event | None:
        statement = select(Event).where(Event.hangout_id == hangout_id)
        return (await self._session.scalars(statement)).one_or_none()

    async def get_proposal(
        self,
        *,
        hangout_id: UUID,
        proposal_id: UUID,
    ) -> Proposal | None:
        statement = select(Proposal).where(
            Proposal.id == proposal_id,
            Proposal.hangout_id == hangout_id,
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def get_time_option(
        self,
        *,
        hangout_id: UUID,
        time_option_id: UUID,
    ) -> TimeOption | None:
        statement = select(TimeOption).where(
            TimeOption.id == time_option_id,
            TimeOption.hangout_id == hangout_id,
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def confirm(
        self,
        hangout: Hangout,
        *,
        proposal: Proposal,
        time_option: TimeOption,
        confirmed_by_user_id: UUID,
        confirmed_at: datetime,
    ) -> Event:
        event = Event(
            hangout_id=hangout.id,
            proposal_id=proposal.id,
            time_option_id=time_option.id,
            confirmed_by_user_id=confirmed_by_user_id,
            title=proposal.title,
            description=proposal.description,
            location_text=proposal.location_text,
            starts_at=time_option.starts_at,
            ends_at=time_option.ends_at,
        )
        self._session.add(event)
        hangout.status = HangoutStatus.CONFIRMED
        hangout.confirmed_at = confirmed_at
        await self._session.flush()
        await self._session.refresh(event)
        return event

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
