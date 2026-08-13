from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import (
    GroupNotFoundError,
    HangoutEditForbiddenError,
    HangoutNotFoundError,
    HangoutProposalRequiredError,
    HangoutStateConflictError,
    HangoutTimeOptionRequiredError,
    HangoutVotingDeadlineElapsedError,
    HangoutVotingForbiddenError,
    InvalidGroupCursorError,
)
from app.core.group_security import HangoutPageCursor, SignedCursorCodec
from app.models.enums import GroupMemberRole, GroupMemberStatus, HangoutStatus
from app.models.group import GroupMember
from app.models.hangout import Hangout
from app.models.user import User
from app.services.hangout import HangoutService

NOW = datetime(2026, 8, 10, 3, 0, tzinfo=UTC)
SECRET = "test-secret-that-is-at-least-32-bytes-long"


def make_user() -> User:
    return User(
        id=uuid4(),
        wechat_openid=f"openid-{uuid4()}",
        wechat_unionid=None,
        display_name="小林",
        avatar_url=None,
        is_active=True,
        profile_completed=True,
        last_login_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def make_membership(
    *,
    group_id: UUID,
    user_id: UUID,
    role: GroupMemberRole = GroupMemberRole.MEMBER,
) -> GroupMember:
    return GroupMember(
        id=uuid4(),
        group_id=group_id,
        user_id=user_id,
        role=role,
        status=GroupMemberStatus.ACTIVE,
        left_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def make_hangout(
    *,
    group_id: UUID,
    creator_id: UUID,
    status: HangoutStatus = HangoutStatus.DRAFT,
    created_at: datetime = NOW,
) -> Hangout:
    return Hangout(
        id=uuid4(),
        group_id=group_id,
        created_by_user_id=creator_id,
        title="周末一起出去玩",
        description=None,
        status=status,
        voting_deadline=None,
        confirmed_at=None,
        cancelled_at=None,
        created_at=created_at,
        updated_at=created_at,
    )


class FakeHangoutRepository:
    def __init__(self, *, user: User, group_id: UUID) -> None:
        self.membership: GroupMember | None = make_membership(
            group_id=group_id,
            user_id=user.id,
        )
        self.hangouts: list[Hangout] = []
        self.hangout: Hangout | None = None
        self.created_with: dict[str, object] | None = None
        self.updated_with: dict[str, object] | None = None
        self.listed_with: dict[str, object] | None = None
        self.fail_commit: Exception | None = None
        self.proposal_count = 1
        self.time_option_count = 1
        self.started_voting = False
        self.committed = False
        self.rolled_back = False

    async def get_active_membership(self, **_arguments: object) -> GroupMember | None:
        return self.membership

    async def get_active_membership_for_update(self, **_arguments: object) -> GroupMember | None:
        return self.membership

    async def create(self, **arguments: object) -> Hangout:
        self.created_with = arguments
        self.hangout = make_hangout(
            group_id=arguments["group_id"],  # type: ignore[arg-type]
            creator_id=arguments["created_by_user_id"],  # type: ignore[arg-type]
        )
        self.hangout.title = str(arguments["title"])
        self.hangout.description = arguments["description"]  # type: ignore[assignment]
        self.hangout.voting_deadline = arguments["voting_deadline"]  # type: ignore[assignment]
        return self.hangout

    async def list_in_group(self, **arguments: object) -> list[Hangout]:
        self.listed_with = arguments
        return self.hangouts

    async def get_in_group(self, **_arguments: object) -> Hangout | None:
        return self.hangout

    async def get_in_group_for_update(self, **_arguments: object) -> Hangout | None:
        return self.hangout

    async def update(self, hangout: Hangout, **arguments: object) -> Hangout:
        self.updated_with = arguments
        hangout.title = str(arguments["title"])
        hangout.description = arguments["description"]  # type: ignore[assignment]
        hangout.voting_deadline = arguments["voting_deadline"]  # type: ignore[assignment]
        return hangout

    async def count_proposals(self, **_arguments: object) -> int:
        return self.proposal_count

    async def count_time_options(self, **_arguments: object) -> int:
        return self.time_option_count

    async def start_voting(self, hangout: Hangout) -> Hangout:
        self.started_voting = True
        hangout.status = HangoutStatus.VOTING
        return hangout

    async def commit(self) -> None:
        if self.fail_commit is not None:
            raise self.fail_commit
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def make_service(repository: FakeHangoutRepository) -> HangoutService:
    return HangoutService(
        repository=repository,  # type: ignore[arg-type]
        cursors=SignedCursorCodec(secret=SECRET),
        clock=lambda: NOW,
    )


async def test_active_member_creates_normalized_draft_and_commits() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeHangoutRepository(user=user, group_id=group_id)
    deadline = NOW + timedelta(days=5)

    hangout = await make_service(repository).create_hangout(
        user,
        group_id=group_id,
        title="  周末一起出去玩  ",
        description="   ",
        voting_deadline=deadline,
    )

    assert repository.created_with == {
        "group_id": group_id,
        "created_by_user_id": user.id,
        "title": "周末一起出去玩",
        "description": None,
        "voting_deadline": deadline,
    }
    assert hangout.status == HangoutStatus.DRAFT
    assert repository.committed
    assert not repository.rolled_back


async def test_non_member_cannot_create_list_or_read_hangouts() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeHangoutRepository(user=user, group_id=group_id)
    repository.membership = None
    service = make_service(repository)

    with pytest.raises(GroupNotFoundError):
        await service.create_hangout(
            user,
            group_id=group_id,
            title="约玩",
            description=None,
            voting_deadline=None,
        )
    assert repository.rolled_back

    repository.rolled_back = False
    with pytest.raises(GroupNotFoundError):
        await service.list_hangouts(user, group_id=group_id, cursor=None, limit=20)
    with pytest.raises(GroupNotFoundError):
        await service.read_hangout(user, group_id=group_id, hangout_id=uuid4())


async def test_hangout_list_builds_stable_group_scoped_cursor() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeHangoutRepository(user=user, group_id=group_id)
    first = make_hangout(group_id=group_id, creator_id=user.id)
    second = make_hangout(group_id=group_id, creator_id=user.id)
    repository.hangouts = [first, second]
    service = make_service(repository)

    page = await service.list_hangouts(user, group_id=group_id, cursor=None, limit=1)

    assert page.items == [first]
    assert page.has_more
    assert page.next_cursor is not None
    decoded = service._cursors.decode(  # noqa: SLF001
        page.next_cursor,
        kind="hangout_list",
        scope=f"group:{group_id}",
    )
    assert decoded == HangoutPageCursor(created_at=first.created_at, hangout_id=first.id)
    with pytest.raises(InvalidGroupCursorError):
        await service.list_hangouts(
            user,
            group_id=uuid4(),
            cursor=page.next_cursor,
            limit=1,
        )


async def test_group_mismatched_or_missing_hangout_is_not_visible() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeHangoutRepository(user=user, group_id=group_id)

    with pytest.raises(HangoutNotFoundError):
        await make_service(repository).read_hangout(
            user,
            group_id=group_id,
            hangout_id=uuid4(),
        )


@pytest.mark.parametrize("editor", ["creator", "owner"])
async def test_creator_or_owner_can_edit_a_draft(editor: str) -> None:
    creator = make_user()
    current_user = creator if editor == "creator" else make_user()
    group_id = uuid4()
    repository = FakeHangoutRepository(user=current_user, group_id=group_id)
    repository.membership = make_membership(
        group_id=group_id,
        user_id=current_user.id,
        role=GroupMemberRole.OWNER if editor == "owner" else GroupMemberRole.MEMBER,
    )
    repository.hangout = make_hangout(group_id=group_id, creator_id=creator.id)

    updated = await make_service(repository).update_hangout(
        current_user,
        group_id=group_id,
        hangout_id=repository.hangout.id,
        title="  新标题  ",
        description="  新说明  ",
        voting_deadline=None,
    )

    assert updated.title == "新标题"
    assert updated.description == "新说明"
    assert repository.committed
    assert not repository.rolled_back


async def test_regular_member_cannot_edit_another_members_draft() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeHangoutRepository(user=user, group_id=group_id)
    repository.hangout = make_hangout(group_id=group_id, creator_id=uuid4())

    with pytest.raises(HangoutEditForbiddenError):
        await make_service(repository).update_hangout(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            title="新标题",
            description=None,
            voting_deadline=None,
        )

    assert repository.updated_with is None
    assert repository.rolled_back
    assert not repository.committed


async def test_non_draft_hangout_cannot_be_edited() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeHangoutRepository(user=user, group_id=group_id)
    repository.hangout = make_hangout(
        group_id=group_id,
        creator_id=user.id,
        status=HangoutStatus.VOTING,
    )

    with pytest.raises(HangoutStateConflictError):
        await make_service(repository).update_hangout(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            title="新标题",
            description=None,
            voting_deadline=None,
        )

    assert repository.updated_with is None
    assert repository.rolled_back


async def test_write_rolls_back_when_commit_fails() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeHangoutRepository(user=user, group_id=group_id)
    repository.hangout = make_hangout(group_id=group_id, creator_id=user.id)
    repository.fail_commit = RuntimeError("database commit failed")

    with pytest.raises(RuntimeError, match="database commit failed"):
        await make_service(repository).update_hangout(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            title="新标题",
            description=None,
            voting_deadline=None,
        )

    assert repository.rolled_back
    assert not repository.committed


@pytest.mark.parametrize("starter", ["creator", "owner"])
async def test_creator_or_owner_can_start_voting(starter: str) -> None:
    creator = make_user()
    current_user = creator if starter == "creator" else make_user()
    group_id = uuid4()
    repository = FakeHangoutRepository(user=current_user, group_id=group_id)
    repository.membership = make_membership(
        group_id=group_id,
        user_id=current_user.id,
        role=GroupMemberRole.OWNER if starter == "owner" else GroupMemberRole.MEMBER,
    )
    repository.hangout = make_hangout(group_id=group_id, creator_id=creator.id)

    hangout = await make_service(repository).start_voting(
        current_user,
        group_id=group_id,
        hangout_id=repository.hangout.id,
    )

    assert hangout.status == HangoutStatus.VOTING
    assert repository.started_voting
    assert repository.committed
    assert not repository.rolled_back


async def test_regular_member_cannot_start_voting() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeHangoutRepository(user=user, group_id=group_id)
    repository.hangout = make_hangout(group_id=group_id, creator_id=uuid4())

    with pytest.raises(HangoutVotingForbiddenError):
        await make_service(repository).start_voting(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
        )

    assert not repository.started_voting
    assert repository.rolled_back


async def test_non_member_and_wrong_hangout_cannot_start_voting() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeHangoutRepository(user=user, group_id=group_id)
    repository.membership = None
    repository.hangout = make_hangout(group_id=group_id, creator_id=user.id)
    service = make_service(repository)

    with pytest.raises(GroupNotFoundError):
        await service.start_voting(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
        )

    repository.membership = make_membership(group_id=group_id, user_id=user.id)
    repository.hangout = None
    with pytest.raises(HangoutNotFoundError):
        await service.start_voting(
            user,
            group_id=group_id,
            hangout_id=uuid4(),
        )

    assert not repository.started_voting
    assert repository.rolled_back


@pytest.mark.parametrize(
    ("setup", "expected_error"),
    [
        ("no_proposal", HangoutProposalRequiredError),
        ("no_time_option", HangoutTimeOptionRequiredError),
        ("wrong_state", HangoutStateConflictError),
        ("elapsed_deadline", HangoutVotingDeadlineElapsedError),
    ],
)
async def test_start_voting_rejects_unready_hangout(
    setup: str,
    expected_error: type[Exception],
) -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeHangoutRepository(user=user, group_id=group_id)
    repository.hangout = make_hangout(group_id=group_id, creator_id=user.id)
    if setup == "no_proposal":
        repository.proposal_count = 0
    elif setup == "no_time_option":
        repository.time_option_count = 0
    elif setup == "wrong_state":
        repository.hangout.status = HangoutStatus.VOTING
    else:
        repository.hangout.voting_deadline = NOW

    with pytest.raises(expected_error):
        await make_service(repository).start_voting(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
        )

    assert not repository.started_voting
    assert repository.rolled_back
