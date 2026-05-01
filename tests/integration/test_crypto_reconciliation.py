# ruff: noqa: E501
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.base import Base
from app.db.models import Channel, CryptoInvoice, Payment, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.runtime_state import record_crypto_reconcile_run, reset_runtime_state
from app.services.crypto_admin import (
    build_crypto_reconciliation_summary,
    render_crypto_reconciliation_summary,
)


@pytest.fixture(autouse=True)
def runtime_state_fixture() -> AsyncIterator[None]:
    reset_runtime_state()
    yield
    reset_runtime_state()


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


async def test_crypto_reconciliation_summary_counts_expected_states(session: AsyncSession) -> None:
    user = User(telegram_id=42, first_name="Anna", is_admin=False, role="user")
    session.add(user)
    await session.flush()

    channel = Channel(
        telegram_chat_id=-1001234567890,
        title="�������� �����",
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

    session.add_all(
        [
            CryptoInvoice(
                user_id=user.id,
                tariff_id=tariff.id,
                external_id="cp-active",
                asset="TON",
                amount=Decimal("1.25"),
                status="active",
            ),
            CryptoInvoice(
                user_id=user.id,
                tariff_id=tariff.id,
                external_id="cp-paid-ok",
                asset="TON",
                amount=Decimal("1.25"),
                status="paid",
                paid_at=datetime(2026, 5, 1, 11, 0, tzinfo=UTC),
            ),
            CryptoInvoice(
                user_id=user.id,
                tariff_id=tariff.id,
                external_id="cp-paid-missing",
                asset="TON",
                amount=Decimal("1.25"),
                status="paid",
                paid_at=datetime(2026, 5, 1, 11, 10, tzinfo=UTC),
            ),
            CryptoInvoice(
                user_id=user.id,
                tariff_id=tariff.id,
                external_id="cp-expired",
                asset="TON",
                amount=Decimal("1.25"),
                status="expired",
            ),
        ]
    )
    await session.flush()

    session.add(
        Payment(
            user_id=user.id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            amount=125,
            currency="TON",
            provider="crypto_pay",
            telegram_payment_charge_id="crypto:invoice:cp-paid-ok",
            provider_payment_charge_id="cp-paid-ok",
            invoice_payload="payload:cp-paid-ok",
            paid_at=datetime(2026, 5, 1, 11, 0, tzinfo=UTC),
            status="paid",
        )
    )
    await session.commit()

    record_crypto_reconcile_run(
        processed_count=3,
        paid_count=1,
        expired_count=1,
        active_invoice_count=1,
        at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [1],
            "crypto_pay_enabled": True,
            "crypto_pay_webhook_path": "/crypto-pay/webhook",
            "timezone": "UTC",
        }
    )

    summary = await build_crypto_reconciliation_summary(session, settings)
    text = render_crypto_reconciliation_summary(summary, timezone="UTC")

    assert summary.active_count == 1
    assert summary.paid_activated_count == 1
    assert summary.paid_not_activated_count == 1
    assert summary.expired_count == 1
    assert "\u041e\u043f\u043b\u0430\u0447\u0435\u043d\u044b, \u043d\u043e \u043d\u0435 \u0430\u043a\u0442\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u043d\u044b: 1" in text
    assert "processed=3" in text
