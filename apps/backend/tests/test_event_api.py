from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_event_service
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
from app.main import app
from app.models.event import Event
from app.models.user import User

NOW = datetime(2026, 8, 12, 3, 0, tzinfo=UTC)


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


def make_event(*, hangout_id, proposal_id, time_option_id, user_id) -> Event:  # type: ignore[no-untyped-def]
    return Event(
        id=uuid4(),
        hangout_id=hangout_id,
        proposal_id=proposal_id,
        time_option_id=time_option_id,
        confirmed_by_user_id=user_id,
        title="桌游店",
        description="包间",
        location_text="徐汇区",
        starts_at=NOW + timedelta(days=1),
        ends_at=NOW + timedelta(days=1, hours=2),
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


async def test_put_event_returns_snapshot_in_standard_envelope() -> None:
    user = make_user()
    group_id = uuid4()
    hangout_id = uuid4()
    proposal_id = uuid4()
    time_option_id = uuid4()
    event = make_event(
        hangout_id=hangout_id,
        proposal_id=proposal_id,
        time_option_id=time_option_id,
        user_id=user.id,
    )

    class FakeService:
        async def confirm_event(self, current_user: User, **arguments: object) -> Event:
            assert current_user is user
            assert arguments == {
                "group_id": group_id,
                "hangout_id": hangout_id,
                "proposal_id": proposal_id,
                "time_option_id": time_option_id,
            }
            return event

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_event_service] = FakeService

    response = await request(
        "PUT",
        f"/api/v1/groups/{group_id}/hangouts/{hangout_id}/event",
        json={"proposal_id": str(proposal_id), "time_option_id": str(time_option_id)},
    )

    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "message": "success",
        "data": {
            "id": str(event.id),
            "hangout_id": str(hangout_id),
            "proposal_id": str(proposal_id),
            "time_option_id": str(time_option_id),
            "confirmed_by_user_id": str(user.id),
            "title": "桌游店",
            "description": "包间",
            "location_text": "徐汇区",
            "starts_at": "2026-08-13T03:00:00Z",
            "ends_at": "2026-08-13T05:00:00Z",
            "created_at": "2026-08-12T03:00:00Z",
            "updated_at": "2026-08-12T03:00:00Z",
        },
    }


async def test_get_event_returns_event_for_active_member() -> None:
    user = make_user()
    group_id = uuid4()
    hangout_id = uuid4()
    event = make_event(
        hangout_id=hangout_id,
        proposal_id=uuid4(),
        time_option_id=uuid4(),
        user_id=user.id,
    )

    class FakeService:
        async def read_event(self, current_user: User, **arguments: object) -> Event:
            assert current_user is user
            assert arguments == {"group_id": group_id, "hangout_id": hangout_id}
            return event

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_event_service] = FakeService

    response = await request("GET", f"/api/v1/groups/{group_id}/hangouts/{hangout_id}/event")

    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(event.id)
    assert response.json()["data"]["confirmed_by_user_id"] == str(user.id)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"proposal_id": str(uuid4())},
        {"proposal_id": "invalid", "time_option_id": str(uuid4())},
        {
            "proposal_id": str(uuid4()),
            "time_option_id": str(uuid4()),
            "confirmed_by_user_id": str(uuid4()),
        },
    ],
)
async def test_event_confirmation_validates_exact_request_fields(
    payload: dict[str, object],
) -> None:
    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_event_service] = lambda: object()

    response = await request(
        "PUT",
        f"/api/v1/groups/{uuid4()}/hangouts/{uuid4()}/event",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json() == {"code": 40001, "message": "Invalid request", "data": None}


@pytest.mark.parametrize(
    ("error", "status_code", "code", "message"),
    [
        (GroupNotFoundError(), 404, 40410, "Group not found"),
        (HangoutNotFoundError(), 404, 40420, "Hangout not found"),
        (ProposalNotFoundError(), 404, 40430, "Proposal not found"),
        (TimeOptionNotFoundError(), 404, 40440, "Time option not found"),
        (EventNotFoundError(), 404, 40450, "Event not found"),
        (
            EventConfirmForbiddenError(),
            403,
            40350,
            "Current member cannot confirm this event",
        ),
        (
            EventStateConflictError(),
            409,
            40960,
            "Hangout state does not allow event confirmation",
        ),
        (
            EventSelectionConflictError(),
            409,
            40961,
            "Event was already confirmed with a different selection",
        ),
    ],
)
async def test_event_domain_errors_use_safe_envelope(
    error: Exception,
    status_code: int,
    code: int,
    message: str,
) -> None:
    class FakeService:
        async def confirm_event(self, *_args: object, **_kwargs: object) -> object:
            raise error

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_event_service] = FakeService

    response = await request(
        "PUT",
        f"/api/v1/groups/{uuid4()}/hangouts/{uuid4()}/event",
        json={"proposal_id": str(uuid4()), "time_option_id": str(uuid4())},
    )

    assert response.status_code == status_code
    assert response.json() == {"code": code, "message": message, "data": None}
    assert "sql" not in response.text.lower()


def test_event_routes_document_bearer_security_statuses_and_envelopes() -> None:
    schema = app.openapi()
    operations = schema["paths"]["/api/v1/groups/{group_id}/hangouts/{hangout_id}/event"]

    for method in ("get", "put"):
        operation = operations[method]
        assert operation["security"] == [{"BearerAuth": []}]
        assert {"200", "401", "403", "404", "409", "422"} <= set(operation["responses"])
        success_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        assert success_schema["$ref"].startswith("#/components/schemas/ApiResponse_")
