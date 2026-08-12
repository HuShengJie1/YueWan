from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import (
    GroupNotFoundError,
    HangoutNotFoundError,
    InvalidGroupCursorError,
    InvalidTimeOptionError,
    TimeOptionManageForbiddenError,
    TimeOptionNotFoundError,
    TimeOptionStateConflictError,
)
from app.core.group_security import SignedCursorCodec, TimeOptionPageCursor
from app.models.enums import GroupMemberRole, GroupMemberStatus, HangoutStatus
from app.models.group import GroupMember
from app.models.hangout import Hangout
from app.models.time_option import TimeOption
from app.models.user import User
from app.services.time_option import TimeOptionService

NOW = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)
STARTS_AT = NOW + timedelta(days=4)
ENDS_AT = STARTS_AT + timedelta(hours=2)
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
) -> Hangout:
    return Hangout(
        id=uuid4(),
        group_id=group_id,
        created_by_user_id=creator_id,
        title="约玩",
        description=None,
        status=status,
        voting_deadline=None,
        confirmed_at=None,
        cancelled_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def make_time_option(*, hangout_id: UUID, creator_id: UUID) -> TimeOption:
    return TimeOption(
        id=uuid4(),
        hangout_id=hangout_id,
        created_by_user_id=creator_id,
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        display_label="周六下午",
        created_at=NOW,
        updated_at=NOW,
    )


class FakeTimeOptionRepository:
    def __init__(self, *, user: User, group_id: UUID) -> None:
        self.membership: GroupMember | None = make_membership(
            group_id=group_id,
            user_id=user.id,
        )
        self.hangout: Hangout | None = make_hangout(
            group_id=group_id,
            creator_id=uuid4(),
        )
        self.time_option: TimeOption | None = make_time_option(
            hangout_id=self.hangout.id,
            creator_id=uuid4(),
        )
        self.time_options: list[TimeOption] = []
        self.created_with: dict[str, object] | None = None
        self.updated_with: dict[str, object] | None = None
        self.listed_with: dict[str, object] | None = None
        self.deleted: TimeOption | None = None
        self.lock_order: list[str] = []
        self.fail_commit: Exception | None = None
        self.committed = False
        self.rolled_back = False

    async def get_active_membership(self, **_arguments: object) -> GroupMember | None:
        return self.membership

    async def get_active_membership_for_update(self, **_arguments: object) -> GroupMember | None:
        self.lock_order.append("membership")
        return self.membership

    async def get_hangout(self, **_arguments: object) -> Hangout | None:
        return self.hangout

    async def get_hangout_for_update(self, **_arguments: object) -> Hangout | None:
        self.lock_order.append("hangout")
        return self.hangout

    async def create(self, **arguments: object) -> TimeOption:
        self.created_with = arguments
        assert self.hangout is not None
        time_option = make_time_option(
            hangout_id=self.hangout.id,
            creator_id=arguments["created_by_user_id"],  # type: ignore[arg-type]
        )
        time_option.starts_at = arguments["starts_at"]  # type: ignore[assignment]
        time_option.ends_at = arguments["ends_at"]  # type: ignore[assignment]
        time_option.display_label = arguments["display_label"]  # type: ignore[assignment]
        self.time_option = time_option
        return time_option

    async def list_in_hangout(self, **arguments: object) -> list[TimeOption]:
        self.listed_with = arguments
        return self.time_options

    async def get_in_hangout_for_update(self, **_arguments: object) -> TimeOption | None:
        self.lock_order.append("time_option")
        return self.time_option

    async def update(self, time_option: TimeOption, **arguments: object) -> TimeOption:
        self.updated_with = arguments
        time_option.starts_at = arguments["starts_at"]  # type: ignore[assignment]
        time_option.ends_at = arguments["ends_at"]  # type: ignore[assignment]
        time_option.display_label = arguments["display_label"]  # type: ignore[assignment]
        return time_option

    async def delete(self, time_option: TimeOption) -> None:
        self.deleted = time_option

    async def commit(self) -> None:
        if self.fail_commit is not None:
            raise self.fail_commit
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def make_service(repository: FakeTimeOptionRepository) -> TimeOptionService:
    return TimeOptionService(
        repository=repository,  # type: ignore[arg-type]
        cursors=SignedCursorCodec(secret=SECRET),
        clock=lambda: NOW,
    )


async def test_active_member_creates_utc_time_option_and_commits() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeTimeOptionRepository(user=user, group_id=group_id)
    assert repository.hangout is not None
    china_tz = timezone(timedelta(hours=8))
    local_start = STARTS_AT.astimezone(china_tz)
    local_end = ENDS_AT.astimezone(china_tz)

    result = await make_service(repository).create_time_option(
        user,
        group_id=group_id,
        hangout_id=repository.hangout.id,
        starts_at=local_start,
        ends_at=local_end,
        display_label="  周六下午  ",
    )

    assert repository.lock_order == ["membership", "hangout"]
    assert repository.created_with == {
        "hangout_id": repository.hangout.id,
        "created_by_user_id": user.id,
        "starts_at": STARTS_AT,
        "ends_at": ENDS_AT,
        "display_label": "周六下午",
    }
    assert result.can_manage is True
    assert repository.committed


@pytest.mark.parametrize("visibility", ["left", "non-member", "missing-group"])
async def test_inactive_membership_cannot_create_or_list(visibility: str) -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeTimeOptionRepository(user=user, group_id=group_id)
    repository.membership = None
    service = make_service(repository)

    with pytest.raises(GroupNotFoundError):
        await service.create_time_option(
            user,
            group_id=group_id,
            hangout_id=uuid4(),
            starts_at=STARTS_AT,
            ends_at=None,
            display_label=None,
        )
    assert repository.rolled_back
    with pytest.raises(GroupNotFoundError):
        await service.list_time_options(
            user,
            group_id=group_id,
            hangout_id=uuid4(),
            cursor=None,
            limit=20,
        )
    assert visibility


async def test_hangout_and_time_option_scope_mismatches_are_hidden() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeTimeOptionRepository(user=user, group_id=group_id)
    repository.hangout = None
    with pytest.raises(HangoutNotFoundError):
        await make_service(repository).list_time_options(
            user,
            group_id=group_id,
            hangout_id=uuid4(),
            cursor=None,
            limit=20,
        )

    repository.hangout = make_hangout(group_id=group_id, creator_id=user.id)
    repository.time_option = None
    with pytest.raises(TimeOptionNotFoundError):
        await make_service(repository).delete_time_option(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            time_option_id=uuid4(),
        )
    assert repository.rolled_back


async def test_list_is_stably_paginated_scoped_and_computes_can_manage() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeTimeOptionRepository(user=user, group_id=group_id)
    assert repository.hangout is not None
    first = make_time_option(hangout_id=repository.hangout.id, creator_id=user.id)
    second = make_time_option(hangout_id=repository.hangout.id, creator_id=uuid4())
    repository.time_options = [first, second]
    service = make_service(repository)

    page = await service.list_time_options(
        user,
        group_id=group_id,
        hangout_id=repository.hangout.id,
        cursor=None,
        limit=1,
    )

    assert [item.time_option for item in page.items] == [first]
    assert page.items[0].can_manage is True
    assert page.has_more
    assert page.next_cursor is not None
    scope = f"group:{group_id}:hangout:{repository.hangout.id}"
    assert service._cursors.decode(  # noqa: SLF001
        page.next_cursor,
        kind="time_option_list",
        scope=scope,
    ) == TimeOptionPageCursor(starts_at=first.starts_at, time_option_id=first.id)
    with pytest.raises(InvalidGroupCursorError):
        await service.list_time_options(
            user,
            group_id=uuid4(),
            hangout_id=repository.hangout.id,
            cursor=page.next_cursor,
            limit=1,
        )


@pytest.mark.parametrize("manager", ["creator", "hangout_creator", "owner"])
async def test_creator_hangout_creator_or_owner_can_update(manager: str) -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeTimeOptionRepository(user=user, group_id=group_id)
    assert repository.membership is not None
    assert repository.hangout is not None
    assert repository.time_option is not None
    if manager == "creator":
        repository.time_option.created_by_user_id = user.id
    elif manager == "hangout_creator":
        repository.hangout.created_by_user_id = user.id
    else:
        repository.membership.role = GroupMemberRole.OWNER

    result = await make_service(repository).update_time_option(
        user,
        group_id=group_id,
        hangout_id=repository.hangout.id,
        time_option_id=repository.time_option.id,
        starts_at=STARTS_AT + timedelta(days=1),
        ends_at=None,
        display_label="  新时间  ",
    )

    assert repository.lock_order == ["membership", "hangout", "time_option"]
    assert result.time_option.display_label == "新时间"
    assert result.can_manage is True
    assert repository.committed


async def test_regular_member_cannot_manage_another_members_time_option() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeTimeOptionRepository(user=user, group_id=group_id)
    assert repository.hangout is not None
    assert repository.time_option is not None

    with pytest.raises(TimeOptionManageForbiddenError):
        await make_service(repository).delete_time_option(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            time_option_id=repository.time_option.id,
        )
    assert repository.deleted is None
    assert repository.rolled_back


async def test_non_draft_rejects_writes_and_list_marks_unmanageable() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeTimeOptionRepository(user=user, group_id=group_id)
    assert repository.hangout is not None
    assert repository.time_option is not None
    repository.hangout.status = HangoutStatus.CONFIRMED
    repository.time_options = [repository.time_option]
    service = make_service(repository)

    with pytest.raises(TimeOptionStateConflictError):
        await service.update_time_option(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            time_option_id=repository.time_option.id,
            starts_at=STARTS_AT,
            ends_at=None,
            display_label=None,
        )
    with pytest.raises(TimeOptionStateConflictError):
        await service.create_time_option(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            starts_at=STARTS_AT,
            ends_at=None,
            display_label=None,
        )
    page = await service.list_time_options(
        user,
        group_id=group_id,
        hangout_id=repository.hangout.id,
        cursor=None,
        limit=20,
    )
    assert page.items[0].can_manage is False
    assert repository.updated_with is None
    assert repository.created_with is None
    assert repository.rolled_back


@pytest.mark.parametrize(
    ("starts_at", "ends_at"),
    [
        (NOW, None),
        (NOW.replace(tzinfo=None), None),
        (STARTS_AT, STARTS_AT),
        (STARTS_AT, ENDS_AT.replace(tzinfo=None)),
    ],
)
async def test_service_revalidates_future_timezone_aware_time_range(
    starts_at: datetime,
    ends_at: datetime | None,
) -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeTimeOptionRepository(user=user, group_id=group_id)
    assert repository.hangout is not None
    with pytest.raises(InvalidTimeOptionError):
        await make_service(repository).create_time_option(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            starts_at=starts_at,
            ends_at=ends_at,
            display_label=None,
        )
    assert repository.created_with is None
    assert repository.rolled_back


async def test_delete_is_hard_delete_and_commit_failure_rolls_back() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeTimeOptionRepository(user=user, group_id=group_id)
    assert repository.hangout is not None
    assert repository.time_option is not None
    repository.time_option.created_by_user_id = user.id
    option_id = repository.time_option.id

    await make_service(repository).delete_time_option(
        user,
        group_id=group_id,
        hangout_id=repository.hangout.id,
        time_option_id=option_id,
    )
    assert repository.deleted is repository.time_option
    assert repository.committed

    repository.committed = False
    repository.rolled_back = False
    repository.fail_commit = RuntimeError("database commit failed")
    with pytest.raises(RuntimeError, match="database commit failed"):
        await make_service(repository).delete_time_option(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            time_option_id=option_id,
        )
    assert repository.rolled_back
    assert not repository.committed
