from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.exceptions import (
    ExpiredGroupInviteTokenError,
    GroupInviteMismatchError,
    InvalidAccessTokenError,
    InvalidGroupCursorError,
    InvalidGroupInviteTokenError,
)
from app.core.group_security import (
    GROUP_INVITE_TOKEN_TYPE,
    GroupInviteTokenService,
    HangoutPageCursor,
    PageCursor,
    SignedCursorCodec,
)
from app.core.security import JWT_ALGORITHM, AccessTokenService

SECRET = "test-secret-that-is-at-least-32-bytes-long"
OTHER_SECRET = "different-secret-that-is-at-least-32-bytes"
ISSUER = "test-issuer"
AUDIENCE = "test-audience"


def invite_service(**overrides: object) -> GroupInviteTokenService:
    options: dict[str, object] = {
        "secret": SECRET,
        "issuer": ISSUER,
        "audience": AUDIENCE,
    }
    options.update(overrides)
    return GroupInviteTokenService(**options)  # type: ignore[arg-type]


def invite_payload(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "group_id": str(uuid4()),
        "iat": now,
        "exp": now + timedelta(days=7),
        "iss": ISSUER,
        "aud": f"{AUDIENCE}:group-invite",
        "type": GROUP_INVITE_TOKEN_TYPE,
    }
    payload.update(overrides)
    return payload


def test_group_invite_token_round_trip_and_seven_day_expiry() -> None:
    group_id = uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    service = invite_service(clock=lambda: now)

    issued = service.issue(group_id)

    assert issued.expires_at == now + timedelta(days=7)
    assert service.verify(issued.value, expected_group_id=group_id) == group_id


def test_group_invite_token_rejects_expired_token() -> None:
    now = datetime.now(UTC)
    payload = invite_payload(iat=now - timedelta(days=8), exp=now - timedelta(days=1))
    token = jwt.encode(payload, SECRET, algorithm=JWT_ALGORITHM)

    with pytest.raises(ExpiredGroupInviteTokenError):
        invite_service().verify(token, expected_group_id=uuid4())


@pytest.mark.parametrize(
    ("payload_override", "signing_secret"),
    [
        ({"type": "access"}, SECRET),
        ({"exp": datetime.now(UTC) + timedelta(days=8)}, SECRET),
        ({}, OTHER_SECRET),
    ],
)
def test_group_invite_token_rejects_wrong_type_lifetime_and_signature(
    payload_override: dict[str, object],
    signing_secret: str,
) -> None:
    group_id = uuid4()
    payload = invite_payload(group_id=str(group_id), **payload_override)
    token = jwt.encode(payload, signing_secret, algorithm=JWT_ALGORITHM)

    with pytest.raises(InvalidGroupInviteTokenError):
        invite_service().verify(token, expected_group_id=group_id)


def test_group_invite_token_rejects_group_id_mismatch() -> None:
    token_group_id = uuid4()
    token = invite_service().issue(token_group_id).value

    with pytest.raises(GroupInviteMismatchError):
        invite_service().verify(token, expected_group_id=uuid4())


def test_access_and_group_invite_tokens_are_not_interchangeable() -> None:
    group_id = uuid4()
    access_tokens = AccessTokenService(
        secret=SECRET,
        issuer=ISSUER,
        audience=AUDIENCE,
        ttl_seconds=7200,
    )
    invite_tokens = invite_service()

    with pytest.raises(InvalidGroupInviteTokenError):
        invite_tokens.verify(access_tokens.issue(uuid4()).value, expected_group_id=group_id)
    with pytest.raises(InvalidAccessTokenError):
        access_tokens.verify(invite_tokens.issue(group_id).value)


def test_signed_cursor_round_trip_is_scoped() -> None:
    codec = SignedCursorCodec(secret=SECRET)
    cursor = PageCursor(joined_at=datetime.now(UTC), membership_id=uuid4())

    encoded = codec.encode(cursor, kind="group_list", scope="user:one")

    assert codec.decode(encoded, kind="group_list", scope="user:one") == cursor
    with pytest.raises(InvalidGroupCursorError):
        codec.decode(encoded, kind="group_list", scope="user:two")
    with pytest.raises(InvalidGroupCursorError):
        codec.decode(encoded, kind="group_member_list", scope="user:one")


def test_hangout_cursor_is_group_scoped_and_kind_isolated() -> None:
    codec = SignedCursorCodec(secret=SECRET)
    cursor = HangoutPageCursor(created_at=datetime.now(UTC), hangout_id=uuid4())

    encoded = codec.encode(cursor, kind="hangout_list", scope="group:one")

    assert codec.decode(encoded, kind="hangout_list", scope="group:one") == cursor
    with pytest.raises(InvalidGroupCursorError):
        codec.decode(encoded, kind="hangout_list", scope="group:two")
    with pytest.raises(InvalidGroupCursorError):
        codec.decode(encoded, kind="group_list", scope="group:one")


@pytest.mark.parametrize("cursor", ["invalid", "a.b.c", "payload.signature-tampered"])
def test_signed_cursor_rejects_malformed_or_tampered_values(cursor: str) -> None:
    with pytest.raises(InvalidGroupCursorError):
        SignedCursorCodec(secret=SECRET).decode(cursor, kind="group_list", scope="user:one")
