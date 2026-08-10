from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from app.core.exceptions import (
    InvalidWeChatCodeError,
    WeChatLoginBlockedError,
    WeChatServiceUnavailableError,
)

WECHAT_API_BASE_URL = "https://api.weixin.qq.com"
CODE_TO_SESSION_PATH = "/sns/jscode2session"
WECHAT_INVALID_CODE = 40029
WECHAT_LOGIN_BLOCKED = 40226
WECHAT_MINUTE_QUOTA_REACHED = 45011


@dataclass(frozen=True, slots=True)
class WeChatIdentity:
    openid: str
    unionid: str | None


class CodeToSessionPayload(BaseModel):
    """Private transport schema; session_key must never leave this adapter."""

    model_config = ConfigDict(extra="ignore")

    openid: str | None = None
    unionid: str | None = None
    session_key: SecretStr | None = None
    errcode: int = 0
    errmsg: str | None = None


class WeChatClient:
    """Exchange a short-lived wx.login code through WeChat's official server API."""

    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        timeout_seconds: float = 5.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._timeout = httpx.Timeout(timeout_seconds)
        self._http_client = http_client

    async def exchange_code(self, code: str) -> WeChatIdentity:
        params = {
            "appid": self._app_id,
            "secret": self._app_secret,
            "js_code": code,
            "grant_type": "authorization_code",
        }

        try:
            if self._http_client is not None:
                response = await self._http_client.get(CODE_TO_SESSION_PATH, params=params)
            else:
                async with httpx.AsyncClient(
                    base_url=WECHAT_API_BASE_URL,
                    timeout=self._timeout,
                ) as client:
                    response = await client.get(CODE_TO_SESSION_PATH, params=params)
            response.raise_for_status()
            payload = CodeToSessionPayload.model_validate(response.json())
        except (httpx.HTTPError, TypeError, ValueError, ValidationError) as exc:
            raise WeChatServiceUnavailableError from exc

        if payload.errcode == WECHAT_INVALID_CODE:
            raise InvalidWeChatCodeError
        if payload.errcode == WECHAT_LOGIN_BLOCKED:
            raise WeChatLoginBlockedError
        if payload.errcode == WECHAT_MINUTE_QUOTA_REACHED:
            raise WeChatServiceUnavailableError(retry_after=60)
        if payload.errcode != 0 or not payload.openid or payload.session_key is None:
            raise WeChatServiceUnavailableError

        return WeChatIdentity(openid=payload.openid, unionid=payload.unionid)
