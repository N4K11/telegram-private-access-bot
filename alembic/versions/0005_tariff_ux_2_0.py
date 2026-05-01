"""tariff ux 2.0 fields

Revision ID: 0005_tariff_ux_2_0
Revises: 0004_referral_fields
Create Date: 2026-05-01 20:30:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_tariff_ux_2_0"
down_revision = "0004_referral_fields"
branch_labels = None
depends_on = None


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = _column_names(inspector, "tariffs")

    if "description" not in columns:
        op.add_column("tariffs", sa.Column("description", sa.Text(), nullable=True))
    if "badge" not in columns:
        op.add_column("tariffs", sa.Column("badge", sa.String(length=64), nullable=True))
    if "is_trial" not in columns:
        op.add_column(
            "tariffs",
            sa.Column("is_trial", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "is_lifetime" not in columns:
        op.add_column(
            "tariffs",
            sa.Column("is_lifetime", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "crypto_price_amount" not in columns:
        op.add_column(
            "tariffs",
            sa.Column("crypto_price_amount", sa.Numeric(12, 2), nullable=True),
        )
    if "crypto_asset" not in columns:
        op.add_column("tariffs", sa.Column("crypto_asset", sa.String(length=32), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = _column_names(inspector, "tariffs")

    if "crypto_asset" in columns:
        op.drop_column("tariffs", "crypto_asset")
    if "crypto_price_amount" in columns:
        op.drop_column("tariffs", "crypto_price_amount")
    if "is_lifetime" in columns:
        op.drop_column("tariffs", "is_lifetime")
    if "is_trial" in columns:
        op.drop_column("tariffs", "is_trial")
    if "badge" in columns:
        op.drop_column("tariffs", "badge")
    if "description" in columns:
        op.drop_column("tariffs", "description")
