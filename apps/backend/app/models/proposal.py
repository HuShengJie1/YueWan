from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ProposalVoteValue, enum_values


class Proposal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "proposals"
    __table_args__ = (
        CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
        Index("ix_proposals_hangout_created", "hangout_id", "created_at", "id"),
        Index("ix_proposals_submitted_by_user_id", "submitted_by_user_id"),
    )

    hangout_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hangouts.id", ondelete="CASCADE"), nullable=False
    )
    submitted_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location_text: Mapped[str | None] = mapped_column(Text)
    external_platform: Mapped[str | None] = mapped_column(Text)
    external_url: Mapped[str | None] = mapped_column(Text)
    external_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class ProposalVote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "proposal_votes"
    __table_args__ = (
        UniqueConstraint("proposal_id", "user_id"),
        Index("ix_proposal_votes_user_created", "user_id", "created_at", "id"),
    )

    proposal_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    value: Mapped[ProposalVoteValue] = mapped_column(
        Enum(
            ProposalVoteValue,
            name="proposal_vote_value",
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
