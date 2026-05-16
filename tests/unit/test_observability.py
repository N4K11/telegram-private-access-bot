from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.base import Base
from app.db.session import create_async_engine, create_session_factory
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
from app.services.admin_read_model_reporting import (
    AdminReadModelDriftItemSummary,
    AdminReadModelDriftSummary,
    AdminReadModelOperatorDigest,
)
from app.services.observability import (
    EVENT_TELEGRAM_API_ERROR,
    EVENT_WORKER_CYCLE_FAILED,
    AdminObservabilityReport,
    build_admin_observability_report,
    render_admin_observability_report,
)


@pytest.fixture(autouse=True)
def runtime_state_fixture() -> AsyncIterator[None]:
    reset_runtime_state()
    yield
    reset_runtime_state()


@pytest_asyncio.fixture
async def session(workspace_tmp_path: Path) -> AsyncIterator[AsyncSession]:
    database_path = workspace_tmp_path / "observability.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


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


async def test_admin_observability_report_renders_recent_runtime_state(
    session: AsyncSession,
) -> None:
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

    report = await build_admin_observability_report(
        session,
        settings=settings,
        critical_error_webhook_url=settings.critical_error_webhook_url,
    )
    text = render_admin_observability_report(report, timezone=settings.timezone)

    assert report.read_model_actions is not None
    assert report.read_model_watchlist is not None
    assert "Critical webhook:" in text
    assert "backup_worker" in text
    assert "Backup worker failed" in text
    assert "TelegramBadRequest: chat not found" in text
    assert "Read-models:" in text
    assert "focus:" in text
    assert "summary:" in text
    assert "snapshot summary unavailable" in text
    assert "watchlist:" in text
    assert "actions:" in text
    assert "drift:" in text


def test_admin_observability_report_renders_drift_leaders() -> None:
    report = AdminObservabilityReport(
        recent_errors=(),
        worker_statuses=(),
        last_telegram_api_error_at=None,
        last_telegram_api_error=None,
        last_backup_result_at=None,
        last_backup_result_status=None,
        last_backup_result_details=None,
        critical_webhook_enabled=False,
        read_model_summary=None,
        read_model_focus=None,
        read_model_operator_digest=AdminReadModelOperatorDigest(
            summary_line="focus live drift: Pricing / Offers В· drift regressions 2",
            focus_line="Live drift В· Pricing / Offers В· budget regression",
            watch_line=None,
            action_line=None,
            drift_line="Pricing / Offers В· budget regression В· +3 queries В· +2048 bytes",
        ),
        read_model_watchlist=None,
        read_model_actions=None,
        read_model_drift=AdminReadModelDriftSummary(
            source="live",
            generated_at_label="06.05.2026 12:00",
            staleness_seconds=0,
            compared_count=3,
            missing_snapshot_count=0,
            regression_count=2,
            improvement_count=1,
            budget_regression_count=1,
            query_regression_count=1,
            payload_regression_count=2,
            build_regression_count=1,
            top_regression_label="Pricing / Offers",
            top_regression_note="Live drifted above snapshot baseline.",
            top_budget_regression_label="Support insights",
            top_query_regression_label="Pricing / Offers",
            top_payload_regression_label="Support insights",
            top_build_regression_label="Admin summary",
            top_items=(
                AdminReadModelDriftItemSummary(
                    label="Pricing / Offers",
                    note="budget regression, +3 queries, +2048 bytes",
                    query_count_delta=3,
                    payload_bytes_delta=2048,
                    build_duration_ms_delta=0,
                    budget_regressed=True,
                ),
                AdminReadModelDriftItemSummary(
                    label="Support insights",
                    note="+512 bytes, +12 ms",
                    query_count_delta=0,
                    payload_bytes_delta=512,
                    build_duration_ms_delta=12,
                    budget_regressed=False,
                ),
            ),
        ),
    )

    text = render_admin_observability_report(report, timezone="UTC")

    assert "query regression: Pricing / Offers" in text
    assert "payload regression: Support insights" in text
    assert "build regression: Admin summary" in text
    assert "summary:" in text
    assert "top drift: Pricing / Offers" in text
    assert "budget regression" in text
