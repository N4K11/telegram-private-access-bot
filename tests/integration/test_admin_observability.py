from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from app.bot.filters.admin import AdminFilter
from app.bot.routers.admin.observability import admin_observability
from app.config import Settings
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

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))


@pytest.fixture(autouse=True)
def runtime_state_fixture() -> AsyncIterator[None]:
    reset_runtime_state()
    yield
    reset_runtime_state()


def _flatten_button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


async def test_admin_observability_command_renders_report() -> None:
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

    await admin_observability(message, settings)

    assert message.answer_calls
    text, markup = message.answer_calls[0]
    assert "🚨 Наблюдаемость" in text
    assert "Crypto reconciliation failed" in text
    assert "daily-backup-20260501.zip" in text
    assert "TelegramBadRequest: chat not found" in text
    assert _flatten_button_texts(markup) == ["⬅️ Назад", "🏠 Админ-панель"]


async def test_observability_filter_rejects_non_admin() -> None:
    event = type("Event", (), {"from_user": DummyUser(user_id=1)})()
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181]})

    result = await AdminFilter(PERMISSION_OBSERVABILITY)(event, settings)

    assert result is False