from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.base import Base
from app.db.models import BackupRecord, Channel, Payment, Subscription, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.runtime_state import (
    mark_started,
    record_maintenance_run,
    record_telegram_api_error,
    record_update,
    reset_runtime_state,
)
from app.services.admin_read_model_reporting import (
    AdminReadModelDriftSummary,
    AdminReadModelWatchlistSummary,
)
from app.services.health_service import (
    StoreProbeResult,
    build_admin_health_report,
    render_admin_health_report,
)


class FakeBot:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error

    async def get_me(self):
        if self.error is not None:
            raise self.error
        return SimpleNamespace(id=500, username="health_bot")


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


async def _seed_health_data(session: AsyncSession, *, now: datetime) -> None:
    user = User(telegram_id=755815181, first_name="Admin", is_admin=True, role="owner")
    session.add(user)
    await session.flush()

    channel = Channel(
        telegram_chat_id=-1001234567890,
        title="Основной канал",
        username="main_channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add(channel)
    await session.flush()

    tariff = Tariff(
        name="VIP 30",
        price_stars=250,
        duration_days=30,
        sort_order=10,
        is_active=True,
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
            started_at=now - timedelta(days=2),
            expires_at=now + timedelta(days=5),
        )
    )
    session.add(
        Payment(
            user_id=user.id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            amount=250,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="charge-health",
            provider_payment_charge_id="provider-health",
            invoice_payload="subscription:755815181:30",
            paid_at=now - timedelta(hours=1),
            status="paid",
        )
    )
    session.add(
        BackupRecord(
            file_name="daily-backup-20260501-030000.zip",
            file_path="/tmp/daily-backup-20260501-030000.zip",
            status="created",
            created_at=now - timedelta(hours=6),
        )
    )
    await session.commit()


async def test_health_service_builds_happy_path_report(session: AsyncSession) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    await _seed_health_data(session, now=now)
    mark_started(now=now - timedelta(hours=2, minutes=15))
    record_update(update_id=321, kind="Message", at=now - timedelta(minutes=1))
    record_maintenance_run(label="background_workers", at=now - timedelta(minutes=2))

    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "database_url": "sqlite+aiosqlite:///:memory:",
            "timezone": "UTC",
            "backup_enabled": True,
        }
    )

    report = await build_admin_health_report(session, FakeBot(), settings, now=now)
    text = render_admin_health_report(report)

    assert report.summary_ok is True
    assert "✅ Бот подключен: @health_bot" in text
    assert "✅ Каналы настроены: 1 активных / 1 всего" in text
    assert "ℹ️ Пользователи: 1" in text
    assert "ℹ️ Активные подписки: 1" in text
    assert "ℹ️ Платежей сегодня: 1" in text
    assert "⚠️ Read-model snapshots: ещё не материализованы" in text
    assert "<code>321</code>" in text
    assert "background_workers" in text
    assert "01.05.2026 06:00" in text
    assert "Итог: всё работает штатно." in text


async def test_health_service_reports_bot_error_and_missing_channels(
    session: AsyncSession,
) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    mark_started(now=now - timedelta(minutes=5))

    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "database_url": "sqlite+aiosqlite:///:memory:",
            "timezone": "UTC",
        }
    )

    report = await build_admin_health_report(
        session,
        FakeBot(error=RuntimeError("telegram unavailable")),
        settings,
        now=now,
    )
    text = render_admin_health_report(report)

    assert report.summary_ok is False
    assert "❌ Бот подключен: telegram unavailable" in text
    assert "❌ Каналы настроены: нет активных каналов в базе" in text
    assert "Итог: есть проблемы, проверьте строки с ❌." in text


async def test_health_service_reports_store_not_writable(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    await _seed_health_data(session, now=now)
    mark_started(now=now - timedelta(minutes=30))

    async def fake_probe(_session: AsyncSession) -> StoreProbeResult:
        return StoreProbeResult(readable=True, writable=False, write_error="read only")

    monkeypatch.setattr("app.services.health_service._probe_store_health", fake_probe)

    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "database_url": "sqlite+aiosqlite:///:memory:",
            "timezone": "UTC",
        }
    )

    report = await build_admin_health_report(session, FakeBot(), settings, now=now)
    text = render_admin_health_report(report)

    assert report.summary_ok is False
    assert "✅ Хранилище: чтение: OK" in text
    assert "❌ Хранилище: запись: read only" in text
    assert "ℹ️ Пользователи: 1" in text


async def test_health_service_includes_last_telegram_error(session: AsyncSession) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    await _seed_health_data(session, now=now)
    mark_started(now=now - timedelta(minutes=30))
    record_telegram_api_error(
        "TelegramBadRequest: chat not found",
        at=now - timedelta(minutes=4),
    )

    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "database_url": "sqlite+aiosqlite:///:memory:",
            "timezone": "UTC",
        }
    )

    report = await build_admin_health_report(session, FakeBot(), settings, now=now)
    text = render_admin_health_report(report)

    assert "⚠️ Последняя Telegram API ошибка:" in text
    assert "01.05.2026 11:56" in text
    assert "TelegramBadRequest: chat not found" in text


async def test_health_service_includes_read_model_drift_metric(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    await _seed_health_data(session, now=now)
    mark_started(now=now - timedelta(minutes=30))

    async def fake_build_drift_summary(*args, **kwargs) -> AdminReadModelDriftSummary:
        return AdminReadModelDriftSummary(
            source="live",
            generated_at_label="01.05.2026 12:00",
            staleness_seconds=0,
            compared_count=3,
            missing_snapshot_count=0,
            regression_count=2,
            improvement_count=0,
            budget_regression_count=1,
            query_regression_count=1,
            payload_regression_count=1,
            build_regression_count=0,
            top_regression_label="Pricing / Offers",
            top_regression_note="Live build drifted above snapshot baseline.",
            top_budget_regression_label="Support insights",
            top_query_regression_label="Pricing / Offers",
            top_payload_regression_label="Support insights",
            top_build_regression_label=None,
            top_items=(),
        )

    monkeypatch.setattr(
        "app.services.health_service.build_admin_read_model_drift_summary",
        fake_build_drift_summary,
    )

    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "database_url": "sqlite+aiosqlite:///:memory:",
            "timezone": "UTC",
        }
    )

    report = await build_admin_health_report(session, FakeBot(), settings, now=now)
    text = render_admin_health_report(report)

    assert "⚠️ Read-model drift:" in text
    assert "regressions 2" in text
    assert "top Pricing / Offers" in text


async def test_health_service_includes_read_model_watchlist_metric(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    await _seed_health_data(session, now=now)
    mark_started(now=now - timedelta(minutes=30))

    async def fake_build_watchlist_summary(*args, **kwargs) -> AdminReadModelWatchlistSummary:
        return AdminReadModelWatchlistSummary(
            source="snapshot",
            generated_at_label="01.05.2026 12:00",
            staleness_seconds=0,
            tracked_count=4,
            alert_item_count=3,
            missing_count=1,
            stale_count=1,
            budget_exceeded_count=1,
            regression_count=0,
            top_attention_label="Support insights",
            top_attention_kind_label="Stale snapshot",
            top_attention_note=None,
            top_regression_label=None,
            top_budget_label="Pricing / Offers",
            top_items=(),
        )

    monkeypatch.setattr(
        "app.services.health_service.build_admin_read_model_watchlist_summary",
        fake_build_watchlist_summary,
    )

    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "database_url": "sqlite+aiosqlite:///:memory:",
            "timezone": "UTC",
        }
    )

    report = await build_admin_health_report(session, FakeBot(), settings, now=now)
    text = render_admin_health_report(report)

    assert "⚠️ Read-model watchlist:" in text
    assert "alerts 3" in text
    assert "top Support insights" in text
