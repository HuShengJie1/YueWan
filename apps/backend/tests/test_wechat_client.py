from collections.abc import Callable

import httpx
import pytest

from app.core.exceptions import (
    InvalidWeChatCodeError,
    WeChatLoginBlockedError,
    WeChatServiceUnavailableError,
)
from app.integrations.wechat.client import WECHAT_API_BASE_URL, WeChatClient


async def exchange_with_handler(
    handler: Callable[[httpx.Request], httpx.Response],
) -> object:
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url=WECHAT_API_BASE_URL,
        transport=transport,
    ) as http_client:
        client = WeChatClient(
            app_id="test-app-id",
            app_secret="test-app-secret",
            http_client=http_client,
        )
        return await client.exchange_code("temporary-code")


async def test_exchange_code_returns_only_stable_identity() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/sns/jscode2session"
        assert request.url.params["appid"] == "test-app-id"
        assert request.url.params["secret"] == "test-app-secret"
        assert request.url.params["js_code"] == "temporary-code"
        assert request.url.params["grant_type"] == "authorization_code"
        return httpx.Response(
            200,
            json={
                "openid": "openid-1",
                "unionid": "unionid-1",
                "session_key": "private-session-key",
            },
        )

    identity = await exchange_with_handler(handler)

    assert identity.openid == "openid-1"  # type: ignore[attr-defined]
    assert identity.unionid == "unionid-1"  # type: ignore[attr-defined]
    assert not hasattr(identity, "session_key")


@pytest.mark.parametrize(
    ("errcode", "error_type"),
    [
        (40029, InvalidWeChatCodeError),
        (40226, WeChatLoginBlockedError),
        (-1, WeChatServiceUnavailableError),
    ],
)
async def test_exchange_code_maps_wechat_errors(
    errcode: int,
    error_type: type[Exception],
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errcode": errcode, "errmsg": "upstream detail"})

    with pytest.raises(error_type):
        await exchange_with_handler(handler)


async def test_exchange_code_maps_quota_error_with_retry_hint() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errcode": 45011, "errmsg": "quota reached"})

    with pytest.raises(WeChatServiceUnavailableError) as error:
        await exchange_with_handler(handler)

    assert error.value.headers == {"Retry-After": "60"}


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(502),
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"session_key": "missing-openid"}),
    ],
)
async def test_exchange_code_hides_malformed_upstream_responses(
    response: httpx.Response,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return response

    with pytest.raises(WeChatServiceUnavailableError) as error:
        await exchange_with_handler(handler)

    assert "upstream" not in error.value.message.lower()
