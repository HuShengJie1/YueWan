from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from app.models.enums import HangoutStatus
from app.models.hangout import Hangout

HangoutTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=60),
]


class HangoutWrite(BaseModel):
    title: HangoutTitle
    description: str | None = None
    voting_deadline: datetime | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: Any) -> Any:
        if value is None or not isinstance(value, str):
            return value
        normalized = value.strip()
        if len(normalized) > 500:
            raise ValueError("description must contain at most 500 characters")
        return normalized or None

    @field_validator("voting_deadline")
    @classmethod
    def validate_voting_deadline(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("voting_deadline must include a timezone")
        normalized = value.astimezone(UTC)
        if normalized <= datetime.now(UTC):
            raise ValueError("voting_deadline must be in the future")
        return normalized


class HangoutCreate(HangoutWrite):
    pass


class HangoutUpdate(HangoutWrite):
    pass


class HangoutRead(BaseModel):
    id: UUID
    group_id: UUID
    created_by_user_id: UUID
    title: str
    description: str | None
    status: HangoutStatus
    voting_deadline: datetime | None
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_hangout(cls, hangout: Hangout) -> "HangoutRead":
        return cls.model_validate(hangout)

    @field_validator(
        "voting_deadline",
        "confirmed_at",
        "cancelled_at",
        "created_at",
        "updated_at",
    )
    @classmethod
    def serialize_dates_as_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.astimezone(UTC)


class HangoutListData(BaseModel):
    items: list[HangoutRead]
    next_cursor: str | None
    has_more: bool
