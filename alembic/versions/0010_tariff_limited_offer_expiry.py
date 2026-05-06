"""add tariff limited offer expiry

Revision ID: 0010_tariff_limited_offer_expiry
Revises: 0009_tariff_offer_fields
Create Date: 2026-05-04 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0010_tariff_limited_offer_expiry"
down_revision = "0009_tariff_offer_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tariffs",
        sa.Column("offer_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tariffs", "offer_expires_at")
