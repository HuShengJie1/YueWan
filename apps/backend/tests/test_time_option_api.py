from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_time_option_service
from app.core.exceptions import (
    GroupNotFoundError,
    HangoutNotFoundError,
    TimeOptionManageForbiddenError,
    TimeOptionNotFoundError,
    TimeOptionStateConflictError,
)
from app.main import app
from app.models.time_option import TimeOption
from app.models.user import User
from app.services.time_option import ManagedTimeOption, TimeOptionPage

NOW = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)
STARTS_AT = datetime(2036, 8, 15, 12, 0, tzinfo=UTC)
ENDS_AT = STARTS_AT + timedelta(hours=2)


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


def make_time_option(*, hangout_id=None, creator_id=None) -> TimeOption:  # type: ignore[no-untyped-def]
    return TimeOption(
        id=uuid4(),
        hangout_id=hangout_id or uuid4(),
        created_by_user_id=creator_id or uuid4(),
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        display_label="周六晚上",
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


async def test_create_time_option_returns_201_location_envelope_and_utc_fields() -> None:
    user = make_user()
    group_id = uuid4()
    hangout_id = uuid4()
    time_option = make_time_option(hangout_id=hangout_id, creator_id=user.id)

    class FakeService:
        async def create_time_option(
            self,
            current_user: User,
            **arguments: object,
        ) -> ManagedTimeOption:
            assert current_user is user
            assert arguments == {
                "group_id": group_id,
                "hangout_id": hangout_id,
                "starts_at": STARTS_AT,
                "ends_at": ENDS_AT,
                "display_label": "周六晚上",
            }
            return ManagedTimeOption(time_option=time_option, can_manage=True)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_time_option_service] = FakeService

    response = await request(
        "POST",
        f"/api/v1/groups/{group_id}/hangouts/{hangout_id}/time-options",
        json={
            "starts_at": "2036-08-15T20:00:00+08:00",
            "ends_at": "2036-08-15T22:00:00+08:00",
            "display_label": "  周六晚上  ",
        },
    )

    assert response.status_code == 201
    assert response.headers["location"] == (
        f"http://testserver/api/v1/groups/{group_id}/hangouts/{hangout_id}"
        f"/time-options/{time_option.id}"
    )
    assert response.json() == {
        "code": 0,
        "message": "success",
        "data": {
            "id": str(time_option.id),
            "hangout_id": str(hangout_id),
            "created_by_user_id": str(user.id),
            "starts_at": "2036-08-15T12:00:00Z",
            "ends_at": "2036-08-15T14:00:00Z",
            "display_label": "周六晚上",
            "created_at": "2026-08-11T03:00:00Z",
            "updated_at": "2026-08-11T03:00:00Z",
            "can_manage": True,
        },
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"starts_at": "2036-08-15T12:00:00"},
        {"starts_at": "2020-08-15T12:00:00Z"},
        {
            "starts_at": "2036-08-15T12:00:00Z",
            "ends_at": "2036-08-15T12:00:00Z",
        },
        {
            "starts_at": "2036-08-15T12:00:00Z",
            "ends_at": "2036-08-15T13:00:00",
        },
        {"starts_at": "2036-08-15T12:00:00Z", "display_label": "a" * 81},
        {"starts_at": "2036-08-15T12:00:00Z", "created_by_user_id": str(uuid4())},
        {"starts_at": "2036-08-15T12:00:00Z", "hangout_id": str(uuid4())},
        {"starts_at": "2036-08-15T12:00:00Z", "can_manage": True},
    ],
)
async def test_time_option_schema_rejects_invalid_or_server_owned_fields(
    payload: dict[str, object],
) -> None:
    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_time_option_service] = lambda: object()

    response = await request(
        "POST",
        f"/api/v1/groups/{uuid4()}/hangouts/{uuid4()}/time-options",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json() == {"code": 40001, "message": "Invalid request", "data": None}


async def test_list_time_options_returns_standard_cursor_page_defaults() -> None:
    user = make_user()
    group_id = uuid4()
    hangout_id = uuid4()
    time_option = make_time_option(hangout_id=hangout_id)

    class FakeService:
        async def list_time_options(
            self,
            current_user: User,
            **arguments: object,
        ) -> TimeOptionPage:
            assert current_user is user
            assert arguments == {
                "group_id": group_id,
                "hangout_id": hangout_id,
                "cursor": "valid",
                "limit": 10,
            }
            return TimeOptionPage(
                items=[ManagedTimeOption(time_option=time_option, can_manage=False)],
                next_cursor="next",
                has_more=True,
            )

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_time_option_service] = FakeService

    response = await request(
        "GET",
        f"/api/v1/groups/{group_id}/hangouts/{hangout_id}/time-options?cursor=valid&limit=10",
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["can_manage"] is False
    assert response.json()["data"]["next_cursor"] == "next"
    assert response.json()["data"]["has_more"] is True


async def test_update_time_option_returns_uniform_success_envelope() -> None:
    user = make_user()
    group_id = uuid4()
    time_option = make_time_option(creator_id=user.id)

    class FakeService:
        async def update_time_option(
            self,
            *_args: object,
            **arguments: object,
        ) -> ManagedTimeOption:
            time_option.display_label = arguments["display_label"]  # type: ignore[assignment]
            return ManagedTimeOption(time_option=time_option, can_manage=True)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_time_option_service] = FakeService

    response = await request(
        "PUT",
        f"/api/v1/groups/{group_id}/hangouts/{time_option.hangout_id}"
        f"/time-options/{time_option.id}",
        json={
            "starts_at": "2036-08-15T12:00:00Z",
            "ends_at": None,
            "display_label": "更新时段",
        },
    )

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["message"] == "success"
    assert response.json()["data"]["display_label"] == "更新时段"


async def test_delete_time_option_returns_empty_204() -> None:
    user = make_user()
    group_id = uuid4()
    hangout_id = uuid4()
    time_option_id = uuid4()

    class FakeService:
        async def delete_time_option(self, current_user: User, **arguments: object) -> None:
            assert current_user is user
            assert arguments == {
                "group_id": group_id,
                "hangout_id": hangout_id,
                "time_option_id": time_option_id,
            }

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_time_option_service] = FakeService

    response = await request(
        "DELETE",
        f"/api/v1/groups/{group_id}/hangouts/{hangout_id}/time-options/{time_option_id}",
    )

    assert response.status_code == 204
    assert response.content == b""
    assert "content-type" not in response.headers


@pytest.mark.parametrize(
    ("error", "status_code", "code", "message"),
    [
        (GroupNotFoundError(), 404, 40410, "Group not found"),
        (HangoutNotFoundError(), 404, 40420, "Hangout not found"),
        (TimeOptionNotFoundError(), 404, 40440, "Time option not found"),
        (
            TimeOptionManageForbiddenError(),
            403,
            40340,
            "Current member cannot manage this time option",
        ),
        (
            TimeOptionStateConflictError(),
            409,
            40940,
            "Hangout state does not allow time option changes",
        ),
    ],
)
async def test_time_option_domain_errors_use_safe_envelope(
    error: Exception,
    status_code: int,
    code: int,
    message: str,
) -> None:
    class FakeService:
        async def list_time_options(self, *_args: object, **_kwargs: object) -> object:
            raise error

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_time_option_service] = FakeService

    response = await request(
        "GET",
        f"/api/v1/groups/{uuid4()}/hangouts/{uuid4()}/time-options",
    )

    assert response.status_code == status_code
    assert response.json() == {"code": code, "message": message, "data": None}
    assert "sql" not in response.text.lower()
    assert "traceback" not in response.text.lower()
