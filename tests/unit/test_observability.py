from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from app.config import Settings
from app.logging_config import (
    CriticalErrorWebhookHandler,
    JsonLogFormatter,
    RuntimeObservabilityHandler,
)
from app.runtime_state import (
    record_backup_result,
    record_critical_error,
    record_telegram_api_error,
    record_worker_status,
    reset_runtime_state,
    snapshot_runtime_state,
)
from app.services.observability import (
    EVENT_TELEGRAM_API_ERROR,
    EVENT_WORKER_CYCLE_FAILED,
    build_admin_observability_report,
    render_admin_observability_report,
)


@pytest.fixture(autouse=True)
def runtime_state_fixture() -> AsyncIterator[None]:
    reset_runtime_state()
    yield
    reset_runtime_state()


def test_json_log_formatter_redacts_token_like_values() -> None:
    record = logging.LogRecord(
        name="app.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=10,
        msg="Payment failed for token 123456:ABCDEFGHIJKLMNOPQRSTUVWX and secret=super-secret",
        args=(),
        exc_info=None,
    )
    record.event_name = EVENT_WORKER_CYCLE_FAILED
    record.invite_link = "https://t.me/+secretInviteValue"

    payload = json.loads(JsonLogFormatter().format(record))

    assert "123456:" not in payload["message"]
    assert "super-secret" not in payload["message"]
    assert "secretInviteValue" not in json.dumps(payload, ensure_ascii=False)
    assert "[redacted-token]" in payload["message"]


def test_runtime_observability_handler_captures_worker_error() -> None:
    record = logging.LogRecord(
        name="app.workers.scheduler",
        level=logging.ERROR,
        pathname=__file__,
        lineno=20,
        msg="Backup worker cycle failed: token=123456:ABCDEFGHIJKLMNOPQRSTUVWX",
        args=(),
        exc_info=None,
    )
    record.event_name = EVENT_WORKER_CYCLE_FAILED

    RuntimeObservabilityHandler().emit(record)
    snapshot = snapshot_runtime_state()

    assert snapshot.recent_critical_errors
    latest = snapshot.recent_critical_errors[0]
    assert latest.event_name == EVENT_WORKER_CYCLE_FAILED
    assert "123456:" not in latest.message


def test_runtime_observability_handler_captures_telegram_error() -> None:
    class FakeTelegramError(Exception):
        __module__ = "telegram.fake"

    exc = FakeTelegramError("chat not found")
    record = logging.LogRecord(
        name="aiogram.dispatcher",
        level=logging.ERROR,
        pathname=__file__,
        lineno=30,
        msg="Telegram request failed",
        args=(),
        exc_info=(FakeTelegramError, exc, None),
    )

    RuntimeObservabilityHandler().emit(record)
    snapshot = snapshot_runtime_state()

    assert snapshot.last_telegram_api_error is not None
    assert snapshot.recent_critical_errors[0].event_name == EVENT_TELEGRAM_API_ERROR


def test_critical_error_webhook_handler_is_disabled_without_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_emit(*args, **kwargs):
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(
        "app.logging_config.emit_critical_error_webhook",
        fake_emit,
    )
    handler = CriticalErrorWebhookHandler(webhook_url="")
    record = logging.LogRecord(
        name="app.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=40,
        msg="Nothing should be sent",
        args=(),
        exc_info=None,
    )

    handler.emit(record)

    assert called is False


def test_admin_observability_report_renders_recent_runtime_state() -> None:
    record_critical_error(
        EVENT_WORKER_CYCLE_FAILED,
        "Backup worker failed",
        source="app.workers.scheduler",
        at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )
    record_worker_status(
        "backup_worker",
        "fail",
        details="Backup worker failed",
        at=datetime(2026, 5, 1, 12, 1, tzinfo=UTC),
    )
    record_backup_result(
        "fail",
        "Backup worker failed",
        at=datetime(2026, 5, 1, 12, 2, tzinfo=UTC),
    )
    record_telegram_api_error(
        "TelegramBadRequest: chat not found",
        at=datetime(2026, 5, 1, 12, 3, tzinfo=UTC),
    )
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "critical_error_webhook_url": "https://example.com/hook",
            "timezone": "UTC",
        }
    )

    report = build_admin_observability_report(
        critical_error_webhook_url=settings.critical_error_webhook_url,
    )
    text = render_admin_observability_report(report, timezone=settings.timezone)

    assert "🚨 Наблюдаемость" in text
    assert "Critical webhook: включён" in text
    assert "backup_worker" in text
    assert "Backup worker failed" in text
    assert "TelegramBadRequest: chat not found" in text