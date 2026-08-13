from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
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
from app.models.enums import GroupMemberRole, GroupMemberStatus, HangoutStatus
from app.models.event import Event
from app.models.group import GroupMember
from app.models.hangout import Hangout
from app.models.proposal import Proposal
from app.models.time_option import TimeOption
from app.models.user import User
from app.services.event import EventService

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


def make_event(
    *,
    hangout_id: UUID,
    proposal_id: UUID,
    time_option_id: UUID,
    user_id: UUID,
) -> Event:
    return Event(
        id=uuid4(),
        hangout_id=hangout_id,
        proposal_id=proposal_id,
        time_option_id=time_option_id,
        confirmed_by_user_id=user_id,
        title="Board games",
        description="Private room",
        location_text="Xuhui",
        starts_at=NOW + timedelta(days=1),
        ends_at=NOW + timedelta(days=1, hours=2),
        created_at=NOW,
        updated_at=NOW,
    )


class FakeEventRepository:
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
        self.hangout: Hangout | None = Hangout(
            id=uuid4(),
            group_id=group_id,
            created_by_user_id=user.id,
            title="Vote",
            description=None,
            status=HangoutStatus.VOTING,
            voting_deadline=NOW + timedelta(days=1),
            confirmed_at=None,
            cancelled_at=None,
            created_at=NOW,
            updated_at=NOW,
        )
        self.proposal: Proposal | None = Proposal(
            id=uuid4(),
            hangout_id=self.hangout.id,
            submitted_by_user_id=user.id,
            title="Board games",
            description="Private room",
            location_text="Xuhui",
            external_platform=None,
            external_url=None,
            external_data=None,
            created_at=NOW,
            updated_at=NOW,
        )
        self.time_option: TimeOption | None = TimeOption(
            id=uuid4(),
            hangout_id=self.hangout.id,
            created_by_user_id=user.id,
            starts_at=NOW + timedelta(days=1),
            ends_at=NOW + timedelta(days=1, hours=2),
            display_label="Tomorrow",
            created_at=NOW,
            updated_at=NOW,
        )
        self.event: Event | None = None
        self.calls: list[str] = []
        self.committed = False
        self.rolled_back = False
        self.fail_confirm: Exception | None = None
        self.fail_commit: Exception | None = None

    async def get_active_membership(self, **_kwargs: object) -> GroupMember | None:
        self.calls.append("membership")
        return self.membership

    async def get_active_membership_for_update(self, **_kwargs: object) -> GroupMember | None:
        self.calls.append("membership_for_update")
        return self.membership

    async def get_hangout(self, **_kwargs: object) -> Hangout | None:
        self.calls.append("hangout")
        return self.hangout

    async def get_hangout_for_update(self, **_kwargs: object) -> Hangout | None:
        self.calls.append("hangout_for_update")
        return self.hangout

    async def get_by_hangout(self, **_kwargs: object) -> Event | None:
        self.calls.append("event")
        return self.event

    async def get_proposal(
        self,
        *,
        hangout_id: UUID,
        proposal_id: UUID,
    ) -> Proposal | None:
        self.calls.append("proposal")
        if (
            self.proposal is None
            or self.proposal.id != proposal_id
            or self.proposal.hangout_id != hangout_id
        ):
            return None
        return self.proposal

    async def get_time_option(
        self,
        *,
        hangout_id: UUID,
        time_option_id: UUID,
    ) -> TimeOption | None:
        self.calls.append("time_option")
        if (
            self.time_option is None
            or self.time_option.id != time_option_id
            or self.time_option.hangout_id != hangout_id
        ):
            return None
        return self.time_option

    async def confirm(
        self,
        hangout: Hangout,
        *,
        proposal: Proposal,
        time_option: TimeOption,
        confirmed_by_user_id: UUID,
        confirmed_at: datetime,
    ) -> Event:
        self.calls.append("confirm")
        if self.fail_confirm is not None:
            raise self.fail_confirm
        self.event = make_event(
            hangout_id=hangout.id,
            proposal_id=proposal.id,
            time_option_id=time_option.id,
            user_id=confirmed_by_user_id,
        )
        self.event.title = proposal.title
        self.event.description = proposal.description
        self.event.location_text = proposal.location_text
        self.event.starts_at = time_option.starts_at
        self.event.ends_at = time_option.ends_at
        hangout.status = HangoutStatus.CONFIRMED
        hangout.confirmed_at = confirmed_at
        return self.event

    async def commit(self) -> None:
        self.calls.append("commit")
        if self.fail_commit is not None:
            raise self.fail_commit
        self.committed = True

    async def rollback(self) -> None:
        self.calls.append("rollback")
        self.rolled_back = True


@pytest.mark.parametrize("confirmer", ["creator", "owner"])
async def test_creator_or_owner_can_confirm_with_candidate_snapshot(confirmer: str) -> None:
    creator = make_user()
    current_user = creator if confirmer == "creator" else make_user()
    group_id = uuid4()
    repository = FakeEventRepository(user=current_user, group_id=group_id)
    assert repository.membership is not None
    assert repository.hangout is not None
    assert repository.proposal is not None
    assert repository.time_option is not None
    repository.membership.role = (
        GroupMemberRole.OWNER if confirmer == "owner" else GroupMemberRole.MEMBER
    )
    repository.hangout.created_by_user_id = creator.id

    event = await EventService(repository=repository, clock=lambda: NOW).confirm_event(
        current_user,
        group_id=group_id,
        hangout_id=repository.hangout.id,
        proposal_id=repository.proposal.id,
        time_option_id=repository.time_option.id,
    )

    assert repository.calls[:2] == ["membership_for_update", "hangout_for_update"]
    assert event.proposal_id == repository.proposal.id
    assert event.time_option_id == repository.time_option.id
    assert event.title == repository.proposal.title
    assert event.description == repository.proposal.description
    assert event.location_text == repository.proposal.location_text
    assert event.starts_at == repository.time_option.starts_at
    assert event.ends_at == repository.time_option.ends_at
    assert event.confirmed_by_user_id == current_user.id
    assert repository.hangout.status == HangoutStatus.CONFIRMED
    assert repository.hangout.confirmed_at == NOW
    assert repository.committed
    assert not repository.rolled_back


async def test_regular_member_cannot_confirm_another_members_hangout() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeEventRepository(user=user, group_id=group_id)
    assert repository.hangout is not None
    assert repository.proposal is not None
    assert repository.time_option is not None
    repository.hangout.created_by_user_id = uuid4()

    with pytest.raises(EventConfirmForbiddenError):
        await EventService(repository=repository, clock=lambda: NOW).confirm_event(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            proposal_id=repository.proposal.id,
            time_option_id=repository.time_option.id,
        )

    assert "confirm" not in repository.calls
    assert repository.rolled_back


async def test_non_active_member_and_wrong_hangout_scope_are_hidden() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeEventRepository(user=user, group_id=group_id)
    assert repository.hangout is not None
    assert repository.proposal is not None
    assert repository.time_option is not None
    service = EventService(repository=repository, clock=lambda: NOW)
    repository.membership = None

    with pytest.raises(GroupNotFoundError):
        await service.confirm_event(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            proposal_id=repository.proposal.id,
            time_option_id=repository.time_option.id,
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
        await service.confirm_event(
            user,
            group_id=group_id,
            hangout_id=uuid4(),
            proposal_id=repository.proposal.id,
            time_option_id=repository.time_option.id,
        )

    assert "confirm" not in repository.calls


@pytest.mark.parametrize(
    ("missing", "expected_error"),
    [("proposal", ProposalNotFoundError), ("time_option", TimeOptionNotFoundError)],
)
async def test_cross_hangout_candidate_rejected_before_any_write(
    missing: str,
    expected_error: type[Exception],
) -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeEventRepository(user=user, group_id=group_id)
    assert repository.hangout is not None
    assert repository.proposal is not None
    assert repository.time_option is not None
    proposal_id = repository.proposal.id
    time_option_id = repository.time_option.id
    if missing == "proposal":
        repository.proposal = None
    else:
        repository.time_option = None

    with pytest.raises(expected_error):
        await EventService(repository=repository, clock=lambda: NOW).confirm_event(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            proposal_id=proposal_id,
            time_option_id=time_option_id,
        )

    assert "confirm" not in repository.calls
    assert repository.hangout.status == HangoutStatus.VOTING
    assert repository.hangout.confirmed_at is None
    assert repository.event is None
    assert repository.rolled_back


@pytest.mark.parametrize(
    "status",
    [
        HangoutStatus.DRAFT,
        HangoutStatus.CONFIRMED,
        HangoutStatus.CANCELLED,
        HangoutStatus.FINISHED,
    ],
)
async def test_only_voting_hangout_can_be_confirmed_for_the_first_time(
    status: HangoutStatus,
) -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeEventRepository(user=user, group_id=group_id)
    assert repository.hangout is not None
    assert repository.proposal is not None
    assert repository.time_option is not None
    repository.hangout.status = status

    with pytest.raises(EventStateConflictError):
        await EventService(repository=repository, clock=lambda: NOW).confirm_event(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            proposal_id=repository.proposal.id,
            time_option_id=repository.time_option.id,
        )

    assert repository.event is None
    assert repository.rolled_back


async def test_same_confirmation_is_idempotent_and_different_selection_conflicts() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeEventRepository(user=user, group_id=group_id)
    assert repository.hangout is not None
    assert repository.proposal is not None
    assert repository.time_option is not None
    repository.hangout.status = HangoutStatus.CONFIRMED
    repository.hangout.confirmed_at = NOW
    repository.event = make_event(
        hangout_id=repository.hangout.id,
        proposal_id=repository.proposal.id,
        time_option_id=repository.time_option.id,
        user_id=user.id,
    )

    returned = await EventService(repository=repository, clock=lambda: NOW).confirm_event(
        user,
        group_id=group_id,
        hangout_id=repository.hangout.id,
        proposal_id=repository.proposal.id,
        time_option_id=repository.time_option.id,
    )

    assert returned is repository.event
    assert repository.committed
    assert "confirm" not in repository.calls

    repository.committed = False
    repository.rolled_back = False
    with pytest.raises(EventSelectionConflictError):
        await EventService(repository=repository, clock=lambda: NOW).confirm_event(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            proposal_id=uuid4(),
            time_option_id=repository.time_option.id,
        )
    assert repository.rolled_back
    assert not repository.committed


async def test_database_errors_roll_back_confirmation_transaction() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeEventRepository(user=user, group_id=group_id)
    assert repository.hangout is not None
    assert repository.proposal is not None
    assert repository.time_option is not None
    repository.fail_confirm = IntegrityError("insert event", {}, RuntimeError("constraint"))

    with pytest.raises(EventStateConflictError):
        await EventService(repository=repository, clock=lambda: NOW).confirm_event(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            proposal_id=repository.proposal.id,
            time_option_id=repository.time_option.id,
        )

    assert repository.rolled_back
    assert not repository.committed


async def test_unexpected_commit_error_is_rolled_back_and_propagated() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeEventRepository(user=user, group_id=group_id)
    assert repository.hangout is not None
    assert repository.proposal is not None
    assert repository.time_option is not None
    repository.fail_commit = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        await EventService(repository=repository, clock=lambda: NOW).confirm_event(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            proposal_id=repository.proposal.id,
            time_option_id=repository.time_option.id,
        )

    assert repository.rolled_back
    assert not repository.committed


async def test_active_member_can_read_event_and_missing_resources_are_hidden() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeEventRepository(user=user, group_id=group_id)
    assert repository.hangout is not None
    assert repository.proposal is not None
    assert repository.time_option is not None
    repository.event = make_event(
        hangout_id=repository.hangout.id,
        proposal_id=repository.proposal.id,
        time_option_id=repository.time_option.id,
        user_id=user.id,
    )
    service = EventService(repository=repository)

    assert (
        await service.read_event(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
        )
        is repository.event
    )

    repository.event = None
    with pytest.raises(EventNotFoundError):
        await service.read_event(user, group_id=group_id, hangout_id=repository.hangout.id)

    repository.hangout = None
    with pytest.raises(HangoutNotFoundError):
        await service.read_event(user, group_id=group_id, hangout_id=uuid4())

    repository.membership = None
    with pytest.raises(GroupNotFoundError):
        await service.read_event(user, group_id=group_id, hangout_id=uuid4())
