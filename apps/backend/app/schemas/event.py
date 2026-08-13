from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.event import Event


class EventConfirm(BaseModel):
    proposal_id: UUID
    time_option_id: UUID

    model_config = ConfigDict(extra="forbid")


class EventRead(BaseModel):
    id: UUID
    hangout_id: UUID
    proposal_id: UUID | None
    time_option_id: UUID | None
    confirmed_by_user_id: UUID
    title: str
    description: str | None
    location_text: str | None
    starts_at: datetime
    ends_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_event(cls, event: Event) -> "EventRead":
        return cls.model_validate(event, from_attributes=True)

    @field_validator("starts_at", "ends_at", "created_at", "updated_at")
    @classmethod
    def serialize_dates_as_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.astimezone(UTC)
