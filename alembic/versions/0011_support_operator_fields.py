"""add support operator fields

Revision ID: 0011_support_operator_fields
Revises: 0010_tariff_limited_offer_expiry
Create Date: 2026-05-05 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011_support_operator_fields"
down_revision = "0010_tariff_limited_offer_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "support_tickets",
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal"),
    )
    op.add_column(
        "support_tickets",
        sa.Column("close_reason", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("support_tickets", "close_reason")
    op.drop_column("support_tickets", "priority")
