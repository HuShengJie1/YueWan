from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import (
    GroupNotFoundError,
    HangoutNotFoundError,
    InvalidGroupCursorError,
    ProposalManageForbiddenError,
    ProposalNotFoundError,
    ProposalStateConflictError,
)
from app.core.group_security import ProposalPageCursor, SignedCursorCodec
from app.models.enums import GroupMemberRole, GroupMemberStatus, HangoutStatus
from app.models.group import GroupMember
from app.models.hangout import Hangout
from app.models.proposal import Proposal
from app.models.user import User
from app.services.proposal import ProposalService

NOW = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)
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


def make_proposal(*, hangout_id: UUID, submitter_id: UUID) -> Proposal:
    return Proposal(
        id=uuid4(),
        hangout_id=hangout_id,
        submitted_by_user_id=submitter_id,
        title="桌游店",
        description=None,
        location_text=None,
        external_platform=None,
        external_url=None,
        external_data=None,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeProposalRepository:
    def __init__(self, *, user: User, group_id: UUID) -> None:
        self.membership: GroupMember | None = make_membership(
            group_id=group_id,
            user_id=user.id,
        )
        self.hangout: Hangout | None = make_hangout(
            group_id=group_id,
            creator_id=uuid4(),
        )
        self.proposal: Proposal | None = make_proposal(
            hangout_id=self.hangout.id,
            submitter_id=uuid4(),
        )
        self.proposals: list[Proposal] = []
        self.created_with: dict[str, object] | None = None
        self.updated_with: dict[str, object] | None = None
        self.listed_with: dict[str, object] | None = None
        self.deleted: Proposal | None = None
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

    async def create(self, **arguments: object) -> Proposal:
        self.created_with = arguments
        assert self.hangout is not None
        proposal = make_proposal(
            hangout_id=self.hangout.id,
            submitter_id=arguments["submitted_by_user_id"],  # type: ignore[arg-type]
        )
        proposal.title = str(arguments["title"])
        proposal.description = arguments["description"]  # type: ignore[assignment]
        proposal.location_text = arguments["location_text"]  # type: ignore[assignment]
        proposal.external_platform = arguments["external_platform"]  # type: ignore[assignment]
        proposal.external_url = arguments["external_url"]  # type: ignore[assignment]
        proposal.external_data = arguments["external_data"]  # type: ignore[assignment]
        self.proposal = proposal
        return proposal

    async def list_in_hangout(self, **arguments: object) -> list[Proposal]:
        self.listed_with = arguments
        return self.proposals

    async def get_in_hangout_for_update(self, **_arguments: object) -> Proposal | None:
        self.lock_order.append("proposal")
        return self.proposal

    async def update(self, proposal: Proposal, **arguments: object) -> Proposal:
        self.updated_with = arguments
        proposal.title = str(arguments["title"])
        proposal.description = arguments["description"]  # type: ignore[assignment]
        return proposal

    async def delete(self, proposal: Proposal) -> None:
        self.deleted = proposal

    async def commit(self) -> None:
        if self.fail_commit is not None:
            raise self.fail_commit
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def make_service(repository: FakeProposalRepository) -> ProposalService:
    return ProposalService(
        repository=repository,  # type: ignore[arg-type]
        cursors=SignedCursorCodec(secret=SECRET),
    )


async def test_active_member_creates_server_owned_proposal_and_commits() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeProposalRepository(user=user, group_id=group_id)
    assert repository.hangout is not None

    result = await make_service(repository).create_proposal(
        user,
        group_id=group_id,
        hangout_id=repository.hangout.id,
        title="  桌游店  ",
        description="   ",
        location_text="  徐汇区  ",
        external_platform="  official  ",
        external_url="  https://example.com/item  ",
        external_data={"source_id": "42"},
    )

    assert repository.lock_order == ["membership", "hangout"]
    assert repository.created_with == {
        "hangout_id": repository.hangout.id,
        "submitted_by_user_id": user.id,
        "title": "桌游店",
        "description": None,
        "location_text": "徐汇区",
        "external_platform": "official",
        "external_url": "https://example.com/item",
        "external_data": {"source_id": "42"},
    }
    assert result.can_manage is True
    assert repository.committed
    assert not repository.rolled_back


@pytest.mark.parametrize("visibility", ["left", "non-member", "missing-group"])
async def test_inactive_membership_cannot_create_or_list(visibility: str) -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeProposalRepository(user=user, group_id=group_id)
    repository.membership = None
    service = make_service(repository)

    with pytest.raises(GroupNotFoundError):
        await service.create_proposal(
            user,
            group_id=group_id,
            hangout_id=uuid4(),
            title="候选",
            description=None,
            location_text=None,
            external_platform=None,
            external_url=None,
            external_data=None,
        )
    assert repository.rolled_back
    with pytest.raises(GroupNotFoundError):
        await service.list_proposals(
            user,
            group_id=group_id,
            hangout_id=uuid4(),
            cursor=None,
            limit=20,
        )
    assert visibility


async def test_hangout_and_proposal_scope_mismatches_are_hidden() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeProposalRepository(user=user, group_id=group_id)
    repository.hangout = None

    with pytest.raises(HangoutNotFoundError):
        await make_service(repository).list_proposals(
            user,
            group_id=group_id,
            hangout_id=uuid4(),
            cursor=None,
            limit=20,
        )

    repository.hangout = make_hangout(group_id=group_id, creator_id=user.id)
    repository.proposal = None
    with pytest.raises(ProposalNotFoundError):
        await make_service(repository).delete_proposal(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            proposal_id=uuid4(),
        )
    assert repository.rolled_back


async def test_list_is_stably_paginated_scoped_and_computes_can_manage() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeProposalRepository(user=user, group_id=group_id)
    assert repository.hangout is not None
    first = make_proposal(hangout_id=repository.hangout.id, submitter_id=user.id)
    second = make_proposal(hangout_id=repository.hangout.id, submitter_id=uuid4())
    repository.proposals = [first, second]
    service = make_service(repository)

    page = await service.list_proposals(
        user,
        group_id=group_id,
        hangout_id=repository.hangout.id,
        cursor=None,
        limit=1,
    )

    assert [item.proposal for item in page.items] == [first]
    assert page.items[0].can_manage is True
    assert page.has_more
    assert page.next_cursor is not None
    scope = f"group:{group_id}:hangout:{repository.hangout.id}"
    assert service._cursors.decode(  # noqa: SLF001
        page.next_cursor,
        kind="proposal_list",
        scope=scope,
    ) == ProposalPageCursor(created_at=first.created_at, proposal_id=first.id)

    with pytest.raises(InvalidGroupCursorError):
        await service.list_proposals(
            user,
            group_id=group_id,
            hangout_id=uuid4(),
            cursor=page.next_cursor,
            limit=1,
        )


@pytest.mark.parametrize("manager", ["submitter", "hangout_creator", "owner"])
async def test_submitter_hangout_creator_or_owner_can_update(manager: str) -> None:
    current_user = make_user()
    group_id = uuid4()
    repository = FakeProposalRepository(user=current_user, group_id=group_id)
    assert repository.membership is not None
    assert repository.hangout is not None
    assert repository.proposal is not None
    if manager == "submitter":
        repository.proposal.submitted_by_user_id = current_user.id
    elif manager == "hangout_creator":
        repository.hangout.created_by_user_id = current_user.id
    else:
        repository.membership.role = GroupMemberRole.OWNER

    result = await make_service(repository).update_proposal(
        current_user,
        group_id=group_id,
        hangout_id=repository.hangout.id,
        proposal_id=repository.proposal.id,
        title="  新候选  ",
        description="  新说明  ",
        location_text=None,
        external_platform=None,
        external_url=None,
        external_data=None,
    )

    assert repository.lock_order == ["membership", "hangout", "proposal"]
    assert result.proposal.title == "新候选"
    assert result.can_manage is True
    assert repository.committed


async def test_regular_member_cannot_manage_another_members_proposal() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeProposalRepository(user=user, group_id=group_id)
    assert repository.hangout is not None
    assert repository.proposal is not None

    with pytest.raises(ProposalManageForbiddenError):
        await make_service(repository).delete_proposal(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            proposal_id=repository.proposal.id,
        )

    assert repository.deleted is None
    assert repository.rolled_back


async def test_non_draft_rejects_writes_and_list_marks_unmanageable() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeProposalRepository(user=user, group_id=group_id)
    assert repository.hangout is not None
    assert repository.proposal is not None
    repository.hangout.status = HangoutStatus.VOTING
    repository.proposals = [repository.proposal]
    service = make_service(repository)

    with pytest.raises(ProposalStateConflictError):
        await service.update_proposal(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            proposal_id=repository.proposal.id,
            title="新候选",
            description=None,
            location_text=None,
            external_platform=None,
            external_url=None,
            external_data=None,
        )
    with pytest.raises(ProposalStateConflictError):
        await service.create_proposal(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            title="另一个候选",
            description=None,
            location_text=None,
            external_platform=None,
            external_url=None,
            external_data=None,
        )
    page = await service.list_proposals(
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


async def test_delete_is_hard_delete_and_commit_failure_rolls_back() -> None:
    user = make_user()
    group_id = uuid4()
    repository = FakeProposalRepository(user=user, group_id=group_id)
    assert repository.hangout is not None
    assert repository.proposal is not None
    repository.proposal.submitted_by_user_id = user.id
    proposal_id = repository.proposal.id

    await make_service(repository).delete_proposal(
        user,
        group_id=group_id,
        hangout_id=repository.hangout.id,
        proposal_id=proposal_id,
    )
    assert repository.deleted is repository.proposal
    assert repository.committed

    repository.committed = False
    repository.rolled_back = False
    repository.fail_commit = RuntimeError("database commit failed")
    with pytest.raises(RuntimeError, match="database commit failed"):
        await make_service(repository).delete_proposal(
            user,
            group_id=group_id,
            hangout_id=repository.hangout.id,
            proposal_id=proposal_id,
        )
    assert repository.rolled_back
    assert not repository.committed
