from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.exceptions import InactiveUserError
from app.core.security import AccessTokenService
from app.integrations.wechat.client import WeChatClient
from app.models.user import User
from app.repositories.user import UserRepository


@dataclass(frozen=True, slots=True)
class LoginResult:
    access_token: str
    expires_in: int
    user: User


class AuthService:
    """Orchestrate WeChat identity exchange, user persistence, and token issuance."""

    def __init__(
        self,
        *,
        user_repository: UserRepository,
        wechat_client: WeChatClient,
        token_service: AccessTokenService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._users = user_repository
        self._wechat = wechat_client
        self._tokens = token_service
        self._clock = clock or (lambda: datetime.now(UTC))

    async def login_with_wechat(self, code: str) -> LoginResult:
        identity = await self._wechat.exchange_code(code)

        try:
            user = await self._users.upsert_wechat_user(
                openid=identity.openid,
                unionid=identity.unionid,
                logged_in_at=self._clock(),
            )
            if not user.is_active:
                raise InactiveUserError
            await self._users.commit()
        except Exception:
            await self._users.rollback()
            raise

        token = self._tokens.issue(user.id)
        return LoginResult(
            access_token=token.value,
            expires_in=token.expires_in,
            user=user,
        )
