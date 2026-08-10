from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import GroupMemberRole, GroupMemberStatus, enum_values


class Group(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "groups"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        Index("ix_groups_creator_created", "created_by_user_id", "created_at", "id"),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class GroupMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id"),
        CheckConstraint(
            "(status = 'active' AND left_at IS NULL) OR (status = 'left' AND left_at IS NOT NULL)",
            name="status_matches_left_at",
        ),
        Index("ix_group_members_user_status", "user_id", "status", "created_at", "id"),
    )

    group_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[GroupMemberRole] = mapped_column(
        Enum(
            GroupMemberRole,
            name="group_member_role",
            values_callable=enum_values,
            validate_strings=True,
        ),
        default=GroupMemberRole.MEMBER,
        server_default=GroupMemberRole.MEMBER.value,
        nullable=False,
    )
    status: Mapped[GroupMemberStatus] = mapped_column(
        Enum(
            GroupMemberStatus,
            name="group_member_status",
            values_callable=enum_values,
            validate_strings=True,
        ),
        default=GroupMemberStatus.ACTIVE,
        server_default=GroupMemberStatus.ACTIVE.value,
        nullable=False,
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
