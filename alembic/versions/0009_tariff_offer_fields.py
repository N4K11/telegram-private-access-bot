"""Add offer metadata fields to tariffs.

Revision ID: 0009_tariff_offer_fields
Revises: 0008_user_onboarding
Create Date: 2026-05-03 17:30:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0009_tariff_offer_fields"
down_revision = "0008_user_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tariffs",
        sa.Column("offer_copy", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "tariffs",
        sa.Column("offer_group", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "tariffs",
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "tariffs",
        sa.Column("is_default_offer", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("tariffs", "is_default_offer")
    op.drop_column("tariffs", "is_featured")
    op.drop_column("tariffs", "offer_group")
    op.drop_column("tariffs", "offer_copy")