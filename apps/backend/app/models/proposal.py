from typing import Any
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import MYSQL_TABLE_OPTIONS, UUID_COLUMN_TYPE
from app.models.enums import ProposalVoteValue, persisted_enum


class Proposal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "proposals"
    __table_args__ = (
        CheckConstraint("char_length(trim(title)) > 0", name="title_not_blank"),
        Index("ix_proposals_hangout_created", "hangout_id", "created_at", "id"),
        Index("ix_proposals_submitted_by_user_id", "submitted_by_user_id"),
        MYSQL_TABLE_OPTIONS,
    )

    hangout_id: Mapped[UUID] = mapped_column(
        UUID_COLUMN_TYPE, ForeignKey("hangouts.id", ondelete="CASCADE"), nullable=False
    )
    submitted_by_user_id: Mapped[UUID] = mapped_column(
        UUID_COLUMN_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    location_text: Mapped[str | None] = mapped_column(String(200))
    external_platform: Mapped[str | None] = mapped_column(String(50))
    external_url: Mapped[str | None] = mapped_column(String(2048))
    external_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ProposalVote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "proposal_votes"
    __table_args__ = (
        UniqueConstraint("proposal_id", "user_id"),
        CheckConstraint("value IN ('LIKE', 'OK', 'DISLIKE')", name="proposal_vote_value"),
        Index("ix_proposal_votes_user_created", "user_id", "created_at", "id"),
        MYSQL_TABLE_OPTIONS,
    )

    proposal_id: Mapped[UUID] = mapped_column(
        UUID_COLUMN_TYPE, ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID_COLUMN_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    value: Mapped[ProposalVoteValue] = mapped_column(
        persisted_enum(ProposalVoteValue, name="proposal_vote_value"),
        nullable=False,
    )
