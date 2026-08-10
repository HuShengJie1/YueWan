from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.exceptions import InvalidAccessTokenError
from app.core.security import JWT_ALGORITHM, AccessTokenService

SECRET = "test-secret-that-is-at-least-32-bytes-long"


def build_service(**overrides: object) -> AccessTokenService:
    options = {
        "secret": SECRET,
        "issuer": "test-issuer",
        "audience": "test-audience",
        "ttl_seconds": 7200,
    }
    options.update(overrides)
    return AccessTokenService(**options)  # type: ignore[arg-type]


def test_access_token_round_trip() -> None:
    user_id = uuid4()
    token = build_service().issue(user_id)

    assert token.expires_in == 7200
    assert build_service().verify(token.value) == user_id


@pytest.mark.parametrize(
    "payload_override",
    [
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
        {"aud": "another-audience"},
        {"type": "refresh"},
        {"sub": "not-a-uuid"},
    ],
)
def test_access_token_rejects_invalid_claims(payload_override: dict[str, object]) -> None:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": str(uuid4()),
        "iat": now,
        "exp": now + timedelta(hours=1),
        "iss": "test-issuer",
        "aud": "test-audience",
        "type": "access",
    }
    payload.update(payload_override)
    token = jwt.encode(payload, SECRET, algorithm=JWT_ALGORITHM)

    with pytest.raises(InvalidAccessTokenError):
        build_service().verify(token)


def test_access_token_rejects_tampering() -> None:
    token = build_service().issue(uuid4()).value

    with pytest.raises(InvalidAccessTokenError):
        build_service(secret="another-secret-that-is-at-least-32-bytes").verify(token)


def test_access_token_requires_strong_secret() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        build_service(secret="too-short")
