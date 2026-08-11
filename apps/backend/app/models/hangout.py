from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import HangoutStatus, enum_values


class Hangout(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "hangouts"
    __table_args__ = (
        CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
        Index("ix_hangouts_group_status_created", "group_id", "status", "created_at", "id"),
        Index("ix_hangouts_group_created", "group_id", "created_at", "id"),
        Index("ix_hangouts_created_by_user_id", "created_by_user_id"),
    )

    group_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[HangoutStatus] = mapped_column(
        Enum(
            HangoutStatus,
            name="hangout_status",
            values_callable=enum_values,
            validate_strings=True,
        ),
        default=HangoutStatus.DRAFT,
        server_default=HangoutStatus.DRAFT.value,
        nullable=False,
    )
    voting_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
