"""add admin read model snapshots

Revision ID: 0012_admin_read_model_snapshots
Revises: 0011_support_operator_fields
Create Date: 2026-05-06 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0012_admin_read_model_snapshots"
down_revision = "0011_support_operator_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_daily_facts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fact_date", sa.Date(), nullable=False),
        sa.Column("fact_key", sa.String(length=64), nullable=False),
        sa.Column("scope_key", sa.String(length=64), nullable=False, server_default="all"),
        sa.Column("product_channel_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["product_channel_id"], ["channels.id"]),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analytics_daily_facts")),
        sa.UniqueConstraint(
            "fact_date",
            "fact_key",
            "scope_key",
            name="uq_analytics_daily_fact_scope",
        ),
    )
    op.create_index(
        "ix_analytics_daily_facts_fact_date",
        "analytics_daily_facts",
        ["fact_date"],
        unique=False,
    )
    op.create_index(
        "ix_analytics_daily_facts_product_channel_id",
        "analytics_daily_facts",
        ["product_channel_id"],
        unique=False,
    )
    op.create_index(
        "ix_analytics_daily_facts_fact_key_generated_at",
        "analytics_daily_facts",
        ["fact_key", "generated_at"],
        unique=False,
    )

    op.create_table(
        "lifecycle_campaign_facts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("view_key", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lifecycle_campaign_facts")),
        sa.UniqueConstraint("view_key", name="uq_lifecycle_campaign_fact_view_key"),
    )
    op.create_index(
        "ix_lifecycle_campaign_facts_view_key",
        "lifecycle_campaign_facts",
        ["view_key"],
        unique=False,
    )
    op.create_index(
        "ix_lifecycle_campaign_facts_generated_at",
        "lifecycle_campaign_facts",
        ["generated_at"],
        unique=False,
    )

    op.create_table(
        "support_queue_facts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("view_key", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_queue_facts")),
        sa.UniqueConstraint("view_key", name="uq_support_queue_fact_view_key"),
    )
    op.create_index(
        "ix_support_queue_facts_view_key",
        "support_queue_facts",
        ["view_key"],
        unique=False,
    )
    op.create_index(
        "ix_support_queue_facts_generated_at",
        "support_queue_facts",
        ["generated_at"],
        unique=False,
    )

    op.create_index(
        "ix_audit_logs_action_created_at_target_user_id",
        "audit_logs",
        ["action", "created_at", "target_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_payments_status_paid_at_user_id_channel_id",
        "payments",
        ["status", "paid_at", "user_id", "channel_id"],
        unique=False,
    )
    op.create_index(
        "ix_support_tickets_status_priority_updated_at_user_id",
        "support_tickets",
        ["status", "priority", "updated_at", "user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_support_tickets_status_priority_updated_at_user_id",
        table_name="support_tickets",
    )
    op.drop_index("ix_payments_status_paid_at_user_id_channel_id", table_name="payments")
    op.drop_index(
        "ix_audit_logs_action_created_at_target_user_id",
        table_name="audit_logs",
    )

    op.drop_index("ix_support_queue_facts_generated_at", table_name="support_queue_facts")
    op.drop_index("ix_support_queue_facts_view_key", table_name="support_queue_facts")
    op.drop_table("support_queue_facts")

    op.drop_index(
        "ix_lifecycle_campaign_facts_generated_at",
        table_name="lifecycle_campaign_facts",
    )
    op.drop_index("ix_lifecycle_campaign_facts_view_key", table_name="lifecycle_campaign_facts")
    op.drop_table("lifecycle_campaign_facts")

    op.drop_index(
        "ix_analytics_daily_facts_fact_key_generated_at",
        table_name="analytics_daily_facts",
    )
    op.drop_index(
        "ix_analytics_daily_facts_product_channel_id",
        table_name="analytics_daily_facts",
    )
    op.drop_index("ix_analytics_daily_facts_fact_date", table_name="analytics_daily_facts")
    op.drop_table("analytics_daily_facts")
