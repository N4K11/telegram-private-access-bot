"""Add promo code tables."""

import sqlalchemy as sa

from alembic import op

revision = "0002_promo_codes"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "promo_codes"):
        op.create_table(
            "promo_codes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("promo_type", sa.String(length=32), nullable=False),
            sa.Column("value", sa.Integer(), nullable=False),
            sa.Column("max_uses", sa.Integer(), nullable=False),
            sa.Column("tariff_id", sa.Integer(), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.ForeignKeyConstraint(["tariff_id"], ["tariffs.id"]),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        )
        inspector = sa.inspect(bind)
    if _table_exists(inspector, "promo_codes") and not _index_exists(
        inspector,
        "promo_codes",
        "ix_promo_codes_code",
    ):
        op.create_index("ix_promo_codes_code", "promo_codes", ["code"], unique=True)

    if not _table_exists(inspector, "promo_redemptions"):
        op.create_table(
            "promo_redemptions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("promo_code_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("payment_id", sa.Integer(), nullable=True),
            sa.Column("applied_tariff_id", sa.Integer(), nullable=True),
            sa.Column("amount_before", sa.Integer(), nullable=True),
            sa.Column("amount_after", sa.Integer(), nullable=True),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
            sa.ForeignKeyConstraint(["applied_tariff_id"], ["tariffs.id"]),
            sa.UniqueConstraint(
                "promo_code_id",
                "user_id",
                name="uq_promo_redemption_promo_user",
            ),
        )
        inspector = sa.inspect(bind)
    if _table_exists(inspector, "promo_redemptions") and not _index_exists(
        inspector,
        "promo_redemptions",
        "ix_promo_redemptions_promo_code_id",
    ):
        op.create_index(
            "ix_promo_redemptions_promo_code_id",
            "promo_redemptions",
            ["promo_code_id"],
            unique=False,
        )
    if _table_exists(inspector, "promo_redemptions") and not _index_exists(
        inspector,
        "promo_redemptions",
        "ix_promo_redemptions_user_id",
    ):
        op.create_index(
            "ix_promo_redemptions_user_id",
            "promo_redemptions",
            ["user_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "promo_redemptions"):
        if _index_exists(inspector, "promo_redemptions", "ix_promo_redemptions_user_id"):
            op.drop_index("ix_promo_redemptions_user_id", table_name="promo_redemptions")
        if _index_exists(inspector, "promo_redemptions", "ix_promo_redemptions_promo_code_id"):
            op.drop_index("ix_promo_redemptions_promo_code_id", table_name="promo_redemptions")
        op.drop_table("promo_redemptions")
        inspector = sa.inspect(bind)

    if _table_exists(inspector, "promo_codes"):
        if _index_exists(inspector, "promo_codes", "ix_promo_codes_code"):
            op.drop_index("ix_promo_codes_code", table_name="promo_codes")
        op.drop_table("promo_codes")
