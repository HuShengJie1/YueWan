from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, StringConstraints, field_validator

from app.models.proposal import Proposal

ProposalTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
]

_SENSITIVE_EXTERNAL_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "app_secret",
    "appsecret",
    "auth",
    "authentication",
    "authorization",
    "client_secret",
    "cookie",
    "credential",
    "credentials",
    "id_token",
    "password",
    "passwd",
    "private_key",
    "refresh_token",
    "secret",
    "session_key",
    "set_cookie",
    "token",
}
_COMPACT_SENSITIVE_EXTERNAL_KEYS = {
    "".join(character for character in key if character.isalnum())
    for key in _SENSITIVE_EXTERNAL_KEYS
}


def _normalize_optional_text(value: Any, *, field_name: str, max_length: int) -> Any:
    if value is None or not isinstance(value, str):
        return value
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must contain at most {max_length} characters")
    return normalized or None


def _contains_sensitive_key(value: JsonValue) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = key.strip().lower().replace("-", "_")
            compact_key = "".join(character for character in normalized_key if character.isalnum())
            if (
                normalized_key in _SENSITIVE_EXTERNAL_KEYS
                or compact_key in _COMPACT_SENSITIVE_EXTERNAL_KEYS
            ):
                return True
            if _contains_sensitive_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


class ProposalWrite(BaseModel):
    title: ProposalTitle
    description: str | None = None
    location_text: str | None = None
    external_platform: str | None = None
    external_url: str | None = None
    external_data: dict[str, JsonValue] | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: Any) -> Any:
        return _normalize_optional_text(value, field_name="description", max_length=500)

    @field_validator("location_text", mode="before")
    @classmethod
    def normalize_location_text(cls, value: Any) -> Any:
        return _normalize_optional_text(value, field_name="location_text", max_length=200)

    @field_validator("external_platform", mode="before")
    @classmethod
    def normalize_external_platform(cls, value: Any) -> Any:
        return _normalize_optional_text(value, field_name="external_platform", max_length=50)

    @field_validator("external_url", mode="before")
    @classmethod
    def validate_external_url(cls, value: Any) -> Any:
        normalized = _normalize_optional_text(value, field_name="external_url", max_length=2048)
        if normalized is None or not isinstance(normalized, str):
            return normalized
        try:
            parsed = urlsplit(normalized)
            hostname = parsed.hostname
        except ValueError as exc:
            raise ValueError("external_url must be a valid HTTP or HTTPS URL") from exc
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or hostname is None
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("external_url must be a valid HTTP or HTTPS URL")
        return normalized

    @field_validator("external_data")
    @classmethod
    def reject_sensitive_external_data(
        cls,
        value: dict[str, JsonValue] | None,
    ) -> dict[str, JsonValue] | None:
        if value is not None and _contains_sensitive_key(value):
            raise ValueError("external_data must not contain credentials or secrets")
        return value


class ProposalCreate(ProposalWrite):
    pass


class ProposalUpdate(ProposalWrite):
    pass


class ProposalRead(BaseModel):
    id: UUID
    hangout_id: UUID
    submitted_by_user_id: UUID
    title: str
    description: str | None
    location_text: str | None
    external_platform: str | None
    external_url: str | None
    external_data: dict[str, JsonValue] | None
    created_at: datetime
    updated_at: datetime
    can_manage: bool

    @classmethod
    def from_proposal(cls, proposal: Proposal, *, can_manage: bool) -> "ProposalRead":
        return cls(
            id=proposal.id,
            hangout_id=proposal.hangout_id,
            submitted_by_user_id=proposal.submitted_by_user_id,
            title=proposal.title,
            description=proposal.description,
            location_text=proposal.location_text,
            external_platform=proposal.external_platform,
            external_url=proposal.external_url,
            external_data=proposal.external_data,
            created_at=proposal.created_at,
            updated_at=proposal.updated_at,
            can_manage=can_manage,
        )

    @field_validator("created_at", "updated_at")
    @classmethod
    def serialize_dates_as_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class ProposalListData(BaseModel):
    items: list[ProposalRead]
    next_cursor: str | None
    has_more: bool
