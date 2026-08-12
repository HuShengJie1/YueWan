from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.group_security import TimeOptionPageCursor
from app.models.enums import GroupMemberStatus
from app.models.group import GroupMember
from app.models.hangout import Hangout
from app.models.time_option import TimeOption


class TimeOptionRepository:
    """Persist time options and execute group/hangout-scoped queries."""

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

    async def create(
        self,
        *,
        hangout_id: UUID,
        created_by_user_id: UUID,
        starts_at: datetime,
        ends_at: datetime | None,
        display_label: str | None,
    ) -> TimeOption:
        time_option = TimeOption(
            hangout_id=hangout_id,
            created_by_user_id=created_by_user_id,
            starts_at=starts_at,
            ends_at=ends_at,
            display_label=display_label,
        )
        self._session.add(time_option)
        await self._session.flush()
        return time_option

    async def list_in_hangout(
        self,
        *,
        hangout_id: UUID,
        after: TimeOptionPageCursor | None,
        limit: int,
    ) -> list[TimeOption]:
        statement = (
            select(TimeOption)
            .where(TimeOption.hangout_id == hangout_id)
            .order_by(TimeOption.starts_at.asc(), TimeOption.id.asc())
            .limit(limit)
        )
        if after is not None:
            statement = statement.where(
                or_(
                    TimeOption.starts_at > after.starts_at,
                    and_(
                        TimeOption.starts_at == after.starts_at,
                        TimeOption.id > after.time_option_id,
                    ),
                )
            )
        return list((await self._session.scalars(statement)).all())

    async def get_in_hangout_for_update(
        self,
        *,
        hangout_id: UUID,
        time_option_id: UUID,
    ) -> TimeOption | None:
        statement = (
            select(TimeOption)
            .where(
                TimeOption.id == time_option_id,
                TimeOption.hangout_id == hangout_id,
            )
            .with_for_update()
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def update(
        self,
        time_option: TimeOption,
        *,
        starts_at: datetime,
        ends_at: datetime | None,
        display_label: str | None,
    ) -> TimeOption:
        time_option.starts_at = starts_at
        time_option.ends_at = ends_at
        time_option.display_label = display_label
        await self._session.flush()
        await self._session.refresh(time_option)
        return time_option

    async def delete(self, time_option: TimeOption) -> None:
        await self._session.delete(time_option)
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
