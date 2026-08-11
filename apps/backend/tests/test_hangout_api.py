from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_hangout_service
from app.core.exceptions import (
    GroupNotFoundError,
    HangoutEditForbiddenError,
    HangoutNotFoundError,
    HangoutStateConflictError,
    InvalidGroupCursorError,
)
from app.main import app
from app.models.enums import HangoutStatus
from app.models.hangout import Hangout
from app.models.user import User
from app.services.hangout import HangoutPage

NOW = datetime(2026, 8, 10, 3, 0, tzinfo=UTC)
FUTURE_DEADLINE = datetime(2036, 8, 15, 12, 0, tzinfo=UTC)


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


def make_hangout(*, group_id=None, creator_id=None) -> Hangout:  # type: ignore[no-untyped-def]
    return Hangout(
        id=uuid4(),
        group_id=group_id or uuid4(),
        created_by_user_id=creator_id or uuid4(),
        title="周末一起出去玩",
        description=None,
        status=HangoutStatus.DRAFT,
        voting_deadline=None,
        confirmed_at=None,
        cancelled_at=None,
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


async def test_create_hangout_returns_envelope_201_location_and_normalized_fields() -> None:
    user = make_user()
    group_id = uuid4()
    hangout = make_hangout(group_id=group_id, creator_id=user.id)

    class FakeService:
        async def create_hangout(
            self,
            current_user: User,
            **arguments: object,
        ) -> Hangout:
            assert current_user is user
            assert arguments == {
                "group_id": group_id,
                "title": "周末一起出去玩",
                "description": None,
                "voting_deadline": FUTURE_DEADLINE,
            }
            hangout.voting_deadline = FUTURE_DEADLINE
            return hangout

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_hangout_service] = FakeService

    response = await request(
        "POST",
        f"/api/v1/groups/{group_id}/hangouts",
        json={
            "title": "  周末一起出去玩  ",
            "description": "   ",
            "voting_deadline": "2036-08-15T20:00:00+08:00",
        },
    )

    assert response.status_code == 201
    assert response.headers["location"] == (
        f"http://testserver/api/v1/groups/{group_id}/hangouts/{hangout.id}"
    )
    assert response.json() == {
        "code": 0,
        "message": "success",
        "data": {
            "id": str(hangout.id),
            "group_id": str(group_id),
            "created_by_user_id": str(user.id),
            "title": "周末一起出去玩",
            "description": None,
            "status": "draft",
            "voting_deadline": "2036-08-15T12:00:00Z",
            "confirmed_at": None,
            "cancelled_at": None,
            "created_at": "2026-08-10T03:00:00Z",
            "updated_at": "2026-08-10T03:00:00Z",
        },
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "   ", "description": None, "voting_deadline": None},
        {"title": "a" * 61, "description": None, "voting_deadline": None},
        {"title": "valid", "description": "a" * 501, "voting_deadline": None},
        {"title": "valid", "description": None, "voting_deadline": "2036-08-15T12:00:00"},
        {"title": "valid", "description": None, "voting_deadline": "2020-01-01T00:00:00Z"},
        {"title": "valid", "status": "voting"},
        {"title": "valid", "group_id": str(uuid4())},
        {"title": "valid", "created_by_user_id": str(uuid4())},
    ],
)
async def test_hangout_write_validates_and_rejects_server_owned_fields(
    payload: dict[str, object],
) -> None:
    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_hangout_service] = lambda: object()

    response = await request("POST", f"/api/v1/groups/{uuid4()}/hangouts", json=payload)

    assert response.status_code == 422
    assert response.json() == {"code": 40001, "message": "Invalid request", "data": None}


async def test_list_hangouts_returns_standard_cursor_page() -> None:
    user = make_user()
    group_id = uuid4()
    hangout = make_hangout(group_id=group_id, creator_id=user.id)

    class FakeService:
        async def list_hangouts(self, current_user: User, **arguments: object) -> HangoutPage:
            assert current_user is user
            assert arguments == {"group_id": group_id, "cursor": "valid", "limit": 10}
            return HangoutPage(items=[hangout], next_cursor="next", has_more=True)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_hangout_service] = FakeService

    response = await request(
        "GET",
        f"/api/v1/groups/{group_id}/hangouts?cursor=valid&limit=10",
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["id"] == str(hangout.id)
    assert response.json()["data"]["next_cursor"] == "next"
    assert response.json()["data"]["has_more"] is True


async def test_list_hangouts_defaults_to_twenty_and_validates_limit_range() -> None:
    user = make_user()
    group_id = uuid4()

    class FakeService:
        async def list_hangouts(self, current_user: User, **arguments: object) -> HangoutPage:
            assert current_user is user
            assert arguments == {"group_id": group_id, "cursor": None, "limit": 20}
            return HangoutPage(items=[], next_cursor=None, has_more=False)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_hangout_service] = FakeService

    response = await request("GET", f"/api/v1/groups/{group_id}/hangouts")
    assert response.status_code == 200

    for invalid_limit in (0, 101):
        invalid = await request(
            "GET",
            f"/api/v1/groups/{group_id}/hangouts?limit={invalid_limit}",
        )
        assert invalid.status_code == 422
        assert invalid.json() == {"code": 40001, "message": "Invalid request", "data": None}


async def test_invalid_hangout_cursor_uses_cursor_error_envelope() -> None:
    class FakeService:
        async def list_hangouts(self, *_args: object, **_kwargs: object) -> object:
            raise InvalidGroupCursorError

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_hangout_service] = FakeService

    response = await request("GET", f"/api/v1/groups/{uuid4()}/hangouts?cursor=tampered")

    assert response.status_code == 422
    assert response.json() == {
        "code": 42213,
        "message": "Invalid pagination cursor",
        "data": None,
    }


@pytest.mark.parametrize(
    ("error", "status_code", "code", "message"),
    [
        (GroupNotFoundError(), 404, 40410, "Group not found"),
        (HangoutNotFoundError(), 404, 40420, "Hangout not found"),
        (
            HangoutEditForbiddenError(),
            403,
            40320,
            "Current member cannot edit this hangout",
        ),
        (
            HangoutStateConflictError(),
            409,
            40920,
            "Hangout state does not allow this operation",
        ),
        (InvalidGroupCursorError(), 422, 42213, "Invalid pagination cursor"),
    ],
)
async def test_hangout_domain_errors_use_safe_envelope(
    error: Exception,
    status_code: int,
    code: int,
    message: str,
) -> None:
    class FakeService:
        async def read_hangout(self, *_args: object, **_kwargs: object) -> object:
            raise error

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_hangout_service] = FakeService

    response = await request(
        "GET",
        f"/api/v1/groups/{uuid4()}/hangouts/{uuid4()}",
    )

    assert response.status_code == status_code
    assert response.json() == {"code": code, "message": message, "data": None}


async def test_update_hangout_uses_put_and_returns_updated_resource() -> None:
    user = make_user()
    group_id = uuid4()
    hangout = make_hangout(group_id=group_id, creator_id=user.id)

    class FakeService:
        async def update_hangout(self, current_user: User, **arguments: object) -> Hangout:
            assert current_user is user
            assert arguments["group_id"] == group_id
            assert arguments["hangout_id"] == hangout.id
            hangout.title = str(arguments["title"])
            return hangout

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_hangout_service] = FakeService

    response = await request(
        "PUT",
        f"/api/v1/groups/{group_id}/hangouts/{hangout.id}",
        json={"title": "更新后的约玩", "description": None, "voting_deadline": None},
    )

    assert response.status_code == 200
    assert response.json()["data"]["title"] == "更新后的约玩"
    assert response.json()["data"]["status"] == "draft"


async def test_update_rejects_status_and_other_server_owned_fields() -> None:
    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_hangout_service] = lambda: object()

    response = await request(
        "PUT",
        f"/api/v1/groups/{uuid4()}/hangouts/{uuid4()}",
        json={"title": "更新", "status": "voting"},
    )

    assert response.status_code == 422
    assert response.json() == {"code": 40001, "message": "Invalid request", "data": None}


def test_hangout_routes_document_bearer_security_and_errors() -> None:
    schema = app.openapi()
    collection = schema["paths"]["/api/v1/groups/{group_id}/hangouts"]
    detail = schema["paths"]["/api/v1/groups/{group_id}/hangouts/{hangout_id}"]

    for operation in (collection["post"], collection["get"], detail["get"], detail["put"]):
        assert operation["security"] == [{"BearerAuth": []}]
        assert "401" in operation["responses"]

    assert "201" in collection["post"]["responses"]
    assert {"403", "404", "409", "422"} <= set(detail["put"]["responses"])
