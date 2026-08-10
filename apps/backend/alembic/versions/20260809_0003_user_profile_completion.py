"""Track whether a user has completed their profile.

Revision ID: 20260809_0003
Revises: 20260809_0002
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260809_0003"
down_revision: str | Sequence[str] | None = "20260809_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add profile completion state and preserve existing completed profiles."""
    op.add_column(
        "users",
        sa.Column("profile_completed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute(sa.text("UPDATE users SET profile_completed = true"))


def downgrade() -> None:
    """Remove profile completion state."""
    op.drop_column("users", "profile_completed")
