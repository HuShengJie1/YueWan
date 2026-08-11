"""Add the cross-status hangout list index.

Revision ID: 20260810_0004
Revises: 20260809_0003
Create Date: 2026-08-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260810_0004"
down_revision: str | Sequence[str] | None = "20260809_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Support stable cross-status hangout keyset pagination."""
    op.create_index(
        "ix_hangouts_group_created",
        "hangouts",
        ["group_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the cross-status hangout list index."""
    op.drop_index("ix_hangouts_group_created", table_name="hangouts")
