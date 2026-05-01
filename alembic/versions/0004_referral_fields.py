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


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _fk_exists(inspector: sa.Inspector, table_name: str, fk_name: str) -> bool:
    return any(fk["name"] == fk_name for fk in inspector.get_foreign_keys(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = _column_names(inspector, "users")

    if "referral_code" not in columns:
        op.add_column("users", sa.Column("referral_code", sa.String(length=32), nullable=True))
    if "referred_by_user_id" not in columns:
        op.add_column("users", sa.Column("referred_by_user_id", sa.Integer(), nullable=True))
    if "referred_at" not in columns:
        op.add_column("users", sa.Column("referred_at", sa.DateTime(timezone=True), nullable=True))
    if "referral_reward_granted_at" not in columns:
        op.add_column(
            "users",
            sa.Column("referral_reward_granted_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "pending_referral_reward_days" not in columns:
        op.add_column(
            "users",
            sa.Column(
                "pending_referral_reward_days",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )

    inspector = sa.inspect(bind)
    if not _index_exists(inspector, "users", "ix_users_referred_by_user_id"):
        op.create_index(
            "ix_users_referred_by_user_id",
            "users",
            ["referred_by_user_id"],
            unique=False,
        )
    if not _index_exists(inspector, "users", "ix_users_referral_code"):
        op.create_index("ix_users_referral_code", "users", ["referral_code"], unique=True)

    if bind.dialect.name != "sqlite" and not _fk_exists(
        inspector,
        "users",
        "fk_users_referred_by_user_id_users",
    ):
        op.create_foreign_key(
            "fk_users_referred_by_user_id_users",
            "users",
            "users",
            ["referred_by_user_id"],
            ["id"],
        )

    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("telegram_id", sa.BigInteger()),
        sa.column("referral_code", sa.String(length=32)),
    )
    rows = bind.execute(
        sa.select(users.c.id, users.c.telegram_id).where(users.c.referral_code.is_(None))
    ).fetchall()
    for row in rows:
        bind.execute(
            users.update()
            .where(users.c.id == row.id)
            .values(referral_code=_build_referral_code(int(row.telegram_id)))
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = _column_names(inspector, "users")

    if bind.dialect.name != "sqlite" and _fk_exists(
        inspector,
        "users",
        "fk_users_referred_by_user_id_users",
    ):
        op.drop_constraint("fk_users_referred_by_user_id_users", "users", type_="foreignkey")
        inspector = sa.inspect(bind)
    if _index_exists(inspector, "users", "ix_users_referral_code"):
        op.drop_index("ix_users_referral_code", table_name="users")
    if _index_exists(inspector, "users", "ix_users_referred_by_user_id"):
        op.drop_index("ix_users_referred_by_user_id", table_name="users")
    if "pending_referral_reward_days" in columns:
        op.drop_column("users", "pending_referral_reward_days")
    if "referral_reward_granted_at" in columns:
        op.drop_column("users", "referral_reward_granted_at")
    if "referred_at" in columns:
        op.drop_column("users", "referred_at")
    if "referred_by_user_id" in columns:
        op.drop_column("users", "referred_by_user_id")
    if "referral_code" in columns:
        op.drop_column("users", "referral_code")
