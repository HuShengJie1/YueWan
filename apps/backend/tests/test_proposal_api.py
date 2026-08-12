from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_proposal_service
from app.core.exceptions import (
    GroupNotFoundError,
    HangoutNotFoundError,
    ProposalManageForbiddenError,
    ProposalNotFoundError,
    ProposalStateConflictError,
)
from app.main import app
from app.models.proposal import Proposal
from app.models.user import User
from app.services.proposal import ManagedProposal, ProposalPage

NOW = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)


def make_user() -> User:
    return User(
        id=uuid4(),
        wechat_openid="openid-private",
        wechat_unionid="unionid-private",
        display_name="小林",
        avatar_url=None,
        is_active=True,
        profile_completed=True,
        last_login_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def make_proposal(*, hangout_id=None, submitter_id=None) -> Proposal:  # type: ignore[no-untyped-def]
    return Proposal(
        id=uuid4(),
        hangout_id=hangout_id or uuid4(),
        submitted_by_user_id=submitter_id or uuid4(),
        title="桌游店",
        description=None,
        location_text="徐汇区",
        external_platform="official",
        external_url="https://example.com/item",
        external_data={"source_id": "42"},
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> None:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


async def request(method: str, path: str, **kwargs: object):  # type: ignore[no-untyped-def]
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, **kwargs)


async def test_create_proposal_returns_201_location_envelope_and_cleaned_fields() -> None:
    user = make_user()
    group_id = uuid4()
    hangout_id = uuid4()
    proposal = make_proposal(hangout_id=hangout_id, submitter_id=user.id)

    class FakeService:
        async def create_proposal(
            self,
            current_user: User,
            **arguments: object,
        ) -> ManagedProposal:
            assert current_user is user
            assert arguments == {
                "group_id": group_id,
                "hangout_id": hangout_id,
                "title": "桌游店",
                "description": None,
                "location_text": "徐汇区",
                "external_platform": "official",
                "external_url": "https://example.com/item",
                "external_data": {"source_id": "42"},
            }
            return ManagedProposal(proposal=proposal, can_manage=True)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_proposal_service] = FakeService

    response = await request(
        "POST",
        f"/api/v1/groups/{group_id}/hangouts/{hangout_id}/proposals",
        json={
            "title": "  桌游店  ",
            "description": "   ",
            "location_text": "  徐汇区  ",
            "external_platform": "  official  ",
            "external_url": "  https://example.com/item  ",
            "external_data": {"source_id": "42"},
        },
    )

    assert response.status_code == 201
    assert response.headers["location"] == (
        f"http://testserver/api/v1/groups/{group_id}/hangouts/{hangout_id}/proposals/{proposal.id}"
    )
    assert response.json() == {
        "code": 0,
        "message": "success",
        "data": {
            "id": str(proposal.id),
            "hangout_id": str(hangout_id),
            "submitted_by_user_id": str(user.id),
            "title": "桌游店",
            "description": None,
            "location_text": "徐汇区",
            "external_platform": "official",
            "external_url": "https://example.com/item",
            "external_data": {"source_id": "42"},
            "created_at": "2026-08-11T03:00:00Z",
            "updated_at": "2026-08-11T03:00:00Z",
            "can_manage": True,
        },
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "   "},
        {"title": "a" * 81},
        {"title": "valid", "description": "a" * 501},
        {"title": "valid", "location_text": "a" * 201},
        {"title": "valid", "external_platform": "a" * 51},
        {"title": "valid", "external_url": "ftp://example.com/item"},
        {"title": "valid", "external_url": "https://user:password@example.com/item"},
        {"title": "valid", "external_data": {"nested": {"accessToken": "private"}}},
        {"title": "valid", "submitted_by_user_id": str(uuid4())},
        {"title": "valid", "hangout_id": str(uuid4())},
        {"title": "valid", "can_manage": True},
    ],
)
async def test_proposal_schema_rejects_invalid_or_server_owned_fields(
    payload: dict[str, object],
) -> None:
    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_proposal_service] = lambda: object()

    response = await request(
        "POST",
        f"/api/v1/groups/{uuid4()}/hangouts/{uuid4()}/proposals",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json() == {"code": 40001, "message": "Invalid request", "data": None}


async def test_list_proposals_returns_standard_scoped_cursor_page_defaults() -> None:
    user = make_user()
    group_id = uuid4()
    hangout_id = uuid4()
    proposal = make_proposal(hangout_id=hangout_id)

    class FakeService:
        async def list_proposals(
            self,
            current_user: User,
            **arguments: object,
        ) -> ProposalPage:
            assert current_user is user
            assert arguments == {
                "group_id": group_id,
                "hangout_id": hangout_id,
                "cursor": None,
                "limit": 20,
            }
            return ProposalPage(
                items=[ManagedProposal(proposal=proposal, can_manage=False)],
                next_cursor="next",
                has_more=True,
            )

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_proposal_service] = FakeService

    response = await request(
        "GET",
        f"/api/v1/groups/{group_id}/hangouts/{hangout_id}/proposals",
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["can_manage"] is False
    assert response.json()["data"]["next_cursor"] == "next"
    assert response.json()["data"]["has_more"] is True


@pytest.mark.parametrize("limit", [0, 101])
async def test_proposal_list_validates_limit_range(limit: int) -> None:
    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_proposal_service] = lambda: object()

    response = await request(
        "GET",
        f"/api/v1/groups/{uuid4()}/hangouts/{uuid4()}/proposals?limit={limit}",
    )

    assert response.status_code == 422
    assert response.json() == {"code": 40001, "message": "Invalid request", "data": None}


async def test_update_proposal_returns_uniform_success_envelope() -> None:
    user = make_user()
    group_id = uuid4()
    proposal = make_proposal(submitter_id=user.id)

    class FakeService:
        async def update_proposal(self, *_args: object, **arguments: object) -> ManagedProposal:
            proposal.title = str(arguments["title"])
            return ManagedProposal(proposal=proposal, can_manage=True)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_proposal_service] = FakeService

    response = await request(
        "PUT",
        f"/api/v1/groups/{group_id}/hangouts/{proposal.hangout_id}/proposals/{proposal.id}",
        json={"title": "更新候选"},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["message"] == "success"
    assert response.json()["data"]["title"] == "更新候选"


async def test_delete_proposal_returns_empty_204() -> None:
    user = make_user()
    group_id = uuid4()
    hangout_id = uuid4()
    proposal_id = uuid4()

    class FakeService:
        async def delete_proposal(self, current_user: User, **arguments: object) -> None:
            assert current_user is user
            assert arguments == {
                "group_id": group_id,
                "hangout_id": hangout_id,
                "proposal_id": proposal_id,
            }

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_proposal_service] = FakeService

    response = await request(
        "DELETE",
        f"/api/v1/groups/{group_id}/hangouts/{hangout_id}/proposals/{proposal_id}",
    )

    assert response.status_code == 204
    assert response.content == b""
    assert "content-type" not in response.headers


@pytest.mark.parametrize(
    ("error", "status_code", "code", "message"),
    [
        (GroupNotFoundError(), 404, 40410, "Group not found"),
        (HangoutNotFoundError(), 404, 40420, "Hangout not found"),
        (ProposalNotFoundError(), 404, 40430, "Proposal not found"),
        (
            ProposalManageForbiddenError(),
            403,
            40330,
            "Current member cannot manage this proposal",
        ),
        (
            ProposalStateConflictError(),
            409,
            40930,
            "Hangout state does not allow proposal changes",
        ),
    ],
)
async def test_proposal_domain_errors_use_safe_envelope(
    error: Exception,
    status_code: int,
    code: int,
    message: str,
) -> None:
    class FakeService:
        async def list_proposals(self, *_args: object, **_kwargs: object) -> object:
            raise error

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_proposal_service] = FakeService

    response = await request(
        "GET",
        f"/api/v1/groups/{uuid4()}/hangouts/{uuid4()}/proposals",
    )

    assert response.status_code == status_code
    assert response.json() == {"code": code, "message": message, "data": None}
    assert "sql" not in response.text.lower()
    assert "traceback" not in response.text.lower()
