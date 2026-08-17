from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import MYSQL_TABLE_OPTIONS, UUID_COLUMN_TYPE, UTCDateTime


class Event(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("hangout_id"),
        CheckConstraint("char_length(trim(title)) > 0", name="title_not_blank"),
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="valid_time_range"),
        Index("ix_events_proposal_id", "proposal_id"),
        Index("ix_events_time_option_id", "time_option_id"),
        Index("ix_events_confirmed_by_user_id", "confirmed_by_user_id"),
        MYSQL_TABLE_OPTIONS,
    )

    hangout_id: Mapped[UUID] = mapped_column(
        UUID_COLUMN_TYPE, ForeignKey("hangouts.id", ondelete="CASCADE"), nullable=False
    )
    proposal_id: Mapped[UUID | None] = mapped_column(
        UUID_COLUMN_TYPE, ForeignKey("proposals.id", ondelete="SET NULL")
    )
    time_option_id: Mapped[UUID | None] = mapped_column(
        UUID_COLUMN_TYPE, ForeignKey("time_options.id", ondelete="SET NULL")
    )
    confirmed_by_user_id: Mapped[UUID] = mapped_column(
        UUID_COLUMN_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    location_text: Mapped[str | None] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
