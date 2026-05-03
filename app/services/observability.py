# ruff: noqa: E501
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from html import escape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.runtime_state import CriticalErrorRecord, WorkerStatusRecord, snapshot_runtime_state
from app.utils.datetime import format_datetime

EVENT_PAYMENT_STARS_PAID = "payment_stars_paid"
EVENT_PAYMENT_CRYPTO_PAID = "payment_crypto_paid"
EVENT_SUBSCRIPTION_ACTIVATED = "subscription_activated"
EVENT_SUBSCRIPTION_REVOKED = "subscription_revoked"
EVENT_INVITE_CREATED = "invite_created"
EVENT_TELEGRAM_API_ERROR = "telegram_api_error"
EVENT_WORKER_CYCLE_FAILED = "worker_cycle_failed"
EVENT_CRITICAL_ERROR = "critical_error"
EVENT_WEBHOOK_UNAUTHORIZED = "webhook_unauthorized"
EVENT_WEBHOOK_INVALID_JSON = "webhook_invalid_json"
EVENT_CRYPTO_WEBHOOK_REJECTED = "crypto_webhook_rejected"
EVENT_CRYPTO_WEBHOOK_FAILED = "crypto_webhook_failed"
EVENT_CABINET_AUTH_FAILED = "cabinet_auth_failed"
EVENT_CHANNEL_GUARD_INCIDENT = "channel_guard_incident"

BOT_TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b")
INVITE_LINK_RE = re.compile(r"https?://t\.me/(?:joinchat/|\+)[A-Za-z0-9_-]+", re.IGNORECASE)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(token|secret|password|authorization|api[_-]?key)\b([=:]\s*)([^\s,;]+)"
)


@dataclass(frozen=True, slots=True)
class AdminObservabilityReport:
    recent_errors: tuple[CriticalErrorRecord, ...]
    worker_statuses: tuple[WorkerStatusRecord, ...]
    last_telegram_api_error_at: datetime | None
    last_telegram_api_error: str | None
    last_backup_result_at: datetime | None
    last_backup_result_status: str | None
    last_backup_result_details: str | None
    critical_webhook_enabled: bool


def sanitize_observability_text(text: str | None) -> str:
    if text is None:
        return ""
    sanitized = str(text)
    sanitized = BOT_TOKEN_RE.sub("[redacted-token]", sanitized)
    sanitized = INVITE_LINK_RE.sub("[redacted-invite-link]", sanitized)
    sanitized = SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[redacted]",
        sanitized,
    )
    return sanitized


def sanitize_observability_payload(value):
    if isinstance(value, str):
        return sanitize_observability_text(value)
    if isinstance(value, dict):
        return {
            sanitize_observability_text(str(key)): sanitize_observability_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(sanitize_observability_payload(item) for item in value)
    if isinstance(value, list):
        return [sanitize_observability_payload(item) for item in value]
    if isinstance(value, set):
        return sorted(sanitize_observability_payload(item) for item in value)
    return value


def emit_critical_error_webhook(
    url: str,
    *,
    event_name: str,
    source: str,
    message: str,
    occurred_at: datetime,
    timeout: float = 5.0,
) -> bool:
    payload = {
        "event_name": event_name,
        "source": source,
        "message": sanitize_observability_text(message),
        "occurred_at": occurred_at.isoformat(),
    }
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout):
            return True
    except (HTTPError, URLError, OSError):
        return False


def build_admin_observability_report(
    *,
    critical_error_webhook_url: str | None,
) -> AdminObservabilityReport:
    runtime = snapshot_runtime_state()
    return AdminObservabilityReport(
        recent_errors=runtime.recent_critical_errors[:20],
        worker_statuses=runtime.worker_statuses,
        last_telegram_api_error_at=runtime.last_telegram_api_error_at,
        last_telegram_api_error=runtime.last_telegram_api_error,
        last_backup_result_at=runtime.last_backup_result_at,
        last_backup_result_status=runtime.last_backup_result_status,
        last_backup_result_details=runtime.last_backup_result_details,
        critical_webhook_enabled=bool(critical_error_webhook_url),
    )


def render_admin_observability_report(report: AdminObservabilityReport, *, timezone: str) -> str:
    lines = ["🚨 Наблюдаемость", ""]
    lines.append(
        "Critical webhook: включён"
        if report.critical_webhook_enabled
        else "Critical webhook: выключен"
    )
    lines.append("")
    lines.append("Последние ошибки:")
    if not report.recent_errors:
        lines.append("— Критических ошибок пока нет")
    else:
        for item in report.recent_errors:
            lines.append(
                f"• {format_datetime(item.occurred_at, timezone)} · "
                f"<code>{escape(item.event_name)}</code> · "
                f"{escape(item.source)} · {escape(item.message)}"
            )

    lines.append("")
    lines.append("Статусы воркеров:")
    if not report.worker_statuses:
        lines.append("— Ещё не зафиксированы")
    else:
        for item in report.worker_statuses:
            details = escape(item.details) if item.details else "без деталей"
            lines.append(
                f"{_worker_status_icon(item.status)} {escape(item.name)}: "
                f"{details} · {format_datetime(item.updated_at, timezone)}"
            )

    lines.append("")
    lines.append(
        "Последняя Telegram API ошибка: "
        + _render_optional_error(
            report.last_telegram_api_error_at,
            report.last_telegram_api_error,
            timezone,
        )
    )
    lines.append(
        "Последний backup: "
        + _render_backup_result(
            report.last_backup_result_at,
            report.last_backup_result_status,
            report.last_backup_result_details,
            timezone,
        )
    )
    return "\n".join(lines)


def _worker_status_icon(status: str) -> str:
    return {
        "ok": "✅",
        "warn": "⚠️",
        "fail": "❌",
    }.get(status, "ℹ️")


def _render_optional_error(at: datetime | None, message: str | None, timezone: str) -> str:
    if at is None or not message:
        return "не было"
    return f"{format_datetime(at, timezone)} · {escape(message)}"


def _render_backup_result(
    at: datetime | None,
    status: str | None,
    details: str | None,
    timezone: str,
) -> str:
    if at is None or not status:
        return "ещё не выполнялся"
    label = {
        "ok": "успешно",
        "fail": "ошибка",
    }.get(status, status)
    suffix = f" · {escape(details)}" if details else ""
    return f"{label} · {format_datetime(at, timezone)}{suffix}"