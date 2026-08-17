"""Create the MySQL baseline schema.

Revision ID: 20260815_0001
Revises:
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260815_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all MVP tables on MySQL 8."""
    op.create_table(
        "users",
        sa.Column(
            "wechat_openid",
            sa.String(length=128, collation="utf8mb4_0900_bin"),
            nullable=False,
        ),
        sa.Column(
            "wechat_unionid",
            sa.String(length=128, collation="utf8mb4_0900_bin"),
            nullable=True,
        ),
        sa.Column("display_name", sa.String(length=24), nullable=False),
        sa.Column("avatar_url", sa.String(length=2048), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("profile_completed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_login_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(trim(display_name)) > 0",
            name=op.f("ck_users_display_name_not_blank"),
        ),
        sa.CheckConstraint(
            "char_length(trim(wechat_openid)) > 0",
            name=op.f("ck_users_wechat_openid_not_blank"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("wechat_openid", name=op.f("uq_users_wechat_openid")),
        sa.UniqueConstraint("wechat_unionid", name=op.f("uq_users_wechat_unionid")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )

    op.create_table(
        "groups",
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column("id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.CheckConstraint("char_length(trim(name)) > 0", name=op.f("ck_groups_name_not_blank")),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_groups_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_groups")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_groups_creator_created",
        "groups",
        ["created_by_user_id", "created_at", "id"],
        unique=False,
    )

    op.create_table(
        "group_members",
        sa.Column("group_id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "owner",
                "member",
                name="group_member_role",
                native_enum=False,
                create_constraint=False,
                length=6,
            ),
            server_default="member",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "left",
                name="group_member_status",
                native_enum=False,
                create_constraint=False,
                length=6,
            ),
            server_default="active",
            nullable=False,
        ),
        sa.Column("left_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'active' AND left_at IS NULL) OR (status = 'left' AND left_at IS NOT NULL)",
            name=op.f("ck_group_members_status_matches_left_at"),
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'member')",
            name=op.f("ck_group_members_group_member_role"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'left')",
            name=op.f("ck_group_members_group_member_status"),
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name=op.f("fk_group_members_group_id_groups"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_group_members_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_group_members")),
        sa.UniqueConstraint(
            "group_id",
            "user_id",
            name=op.f("uq_group_members_group_id_user_id"),
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_group_members_user_status",
        "group_members",
        ["user_id", "status", "created_at", "id"],
        unique=False,
    )

    op.create_table(
        "hangouts",
        sa.Column("group_id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column("title", sa.String(length=60), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "voting",
                "confirmed",
                "cancelled",
                "finished",
                name="hangout_status",
                native_enum=False,
                create_constraint=False,
                length=9,
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("voting_deadline", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("confirmed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("cancelled_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(trim(title)) > 0", name=op.f("ck_hangouts_title_not_blank")
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'voting', 'confirmed', 'cancelled', 'finished')",
            name=op.f("ck_hangouts_hangout_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_hangouts_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name=op.f("fk_hangouts_group_id_groups"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hangouts")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_hangouts_created_by_user_id",
        "hangouts",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_hangouts_group_created",
        "hangouts",
        ["group_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_hangouts_group_status_created",
        "hangouts",
        ["group_id", "status", "created_at", "id"],
        unique=False,
    )

    op.create_table(
        "proposals",
        sa.Column("hangout_id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column("submitted_by_user_id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("location_text", sa.String(length=200), nullable=True),
        sa.Column("external_platform", sa.String(length=50), nullable=True),
        sa.Column("external_url", sa.String(length=2048), nullable=True),
        sa.Column("external_data", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(trim(title)) > 0", name=op.f("ck_proposals_title_not_blank")
        ),
        sa.ForeignKeyConstraint(
            ["hangout_id"],
            ["hangouts.id"],
            name=op.f("fk_proposals_hangout_id_hangouts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_user_id"],
            ["users.id"],
            name=op.f("fk_proposals_submitted_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proposals")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_proposals_hangout_created",
        "proposals",
        ["hangout_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_proposals_submitted_by_user_id",
        "proposals",
        ["submitted_by_user_id"],
        unique=False,
    )

    op.create_table(
        "time_options",
        sa.Column("hangout_id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column("starts_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("ends_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("display_label", sa.String(length=80), nullable=True),
        sa.Column("id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "ends_at IS NULL OR ends_at > starts_at",
            name=op.f("ck_time_options_valid_time_range"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_time_options_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hangout_id"],
            ["hangouts.id"],
            name=op.f("fk_time_options_hangout_id_hangouts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_time_options")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_time_options_created_by_user_id",
        "time_options",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_time_options_hangout_starts",
        "time_options",
        ["hangout_id", "starts_at", "id"],
        unique=False,
    )

    op.create_table(
        "events",
        sa.Column("hangout_id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column("proposal_id", sa.Uuid(native_uuid=False), nullable=True),
        sa.Column("time_option_id", sa.Uuid(native_uuid=False), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("location_text", sa.String(length=200), nullable=True),
        sa.Column("starts_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("ends_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.CheckConstraint("char_length(trim(title)) > 0", name=op.f("ck_events_title_not_blank")),
        sa.CheckConstraint(
            "ends_at IS NULL OR ends_at > starts_at",
            name=op.f("ck_events_valid_time_range"),
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_user_id"],
            ["users.id"],
            name=op.f("fk_events_confirmed_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hangout_id"],
            ["hangouts.id"],
            name=op.f("fk_events_hangout_id_hangouts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["proposals.id"],
            name=op.f("fk_events_proposal_id_proposals"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["time_option_id"],
            ["time_options.id"],
            name=op.f("fk_events_time_option_id_time_options"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
        sa.UniqueConstraint("hangout_id", name=op.f("uq_events_hangout_id")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_events_confirmed_by_user_id",
        "events",
        ["confirmed_by_user_id"],
        unique=False,
    )
    op.create_index("ix_events_proposal_id", "events", ["proposal_id"], unique=False)
    op.create_index("ix_events_time_option_id", "events", ["time_option_id"], unique=False)

    op.create_table(
        "proposal_votes",
        sa.Column("proposal_id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column(
            "value",
            sa.Enum(
                "LIKE",
                "OK",
                "DISLIKE",
                name="proposal_vote_value",
                native_enum=False,
                create_constraint=False,
                length=7,
            ),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "value IN ('LIKE', 'OK', 'DISLIKE')",
            name=op.f("ck_proposal_votes_proposal_vote_value"),
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["proposals.id"],
            name=op.f("fk_proposal_votes_proposal_id_proposals"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_proposal_votes_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proposal_votes")),
        sa.UniqueConstraint(
            "proposal_id",
            "user_id",
            name=op.f("uq_proposal_votes_proposal_id_user_id"),
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_proposal_votes_user_created",
        "proposal_votes",
        ["user_id", "created_at", "id"],
        unique=False,
    )

    op.create_table(
        "time_votes",
        sa.Column("time_option_id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column("id", sa.Uuid(native_uuid=False), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["time_option_id"],
            ["time_options.id"],
            name=op.f("fk_time_votes_time_option_id_time_options"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_time_votes_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_time_votes")),
        sa.UniqueConstraint(
            "time_option_id",
            "user_id",
            name=op.f("uq_time_votes_time_option_id_user_id"),
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_time_votes_user_created",
        "time_votes",
        ["user_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop all MVP tables in dependency order."""
    op.drop_index("ix_time_votes_user_created", table_name="time_votes")
    op.drop_table("time_votes")
    op.drop_index("ix_proposal_votes_user_created", table_name="proposal_votes")
    op.drop_table("proposal_votes")
    op.drop_index("ix_events_time_option_id", table_name="events")
    op.drop_index("ix_events_proposal_id", table_name="events")
    op.drop_index("ix_events_confirmed_by_user_id", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_time_options_hangout_starts", table_name="time_options")
    op.drop_index("ix_time_options_created_by_user_id", table_name="time_options")
    op.drop_table("time_options")
    op.drop_index("ix_proposals_submitted_by_user_id", table_name="proposals")
    op.drop_index("ix_proposals_hangout_created", table_name="proposals")
    op.drop_table("proposals")
    op.drop_index("ix_hangouts_group_status_created", table_name="hangouts")
    op.drop_index("ix_hangouts_group_created", table_name="hangouts")
    op.drop_index("ix_hangouts_created_by_user_id", table_name="hangouts")
    op.drop_table("hangouts")
    op.drop_index("ix_group_members_user_status", table_name="group_members")
    op.drop_table("group_members")
    op.drop_index("ix_groups_creator_created", table_name="groups")
    op.drop_table("groups")
    op.drop_table("users")
