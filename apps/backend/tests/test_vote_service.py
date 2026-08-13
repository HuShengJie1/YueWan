from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    DuplicateTimeVoteSelectionError,
    GroupNotFoundError,
    HangoutNotFoundError,
    ProposalNotFoundError,
    TimeOptionNotFoundError,
    VoteStateConflictError,
)
from app.models.enums import (
    GroupMemberRole,
    GroupMemberStatus,
    HangoutStatus,
    ProposalVoteValue,
)
from app.models.group import GroupMember
from app.models.hangout import Hangout
from app.models.proposal import Proposal
from app.models.time_option import TimeOption
from app.models.user import User
from app.repositories.vote import ProposalVoteSummary, TimeVoteSummary
from app.services.vote import VoteService

NOW = datetime(2026, 8, 12, 3, 0, tzinfo=UTC)


def make_user() -> User:
    return User(
        id=uuid4(),
        wechat_openid=f"openid-{uuid4()}",
        wechat_unionid=None,
        display_name="Member",
        avatar_url=None,
        is_active=True,
        profile_completed=True,
        last_login_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def make_hangout(
    *,
    group_id: UUID,
    creator_id: UUID,
    status: HangoutStatus = HangoutStatus.VOTING,
    deadline: datetime | None = None,
) -> Hangout:
    return Hangout(
        id=uuid4(),
        group_id=group_id,
        created_by_user_id=creator_id,
        title="Vote",
        description=None,
        status=status,
        voting_deadline=deadline,
        confirmed_at=None,
        cancelled_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def make_proposal(*, hangout_id: UUID, user_id: UUID) -> Proposal:
    return Proposal(
        id=uuid4(),
        hangout_id=hangout_id,
        submitted_by_user_id=user_id,
        title="Board games",
        description=None,
        location_text=None,
        external_platform=None,
        external_url=None,
        external_data=None,
        created_at=NOW,
        updated_at=NOW,
    )


def make_time_option(*, hangout_id: UUID, user_id: UUID) -> TimeOption:
    return TimeOption(
        id=uuid4(),
        hangout_id=hangout_id,
        created_by_user_id=user_id,
        starts_at=NOW + timedelta(days=1),
        ends_at=None,
        display_label="Tomorrow",
        created_at=NOW,
        updated_at=NOW,
    )


class FakeVoteRepository:
    def __init__(self, *, user: User, group_id: UUID) -> None:
        self.membership: GroupMember | None = GroupMember(
            id=uuid4(),
            group_id=group_id,
            user_id=user.id,
            role=GroupMemberRole.MEMBER,
            status=GroupMemberStatus.ACTIVE,
            left_at=None,
            created_at=NOW,
            updated_at=NOW,
        )
        self.hangout: Hangout | None = make_hangout(group_id=group_id, creator_id=user.id)
        self.proposal = make_proposal(hangout_id=self.hangout.id, user_id=user.id)
        self.time_options = [
            make_time_option(hangout_id=self.hangout.id, user_id=user.id),
            make_time_option(hangout_id=self.hangout.id, user_id=user.id),
        ]
        self.proposal_votes: dict[tuple[UUID, UUID], ProposalVoteValue] = {}
        self.time_votes: dict[UUID, set[UUID]] = {}
        self.upsert_calls = 0
        self.replace_calls = 0
        self.commit_failure: Exception | None = None
        self.committed = False
        self.rolled_back = False

    async def get_active_membership(self, **_arguments: object) -> GroupMember | None:
        return self.membership

    async def get_active_membership_for_update(self, **_arguments: object) -> GroupMember | None:
        return self.membership

    async def get_hangout(self, **_arguments: object) -> Hangout | None:
        return self.hangout

    async def get_hangout_for_share(self, **_arguments: object) -> Hangout | None:
        return self.hangout

    async def get_proposal(self, **arguments: object) -> Proposal | None:
        if arguments["proposal_id"] != self.proposal.id:
            return None
        return self.proposal

    async def get_time_option_ids(self, **arguments: object) -> set[UUID]:
        valid_ids = {item.id for item in self.time_options}
        return set(arguments["time_option_ids"]) & valid_ids  # type: ignore[arg-type]

    async def upsert_proposal_vote(self, **arguments: object) -> None:
        self.upsert_calls += 1
        key = (arguments["proposal_id"], arguments["user_id"])
        self.proposal_votes[key] = arguments["value"]  # type: ignore[index,assignment]

    async def delete_proposal_vote(self, **arguments: object) -> None:
        key = (arguments["proposal_id"], arguments["user_id"])
        self.proposal_votes.pop(key, None)

    async def replace_time_votes(self, **arguments: object) -> None:
        self.replace_calls += 1
        self.time_votes[arguments["user_id"]] = set(arguments["time_option_ids"])  # type: ignore[index,arg-type]

    async def list_proposal_summaries(self, **arguments: object) -> list[ProposalVoteSummary]:
        current_user_id = arguments["current_user_id"]
        values = [
            value
            for (proposal_id, _user_id), value in self.proposal_votes.items()
            if proposal_id == self.proposal.id
        ]
        return [
            ProposalVoteSummary(
                proposal=self.proposal,
                like_count=values.count(ProposalVoteValue.LIKE),
                ok_count=values.count(ProposalVoteValue.OK),
                dislike_count=values.count(ProposalVoteValue.DISLIKE),
                current_user_vote=self.proposal_votes.get(
                    (self.proposal.id, current_user_id)  # type: ignore[arg-type]
                ),
            )
        ]

    async def get_proposal_summary(self, **arguments: object) -> ProposalVoteSummary | None:
        if arguments["proposal_id"] != self.proposal.id:
            return None
        return (await self.list_proposal_summaries(**arguments))[0]

    async def list_time_summaries(self, **arguments: object) -> list[TimeVoteSummary]:
        current_user_id = arguments["current_user_id"]
        return [
            TimeVoteSummary(
                time_option=time_option,
                availability_count=sum(
                    time_option.id in selected for selected in self.time_votes.values()
                ),
                current_user_selected=time_option.id in self.time_votes.get(current_user_id, set()),  # type: ignore[arg-type]
            )
            for time_option in self.time_options
        ]

    async def commit(self) -> None:
        if self.commit_failure is not None:
            raise self.commit_failure
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def make_service(repository: FakeVoteRepository) -> VoteService:
    return VoteService(repository=repository, clock=lambda: NOW)  # type: ignore[arg-type]


async def test_active_member_reads_batch_summary_with_counts_and_current_choices() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeVoteRepository(user=user, group_id=group_id)
    other_user_id = uuid4()
    repository.proposal_votes[(repository.proposal.id, user.id)] = ProposalVoteValue.LIKE
    repository.proposal_votes[(repository.proposal.id, other_user_id)] = ProposalVoteValue.OK
    repository.time_votes[user.id] = {repository.time_options[0].id}
    repository.time_votes[other_user_id] = {
        repository.time_options[0].id,
        repository.time_options[1].id,
    }

    summary = await make_service(repository).read_summary(
        user,
        group_id=group_id,
        hangout_id=repository.hangout.id,  # type: ignore[union-attr]
    )

    assert summary.proposals[0].like_count == 1
    assert summary.proposals[0].ok_count == 1
    assert summary.proposals[0].current_user_vote == ProposalVoteValue.LIKE
    assert [item.availability_count for item in summary.time_options] == [2, 1]
    assert [item.current_user_selected for item in summary.time_options] == [True, False]


async def test_non_active_member_and_wrong_hangout_are_hidden() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeVoteRepository(user=user, group_id=group_id)
    repository.membership = None

    with pytest.raises(GroupNotFoundError):
        await make_service(repository).read_summary(
            user,
            group_id=group_id,
            hangout_id=uuid4(),
        )
    with pytest.raises(GroupNotFoundError):
        await make_service(repository).set_proposal_vote(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,  # type: ignore[union-attr]
            proposal_id=repository.proposal.id,
            value=ProposalVoteValue.LIKE,
        )

    repository.membership = GroupMember(
        id=uuid4(),
        group_id=group_id,
        user_id=user.id,
        role=GroupMemberRole.MEMBER,
        status=GroupMemberStatus.ACTIVE,
        left_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    repository.hangout = None
    with pytest.raises(HangoutNotFoundError):
        await make_service(repository).read_summary(
            user,
            group_id=group_id,
            hangout_id=uuid4(),
        )


async def test_proposal_vote_creates_overwrites_repeats_and_deletes_without_duplicates() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeVoteRepository(user=user, group_id=group_id)
    service = make_service(repository)
    arguments = {
        "group_id": group_id,
        "hangout_id": repository.hangout.id,  # type: ignore[union-attr]
        "proposal_id": repository.proposal.id,
    }

    created = await service.set_proposal_vote(
        user,
        **arguments,  # type: ignore[arg-type]
        value=ProposalVoteValue.LIKE,
    )
    overwritten = await service.set_proposal_vote(
        user,
        **arguments,  # type: ignore[arg-type]
        value=ProposalVoteValue.DISLIKE,
    )
    repeated = await service.set_proposal_vote(
        user,
        **arguments,  # type: ignore[arg-type]
        value=ProposalVoteValue.DISLIKE,
    )
    deleted = await service.delete_proposal_vote(user, **arguments)  # type: ignore[arg-type]
    deleted_again = await service.delete_proposal_vote(user, **arguments)  # type: ignore[arg-type]

    assert created.current_user_vote == ProposalVoteValue.LIKE
    assert overwritten.current_user_vote == ProposalVoteValue.DISLIKE
    assert repeated.dislike_count == 1
    assert len(repository.proposal_votes) == 0
    assert deleted.current_user_vote is None
    assert deleted_again.current_user_vote is None
    assert repository.upsert_calls == 3


async def test_cross_hangout_proposal_is_hidden_and_rolls_back() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeVoteRepository(user=user, group_id=group_id)

    with pytest.raises(ProposalNotFoundError):
        await make_service(repository).set_proposal_vote(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,  # type: ignore[union-attr]
            proposal_id=uuid4(),
            value=ProposalVoteValue.OK,
        )

    assert repository.upsert_calls == 0
    assert repository.rolled_back


@pytest.mark.parametrize(
    ("status", "deadline"),
    [
        (HangoutStatus.DRAFT, None),
        (HangoutStatus.VOTING, NOW),
        (HangoutStatus.VOTING, NOW - timedelta(seconds=1)),
    ],
)
async def test_vote_writes_reject_non_voting_or_elapsed_deadline(
    status: HangoutStatus,
    deadline: datetime | None,
) -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeVoteRepository(user=user, group_id=group_id)
    repository.hangout.status = status  # type: ignore[union-attr]
    repository.hangout.voting_deadline = deadline  # type: ignore[union-attr]

    with pytest.raises(VoteStateConflictError):
        await make_service(repository).set_proposal_vote(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,  # type: ignore[union-attr]
            proposal_id=repository.proposal.id,
            value=ProposalVoteValue.LIKE,
        )

    assert repository.upsert_calls == 0
    assert repository.rolled_back


async def test_time_votes_replace_clear_and_repeat_atomically() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeVoteRepository(user=user, group_id=group_id)
    service = make_service(repository)
    ids = [item.id for item in repository.time_options]
    arguments = {
        "group_id": group_id,
        "hangout_id": repository.hangout.id,  # type: ignore[union-attr]
    }

    selected = await service.replace_time_votes(user, **arguments, time_option_ids=ids)  # type: ignore[arg-type]
    repeated = await service.replace_time_votes(user, **arguments, time_option_ids=ids)  # type: ignore[arg-type]
    cleared = await service.replace_time_votes(user, **arguments, time_option_ids=[])  # type: ignore[arg-type]

    assert all(item.current_user_selected for item in selected)
    assert all(item.current_user_selected for item in repeated)
    assert not any(item.current_user_selected for item in cleared)
    assert repository.time_votes[user.id] == set()
    assert repository.replace_calls == 3


async def test_time_vote_duplicates_and_cross_hangout_ids_preserve_old_selection() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeVoteRepository(user=user, group_id=group_id)
    existing_id = repository.time_options[0].id
    repository.time_votes[user.id] = {existing_id}
    service = make_service(repository)
    arguments = {
        "group_id": group_id,
        "hangout_id": repository.hangout.id,  # type: ignore[union-attr]
    }

    with pytest.raises(DuplicateTimeVoteSelectionError):
        await service.replace_time_votes(
            user,
            **arguments,  # type: ignore[arg-type]
            time_option_ids=[existing_id, existing_id],
        )
    with pytest.raises(TimeOptionNotFoundError):
        await service.replace_time_votes(
            user,
            **arguments,  # type: ignore[arg-type]
            time_option_ids=[existing_id, uuid4()],
        )

    assert repository.time_votes[user.id] == {existing_id}
    assert repository.replace_calls == 0
    assert repository.rolled_back


async def test_integrity_error_is_mapped_to_safe_vote_conflict() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeVoteRepository(user=user, group_id=group_id)

    async def fail_upsert(**_arguments: object) -> None:
        raise IntegrityError("unsafe sql", {}, RuntimeError("unique constraint details"))

    repository.upsert_proposal_vote = fail_upsert  # type: ignore[method-assign]

    with pytest.raises(VoteStateConflictError) as error:
        await make_service(repository).set_proposal_vote(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,  # type: ignore[union-attr]
            proposal_id=repository.proposal.id,
            value=ProposalVoteValue.LIKE,
        )

    assert error.value.message == "Hangout is not open for voting"
    assert "sql" not in error.value.message.lower()
    assert repository.rolled_back
