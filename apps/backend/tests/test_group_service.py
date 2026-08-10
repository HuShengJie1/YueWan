from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    GroupConfirmationNameMismatchError,
    GroupNotFoundError,
    GroupOwnerRequiredError,
    GroupStateConflictError,
)
from app.core.group_security import GroupInviteTokenService, SignedCursorCodec
from app.models.enums import GroupMemberRole
from app.models.group import Group
from app.models.user import User
from app.repositories.group import GroupDeleteTarget, GroupMemberSummary, GroupSummary
from app.services.group import GroupService

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


def make_group_summary(*, role: GroupMemberRole = GroupMemberRole.OWNER) -> GroupSummary:
    group_id = uuid4()
    return GroupSummary(
        group=Group(
            id=group_id,
            name="周末搭子",
            description=None,
            created_by_user_id=uuid4(),
            created_at=NOW,
            updated_at=NOW,
        ),
        current_user_role=role,
        member_count=1,
        joined_at=NOW,
        membership_id=uuid4(),
    )


class FakeGroupRepository:
    def __init__(self) -> None:
        self.summary = make_group_summary()
        self.groups: list[GroupSummary] = []
        self.members: list[GroupMemberSummary] = []
        self.exists = True
        self.fail_create: Exception | None = None
        self.fail_commit: Exception | None = None
        self.committed = False
        self.rolled_back = False
        self.created_with: dict[str, object] | None = None
        self.joined_with: tuple[UUID, UUID] | None = None
        self.locked_with: tuple[UUID, UUID] | None = None
        self.delete_target: GroupDeleteTarget | None = GroupDeleteTarget(
            group=self.summary.group,
            current_user_role=GroupMemberRole.OWNER,
        )
        self.deleted_group: Group | None = None

    async def create_with_owner(self, **arguments: object) -> GroupSummary:
        self.created_with = arguments
        if self.fail_create is not None:
            raise self.fail_create
        return self.summary

    async def list_active_groups(self, **_arguments: object) -> list[GroupSummary]:
        return self.groups

    async def get_active_group(self, **_arguments: object) -> GroupSummary | None:
        return self.summary if self.exists else None

    async def list_active_members(self, **_arguments: object) -> list[GroupMemberSummary]:
        return self.members

    async def group_exists(self, _group_id: UUID) -> bool:
        return self.exists

    async def join_group(self, *, group_id: UUID, user_id: UUID) -> object:
        self.joined_with = (group_id, user_id)
        return object()

    async def get_active_group_for_update(
        self,
        *,
        group_id: UUID,
        user_id: UUID,
    ) -> GroupDeleteTarget | None:
        self.locked_with = (group_id, user_id)
        return self.delete_target

    async def delete_group(self, group: Group) -> None:
        self.deleted_group = group

    async def commit(self) -> None:
        if self.fail_commit is not None:
            raise self.fail_commit
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def make_service(repository: FakeGroupRepository) -> GroupService:
    return GroupService(
        repository=repository,  # type: ignore[arg-type]
        invite_tokens=GroupInviteTokenService(
            secret=SECRET,
            issuer="test-issuer",
            audience="test-audience",
        ),
        cursors=SignedCursorCodec(secret=SECRET),
    )


async def test_create_group_commits_group_and_owner_as_one_unit() -> None:
    user = make_user()
    repository = FakeGroupRepository()

    result = await make_service(repository).create_group(
        user,
        name="  周末搭子  ",
        description="   ",
    )

    assert result is repository.summary
    assert repository.created_with == {
        "user_id": user.id,
        "name": "周末搭子",
        "description": None,
    }
    assert repository.committed
    assert not repository.rolled_back


async def test_create_group_rolls_back_the_whole_unit_on_owner_failure() -> None:
    repository = FakeGroupRepository()
    repository.fail_create = RuntimeError("owner insert failed")

    with pytest.raises(RuntimeError, match="owner insert failed"):
        await make_service(repository).create_group(
            make_user(),
            name="周末搭子",
            description=None,
        )

    assert repository.rolled_back
    assert not repository.committed


async def test_group_integrity_conflict_is_mapped_without_database_details() -> None:
    repository = FakeGroupRepository()
    repository.fail_create = IntegrityError("insert", {}, RuntimeError("unique detail"))

    with pytest.raises(GroupStateConflictError):
        await make_service(repository).create_group(
            make_user(),
            name="周末搭子",
            description=None,
        )

    assert repository.rolled_back


async def test_group_list_uses_stable_signed_cursor() -> None:
    repository = FakeGroupRepository()
    first = make_group_summary()
    second = make_group_summary()
    repository.groups = [first, second]
    service = make_service(repository)
    user = make_user()

    page = await service.list_groups(user, cursor=None, limit=1)

    assert page.items == [first]
    assert page.has_more
    assert page.next_cursor is not None
    decoded = service._cursors.decode(  # noqa: SLF001
        page.next_cursor,
        kind="group_list",
        scope=f"user:{user.id}",
    )
    assert decoded.joined_at == first.joined_at
    assert decoded.membership_id == first.membership_id


async def test_non_member_cannot_read_group_members_or_create_invite() -> None:
    repository = FakeGroupRepository()
    repository.exists = False
    service = make_service(repository)
    user = make_user()
    group_id = uuid4()

    with pytest.raises(GroupNotFoundError):
        await service.read_group(user, group_id=group_id)
    with pytest.raises(GroupNotFoundError):
        await service.list_members(user, group_id=group_id, cursor=None, limit=20)
    with pytest.raises(GroupNotFoundError):
        await service.create_invite_token(user, group_id=group_id)


async def test_first_or_repeated_join_commits_and_returns_current_group() -> None:
    repository = FakeGroupRepository()
    repository.summary = make_group_summary(role=GroupMemberRole.MEMBER)
    service = make_service(repository)
    user = make_user()
    group_id = repository.summary.group.id
    token = service._invite_tokens.issue(group_id).value  # noqa: SLF001

    result = await service.join_group(
        user,
        group_id=group_id,
        invite_token=token,
    )

    assert result is repository.summary
    assert repository.joined_with == (group_id, user.id)
    assert repository.committed
    assert not repository.rolled_back


async def test_owner_deletes_group_after_trimmed_confirmation_matches() -> None:
    repository = FakeGroupRepository()
    service = make_service(repository)
    user = make_user()
    group_id = repository.summary.group.id

    await service.delete_group(
        user,
        group_id=group_id,
        confirmation_name="  周末搭子  ",
    )

    assert repository.locked_with == (group_id, user.id)
    assert repository.deleted_group is repository.summary.group
    assert repository.committed
    assert not repository.rolled_back


async def test_active_member_cannot_delete_group() -> None:
    repository = FakeGroupRepository()
    repository.delete_target = GroupDeleteTarget(
        group=repository.summary.group,
        current_user_role=GroupMemberRole.MEMBER,
    )

    with pytest.raises(GroupOwnerRequiredError):
        await make_service(repository).delete_group(
            make_user(),
            group_id=repository.summary.group.id,
            confirmation_name="周末搭子",
        )

    assert repository.deleted_group is None
    assert repository.rolled_back
    assert not repository.committed


@pytest.mark.parametrize("visibility", ["missing", "non-member", "left-member"])
async def test_invisible_group_delete_uses_not_found(visibility: str) -> None:
    repository = FakeGroupRepository()
    repository.delete_target = None

    with pytest.raises(GroupNotFoundError):
        await make_service(repository).delete_group(
            make_user(),
            group_id=uuid4(),
            confirmation_name="周末搭子",
        )

    assert visibility
    assert repository.deleted_group is None
    assert repository.rolled_back


@pytest.mark.parametrize("confirmation_name", ["", "   ", "错误名称"])
async def test_delete_rejects_blank_or_incorrect_confirmation(confirmation_name: str) -> None:
    repository = FakeGroupRepository()

    with pytest.raises(GroupConfirmationNameMismatchError):
        await make_service(repository).delete_group(
            make_user(),
            group_id=repository.summary.group.id,
            confirmation_name=confirmation_name,
        )

    assert repository.deleted_group is None
    assert repository.rolled_back
    assert not repository.committed


async def test_delete_rolls_back_when_commit_fails() -> None:
    repository = FakeGroupRepository()
    repository.fail_commit = RuntimeError("database commit failed")

    with pytest.raises(RuntimeError, match="database commit failed"):
        await make_service(repository).delete_group(
            make_user(),
            group_id=repository.summary.group.id,
            confirmation_name="周末搭子",
        )

    assert repository.deleted_group is repository.summary.group
    assert repository.rolled_back
    assert not repository.committed
