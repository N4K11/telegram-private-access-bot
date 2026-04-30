"""Add subscription warning and grace fields."""

import sqlalchemy as sa

from alembic import op

revision = "0003_subscription_grace_fields"
down_revision = "0002_promo_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("warning_3d_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("warning_1d_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("expired_notice_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("grace_revoke_after", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "grace_revoke_after")
    op.drop_column("subscriptions", "expired_notice_sent_at")
    op.drop_column("subscriptions", "warning_1d_sent_at")
    op.drop_column("subscriptions", "warning_3d_sent_at")
