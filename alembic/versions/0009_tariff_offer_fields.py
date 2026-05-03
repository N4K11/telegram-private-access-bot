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


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = _column_names(inspector, "tariffs")

    if "offer_copy" not in columns:
        op.add_column(
            "tariffs",
            sa.Column("offer_copy", sa.String(length=160), nullable=True),
        )
    if "offer_group" not in columns:
        op.add_column(
            "tariffs",
            sa.Column("offer_group", sa.String(length=64), nullable=True),
        )
    if "is_featured" not in columns:
        op.add_column(
            "tariffs",
            sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "is_default_offer" not in columns:
        op.add_column(
            "tariffs",
            sa.Column("is_default_offer", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = _column_names(inspector, "tariffs")

    if "is_default_offer" in columns:
        op.drop_column("tariffs", "is_default_offer")
    if "is_featured" in columns:
        op.drop_column("tariffs", "is_featured")
    if "offer_group" in columns:
        op.drop_column("tariffs", "offer_group")
    if "offer_copy" in columns:
        op.drop_column("tariffs", "offer_copy")