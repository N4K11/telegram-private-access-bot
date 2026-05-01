# ruff: noqa: E501
from __future__ import annotations

import csv
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import (
    AuditLog,
    Channel,
    CryptoInvoice,
    Payment,
    PromoCode,
    PromoRedemption,
    Tariff,
    User,
)
from app.db.session import create_async_engine, create_session_factory
from app.services.finance import (
    PERIOD_ALL,
    PERIOD_DAY,
    PERIOD_MONTH,
    build_finance_report_csv,
    build_finance_snapshot,
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


async def test_finance_snapshot_handles_empty_database(session: AsyncSession) -> None:
    snapshot = await build_finance_snapshot(session, now=datetime(2026, 5, 1, 12, 0, tzinfo=UTC))

    assert snapshot.periods[PERIOD_DAY].stars_revenue == 0
    assert snapshot.periods[PERIOD_ALL].crypto_revenue == {}
    assert snapshot.unpaid_crypto_invoices == 0
    assert snapshot.expired_crypto_invoices == 0
    assert snapshot.top_tariffs == []

    report = build_finance_report_csv(snapshot, period=PERIOD_ALL, timezone="UTC").decode("utf-8")
    assert "summary,stars_revenue,all,telegram_stars,Stars,0" in report


async def test_finance_snapshot_counts_revenue_and_non_revenue_events(session: AsyncSession) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    stars_user = User(telegram_id=1001, first_name="Anna", role="user")
    crypto_user = User(telegram_id=1002, first_name="Ivan", role="user")
    referred_user = User(
        telegram_id=1003,
        first_name="Kate",
        role="user",
        referral_reward_granted_at=now,
    )
    session.add_all([stars_user, crypto_user, referred_user])
    await session.flush()

    channel = Channel(
        telegram_chat_id=-1001234567890,
        title="Main channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add(channel)
    await session.flush()

    stars_tariff = Tariff(
        name="VIP 30",
        price_stars=250,
        price_crypto=Decimal("1.25"),
        duration_days=30,
        sort_order=10,
        is_active=True,
        channel_id=channel.id,
    )
    crypto_tariff = Tariff(
        name="VIP 90",
        price_stars=400,
        price_crypto=Decimal("2.50"),
        duration_days=90,
        sort_order=20,
        is_active=True,
        channel_id=channel.id,
    )
    session.add_all([stars_tariff, crypto_tariff])
    await session.flush()

    session.add_all(
        [
            Payment(
                user_id=stars_user.id,
                tariff_id=stars_tariff.id,
                channel_id=channel.id,
                amount=250,
                currency="Stars",
                provider="telegram_stars",
                telegram_payment_charge_id="tg-stars-1",
                provider_payment_charge_id="provider-stars-1",
                invoice_payload="stars:tariff:1",
                paid_at=now,
                status="paid",
            ),
            Payment(
                user_id=stars_user.id,
                tariff_id=stars_tariff.id,
                channel_id=channel.id,
                amount=400,
                currency="Stars",
                provider="telegram_stars",
                telegram_payment_charge_id="tg-stars-2",
                provider_payment_charge_id="provider-stars-2",
                invoice_payload="stars:tariff:1",
                paid_at=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
                status="paid",
            ),
            Payment(
                user_id=crypto_user.id,
                tariff_id=crypto_tariff.id,
                channel_id=channel.id,
                amount=125,
                currency="TON",
                provider="crypto_pay",
                telegram_payment_charge_id="crypto:invoice:cp-1",
                provider_payment_charge_id="cp-1",
                invoice_payload="crypto:tariff:2:user:2:ts:1",
                paid_at=now,
                status="paid",
            ),
            Payment(
                user_id=stars_user.id,
                tariff_id=stars_tariff.id,
                channel_id=channel.id,
                amount=999,
                currency="Stars",
                provider="telegram_stars",
                telegram_payment_charge_id="tg-refund-1",
                provider_payment_charge_id="provider-refund-1",
                invoice_payload="stars:tariff:1",
                paid_at=now,
                status="refunded",
            ),
        ]
    )
    session.add_all(
        [
            CryptoInvoice(
                user_id=crypto_user.id,
                tariff_id=crypto_tariff.id,
                external_id="active-1",
                asset="TON",
                amount=Decimal("1.25"),
                status="active",
                expires_at=datetime(2026, 5, 1, 13, 0, tzinfo=UTC),
            ),
            CryptoInvoice(
                user_id=crypto_user.id,
                tariff_id=crypto_tariff.id,
                external_id="expired-1",
                asset="TON",
                amount=Decimal("1.25"),
                status="expired",
                expires_at=datetime(2026, 4, 30, 13, 0, tzinfo=UTC),
            ),
        ]
    )
    session.add(AuditLog(action="admin_subscription_granted", target_user_id=stars_user.id))

    promo = PromoCode(
        code="FREE7",
        promo_type="free_days",
        value=7,
        max_uses=10,
        tariff_id=stars_tariff.id,
        is_active=True,
        created_by_user_id=stars_user.id,
    )
    session.add(promo)
    await session.flush()
    session.add(
        PromoRedemption(
            promo_code_id=promo.id,
            user_id=stars_user.id,
            status="consumed",
            applied_tariff_id=stars_tariff.id,
            used_at=now,
        )
    )
    await session.commit()

    snapshot = await build_finance_snapshot(session, now=now)

    assert snapshot.periods[PERIOD_DAY].stars_revenue == 250
    assert snapshot.periods[PERIOD_DAY].stars_payment_count == 1
    assert snapshot.periods[PERIOD_DAY].crypto_revenue == {"TON": Decimal("1.25")}
    assert snapshot.periods[PERIOD_MONTH].stars_revenue == 650
    assert snapshot.periods[PERIOD_ALL].stars_payment_count == 2
    assert snapshot.periods[PERIOD_ALL].crypto_payment_count == 1
    assert snapshot.unpaid_crypto_invoices == 1
    assert snapshot.expired_crypto_invoices == 1
    assert snapshot.refunds_count == 1
    assert snapshot.manual_recoveries_count == 1
    assert snapshot.promo_free_days_count == 1
    assert snapshot.referral_rewards_count == 1
    assert snapshot.stars_average_revenue_per_user == Decimal("650.00")
    assert snapshot.crypto_average_revenue_per_user == {"TON": Decimal("1.25")}
    assert snapshot.top_tariffs[0].tariff_name == "VIP 30"
    assert snapshot.top_tariffs[0].payment_count == 2

    report_bytes = build_finance_report_csv(snapshot, period=PERIOD_MONTH, timezone="UTC")
    report_text = report_bytes.decode("utf-8")
    parsed = list(csv.reader(StringIO(report_text)))

    assert any(row[:3] == ["summary", "stars_revenue", "month"] and row[-1] == "650" for row in parsed)
    assert any(row[:2] == ["payments", "1"] for row in parsed)
    assert "invoice_payload" not in report_text
    assert "https://t.me/+" not in report_text

