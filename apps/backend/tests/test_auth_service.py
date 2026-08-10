from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import InactiveUserError
from app.core.security import IssuedAccessToken
from app.integrations.wechat.client import WeChatIdentity
from app.models.user import User
from app.services.auth import AuthService

NOW = datetime(2026, 8, 9, 3, 0, tzinfo=UTC)


def make_user(*, is_active: bool = True) -> User:
    return User(
        id=uuid4(),
        wechat_openid="openid-1",
        wechat_unionid="unionid-1",
        display_name="微信用户",
        avatar_url=None,
        is_active=is_active,
        profile_completed=False,
        last_login_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeWeChatClient:
    def __init__(self, identity: WeChatIdentity) -> None:
        self.identity = identity
        self.received_code: str | None = None

    async def exchange_code(self, code: str) -> WeChatIdentity:
        self.received_code = code
        return self.identity


class FakeUserRepository:
    def __init__(self, user: User, *, failure: Exception | None = None) -> None:
        self.user = user
        self.failure = failure
        self.upsert_arguments: dict[str, object] | None = None
        self.committed = False
        self.rolled_back = False

    async def upsert_wechat_user(self, **arguments: object) -> User:
        self.upsert_arguments = arguments
        if self.failure is not None:
            raise self.failure
        return self.user

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeTokenService:
    def __init__(self) -> None:
        self.user_id: UUID | None = None

    def issue(self, user_id: UUID) -> IssuedAccessToken:
        self.user_id = user_id
        return IssuedAccessToken(value="signed-token", expires_in=7200)


async def test_wechat_login_persists_user_and_issues_token() -> None:
    user = make_user()
    repository = FakeUserRepository(user)
    wechat = FakeWeChatClient(WeChatIdentity(openid="openid-1", unionid="unionid-1"))
    tokens = FakeTokenService()
    service = AuthService(
        user_repository=repository,  # type: ignore[arg-type]
        wechat_client=wechat,  # type: ignore[arg-type]
        token_service=tokens,  # type: ignore[arg-type]
        clock=lambda: NOW,
    )

    result = await service.login_with_wechat("temporary-code")

    assert wechat.received_code == "temporary-code"
    assert repository.upsert_arguments == {
        "openid": "openid-1",
        "unionid": "unionid-1",
        "logged_in_at": NOW,
    }
    assert repository.committed
    assert not repository.rolled_back
    assert tokens.user_id == user.id
    assert result.access_token == "signed-token"
    assert result.expires_in == 7200
    assert result.user is user


async def test_wechat_login_rolls_back_inactive_user() -> None:
    repository = FakeUserRepository(make_user(is_active=False))
    tokens = FakeTokenService()
    service = AuthService(
        user_repository=repository,  # type: ignore[arg-type]
        wechat_client=FakeWeChatClient(  # type: ignore[arg-type]
            WeChatIdentity(openid="openid-1", unionid=None)
        ),
        token_service=tokens,  # type: ignore[arg-type]
        clock=lambda: NOW,
    )

    with pytest.raises(InactiveUserError):
        await service.login_with_wechat("temporary-code")

    assert repository.rolled_back
    assert not repository.committed
    assert tokens.user_id is None


async def test_wechat_login_rolls_back_repository_failure() -> None:
    repository = FakeUserRepository(make_user(), failure=RuntimeError("database failed"))
    service = AuthService(
        user_repository=repository,  # type: ignore[arg-type]
        wechat_client=FakeWeChatClient(  # type: ignore[arg-type]
            WeChatIdentity(openid="openid-1", unionid=None)
        ),
        token_service=FakeTokenService(),  # type: ignore[arg-type]
        clock=lambda: NOW,
    )

    with pytest.raises(RuntimeError, match="database failed"):
        await service.login_with_wechat("temporary-code")

    assert repository.rolled_back
    assert not repository.committed
