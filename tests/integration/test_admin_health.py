from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.routers.admin.health import admin_health
from app.config import Settings
from app.db.base import Base
from app.db.models import BackupRecord, Channel, Payment, Subscription, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.runtime_state import (
    mark_started,
    record_maintenance_run,
    record_update,
    reset_runtime_state,
)


class DummyUser:
    def __init__(self, user_id: int = 755815181, first_name: str = "Admin") -> None:
        self.id = user_id
        self.first_name = first_name
        self.username = "admin"
        self.last_name = None
        self.language_code = "ru"


class DummyMessage:
    def __init__(self) -> None:
        self.from_user = DummyUser()
        self.answer_calls: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))


class FakeBot:
    async def get_me(self):
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
            telegram_payment_charge_id="charge-health-route",
            provider_payment_charge_id="provider-health-route",
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


def _flatten_button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


async def test_admin_health_command_renders_report(session: AsyncSession) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    await _seed_health_data(session, now=now)
    mark_started(now=now - timedelta(hours=1, minutes=5))
    record_update(update_id=777, kind="Message", at=now - timedelta(minutes=1))
    record_maintenance_run(label="background_workers", at=now - timedelta(minutes=2))
    message = DummyMessage()
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "database_url": "sqlite+aiosqlite:///:memory:",
            "timezone": "UTC",
        }
    )

    await admin_health(message, session, settings, FakeBot())

    assert message.answer_calls
    text, markup = message.answer_calls[0]
    assert "❤️ Состояние бота" in text
    assert "✅ Бот подключен: @health_bot" in text
    assert "<code>777</code>" in text
    assert "background_workers" in text
    assert _flatten_button_texts(markup) == ["⬅️ Назад", "🏠 Админ-панель"]


async def test_admin_health_filter_rejects_non_admin() -> None:
    event = type("Event", (), {"from_user": DummyUser(user_id=1)})()
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181]})

    result = await AdminFilter()(event, settings)

    assert result is False
