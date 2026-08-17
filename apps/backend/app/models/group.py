from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import MYSQL_TABLE_OPTIONS, UUID_COLUMN_TYPE, UTCDateTime
from app.models.enums import GroupMemberRole, GroupMemberStatus, persisted_enum


class Group(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "groups"
    __table_args__ = (
        CheckConstraint("char_length(trim(name)) > 0", name="name_not_blank"),
        Index("ix_groups_creator_created", "created_by_user_id", "created_at", "id"),
        MYSQL_TABLE_OPTIONS,
    )

    name: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200))
    created_by_user_id: Mapped[UUID] = mapped_column(
        UUID_COLUMN_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class GroupMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id"),
        CheckConstraint(
            "(status = 'active' AND left_at IS NULL) OR (status = 'left' AND left_at IS NOT NULL)",
            name="status_matches_left_at",
        ),
        CheckConstraint("role IN ('owner', 'member')", name="group_member_role"),
        CheckConstraint("status IN ('active', 'left')", name="group_member_status"),
        Index("ix_group_members_user_status", "user_id", "status", "created_at", "id"),
        MYSQL_TABLE_OPTIONS,
    )

    group_id: Mapped[UUID] = mapped_column(
        UUID_COLUMN_TYPE, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID_COLUMN_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[GroupMemberRole] = mapped_column(
        persisted_enum(GroupMemberRole, name="group_member_role"),
        default=GroupMemberRole.MEMBER,
        server_default=GroupMemberRole.MEMBER.value,
        nullable=False,
    )
    status: Mapped[GroupMemberStatus] = mapped_column(
        persisted_enum(GroupMemberStatus, name="group_member_status"),
        default=GroupMemberStatus.ACTIVE,
        server_default=GroupMemberStatus.ACTIVE.value,
        nullable=False,
    )
    left_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
