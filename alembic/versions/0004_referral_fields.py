"""Add referral fields to users."""

import sqlalchemy as sa

from alembic import op

revision = "0004_referral_fields"
down_revision = "0003_subscription_grace_fields"
branch_labels = None
depends_on = None

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _encode_base36(value: int) -> str:
    if value == 0:
        return "0"

    digits: list[str] = []
    current = value
    while current:
        current, remainder = divmod(current, 36)
        digits.append(ALPHABET[remainder])
    return "".join(reversed(digits))


def _build_referral_code(telegram_id: int) -> str:
    return f"R{_encode_base36(int(telegram_id))}"


def upgrade() -> None:
    op.add_column("users", sa.Column("referral_code", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("referred_by_user_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("referred_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("referral_reward_granted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "pending_referral_reward_days",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index("ix_users_referred_by_user_id", "users", ["referred_by_user_id"], unique=False)
    op.create_index("ix_users_referral_code", "users", ["referral_code"], unique=True)
    op.create_foreign_key(
        "fk_users_referred_by_user_id_users",
        "users",
        "users",
        ["referred_by_user_id"],
        ["id"],
    )

    bind = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("telegram_id", sa.BigInteger()),
        sa.column("referral_code", sa.String(length=32)),
    )
    rows = bind.execute(sa.select(users.c.id, users.c.telegram_id)).fetchall()
    for row in rows:
        bind.execute(
            users.update()
            .where(users.c.id == row.id)
            .values(referral_code=_build_referral_code(int(row.telegram_id)))
        )


def downgrade() -> None:
    op.drop_constraint("fk_users_referred_by_user_id_users", "users", type_="foreignkey")
    op.drop_index("ix_users_referral_code", table_name="users")
    op.drop_index("ix_users_referred_by_user_id", table_name="users")
    op.drop_column("users", "pending_referral_reward_days")
    op.drop_column("users", "referral_reward_granted_at")
    op.drop_column("users", "referred_at")
    op.drop_column("users", "referred_by_user_id")
    op.drop_column("users", "referral_code")
