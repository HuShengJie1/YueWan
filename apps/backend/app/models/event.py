from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Event(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("hangout_id"),
        CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="valid_time_range"),
        Index("ix_events_proposal_id", "proposal_id"),
        Index("ix_events_time_option_id", "time_option_id"),
        Index("ix_events_confirmed_by_user_id", "confirmed_by_user_id"),
    )

    hangout_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hangouts.id", ondelete="CASCADE"), nullable=False
    )
    proposal_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("proposals.id", ondelete="SET NULL")
    )
    time_option_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("time_options.id", ondelete="SET NULL")
    )
    confirmed_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location_text: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
