from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.group_security import ProposalPageCursor
from app.models.enums import GroupMemberStatus
from app.models.group import GroupMember
from app.models.hangout import Hangout
from app.models.proposal import Proposal


class ProposalRepository:
    """Persist proposals and execute group/hangout-scoped queries."""

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
        submitted_by_user_id: UUID,
        title: str,
        description: str | None,
        location_text: str | None,
        external_platform: str | None,
        external_url: str | None,
        external_data: dict[str, Any] | None,
    ) -> Proposal:
        proposal = Proposal(
            hangout_id=hangout_id,
            submitted_by_user_id=submitted_by_user_id,
            title=title,
            description=description,
            location_text=location_text,
            external_platform=external_platform,
            external_url=external_url,
            external_data=external_data,
        )
        self._session.add(proposal)
        await self._session.flush()
        return proposal

    async def list_in_hangout(
        self,
        *,
        hangout_id: UUID,
        after: ProposalPageCursor | None,
        limit: int,
    ) -> list[Proposal]:
        statement = (
            select(Proposal)
            .where(Proposal.hangout_id == hangout_id)
            .order_by(Proposal.created_at.desc(), Proposal.id.desc())
            .limit(limit)
        )
        if after is not None:
            statement = statement.where(
                or_(
                    Proposal.created_at < after.created_at,
                    and_(
                        Proposal.created_at == after.created_at,
                        Proposal.id < after.proposal_id,
                    ),
                )
            )
        return list((await self._session.scalars(statement)).all())

    async def get_in_hangout_for_update(
        self,
        *,
        hangout_id: UUID,
        proposal_id: UUID,
    ) -> Proposal | None:
        statement = (
            select(Proposal)
            .where(
                Proposal.id == proposal_id,
                Proposal.hangout_id == hangout_id,
            )
            .with_for_update()
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def update(
        self,
        proposal: Proposal,
        *,
        title: str,
        description: str | None,
        location_text: str | None,
        external_platform: str | None,
        external_url: str | None,
        external_data: dict[str, Any] | None,
    ) -> Proposal:
        proposal.title = title
        proposal.description = description
        proposal.location_text = location_text
        proposal.external_platform = external_platform
        proposal.external_url = external_url
        proposal.external_data = external_data
        await self._session.flush()
        await self._session.refresh(proposal)
        return proposal

    async def delete(self, proposal: Proposal) -> None:
        await self._session.delete(proposal)
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
