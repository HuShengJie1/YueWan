"""Create the initial MVP business schema.

Revision ID: 20260809_0001
Revises:
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260809_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create users, groups, hangouts, voting, time options, and events."""
    bind = op.get_bind()
    postgresql.ENUM("owner", "member", name="group_member_role").create(bind)
    postgresql.ENUM("active", "left", name="group_member_status").create(bind)
    postgresql.ENUM(
        "draft", "voting", "confirmed", "cancelled", "finished", name="hangout_status"
    ).create(bind)
    postgresql.ENUM("LIKE", "OK", "DISLIKE", name="proposal_vote_value").create(bind)

    op.create_table(
        "users",
        sa.Column("wechat_openid", sa.Text(), nullable=False),
        sa.Column("wechat_unionid", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(display_name)) > 0", name=op.f("ck_users_display_name_not_blank")
        ),
        sa.CheckConstraint(
            "length(btrim(wechat_openid)) > 0",
            name=op.f("ck_users_wechat_openid_not_blank"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("wechat_openid", name="uq_users_wechat_openid"),
        sa.UniqueConstraint("wechat_unionid", name="uq_users_wechat_unionid"),
    )

    op.create_table(
        "groups",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(btrim(name)) > 0", name=op.f("ck_groups_name_not_blank")),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_groups_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_groups"),
    )
    op.create_index(
        "ix_groups_creator_created",
        "groups",
        ["created_by_user_id", "created_at", "id"],
        unique=False,
    )

    op.create_table(
        "group_members",
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("owner", "member", name="group_member_role", create_type=False),
            server_default=sa.text("'member'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM("active", "left", name="group_member_status", create_type=False),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'active' AND left_at IS NULL) OR (status = 'left' AND left_at IS NOT NULL)",
            name=op.f("ck_group_members_status_matches_left_at"),
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name="fk_group_members_group_id_groups",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_group_members_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_group_members"),
        sa.UniqueConstraint("group_id", "user_id", name="uq_group_members_group_id_user_id"),
    )
    op.create_index(
        "ix_group_members_user_status",
        "group_members",
        ["user_id", "status", "created_at", "id"],
        unique=False,
    )

    op.create_table(
        "hangouts",
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "draft",
                "voting",
                "confirmed",
                "cancelled",
                "finished",
                name="hangout_status",
                create_type=False,
            ),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column("voting_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(btrim(title)) > 0", name=op.f("ck_hangouts_title_not_blank")),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_hangouts_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name="fk_hangouts_group_id_groups",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hangouts"),
    )
    op.create_index(
        "ix_hangouts_created_by_user_id",
        "hangouts",
        ["created_by_user_id"],
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
        sa.Column("hangout_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitted_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location_text", sa.Text(), nullable=True),
        sa.Column("external_platform", sa.Text(), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("external_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(btrim(title)) > 0", name=op.f("ck_proposals_title_not_blank")),
        sa.ForeignKeyConstraint(
            ["hangout_id"],
            ["hangouts.id"],
            name="fk_proposals_hangout_id_hangouts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_user_id"],
            ["users.id"],
            name="fk_proposals_submitted_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_proposals"),
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
        "proposal_votes",
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "value",
            postgresql.ENUM("LIKE", "OK", "DISLIKE", name="proposal_vote_value", create_type=False),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["proposals.id"],
            name="fk_proposal_votes_proposal_id_proposals",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_proposal_votes_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_proposal_votes"),
        sa.UniqueConstraint("proposal_id", "user_id", name="uq_proposal_votes_proposal_id_user_id"),
    )
    op.create_index(
        "ix_proposal_votes_user_created",
        "proposal_votes",
        ["user_id", "created_at", "id"],
        unique=False,
    )

    op.create_table(
        "time_options",
        sa.Column("hangout_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("display_label", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "ends_at IS NULL OR ends_at > starts_at",
            name=op.f("ck_time_options_valid_time_range"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_time_options_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hangout_id"],
            ["hangouts.id"],
            name="fk_time_options_hangout_id_hangouts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_time_options"),
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
        "time_votes",
        sa.Column("time_option_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["time_option_id"],
            ["time_options.id"],
            name="fk_time_votes_time_option_id_time_options",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_time_votes_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_time_votes"),
        sa.UniqueConstraint(
            "time_option_id", "user_id", name="uq_time_votes_time_option_id_user_id"
        ),
    )
    op.create_index(
        "ix_time_votes_user_created",
        "time_votes",
        ["user_id", "created_at", "id"],
        unique=False,
    )

    op.create_table(
        "events",
        sa.Column("hangout_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("time_option_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location_text", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(btrim(title)) > 0", name=op.f("ck_events_title_not_blank")),
        sa.CheckConstraint(
            "ends_at IS NULL OR ends_at > starts_at",
            name=op.f("ck_events_valid_time_range"),
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_user_id"],
            ["users.id"],
            name="fk_events_confirmed_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hangout_id"],
            ["hangouts.id"],
            name="fk_events_hangout_id_hangouts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["proposals.id"],
            name="fk_events_proposal_id_proposals",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["time_option_id"],
            ["time_options.id"],
            name="fk_events_time_option_id_time_options",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_events"),
        sa.UniqueConstraint("hangout_id", name="uq_events_hangout_id"),
    )
    op.create_index(
        "ix_events_confirmed_by_user_id", "events", ["confirmed_by_user_id"], unique=False
    )
    op.create_index("ix_events_proposal_id", "events", ["proposal_id"], unique=False)
    op.create_index("ix_events_time_option_id", "events", ["time_option_id"], unique=False)


def downgrade() -> None:
    """Drop the initial MVP business schema."""
    op.drop_table("events")
    op.drop_table("time_votes")
    op.drop_table("time_options")
    op.drop_table("proposal_votes")
    op.drop_table("proposals")
    op.drop_table("hangouts")
    op.drop_table("group_members")
    op.drop_table("groups")
    op.drop_table("users")

    bind = op.get_bind()
    postgresql.ENUM("LIKE", "OK", "DISLIKE", name="proposal_vote_value").drop(bind)
    postgresql.ENUM(
        "draft", "voting", "confirmed", "cancelled", "finished", name="hangout_status"
    ).drop(bind)
    postgresql.ENUM("active", "left", name="group_member_status").drop(bind)
    postgresql.ENUM("owner", "member", name="group_member_role").drop(bind)
