import base64
import binascii
import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import jwt
from jwt import ExpiredSignatureError, PyJWTError

from app.core.exceptions import (
    ExpiredGroupInviteTokenError,
    GroupInviteMismatchError,
    InvalidGroupCursorError,
    InvalidGroupInviteTokenError,
)
from app.core.security import JWT_ALGORITHM, MINIMUM_SECRET_BYTES

GROUP_INVITE_TOKEN_TYPE = "group_invite"
GROUP_INVITE_TTL = timedelta(days=7)
CursorKind = Literal["group_list", "group_member_list"]


@dataclass(frozen=True, slots=True)
class IssuedGroupInviteToken:
    value: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class PageCursor:
    joined_at: datetime
    membership_id: UUID


class GroupInviteTokenService:
    """Issue JWTs that are cryptographically and semantically isolated from access tokens."""

    def __init__(
        self,
        *,
        secret: str,
        issuer: str,
        audience: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if len(secret.encode()) < MINIMUM_SECRET_BYTES:
            raise ValueError("JWT secret must contain at least 32 bytes")
        self._secret = secret
        self._issuer = issuer
        self._audience = f"{audience}:group-invite"
        self._clock = clock or (lambda: datetime.now(UTC))

    def issue(self, group_id: UUID) -> IssuedGroupInviteToken:
        issued_at = self._clock().astimezone(UTC).replace(microsecond=0)
        expires_at = issued_at + GROUP_INVITE_TTL
        payload = {
            "group_id": str(group_id),
            "iat": issued_at,
            "exp": expires_at,
            "iss": self._issuer,
            "aud": self._audience,
            "type": GROUP_INVITE_TOKEN_TYPE,
        }
        return IssuedGroupInviteToken(
            value=jwt.encode(payload, self._secret, algorithm=JWT_ALGORITHM),
            expires_at=expires_at,
        )

    def verify(self, token: str, *, expected_group_id: UUID) -> UUID:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[JWT_ALGORITHM],
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": ["group_id", "iat", "exp", "iss", "aud", "type"],
                },
            )
            if payload["type"] != GROUP_INVITE_TOKEN_TYPE:
                raise InvalidGroupInviteTokenError
            issued_at = payload["iat"]
            expires_at = payload["exp"]
            if not self._valid_timestamps(issued_at=issued_at, expires_at=expires_at):
                raise InvalidGroupInviteTokenError
            group_id = UUID(payload["group_id"])
        except ExpiredSignatureError as exc:
            raise ExpiredGroupInviteTokenError from exc
        except InvalidGroupInviteTokenError:
            raise
        except (KeyError, TypeError, ValueError, PyJWTError) as exc:
            raise InvalidGroupInviteTokenError from exc

        if group_id != expected_group_id:
            raise GroupInviteMismatchError
        return group_id

    @staticmethod
    def _valid_timestamps(*, issued_at: object, expires_at: object) -> bool:
        if (
            isinstance(issued_at, bool)
            or isinstance(expires_at, bool)
            or not isinstance(issued_at, (int, float))
            or not isinstance(expires_at, (int, float))
        ):
            return False
        lifetime = expires_at - issued_at
        return 0 < lifetime <= GROUP_INVITE_TTL.total_seconds()


class SignedCursorCodec:
    """Encode scoped keyset cursors whose contents cannot be modified by clients."""

    def __init__(self, *, secret: str) -> None:
        if len(secret.encode()) < MINIMUM_SECRET_BYTES:
            raise ValueError("JWT secret must contain at least 32 bytes")
        self._secret = secret.encode()

    def encode(self, cursor: PageCursor, *, kind: CursorKind, scope: str) -> str:
        payload = {
            "v": 1,
            "kind": kind,
            "scope": scope,
            "joined_at": cursor.joined_at.astimezone(UTC).isoformat(timespec="microseconds"),
            "membership_id": str(cursor.membership_id),
        }
        encoded_payload = self._base64_encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )
        signature = hmac.new(self._secret, encoded_payload.encode(), hashlib.sha256).digest()
        return f"{encoded_payload}.{self._base64_encode(signature)}"

    def decode(self, value: str, *, kind: CursorKind, scope: str) -> PageCursor:
        try:
            if len(value) > 2048:
                raise ValueError("cursor is too long")
            encoded_payload, encoded_signature = value.split(".")
            expected_signature = hmac.new(
                self._secret,
                encoded_payload.encode(),
                hashlib.sha256,
            ).digest()
            supplied_signature = self._base64_decode(encoded_signature)
            if not hmac.compare_digest(supplied_signature, expected_signature):
                raise ValueError("invalid cursor signature")

            payload = json.loads(self._base64_decode(encoded_payload))
            if not isinstance(payload, dict) or set(payload) != {
                "v",
                "kind",
                "scope",
                "joined_at",
                "membership_id",
            }:
                raise ValueError("invalid cursor payload")
            if payload["v"] != 1 or payload["kind"] != kind or payload["scope"] != scope:
                raise ValueError("cursor scope mismatch")
            joined_at = datetime.fromisoformat(payload["joined_at"])
            if joined_at.tzinfo is None or joined_at.utcoffset() is None:
                raise ValueError("cursor timestamp must be timezone-aware")
            membership_id = UUID(payload["membership_id"])
        except (
            AttributeError,
            binascii.Error,
            json.JSONDecodeError,
            TypeError,
            UnicodeDecodeError,
            ValueError,
        ) as exc:
            raise InvalidGroupCursorError from exc
        return PageCursor(
            joined_at=joined_at.astimezone(UTC),
            membership_id=membership_id,
        )

    @staticmethod
    def _base64_encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

    @staticmethod
    def _base64_decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.b64decode(value + padding, altchars=b"-_", validate=True)
