"""Persist onboarding progress for new users.

Revision ID: 0008_user_onboarding
Revises: 0007_support_tickets
Create Date: 2026-05-02 14:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0008_user_onboarding"
down_revision = "0007_support_tickets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("onboarding_step", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE users SET onboarding_completed_at = COALESCE(created_at, CURRENT_TIMESTAMP)"
    )


def downgrade() -> None:
    op.drop_column("users", "onboarding_completed_at")
    op.drop_column("users", "onboarding_step")