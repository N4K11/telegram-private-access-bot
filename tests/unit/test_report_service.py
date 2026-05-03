from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.base import Base
from app.db.models import Channel, Payment, Subscription, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.runtime_state import record_critical_error, reset_runtime_state
from app.services.report_service import (
    DAILY_REPORT_LABEL,
    REPORT_PERIOD_DAILY,
    REPORT_PERIOD_WEEKLY,
    WEEKLY_REPORT_LABEL,
    build_admin_report,
    dispatch_scheduled_admin_reports,
    render_admin_report,
)


class FakeBot:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent_messages.append((chat_id, text))


@pytest.fixture(autouse=True)
def runtime_reset() -> None:
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


async def _seed_report_data(session: AsyncSession, *, now: datetime) -> None:
    user = User(
        telegram_id=1001,
        first_name="Anna",
        created_at=now - timedelta(hours=3),
    )
    channel = Channel(
        telegram_chat_id=-1001234567890,
        title="Private channel",
        username="private_channel_demo",
        invite_users_permission=True,
        ban_users_permission=True,
    )
    session.add_all([user, channel])
    await session.flush()

    tariff = Tariff(
        name="Base",
        price_stars=150,
        price_crypto=Decimal("3.50"),
        crypto_price_amount=Decimal("3.50"),
        crypto_asset="USDT",
        duration_days=30,
        sort_order=10,
        channel_id=channel.id,
    )
    session.add(tariff)
    await session.flush()

    session.add(
        Subscription(
            user_id=user.id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            status="active",
            source="purchase",
            started_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=5),
        )
    )
    session.add(
        Payment(
            user_id=user.id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            amount=150,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="report-charge-1",
            provider_payment_charge_id="report-provider-1",
            invoice_payload="subscription:1001:30",
            paid_at=now - timedelta(hours=1),
            status="paid",
        )
    )
    session.add(
        Payment(
            user_id=user.id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            amount=350,
            currency="USDT",
            provider="crypto_pay",
            telegram_payment_charge_id=None,
            provider_payment_charge_id="report-provider-2",
            invoice_payload="crypto:1001:30",
            paid_at=now - timedelta(hours=2),
            status="paid",
        )
    )
    await session.commit()


async def test_daily_report_generated(session: AsyncSession) -> None:
    now = datetime(2026, 5, 3, 9, 5, tzinfo=UTC)
    await _seed_report_data(session, now=now)
    record_critical_error(
        "worker_cycle_failed",
        "broadcast failed",
        source="scheduler",
        at=now - timedelta(minutes=5),
    )

    report = await build_admin_report(
        session,
        period=REPORT_PERIOD_DAILY,
        timezone="UTC",
        now=now,
    )
    text = render_admin_report(report, timezone="UTC")

    assert report.new_users == 1
    assert report.payments_count == 2
    assert report.stars_revenue == 150
    assert report.crypto_revenue == {"USDT": Decimal("3.5")}
    assert report.active_subscriptions == 1
    assert report.anomalies == 1
    assert DAILY_REPORT_LABEL in text
    assert "Stars: 150" in text
    assert "Crypto: 3.5 USDT" in text


async def test_weekly_report_generated(session: AsyncSession) -> None:
    now = datetime(2026, 5, 4, 9, 10, tzinfo=UTC)
    await _seed_report_data(session, now=now)

    report = await build_admin_report(
        session,
        period=REPORT_PERIOD_WEEKLY,
        timezone="UTC",
        now=now,
    )
    text = render_admin_report(report, timezone="UTC")

    assert report.period == REPORT_PERIOD_WEEKLY
    assert WEEKLY_REPORT_LABEL in text
    assert report.payments_count == 2


async def test_empty_db_report_works(session: AsyncSession) -> None:
    now = datetime(2026, 5, 3, 9, 0, tzinfo=UTC)
    report = await build_admin_report(
        session,
        period=REPORT_PERIOD_DAILY,
        timezone="UTC",
        now=now,
    )
    text = render_admin_report(report, timezone="UTC")

    assert report.new_users == 0
    assert report.payments_count == 0
    assert report.stars_revenue == 0
    assert report.crypto_revenue == {}
    assert "Crypto: 0" in text


async def test_no_duplicate_daily_report(session: AsyncSession) -> None:
    now = datetime(2026, 5, 3, 9, 15, tzinfo=UTC)
    await _seed_report_data(session, now=now)
    bot = FakeBot()
    settings = Settings.model_validate(
        {"bot_token": "123:token", "admin_ids": [42], "timezone": "UTC"}
    )

    first = await dispatch_scheduled_admin_reports(session, bot, settings, now=now)
    second = await dispatch_scheduled_admin_reports(session, bot, settings, now=now)

    assert first.sent_periods == ("daily",)
    assert second.sent_periods == ()
    assert len(bot.sent_messages) == 1


async def test_weekly_report_is_sent_on_monday(session: AsyncSession) -> None:
    now = datetime(2026, 5, 4, 9, 20, tzinfo=UTC)
    await _seed_report_data(session, now=now)
    bot = FakeBot()
    settings = Settings.model_validate(
        {"bot_token": "123:token", "admin_ids": [42], "timezone": "UTC"}
    )

    result = await dispatch_scheduled_admin_reports(session, bot, settings, now=now)

    assert result.sent_periods == ("daily", "weekly")
    assert len(bot.sent_messages) == 2
    assert any(WEEKLY_REPORT_LABEL in text for _, text in bot.sent_messages)


async def test_reports_are_sent_to_admins_only(session: AsyncSession) -> None:
    now = datetime(2026, 5, 3, 9, 20, tzinfo=UTC)
    await _seed_report_data(session, now=now)
    bot = FakeBot()
    settings = Settings.model_validate(
        {"bot_token": "123:token", "admin_ids": [42, 77], "timezone": "UTC"}
    )

    result = await dispatch_scheduled_admin_reports(session, bot, settings, now=now)

    assert result.sent_periods == ("daily",)
    assert {chat_id for chat_id, _ in bot.sent_messages} == {42, 77}
