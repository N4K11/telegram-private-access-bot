from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.routers.admin.observability import (
    admin_observability,
    admin_observability_read_models,
    admin_observability_read_models_actions,
    admin_observability_read_models_watchlist,
)
from app.config import Settings
from app.db.base import Base
from app.db.session import create_async_engine, create_session_factory
from app.runtime_state import (
    record_backup_result,
    record_critical_error,
    record_telegram_api_error,
    record_worker_status,
    reset_runtime_state,
)
from app.services.admin_roles import PERMISSION_OBSERVABILITY
from app.services.observability import EVENT_WORKER_CYCLE_FAILED


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
        self.edit_calls: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edit_calls.append((text, reply_markup))


class DummyCallback:
    def __init__(self) -> None:
        self.from_user = DummyUser()
        self.message = DummyMessage()
        self.answer_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args, **kwargs) -> None:
        self.answer_calls.append((args, kwargs))


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


def _flatten_button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


async def test_admin_observability_command_renders_report(session: AsyncSession) -> None:
    record_critical_error(
        EVENT_WORKER_CYCLE_FAILED,
        "Crypto reconciliation failed",
        source="app.workers.scheduler",
        at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )
    record_worker_status(
        "crypto_reconciler",
        "fail",
        details="Crypto reconciliation failed",
        at=datetime(2026, 5, 1, 12, 1, tzinfo=UTC),
    )
    record_backup_result(
        "ok",
        "daily-backup-20260501.zip",
        at=datetime(2026, 5, 1, 12, 2, tzinfo=UTC),
    )
    record_telegram_api_error(
        "TelegramBadRequest: chat not found",
        at=datetime(2026, 5, 1, 12, 3, tzinfo=UTC),
    )
    message = DummyMessage()
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "timezone": "UTC",
        }
    )

    await admin_observability(message, settings, session)

    assert message.answer_calls
    text, markup = message.answer_calls[0]
    assert "Crypto reconciliation failed" in text
    assert "daily-backup-20260501.zip" in text
    assert "TelegramBadRequest: chat not found" in text
    assert "Read-models:" in text
    assert "focus:" in text
    assert "summary:" in text
    assert _flatten_button_texts(markup) == [
        "🗂 Read-models",
        "⚠️ Watchlist",
        "🔄 Обновить",
        "🏠 Админ-панель",
    ]


async def test_admin_observability_read_models_callback_renders_report(
    session: AsyncSession,
) -> None:
    callback = DummyCallback()
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "timezone": "UTC",
        }
    )

    await admin_observability_read_models(callback, settings, session)

    assert callback.message.edit_calls
    text, markup = callback.message.edit_calls[0]
    assert "Read-model diagnostics" in text
    assert "Summary:" in text
    assert "Focus:" in text
    assert "Tracked:" in text
    assert "Alerts:" in text
    assert _flatten_button_texts(markup) == [
        "⚠️ Watchlist",
        "🛠 Actions",
        "🔄 Live overview",
        "🧪 Snapshot vs live",
        "⬅️ Наблюдаемость",
        "🏠 Админ-панель",
    ]
    assert callback.answer_calls == [((), {})]


async def test_admin_observability_watchlist_callback_renders_report(
    session: AsyncSession,
) -> None:
    callback = DummyCallback()
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "timezone": "UTC",
        }
    )

    await admin_observability_read_models_watchlist(callback, settings, session)

    assert callback.message.edit_calls
    text, markup = callback.message.edit_calls[0]
    assert "Read-model watchlist" in text
    assert "Summary:" in text
    assert "Focus:" in text
    assert "Open alerts:" in text
    assert "Kinds:" in text
    assert _flatten_button_texts(markup) == [
        "📦 Snapshot overview",
        "🛠 Actions",
        "🔄 Live overview",
        "🧪 Snapshot vs live",
        "⬅️ Наблюдаемость",
        "🏠 Админ-панель",
    ]
    assert callback.answer_calls == [((), {})]


async def test_admin_observability_actions_callback_renders_report(
    session: AsyncSession,
) -> None:
    callback = DummyCallback()
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "timezone": "UTC",
        }
    )

    await admin_observability_read_models_actions(callback, settings, session)

    assert callback.message.edit_calls
    text, markup = callback.message.edit_calls[0]
    assert "Read-model action digest" in text
    assert "Summary:" in text
    assert "Focus:" in text
    assert "Action mix:" in text
    assert _flatten_button_texts(markup) == [
        "📦 Snapshot overview",
        "⚠️ Watchlist",
        "🔄 Live overview",
        "🧪 Snapshot vs live",
        "⬅️ Наблюдаемость",
        "🏠 Админ-панель",
    ]
    assert callback.answer_calls == [((), {})]


async def test_observability_filter_rejects_non_admin() -> None:
    event = type("Event", (), {"from_user": DummyUser(user_id=1)})()
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181]})

    result = await AdminFilter(PERMISSION_OBSERVABILITY)(event, settings)

    assert result is False
