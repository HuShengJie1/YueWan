from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from jwt import PyJWTError

from app.core.exceptions import InvalidAccessTokenError

JWT_ALGORITHM = "HS256"
MINIMUM_SECRET_BYTES = 32


@dataclass(frozen=True, slots=True)
class IssuedAccessToken:
    value: str
    expires_in: int


class AccessTokenService:
    """Issue and verify this application's stateless JWT access tokens."""

    def __init__(
        self,
        *,
        secret: str,
        issuer: str,
        audience: str,
        ttl_seconds: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if len(secret.encode()) < MINIMUM_SECRET_BYTES:
            raise ValueError("JWT secret must contain at least 32 bytes")
        self._secret = secret
        self._issuer = issuer
        self._audience = audience
        self._ttl_seconds = ttl_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    def issue(self, user_id: UUID) -> IssuedAccessToken:
        issued_at = self._clock()
        expires_at = issued_at + timedelta(seconds=self._ttl_seconds)
        payload = {
            "sub": str(user_id),
            "iat": issued_at,
            "exp": expires_at,
            "iss": self._issuer,
            "aud": self._audience,
            "type": "access",
        }
        return IssuedAccessToken(
            value=jwt.encode(payload, self._secret, algorithm=JWT_ALGORITHM),
            expires_in=self._ttl_seconds,
        )

    def verify(self, token: str) -> UUID:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[JWT_ALGORITHM],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["sub", "iat", "exp", "iss", "aud", "type"]},
            )
            if payload["type"] != "access":
                raise InvalidAccessTokenError
            return UUID(payload["sub"])
        except (KeyError, TypeError, ValueError, PyJWTError) as exc:
            raise InvalidAccessTokenError from exc
