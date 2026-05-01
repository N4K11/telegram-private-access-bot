"""Add subscription warning and grace fields."""

import sqlalchemy as sa

from alembic import op

revision = "0003_subscription_grace_fields"
down_revision = "0002_promo_codes"
branch_labels = None
depends_on = None


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = _column_names(inspector, "subscriptions")

    if "warning_3d_sent_at" not in columns:
        op.add_column(
            "subscriptions",
            sa.Column("warning_3d_sent_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "warning_1d_sent_at" not in columns:
        op.add_column(
            "subscriptions",
            sa.Column("warning_1d_sent_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "expired_notice_sent_at" not in columns:
        op.add_column(
            "subscriptions",
            sa.Column("expired_notice_sent_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "grace_revoke_after" not in columns:
        op.add_column(
            "subscriptions",
            sa.Column("grace_revoke_after", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = _column_names(inspector, "subscriptions")

    if "grace_revoke_after" in columns:
        op.drop_column("subscriptions", "grace_revoke_after")
    if "expired_notice_sent_at" in columns:
        op.drop_column("subscriptions", "expired_notice_sent_at")
    if "warning_1d_sent_at" in columns:
        op.drop_column("subscriptions", "warning_1d_sent_at")
    if "warning_3d_sent_at" in columns:
        op.drop_column("subscriptions", "warning_3d_sent_at")
