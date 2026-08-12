from datetime import UTC, datetime
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.models.time_option import TimeOption


class TimeOptionWrite(BaseModel):
    starts_at: datetime
    ends_at: datetime | None = None
    display_label: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("starts_at")
    @classmethod
    def validate_starts_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("starts_at must include a timezone")
        normalized = value.astimezone(UTC)
        if normalized <= datetime.now(UTC):
            raise ValueError("starts_at must be in the future")
        return normalized

    @field_validator("ends_at")
    @classmethod
    def validate_ends_at_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ends_at must include a timezone")
        return value.astimezone(UTC)

    @field_validator("display_label", mode="before")
    @classmethod
    def normalize_display_label(cls, value: Any) -> Any:
        if value is None or not isinstance(value, str):
            return value
        normalized = value.strip()
        if len(normalized) > 80:
            raise ValueError("display_label must contain at most 80 characters")
        return normalized or None

    @model_validator(mode="after")
    def validate_time_range(self) -> Self:
        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return self


class TimeOptionCreate(TimeOptionWrite):
    pass


class TimeOptionUpdate(TimeOptionWrite):
    pass


class TimeOptionRead(BaseModel):
    id: UUID
    hangout_id: UUID
    created_by_user_id: UUID
    starts_at: datetime
    ends_at: datetime | None
    display_label: str | None
    created_at: datetime
    updated_at: datetime
    can_manage: bool

    @classmethod
    def from_time_option(
        cls,
        time_option: TimeOption,
        *,
        can_manage: bool,
    ) -> "TimeOptionRead":
        return cls(
            id=time_option.id,
            hangout_id=time_option.hangout_id,
            created_by_user_id=time_option.created_by_user_id,
            starts_at=time_option.starts_at,
            ends_at=time_option.ends_at,
            display_label=time_option.display_label,
            created_at=time_option.created_at,
            updated_at=time_option.updated_at,
            can_manage=can_manage,
        )

    @field_validator("starts_at", "ends_at", "created_at", "updated_at")
    @classmethod
    def serialize_dates_as_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.astimezone(UTC)


class TimeOptionListData(BaseModel):
    items: list[TimeOptionRead]
    next_cursor: str | None
    has_more: bool
