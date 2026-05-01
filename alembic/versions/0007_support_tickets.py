"""Support tickets and threaded messages.

Revision ID: 0007_support_tickets
Revises: 0006_promo_system_2_0
Create Date: 2026-05-02 01:20:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_support_tickets"
down_revision = "0006_promo_system_2_0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("last_user_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_admin_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_user_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["closed_by_user_id"],
            ["users.id"],
            name=op.f("fk_support_tickets_closed_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_support_tickets_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_tickets")),
    )
    op.create_index(
        op.f("ix_support_tickets_user_id"),
        "support_tickets",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_support_tickets_status"),
        "support_tickets",
        ["status"],
        unique=False,
    )

    op.create_table(
        "support_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["sender_user_id"],
            ["users.id"],
            name=op.f("fk_support_messages_sender_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["support_tickets.id"],
            name=op.f("fk_support_messages_ticket_id_support_tickets"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_messages")),
    )
    op.create_index(
        op.f("ix_support_messages_ticket_id"),
        "support_messages",
        ["ticket_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_support_messages_sender_user_id"),
        "support_messages",
        ["sender_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_support_messages_sender_user_id"), table_name="support_messages")
    op.drop_index(op.f("ix_support_messages_ticket_id"), table_name="support_messages")
    op.drop_table("support_messages")
    op.drop_index(op.f("ix_support_tickets_status"), table_name="support_tickets")
    op.drop_index(op.f("ix_support_tickets_user_id"), table_name="support_tickets")
    op.drop_table("support_tickets")
