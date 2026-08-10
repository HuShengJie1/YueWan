from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_group_service
from app.core.exceptions import (
    GroupConfirmationNameMismatchError,
    GroupNotFoundError,
    GroupOwnerRequiredError,
    InvalidGroupCursorError,
)
from app.core.group_security import IssuedGroupInviteToken
from app.main import app
from app.models.enums import GroupMemberRole
from app.models.group import Group
from app.models.user import User
from app.repositories.group import GroupMemberSummary, GroupSummary
from app.services.group import Page

NOW = datetime(2026, 8, 10, 3, 0, tzinfo=UTC)


def make_user() -> User:
    return User(
        id=uuid4(),
        wechat_openid="openid-private",
        wechat_unionid="unionid-private",
        display_name="小林",
        avatar_url="https://example.com/avatar.jpg",
        is_active=True,
        profile_completed=True,
        last_login_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def make_summary() -> GroupSummary:
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
        current_user_role=GroupMemberRole.OWNER,
        member_count=1,
        joined_at=NOW,
        membership_id=uuid4(),
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


async def test_create_group_returns_201_location_and_normalized_payload() -> None:
    user = make_user()
    summary = make_summary()

    class FakeService:
        async def create_group(
            self,
            current_user: User,
            *,
            name: str,
            description: str | None,
        ) -> GroupSummary:
            assert current_user is user
            assert name == "周末搭子"
            assert description is None
            return summary

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_group_service] = FakeService

    response = await request(
        "POST",
        "/api/v1/groups",
        headers={"Authorization": "Bearer signed-token"},
        json={"name": "  周末搭子  ", "description": "   "},
    )

    assert response.status_code == 201
    assert response.headers["location"] == f"http://testserver/api/v1/groups/{summary.group.id}"
    assert response.json()["data"] == {
        "id": str(summary.group.id),
        "name": "周末搭子",
        "description": None,
        "current_user_role": "owner",
        "member_count": 1,
        "created_at": "2026-08-10T03:00:00Z",
        "updated_at": "2026-08-10T03:00:00Z",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "   ", "description": None},
        {"name": "a" * 41, "description": None},
        {"name": "valid", "description": "a" * 201},
    ],
)
async def test_create_group_validates_name_and_description(payload: dict[str, object]) -> None:
    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_group_service] = lambda: object()

    response = await request("POST", "/api/v1/groups", json=payload)

    assert response.status_code == 422
    assert response.json() == {"code": 40001, "message": "Invalid request", "data": None}


async def test_list_groups_returns_standard_cursor_page() -> None:
    user = make_user()
    summary = make_summary()

    class FakeService:
        async def list_groups(
            self,
            current_user: User,
            *,
            cursor: str | None,
            limit: int,
        ) -> Page[GroupSummary]:
            assert current_user is user
            assert cursor == "valid-cursor"
            assert limit == 10
            return Page(items=[summary], next_cursor="next", has_more=True)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_group_service] = FakeService

    response = await request("GET", "/api/v1/groups?cursor=valid-cursor&limit=10")

    assert response.status_code == 200
    assert response.json()["data"]["next_cursor"] == "next"
    assert response.json()["data"]["has_more"] is True
    assert response.json()["data"]["items"][0]["member_count"] == 1


async def test_invalid_group_cursor_uses_safe_domain_error() -> None:
    class FakeService:
        async def list_groups(self, *_args: object, **_kwargs: object) -> object:
            raise InvalidGroupCursorError

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_group_service] = FakeService

    response = await request("GET", "/api/v1/groups?cursor=tampered")

    assert response.status_code == 422
    assert response.json() == {
        "code": 42213,
        "message": "Invalid pagination cursor",
        "data": None,
    }


async def test_non_member_group_read_is_indistinguishable_from_missing_group() -> None:
    class FakeService:
        async def read_group(self, *_args: object, **_kwargs: object) -> object:
            raise GroupNotFoundError

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_group_service] = FakeService

    response = await request("GET", f"/api/v1/groups/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"code": 40410, "message": "Group not found", "data": None}


async def test_member_list_does_not_expose_wechat_identity_fields() -> None:
    user = make_user()
    member = GroupMemberSummary(
        user_id=user.id,
        nickname=user.display_name,
        avatar_url=user.avatar_url,
        role=GroupMemberRole.MEMBER,
        joined_at=NOW,
        membership_id=uuid4(),
    )

    class FakeService:
        async def list_members(self, *_args: object, **_kwargs: object) -> Page[GroupMemberSummary]:
            return Page(items=[member], next_cursor=None, has_more=False)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_group_service] = FakeService

    response = await request("GET", f"/api/v1/groups/{uuid4()}/members")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["items"] == [
        {
            "user_id": str(user.id),
            "nickname": "小林",
            "avatar_url": "https://example.com/avatar.jpg",
            "role": "member",
            "joined_at": "2026-08-10T03:00:00Z",
        }
    ]
    serialized = response.text
    assert "wechat_openid" not in serialized
    assert "wechat_unionid" not in serialized
    assert "openid-private" not in serialized
    assert "unionid-private" not in serialized


async def test_active_member_can_create_invite_token() -> None:
    group_id = uuid4()
    expires_at = NOW + timedelta(days=7)

    class FakeService:
        async def create_invite_token(self, *_args: object, **_kwargs: object):  # type: ignore[no-untyped-def]
            return IssuedGroupInviteToken(value="opaque-token", expires_at=expires_at)

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_group_service] = FakeService

    response = await request("POST", f"/api/v1/groups/{group_id}/invite-tokens")

    assert response.status_code == 201
    assert response.json()["data"] == {
        "invite_token": "opaque-token",
        "expires_at": "2026-08-17T03:00:00Z",
    }


async def test_join_group_returns_group_detail() -> None:
    user = make_user()
    summary = make_summary()

    class FakeService:
        async def join_group(
            self,
            current_user: User,
            *,
            group_id: object,
            invite_token: str,
        ) -> GroupSummary:
            assert current_user is user
            assert group_id == summary.group.id
            assert invite_token == "opaque-token"
            return summary

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_group_service] = FakeService

    response = await request(
        "PUT",
        f"/api/v1/groups/{summary.group.id}/members/me",
        json={"invite_token": "opaque-token"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(summary.group.id)


async def test_owner_delete_returns_empty_204_and_group_then_reads_as_not_found() -> None:
    user = make_user()
    summary = make_summary()

    class FakeService:
        def __init__(self) -> None:
            self.deleted = False

        async def delete_group(
            self,
            current_user: User,
            *,
            group_id: object,
            confirmation_name: str,
        ) -> None:
            assert current_user is user
            assert group_id == summary.group.id
            assert confirmation_name == "  周末搭子  "
            self.deleted = True

        async def read_group(self, *_args: object, **_kwargs: object) -> GroupSummary:
            if self.deleted:
                raise GroupNotFoundError
            return summary

    service = FakeService()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_group_service] = lambda: service

    response = await request(
        "DELETE",
        f"/api/v1/groups/{summary.group.id}",
        json={"confirmation_name": "  周末搭子  "},
    )
    after_delete = await request("GET", f"/api/v1/groups/{summary.group.id}")

    assert response.status_code == 204
    assert response.content == b""
    assert "content-type" not in response.headers
    assert after_delete.status_code == 404
    assert after_delete.json() == {"code": 40410, "message": "Group not found", "data": None}


async def test_active_member_delete_returns_safe_owner_error() -> None:
    class FakeService:
        async def delete_group(self, *_args: object, **_kwargs: object) -> None:
            raise GroupOwnerRequiredError

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_group_service] = FakeService

    response = await request(
        "DELETE",
        f"/api/v1/groups/{uuid4()}",
        json={"confirmation_name": "周末搭子"},
    )

    assert response.status_code == 403
    assert response.json() == {
        "code": 40310,
        "message": "Only the group owner can delete this group",
        "data": None,
    }
    assert "sql" not in response.text.lower()
    assert "traceback" not in response.text.lower()
    assert "signed-token" not in response.text


async def test_non_member_or_missing_group_delete_returns_same_404() -> None:
    class FakeService:
        async def delete_group(self, *_args: object, **_kwargs: object) -> None:
            raise GroupNotFoundError

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_group_service] = FakeService

    response = await request(
        "DELETE",
        f"/api/v1/groups/{uuid4()}",
        json={"confirmation_name": "周末搭子"},
    )

    assert response.status_code == 404
    assert response.json() == {"code": 40410, "message": "Group not found", "data": None}


@pytest.mark.parametrize("confirmation_name", ["", "   ", "错误名称"])
async def test_delete_rejects_blank_or_incorrect_confirmation_name(
    confirmation_name: str,
) -> None:
    class FakeService:
        async def delete_group(self, *_args: object, **_kwargs: object) -> None:
            raise GroupConfirmationNameMismatchError

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_group_service] = FakeService

    response = await request(
        "DELETE",
        f"/api/v1/groups/{uuid4()}",
        json={"confirmation_name": confirmation_name},
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": 42214,
        "message": "Group confirmation name does not match",
        "data": None,
    }
    assert confirmation_name not in response.text or not confirmation_name


def test_group_routes_document_bearer_auth_and_status_codes() -> None:
    schema = app.openapi()

    for path, method in {
        "/api/v1/groups": ("post", "get"),
        "/api/v1/groups/{group_id}": ("get", "delete"),
        "/api/v1/groups/{group_id}/members": ("get",),
        "/api/v1/groups/{group_id}/invite-tokens": ("post",),
        "/api/v1/groups/{group_id}/members/me": ("put",),
    }.items():
        for operation_name in method:
            operation = schema["paths"][path][operation_name]
            assert operation["security"] == [{"BearerAuth": []}]
            assert "401" in operation["responses"]

    assert "201" in schema["paths"]["/api/v1/groups"]["post"]["responses"]
    assert "201" in schema["paths"]["/api/v1/groups/{group_id}/invite-tokens"]["post"]["responses"]
    delete_responses = schema["paths"]["/api/v1/groups/{group_id}"]["delete"]["responses"]
    assert {"204", "403", "404", "409", "422"} <= set(delete_responses)
