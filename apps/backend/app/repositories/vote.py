from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import GroupMemberStatus, ProposalVoteValue
from app.models.group import GroupMember
from app.models.hangout import Hangout
from app.models.proposal import Proposal, ProposalVote
from app.models.time_option import TimeOption, TimeVote


@dataclass(frozen=True, slots=True)
class ProposalVoteSummary:
    proposal: Proposal
    like_count: int
    ok_count: int
    dislike_count: int
    current_user_vote: ProposalVoteValue | None


@dataclass(frozen=True, slots=True)
class TimeVoteSummary:
    time_option: TimeOption
    availability_count: int
    current_user_selected: bool


class VoteRepository:
    """Persist votes and load group/hangout-scoped vote aggregates."""

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

    async def get_hangout_for_share(
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
            .with_for_update(read=True)
        )
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

    async def get_time_option_ids(
        self,
        *,
        hangout_id: UUID,
        time_option_ids: set[UUID],
    ) -> set[UUID]:
        if not time_option_ids:
            return set()
        statement = select(TimeOption.id).where(
            TimeOption.hangout_id == hangout_id,
            TimeOption.id.in_(time_option_ids),
        )
        return set((await self._session.scalars(statement)).all())

    async def upsert_proposal_vote(
        self,
        *,
        proposal_id: UUID,
        user_id: UUID,
        value: ProposalVoteValue,
    ) -> None:
        statement = (
            insert(ProposalVote)
            .values(
                id=uuid4(),
                proposal_id=proposal_id,
                user_id=user_id,
                value=value,
            )
            .on_conflict_do_update(
                index_elements=[ProposalVote.proposal_id, ProposalVote.user_id],
                set_={
                    "value": value,
                    "updated_at": func.now(),
                },
            )
        )
        await self._session.execute(statement)
        await self._session.flush()

    async def delete_proposal_vote(
        self,
        *,
        proposal_id: UUID,
        user_id: UUID,
    ) -> None:
        statement = delete(ProposalVote).where(
            ProposalVote.proposal_id == proposal_id,
            ProposalVote.user_id == user_id,
        )
        await self._session.execute(statement)
        await self._session.flush()

    async def replace_time_votes(
        self,
        *,
        hangout_id: UUID,
        user_id: UUID,
        time_option_ids: set[UUID],
    ) -> None:
        hangout_time_options = select(TimeOption.id).where(TimeOption.hangout_id == hangout_id)
        await self._session.execute(
            delete(TimeVote).where(
                TimeVote.user_id == user_id,
                TimeVote.time_option_id.in_(hangout_time_options),
            )
        )
        self._session.add_all(
            TimeVote(time_option_id=time_option_id, user_id=user_id)
            for time_option_id in sorted(time_option_ids)
        )
        await self._session.flush()

    async def list_proposal_summaries(
        self,
        *,
        hangout_id: UUID,
        current_user_id: UUID,
        proposal_id: UUID | None = None,
    ) -> list[ProposalVoteSummary]:
        hangout_proposal_ids = select(Proposal.id).where(Proposal.hangout_id == hangout_id)
        counts = (
            select(
                ProposalVote.proposal_id.label("proposal_id"),
                func.count(ProposalVote.id)
                .filter(ProposalVote.value == ProposalVoteValue.LIKE)
                .label("like_count"),
                func.count(ProposalVote.id)
                .filter(ProposalVote.value == ProposalVoteValue.OK)
                .label("ok_count"),
                func.count(ProposalVote.id)
                .filter(ProposalVote.value == ProposalVoteValue.DISLIKE)
                .label("dislike_count"),
            )
            .where(ProposalVote.proposal_id.in_(hangout_proposal_ids))
            .group_by(ProposalVote.proposal_id)
            .subquery()
        )
        current_votes = (
            select(
                ProposalVote.proposal_id.label("proposal_id"),
                ProposalVote.value.label("current_user_vote"),
            )
            .where(
                ProposalVote.user_id == current_user_id,
                ProposalVote.proposal_id.in_(hangout_proposal_ids),
            )
            .subquery()
        )
        statement = (
            select(
                Proposal,
                func.coalesce(counts.c.like_count, 0).label("like_count"),
                func.coalesce(counts.c.ok_count, 0).label("ok_count"),
                func.coalesce(counts.c.dislike_count, 0).label("dislike_count"),
                current_votes.c.current_user_vote,
            )
            .outerjoin(counts, counts.c.proposal_id == Proposal.id)
            .outerjoin(current_votes, current_votes.c.proposal_id == Proposal.id)
            .where(Proposal.hangout_id == hangout_id)
            .order_by(Proposal.created_at.desc(), Proposal.id.desc())
        )
        if proposal_id is not None:
            statement = statement.where(Proposal.id == proposal_id)
        rows = (await self._session.execute(statement)).all()
        return [
            ProposalVoteSummary(
                proposal=row.Proposal,
                like_count=int(row.like_count),
                ok_count=int(row.ok_count),
                dislike_count=int(row.dislike_count),
                current_user_vote=row.current_user_vote,
            )
            for row in rows
        ]

    async def get_proposal_summary(
        self,
        *,
        hangout_id: UUID,
        proposal_id: UUID,
        current_user_id: UUID,
    ) -> ProposalVoteSummary | None:
        summaries = await self.list_proposal_summaries(
            hangout_id=hangout_id,
            current_user_id=current_user_id,
            proposal_id=proposal_id,
        )
        return summaries[0] if summaries else None

    async def list_time_summaries(
        self,
        *,
        hangout_id: UUID,
        current_user_id: UUID,
    ) -> list[TimeVoteSummary]:
        hangout_time_option_ids = select(TimeOption.id).where(TimeOption.hangout_id == hangout_id)
        counts = (
            select(
                TimeVote.time_option_id.label("time_option_id"),
                func.count(TimeVote.id).label("availability_count"),
            )
            .where(TimeVote.time_option_id.in_(hangout_time_option_ids))
            .group_by(TimeVote.time_option_id)
            .subquery()
        )
        current_votes = (
            select(TimeVote.time_option_id.label("time_option_id"))
            .where(
                TimeVote.user_id == current_user_id,
                TimeVote.time_option_id.in_(hangout_time_option_ids),
            )
            .subquery()
        )
        statement = (
            select(
                TimeOption,
                func.coalesce(counts.c.availability_count, 0).label("availability_count"),
                current_votes.c.time_option_id.is_not(None).label("current_user_selected"),
            )
            .outerjoin(counts, counts.c.time_option_id == TimeOption.id)
            .outerjoin(current_votes, current_votes.c.time_option_id == TimeOption.id)
            .where(TimeOption.hangout_id == hangout_id)
            .order_by(TimeOption.starts_at.asc(), TimeOption.id.asc())
        )
        rows = (await self._session.execute(statement)).all()
        return [
            TimeVoteSummary(
                time_option=row.TimeOption,
                availability_count=int(row.availability_count),
                current_user_selected=bool(row.current_user_selected),
            )
            for row in rows
        ]

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
