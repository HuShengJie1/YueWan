from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import MYSQL_TABLE_OPTIONS, UUID_COLUMN_TYPE, UTCDateTime


class TimeOption(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "time_options"
    __table_args__ = (
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="valid_time_range"),
        Index("ix_time_options_hangout_starts", "hangout_id", "starts_at", "id"),
        Index("ix_time_options_created_by_user_id", "created_by_user_id"),
        MYSQL_TABLE_OPTIONS,
    )

    hangout_id: Mapped[UUID] = mapped_column(
        UUID_COLUMN_TYPE, ForeignKey("hangouts.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        UUID_COLUMN_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    display_label: Mapped[str | None] = mapped_column(String(80))


class TimeVote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "time_votes"
    __table_args__ = (
        UniqueConstraint("time_option_id", "user_id"),
        Index("ix_time_votes_user_created", "user_id", "created_at", "id"),
        MYSQL_TABLE_OPTIONS,
    )

    time_option_id: Mapped[UUID] = mapped_column(
        UUID_COLUMN_TYPE, ForeignKey("time_options.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID_COLUMN_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
