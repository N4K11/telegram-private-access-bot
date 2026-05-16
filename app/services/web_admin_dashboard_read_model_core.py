from __future__ import annotations

import json
from datetime import datetime

from app.services.admin_roles import ROLE_LABELS
from app.services.web_admin_dashboard_read_model_descriptors import ReadModelDescriptor
from app.utils.datetime import ensure_aware_utc

READ_MODEL_VIEW_OVERVIEW = "overview"
READ_MODEL_VIEW_DRIFT = "drift"
READ_MODEL_VIEW_WATCHLIST = "watchlist"
READ_MODEL_VIEW_ACTIONS = "actions"
READ_MODEL_STATUS_OK = "ok"
READ_MODEL_STATUS_STALE = "stale"
READ_MODEL_STATUS_BUDGET = "budget"
READ_MODEL_STATUS_MISSING = "missing"
READ_MODEL_STATUS_REGRESSION = "regression"
READ_MODEL_STATUS_IMPROVED = "improved"

READ_MODEL_VIEW_LABELS = {
    READ_MODEL_VIEW_OVERVIEW: "Read-model diagnostics",
    READ_MODEL_VIEW_DRIFT: "Snapshot vs live drift",
    READ_MODEL_VIEW_WATCHLIST: "Read-model watchlist",
    READ_MODEL_VIEW_ACTIONS: "Read-model action digest",
}


def _decode_payload(raw_payload: str) -> dict[str, object]:
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _int_or_default(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _model_scope_label(descriptor: ReadModelDescriptor) -> str | None:
    if descriptor.scope_key and descriptor.scope_key.startswith("role:"):
        role = descriptor.scope_key.split(":", 1)[1]
        return ROLE_LABELS.get(role, role.title())
    return None


def _staleness_seconds(*, generated_at: datetime | None, now: datetime) -> int | None:
    if generated_at is None:
        return None
    return max(0, int((ensure_aware_utc(now) - ensure_aware_utc(generated_at)).total_seconds()))


def _read_model_status(
    *,
    is_missing: bool,
    is_stale: bool,
    query_budget_ok: bool | None,
) -> tuple[str, str]:
    if is_missing:
        return READ_MODEL_STATUS_MISSING, "Missing"
    if query_budget_ok is False:
        return READ_MODEL_STATUS_BUDGET, "Budget exceeded"
    if is_stale:
        return READ_MODEL_STATUS_STALE, "Stale"
    return READ_MODEL_STATUS_OK, "Healthy"


def _read_model_note(
    *,
    is_missing: bool,
    is_stale: bool,
    descriptor: ReadModelDescriptor,
    query_budget_ok: bool | None,
    query_count: int | None,
    query_budget: int | None,
    payload_budget_ok: bool | None,
    payload_bytes: int | None,
    payload_budget: int | None,
) -> str:
    if is_missing:
        return "Snapshot has not been materialized yet."
    if query_budget_ok is False and query_budget is not None and query_count is not None:
        return (
            f"Query budget exceeded: {query_count} > {query_budget} "
            f"(cadence {descriptor.cadence_minutes}m)."
        )
    if payload_budget_ok is False and payload_budget is not None and payload_bytes is not None:
        return (
            f"Payload budget exceeded: {payload_bytes} > {payload_budget} bytes "
            f"(cadence {descriptor.cadence_minutes}m)."
        )
    if is_stale:
        return f"Older than the {descriptor.cadence_minutes} minute refresh cadence."
    return f"Within the {descriptor.cadence_minutes} minute refresh cadence."


def _read_model_severity(
    *,
    is_missing: bool,
    is_stale: bool,
    query_budget_ok: bool | None,
    payload_budget_ok: bool | None,
    staleness_seconds: int | None,
    query_count: int | None,
    payload_bytes: int | None,
    build_duration_ms: int | None,
) -> int:
    score = 0
    if is_missing:
        score += 1_000_000
    if query_budget_ok is False:
        score += 100_000
    if payload_budget_ok is False:
        score += 75_000
    if is_stale:
        score += 50_000 + min(staleness_seconds or 0, 49_999)
    score += max(0, payload_bytes or 0) // 100
    score += max(0, build_duration_ms or 0) * 5
    score += max(0, query_count or 0) * 100
    return score
