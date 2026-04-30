from __future__ import annotations

from sqlalchemy import inspect

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.session import create_async_engine


async def test_metadata_creates_core_tables() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        table_names = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )

    await engine.dispose()

    expected = {
        "users",
        "channels",
        "tariffs",
        "subscriptions",
        "payments",
        "invite_links",
        "audit_logs",
        "text_templates",
        "broadcast_campaigns",
        "broadcast_deliveries",
        "backup_records",
        "crypto_invoices",
        "promo_codes",
        "promo_redemptions",
    }
    assert expected.issubset(set(table_names))
