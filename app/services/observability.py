# ruff: noqa: E501
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from html import escape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.runtime_state import CriticalErrorRecord, WorkerStatusRecord, snapshot_runtime_state
from app.services.admin_read_model_reporting import (
    AdminReadModelActionSummary,
    AdminReadModelAlertSummary,
    AdminReadModelDriftSummary,
    AdminReadModelFocusSummary,
    AdminReadModelOperatorDigest,
    AdminReadModelWatchlistSummary,
    build_admin_read_model_action_digest,
    build_admin_read_model_action_summary,
    build_admin_read_model_drift_digest,
    build_admin_read_model_drift_summary,
    build_admin_read_model_focus_summary,
    build_admin_read_model_operator_digest,
    build_admin_read_model_watchlist_digest,
    build_admin_read_model_watchlist_summary,
    load_admin_read_model_alert_summary,
)
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
    read_model_summary: AdminReadModelAlertSummary | None
    read_model_focus: AdminReadModelFocusSummary | None
    read_model_operator_digest: AdminReadModelOperatorDigest | None
    read_model_watchlist: AdminReadModelWatchlistSummary | None
    read_model_actions: AdminReadModelActionSummary | None
    read_model_drift: AdminReadModelDriftSummary | None


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


async def build_admin_observability_report(
    session: AsyncSession | None = None,
    *,
    settings: Settings | None = None,
    viewer_role: str = "owner",
    critical_error_webhook_url: str | None,
    now: datetime | None = None,
) -> AdminObservabilityReport:
    runtime = snapshot_runtime_state()
    read_model_summary = None
    read_model_focus = None
    read_model_operator_digest = None
    read_model_watchlist = None
    read_model_actions = None
    read_model_drift = None
    if session is not None:
        read_model_summary = await load_admin_read_model_alert_summary(session, now=now)
        if settings is not None:
            read_model_watchlist = await build_admin_read_model_watchlist_summary(
                session,
                settings=settings,
                viewer_role=viewer_role,
                now=now,
                limit=3,
                source="snapshot",
            )
            read_model_actions = await build_admin_read_model_action_summary(
                session,
                settings=settings,
                viewer_role=viewer_role,
                now=now,
                limit=3,
                source="live",
            )
            read_model_drift = await build_admin_read_model_drift_summary(
                session,
                settings=settings,
                viewer_role=viewer_role,
                now=now,
                limit=5,
            )
            read_model_focus = build_admin_read_model_focus_summary(
                watchlist_summary=read_model_watchlist,
                action_summary=read_model_actions,
                drift_summary=read_model_drift,
            )
            read_model_operator_digest = build_admin_read_model_operator_digest(
                watchlist_summary=read_model_watchlist,
                action_summary=read_model_actions,
                drift_summary=read_model_drift,
            )
    return AdminObservabilityReport(
        recent_errors=runtime.recent_critical_errors[:20],
        worker_statuses=runtime.worker_statuses,
        last_telegram_api_error_at=runtime.last_telegram_api_error_at,
        last_telegram_api_error=runtime.last_telegram_api_error,
        last_backup_result_at=runtime.last_backup_result_at,
        last_backup_result_status=runtime.last_backup_result_status,
        last_backup_result_details=runtime.last_backup_result_details,
        critical_webhook_enabled=bool(critical_error_webhook_url),
        read_model_summary=read_model_summary,
        read_model_focus=read_model_focus,
        read_model_operator_digest=read_model_operator_digest,
        read_model_watchlist=read_model_watchlist,
        read_model_actions=read_model_actions,
        read_model_drift=read_model_drift,
    )


def render_admin_observability_report(report: AdminObservabilityReport, *, timezone: str) -> str:
    lines = ["Observability", ""]
    lines.append(
        "Critical webhook: enabled"
        if report.critical_webhook_enabled
        else "Critical webhook: disabled"
    )
    lines.append("")
    lines.append("Recent errors:")
    if not report.recent_errors:
        lines.append("- No critical errors yet")
    else:
        for item in report.recent_errors:
            lines.append(
                f"- {format_datetime(item.occurred_at, timezone)} | "
                f"<code>{escape(item.event_name)}</code> | "
                f"{escape(item.source)} | {escape(item.message)}"
            )

    lines.append("")
    lines.append("Worker statuses:")
    if not report.worker_statuses:
        lines.append("- No worker statuses recorded")
    else:
        for item in report.worker_statuses:
            details = escape(item.details) if item.details else "no details"
            lines.append(
                f"{_worker_status_icon(item.status)} {escape(item.name)}: "
                f"{details} | {format_datetime(item.updated_at, timezone)}"
            )

    lines.append("")
    lines.append(
        "Last Telegram API error: "
        + _render_optional_error(
            report.last_telegram_api_error_at,
            report.last_telegram_api_error,
            timezone,
        )
    )
    lines.append(
        "Last backup: "
        + _render_backup_result(
            report.last_backup_result_at,
            report.last_backup_result_status,
            report.last_backup_result_details,
            timezone,
        )
    )
    lines.append("")
    lines.extend(_render_read_model_section(report))
    return "\n".join(lines)


def _render_read_model_section(report: AdminObservabilityReport) -> list[str]:
    lines = ["Read-models:"]
    summary = report.read_model_summary
    if summary is None:
        lines.append("- snapshot summary unavailable")
    else:
        lines.append(
            "- snapshots: "
            f"alerts {summary.alert_count} | "
            f"stale {summary.stale_count} | "
            f"missing {summary.missing_count} | "
            f"budget {summary.budget_exceeded_count}"
        )
        if summary.generated_at_label:
            lines.append(f"- snapshot generated: {escape(summary.generated_at_label)}")
        if summary.top_attention_label:
            lines.append(
                "- top snapshot risk: "
                f"{escape(summary.top_attention_label)}"
                f" | {escape(summary.top_attention_status_label or 'alert')}"
            )

    if report.read_model_focus is not None:
        lines.append(
            "- focus: "
            f"{escape(report.read_model_focus.line)}"
        )

    if report.read_model_operator_digest is not None:
        lines.append(
            "- summary: "
            f"{escape(report.read_model_operator_digest.summary_line)}"
        )

    watchlist = report.read_model_watchlist
    if watchlist is None:
        lines.append("- watchlist summary unavailable")
    else:
        watchlist_digest = build_admin_read_model_watchlist_digest(
            watchlist,
            max_items=0,
        )
        lines.append(f"- watchlist: {watchlist_digest.summary_line}")
        if watchlist_digest.top_label:
            lines.append(
                "- top watch: "
                f"{escape(watchlist_digest.top_label)}"
                f" | {escape(watchlist_digest.top_detail or 'watch item')}"
            )
        for item_line in watchlist_digest.item_lines:
            lines.append(f"- watch item: {escape(item_line)}")

    actions = report.read_model_actions
    if actions is None:
        lines.append("- action digest unavailable")
    else:
        action_digest = build_admin_read_model_action_digest(actions, max_items=0)
        lines.append(
            f"- actions: {action_digest.summary_line}"
        )
        for item_line in action_digest.item_lines:
            lines.append(
                "- action: "
                f"{escape(item_line)}"
            )

    drift = report.read_model_drift
    if drift is None:
        lines.append("- live drift compare unavailable")
    else:
        drift_digest = build_admin_read_model_drift_digest(drift, max_items=0)
        lines.append(
            f"- drift: {drift_digest.extended_summary_line}"
        )
        if drift.generated_at_label:
            lines.append(f"- drift generated: {escape(drift.generated_at_label)}")
        if drift_digest.top_label:
            lines.append(
                "- top drift: "
                f"{escape(drift_digest.top_label)}"
                f" | {escape(drift_digest.top_detail or 'drift detected')}"
            )
        elif drift.top_budget_regression_label:
            lines.append(
                "- budget regression: "
                f"{escape(drift.top_budget_regression_label)}"
            )
        if drift.top_query_regression_label:
            lines.append(
                "- query regression: "
                f"{escape(drift.top_query_regression_label)}"
            )
        if drift.top_payload_regression_label:
            lines.append(
                "- payload regression: "
                f"{escape(drift.top_payload_regression_label)}"
            )
        if drift.top_build_regression_label:
            lines.append(
                "- build regression: "
                f"{escape(drift.top_build_regression_label)}"
            )
        for item_line in drift_digest.item_lines:
            lines.append(
                "- drift item: "
                f"{escape(item_line)}"
            )
    return lines


def _worker_status_icon(status: str) -> str:
    return {
        "ok": "OK",
        "warn": "WARN",
        "fail": "FAIL",
    }.get(status, "INFO")


def _render_optional_error(at: datetime | None, message: str | None, timezone: str) -> str:
    if at is None or not message:
        return "none"
    return f"{format_datetime(at, timezone)} | {escape(message)}"


def _render_backup_result(
    at: datetime | None,
    status: str | None,
    details: str | None,
    timezone: str,
) -> str:
    if at is None or not status:
        return "not run yet"
    label = {
        "ok": "ok",
        "fail": "failed",
    }.get(status, status)
    suffix = f" | {escape(details)}" if details else ""
    return f"{label} | {format_datetime(at, timezone)}{suffix}"
