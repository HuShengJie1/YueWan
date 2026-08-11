from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.group_security import HangoutPageCursor
from app.models.enums import GroupMemberStatus, HangoutStatus
from app.models.group import GroupMember
from app.models.hangout import Hangout


class HangoutRepository:
    """Persist hangouts and execute group-scoped hangout queries."""

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

    async def create(
        self,
        *,
        group_id: UUID,
        created_by_user_id: UUID,
        title: str,
        description: str | None,
        voting_deadline: datetime | None,
    ) -> Hangout:
        hangout = Hangout(
            group_id=group_id,
            created_by_user_id=created_by_user_id,
            title=title,
            description=description,
            status=HangoutStatus.DRAFT,
            voting_deadline=voting_deadline,
            confirmed_at=None,
            cancelled_at=None,
        )
        self._session.add(hangout)
        await self._session.flush()
        return hangout

    async def list_in_group(
        self,
        *,
        group_id: UUID,
        after: HangoutPageCursor | None,
        limit: int,
    ) -> list[Hangout]:
        statement = (
            select(Hangout)
            .where(Hangout.group_id == group_id)
            .order_by(Hangout.created_at.desc(), Hangout.id.desc())
            .limit(limit)
        )
        if after is not None:
            statement = statement.where(
                or_(
                    Hangout.created_at < after.created_at,
                    and_(
                        Hangout.created_at == after.created_at,
                        Hangout.id < after.hangout_id,
                    ),
                )
            )
        return list((await self._session.scalars(statement)).all())

    async def get_in_group(
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

    async def get_in_group_for_update(
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

    async def update(
        self,
        hangout: Hangout,
        *,
        title: str,
        description: str | None,
        voting_deadline: datetime | None,
    ) -> Hangout:
        hangout.title = title
        hangout.description = description
        hangout.voting_deadline = voting_deadline
        await self._session.flush()
        await self._session.refresh(hangout)
        return hangout

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
