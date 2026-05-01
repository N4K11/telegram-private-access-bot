# ruff: noqa: E501
from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.base import Base
from app.db.models import AuditLog, Channel, CryptoInvoice, Payment, Subscription, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.webhook.server import build_webhook_app


@pytest_asyncio.fixture
async def crypto_webhook_runtime(tmp_path: Path) -> AsyncIterator[tuple[TestClient, Settings, async_sessionmaker[AsyncSession], int]]:
    database_path = tmp_path / "crypto-webhook.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        user = User(telegram_id=42, first_name="Anna", is_admin=False, role="user")
        session.add(user)
        await session.flush()

        channel = Channel(
            telegram_chat_id=-1001234567890,
            title="\u041e\u0441\u043d\u043e\u0432\u043d\u043e\u0439 \u043a\u0430\u043d\u0430\u043b",
            invite_users_permission=True,
            ban_users_permission=True,
            is_active=True,
        )
        session.add(channel)
        await session.flush()

        tariff = Tariff(
            name="VIP 30",
            price_stars=250,
            price_crypto=Decimal("1.25"),
            duration_days=30,
            sort_order=10,
            is_active=True,
            channel_id=channel.id,
        )
        session.add(tariff)
        await session.flush()

        invoice = CryptoInvoice(
            user_id=user.id,
            tariff_id=tariff.id,
            external_id="cp-202",
            asset="TON",
            amount=Decimal("1.25"),
            invoice_url="https://pay.example/cp-202",
            status="active",
            expires_at=datetime(2026, 5, 1, 15, 0, tzinfo=UTC),
            raw_payload="{}",
        )
        session.add(invoice)
        await session.commit()
        invoice_id = invoice.id

    settings = Settings.model_validate(
        {
            "bot_token": "123456789:token",
            "admin_ids": [1],
            "database_url": f"sqlite+aiosqlite:///{database_path.as_posix()}",
            "backup_directory": str(tmp_path / "backups"),
            "use_webhook": True,
            "public_webhook_url": "https://example.com",
            "webhook_secret_token": "telegram-secret",
            "webhook_path": "/telegram/webhook",
            "crypto_pay_enabled": True,
            "crypto_pay_token": "crypto-token",
            "crypto_pay_webhook_path": "/crypto-pay/webhook",
        }
    )
    bot = Bot(
        token="123456789:token",
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    app = build_webhook_app(
        bot=bot,
        dispatcher=Dispatcher(),
        settings=settings,
        session_factory=session_factory,
    )
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        yield client, settings, session_factory, invoice_id
    finally:
        await client.close()
        await bot.session.close()
        await engine.dispose()


def _paid_payload() -> dict[str, object]:
    return {
        "update_type": "invoice_paid",
        "payload": {
            "invoice_id": "cp-202",
            "status": "paid",
            "asset": "TON",
            "amount": "1.25",
            "payload": "crypto:tariff:1:user:1:ts:1714550400",
            "paid_at": "2026-05-01T12:05:00+00:00",
            "expiration_date": "2026-05-01T15:00:00+00:00",
        },
    }


def _signature(body: bytes, token: str) -> str:
    secret = hashlib.sha256(token.encode("utf-8")).digest()
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


async def test_crypto_webhook_paid_payload_activates_once(
    crypto_webhook_runtime: tuple[TestClient, Settings, async_sessionmaker[AsyncSession], int],
) -> None:
    client, settings, session_factory, invoice_id = crypto_webhook_runtime
    body = json.dumps(_paid_payload(), separators=(",", ":")).encode("utf-8")
    signature = _signature(body, settings.crypto_pay_token.get_secret_value())

    first = await client.post(
        settings.crypto_pay_webhook_path,
        data=body,
        headers={"crypto-pay-api-signature": signature, "Content-Type": "application/json"},
    )
    second = await client.post(
        settings.crypto_pay_webhook_path,
        data=body,
        headers={"crypto-pay-api-signature": signature, "Content-Type": "application/json"},
    )

    assert first.status == 200
    assert await first.json() == {"ok": True, "handled": True}
    assert second.status == 200
    assert await second.json() == {"ok": True, "handled": True}

    async with session_factory() as session:
        payments = list((await session.execute(select(Payment))).scalars())
        subscriptions = list((await session.execute(select(Subscription))).scalars())
        invoice = await session.get(CryptoInvoice, invoice_id)
        audit_actions = [record.action for record in (await session.execute(select(AuditLog))).scalars()]

    assert len(payments) == 1
    assert len(subscriptions) == 1
    assert invoice is not None
    assert invoice.status == "paid"
    assert "crypto_invoice_paid" in audit_actions
    assert "crypto_subscription_activated" in audit_actions
    assert "crypto_invoice_duplicate" in audit_actions


async def test_crypto_webhook_rejects_invalid_signature(
    crypto_webhook_runtime: tuple[TestClient, Settings, async_sessionmaker[AsyncSession], int],
) -> None:
    client, settings, session_factory, _ = crypto_webhook_runtime
    body = json.dumps(_paid_payload(), separators=(",", ":")).encode("utf-8")

    response = await client.post(
        settings.crypto_pay_webhook_path,
        data=body,
        headers={"crypto-pay-api-signature": "bad-signature", "Content-Type": "application/json"},
    )

    assert response.status == 401
    assert await response.json() == {"ok": False, "error": "unauthorized"}

    async with session_factory() as session:
        payments = list((await session.execute(select(Payment))).scalars())

    assert payments == []