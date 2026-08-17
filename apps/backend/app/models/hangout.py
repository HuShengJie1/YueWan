from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import MYSQL_TABLE_OPTIONS, UUID_COLUMN_TYPE, UTCDateTime
from app.models.enums import HangoutStatus, persisted_enum


class Hangout(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "hangouts"
    __table_args__ = (
        CheckConstraint("char_length(trim(title)) > 0", name="title_not_blank"),
        CheckConstraint(
            "status IN ('draft', 'voting', 'confirmed', 'cancelled', 'finished')",
            name="hangout_status",
        ),
        Index("ix_hangouts_group_status_created", "group_id", "status", "created_at", "id"),
        Index("ix_hangouts_group_created", "group_id", "created_at", "id"),
        Index("ix_hangouts_created_by_user_id", "created_by_user_id"),
        MYSQL_TABLE_OPTIONS,
    )

    group_id: Mapped[UUID] = mapped_column(
        UUID_COLUMN_TYPE, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        UUID_COLUMN_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[HangoutStatus] = mapped_column(
        persisted_enum(HangoutStatus, name="hangout_status"),
        default=HangoutStatus.DRAFT,
        server_default=HangoutStatus.DRAFT.value,
        nullable=False,
    )
    voting_deadline: Mapped[datetime | None] = mapped_column(UTCDateTime())
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
