from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    DuplicateTimeVoteSelectionError,
    GroupNotFoundError,
    HangoutNotFoundError,
    ProposalNotFoundError,
    TimeOptionNotFoundError,
    VoteStateConflictError,
)
from app.models.enums import HangoutStatus, ProposalVoteValue
from app.models.hangout import Hangout
from app.models.user import User
from app.repositories.vote import ProposalVoteSummary, TimeVoteSummary, VoteRepository


@dataclass(frozen=True, slots=True)
class VotingSummary:
    hangout: Hangout
    proposals: list[ProposalVoteSummary]
    time_options: list[TimeVoteSummary]


class VoteService:
    """Apply vote visibility/state rules and own vote write transactions."""

    def __init__(
        self,
        *,
        repository: VoteRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._votes = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    async def read_summary(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
    ) -> VotingSummary:
        membership = await self._votes.get_active_membership(
            group_id=group_id,
            user_id=current_user.id,
        )
        if membership is None:
            raise GroupNotFoundError
        hangout = await self._votes.get_hangout(
            group_id=group_id,
            hangout_id=hangout_id,
        )
        if hangout is None:
            raise HangoutNotFoundError
        proposals = await self._votes.list_proposal_summaries(
            hangout_id=hangout_id,
            current_user_id=current_user.id,
        )
        time_options = await self._votes.list_time_summaries(
            hangout_id=hangout_id,
            current_user_id=current_user.id,
        )
        return VotingSummary(
            hangout=hangout,
            proposals=proposals,
            time_options=time_options,
        )

    async def set_proposal_vote(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
        proposal_id: UUID,
        value: ProposalVoteValue,
    ) -> ProposalVoteSummary:
        try:
            await self._lock_open_voting_context(
                current_user,
                group_id=group_id,
                hangout_id=hangout_id,
            )
            proposal = await self._votes.get_proposal(
                hangout_id=hangout_id,
                proposal_id=proposal_id,
            )
            if proposal is None:
                raise ProposalNotFoundError
            await self._votes.upsert_proposal_vote(
                proposal_id=proposal_id,
                user_id=current_user.id,
                value=value,
            )
            summary = await self._votes.get_proposal_summary(
                hangout_id=hangout_id,
                proposal_id=proposal_id,
                current_user_id=current_user.id,
            )
            if summary is None:
                raise ProposalNotFoundError
            await self._votes.commit()
        except IntegrityError as exc:
            await self._votes.rollback()
            raise VoteStateConflictError from exc
        except Exception:
            await self._votes.rollback()
            raise
        return summary

    async def delete_proposal_vote(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
        proposal_id: UUID,
    ) -> ProposalVoteSummary:
        try:
            await self._lock_open_voting_context(
                current_user,
                group_id=group_id,
                hangout_id=hangout_id,
            )
            proposal = await self._votes.get_proposal(
                hangout_id=hangout_id,
                proposal_id=proposal_id,
            )
            if proposal is None:
                raise ProposalNotFoundError
            await self._votes.delete_proposal_vote(
                proposal_id=proposal_id,
                user_id=current_user.id,
            )
            summary = await self._votes.get_proposal_summary(
                hangout_id=hangout_id,
                proposal_id=proposal_id,
                current_user_id=current_user.id,
            )
            if summary is None:
                raise ProposalNotFoundError
            await self._votes.commit()
        except IntegrityError as exc:
            await self._votes.rollback()
            raise VoteStateConflictError from exc
        except Exception:
            await self._votes.rollback()
            raise
        return summary

    async def replace_time_votes(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
        time_option_ids: list[UUID],
    ) -> list[TimeVoteSummary]:
        try:
            selected_ids = set(time_option_ids)
            if len(selected_ids) != len(time_option_ids):
                raise DuplicateTimeVoteSelectionError
            await self._lock_open_voting_context(
                current_user,
                group_id=group_id,
                hangout_id=hangout_id,
            )
            scoped_ids = await self._votes.get_time_option_ids(
                hangout_id=hangout_id,
                time_option_ids=selected_ids,
            )
            if scoped_ids != selected_ids:
                raise TimeOptionNotFoundError
            await self._votes.replace_time_votes(
                hangout_id=hangout_id,
                user_id=current_user.id,
                time_option_ids=selected_ids,
            )
            summaries = await self._votes.list_time_summaries(
                hangout_id=hangout_id,
                current_user_id=current_user.id,
            )
            await self._votes.commit()
        except IntegrityError as exc:
            await self._votes.rollback()
            raise VoteStateConflictError from exc
        except Exception:
            await self._votes.rollback()
            raise
        return summaries

    async def _lock_open_voting_context(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
    ) -> Hangout:
        membership = await self._votes.get_active_membership_for_update(
            group_id=group_id,
            user_id=current_user.id,
        )
        if membership is None:
            raise GroupNotFoundError
        hangout = await self._votes.get_hangout_for_share(
            group_id=group_id,
            hangout_id=hangout_id,
        )
        if hangout is None:
            raise HangoutNotFoundError
        if hangout.status != HangoutStatus.VOTING:
            raise VoteStateConflictError
        if hangout.voting_deadline is not None and (
            hangout.voting_deadline.astimezone(UTC) <= self._clock().astimezone(UTC)
        ):
            raise VoteStateConflictError
        return hangout
