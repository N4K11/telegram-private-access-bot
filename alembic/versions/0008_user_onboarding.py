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


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = _column_names(inspector, "users")

    if "onboarding_step" not in columns:
        op.add_column(
            "users",
            sa.Column("onboarding_step", sa.Integer(), nullable=False, server_default="0"),
        )
    if "onboarding_completed_at" not in columns:
        op.add_column(
            "users",
            sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
        )

    op.execute(
        "UPDATE users SET onboarding_completed_at = COALESCE(onboarding_completed_at, created_at, CURRENT_TIMESTAMP)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = _column_names(inspector, "users")

    if "onboarding_completed_at" in columns:
        op.drop_column("users", "onboarding_completed_at")
    if "onboarding_step" in columns:
        op.drop_column("users", "onboarding_step")