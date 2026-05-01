"""Promo system 2.0 fields and per-user reuse support.

Revision ID: 0006_promo_system_2_0
Revises: 0005_tariff_ux_2_0
Create Date: 2026-05-01 23:30:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_promo_system_2_0"
down_revision = "0005_tariff_ux_2_0"
branch_labels = None
depends_on = None


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _unique_constraint_exists(
    inspector: sa.Inspector,
    table_name: str,
    constraint_name: str,
) -> bool:
    return any(
        constraint["name"] == constraint_name
        for constraint in inspector.get_unique_constraints(table_name)
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = _column_names(inspector, "promo_codes")

    if "valid_from" not in columns:
        op.add_column(
            "promo_codes",
            sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        )
    if "valid_until" not in columns:
        op.add_column(
            "promo_codes",
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        )
    if "first_purchase_only" not in columns:
        op.add_column(
            "promo_codes",
            sa.Column(
                "first_purchase_only",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    if "per_user_limit" not in columns:
        op.add_column(
            "promo_codes",
            sa.Column("per_user_limit", sa.Integer(), nullable=True),
        )
    if "campaign_name" not in columns:
        op.add_column(
            "promo_codes",
            sa.Column("campaign_name", sa.String(length=128), nullable=True),
        )
    if "notes" not in columns:
        op.add_column("promo_codes", sa.Column("notes", sa.Text(), nullable=True))

    inspector = sa.inspect(bind)
    if not _index_exists(inspector, "promo_codes", "ix_promo_codes_campaign_name"):
        op.create_index(
            "ix_promo_codes_campaign_name",
            "promo_codes",
            ["campaign_name"],
            unique=False,
        )

    if _unique_constraint_exists(
        inspector,
        "promo_redemptions",
        "uq_promo_redemption_promo_user",
    ):
        with op.batch_alter_table("promo_redemptions", recreate="always") as batch_op:
            batch_op.drop_constraint("uq_promo_redemption_promo_user", type_="unique")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _unique_constraint_exists(
        inspector,
        "promo_redemptions",
        "uq_promo_redemption_promo_user",
    ):
        with op.batch_alter_table("promo_redemptions", recreate="always") as batch_op:
            batch_op.create_unique_constraint(
                "uq_promo_redemption_promo_user",
                ["promo_code_id", "user_id"],
            )
        inspector = sa.inspect(bind)

    if _index_exists(inspector, "promo_codes", "ix_promo_codes_campaign_name"):
        op.drop_index("ix_promo_codes_campaign_name", table_name="promo_codes")

    columns = _column_names(inspector, "promo_codes")
    if "notes" in columns:
        op.drop_column("promo_codes", "notes")
    if "campaign_name" in columns:
        op.drop_column("promo_codes", "campaign_name")
    if "per_user_limit" in columns:
        op.drop_column("promo_codes", "per_user_limit")
    if "first_purchase_only" in columns:
        op.drop_column("promo_codes", "first_purchase_only")
    if "valid_until" in columns:
        op.drop_column("promo_codes", "valid_until")
    if "valid_from" in columns:
        op.drop_column("promo_codes", "valid_from")
