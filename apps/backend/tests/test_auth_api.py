from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_auth_service,
    get_avatar_service,
    get_avatar_upload_limit,
    get_current_user,
    get_user_service,
)
from app.core.exceptions import InvalidWeChatCodeError
from app.main import app
from app.models.user import User
from app.services.auth import LoginResult

NOW = datetime(2026, 8, 9, 3, 0, tzinfo=UTC)


def make_user() -> User:
    return User(
        id=uuid4(),
        wechat_openid="openid-1",
        wechat_unionid=None,
        display_name="微信用户",
        avatar_url=None,
        is_active=True,
        profile_completed=False,
        last_login_at=NOW,
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


async def test_wechat_login_returns_access_token_and_user() -> None:
    user = make_user()

    class FakeAuthService:
        async def login_with_wechat(self, code: str) -> LoginResult:
            assert code == "temporary-code"
            return LoginResult(access_token="signed-token", expires_in=7200, user=user)

    app.dependency_overrides[get_auth_service] = FakeAuthService

    response = await request(
        "POST",
        "/api/v1/auth/wechat/login",
        json={"code": " temporary-code "},
    )

    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "message": "success",
        "data": {
            "access_token": "signed-token",
            "token_type": "bearer",
            "expires_in": 7200,
            "user": {
                "id": str(user.id),
                "nickname": None,
                "avatar_url": None,
                "profile_completed": False,
            },
        },
    }


async def test_wechat_login_uses_safe_error_envelope() -> None:
    class FakeAuthService:
        async def login_with_wechat(self, _code: str) -> LoginResult:
            raise InvalidWeChatCodeError

    app.dependency_overrides[get_auth_service] = FakeAuthService

    response = await request(
        "POST",
        "/api/v1/auth/wechat/login",
        json={"code": "bad-code"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {
        "code": 40101,
        "message": "Invalid or expired WeChat login code",
        "data": None,
    }


async def test_wechat_login_validation_uses_error_envelope() -> None:
    app.dependency_overrides[get_auth_service] = lambda: object()

    response = await request("POST", "/api/v1/auth/wechat/login", json={"code": "   "})

    assert response.status_code == 422
    assert response.json() == {
        "code": 40001,
        "message": "Invalid request",
        "data": None,
    }


async def test_read_current_user() -> None:
    user = make_user()
    app.dependency_overrides[get_current_user] = lambda: user

    response = await request(
        "GET",
        "/api/v1/users/me",
        headers={"Authorization": "Bearer signed-token"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(user.id)
    assert response.json()["data"]["nickname"] is None


async def test_read_current_user_requires_bearer_token() -> None:
    response = await request("GET", "/api/v1/users/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {
        "code": 40102,
        "message": "Invalid or expired access token",
        "data": None,
    }


async def test_update_current_user_completes_profile() -> None:
    user = make_user()

    class FakeUserService:
        async def update_profile(self, current_user: User, *, nickname: str) -> User:
            assert current_user is user
            assert nickname == "小林"
            current_user.display_name = nickname
            current_user.profile_completed = True
            return current_user

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_user_service] = FakeUserService

    response = await request(
        "PUT",
        "/api/v1/users/me",
        headers={"Authorization": "Bearer signed-token"},
        json={"nickname": "  小林  "},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "id": str(user.id),
        "nickname": "小林",
        "avatar_url": None,
        "profile_completed": True,
    }


async def test_update_current_user_rejects_blank_nickname() -> None:
    user = make_user()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_user_service] = lambda: object()

    response = await request(
        "PUT",
        "/api/v1/users/me",
        headers={"Authorization": "Bearer signed-token"},
        json={"nickname": "   "},
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": 40001,
        "message": "Invalid request",
        "data": None,
    }


def test_authentication_routes_are_documented_with_bearer_security() -> None:
    schema = app.openapi()

    assert "/api/v1/auth/wechat/login" in schema["paths"]
    assert "security" not in schema["paths"]["/api/v1/auth/wechat/login"]["post"]
    for method in ("get", "put"):
        operation = schema["paths"]["/api/v1/users/me"][method]
        assert operation["security"] == [{"BearerAuth": []}]
        assert "401" in operation["responses"]

    avatar_operation = schema["paths"]["/api/v1/users/me/avatar"]["post"]
    assert avatar_operation["security"] == [{"BearerAuth": []}]
    assert "multipart/form-data" in avatar_operation["requestBody"]["content"]
    assert "413" in avatar_operation["responses"]
    cloud_avatar_operation = schema["paths"]["/api/v1/users/me/avatar"]["put"]
    assert cloud_avatar_operation["security"] == [{"BearerAuth": []}]
    assert "application/json" in cloud_avatar_operation["requestBody"]["content"]
    assert "503" in cloud_avatar_operation["responses"]


async def test_upload_current_user_avatar() -> None:
    user = make_user()

    class FakeAvatarService:
        async def update_avatar(self, current_user: User, *, content: bytes) -> User:
            assert current_user is user
            assert content == b"image-content"
            current_user.avatar_url = "http://testserver/media/avatars/new.jpg"
            return current_user

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_avatar_service] = FakeAvatarService
    app.dependency_overrides[get_avatar_upload_limit] = lambda: 1024

    response = await request(
        "POST",
        "/api/v1/users/me/avatar",
        headers={"Authorization": "Bearer signed-token"},
        files={"file": ("avatar.png", b"image-content", "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["data"]["avatar_url"] == ("http://testserver/media/avatars/new.jpg")


async def test_upload_current_user_avatar_rejects_oversized_file() -> None:
    user = make_user()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_avatar_service] = lambda: object()
    app.dependency_overrides[get_avatar_upload_limit] = lambda: 3

    response = await request(
        "POST",
        "/api/v1/users/me/avatar",
        headers={"Authorization": "Bearer signed-token"},
        files={"file": ("avatar.png", b"four", "image/png")},
    )

    assert response.status_code == 413
    assert response.json() == {
        "code": 41301,
        "message": "Avatar file is too large",
        "data": None,
    }


async def test_update_current_user_avatar_from_cloud_file() -> None:
    user = make_user()

    class FakeAvatarService:
        async def update_avatar_from_cloud(self, current_user: User, *, file_id: str) -> User:
            assert current_user is user
            assert file_id == "cloud://prod.bucket/avatar-uploads/user/source"
            current_user.avatar_url = "https://storage.example.com/avatars/new.jpg"
            return current_user

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_avatar_service] = FakeAvatarService

    response = await request(
        "PUT",
        "/api/v1/users/me/avatar",
        headers={"Authorization": "Bearer signed-token"},
        json={"file_id": " cloud://prod.bucket/avatar-uploads/user/source "},
    )

    assert response.status_code == 200
    assert response.json()["data"]["avatar_url"] == ("https://storage.example.com/avatars/new.jpg")
