from __future__ import annotations

from datetime import datetime

from app.config import Settings
from app.services.web_admin_dashboard_read_model_core import (
    READ_MODEL_STATUS_IMPROVED,
    READ_MODEL_STATUS_MISSING,
    READ_MODEL_STATUS_OK,
    READ_MODEL_STATUS_REGRESSION,
    _bool_or_none,
    _int_or_default,
    _model_scope_label,
    _staleness_seconds,
)
from app.services.web_admin_dashboard_read_model_descriptors import ReadModelDescriptor
from app.utils.datetime import ensure_aware_utc, format_datetime


def _drift_tone(status: str) -> str:
    if status in {READ_MODEL_STATUS_MISSING, READ_MODEL_STATUS_REGRESSION}:
        return "warn"
    if status == READ_MODEL_STATUS_IMPROVED:
        return "good"
    return "info"


def _build_drift_item(
    descriptor: ReadModelDescriptor,
    *,
    snapshot_payload: dict[str, object] | None,
    snapshot_generated_at: datetime | None,
    live_payload: dict[str, object] | None,
    settings: Settings,
    now: datetime,
) -> dict[str, object]:
    snapshot_missing = snapshot_payload is None or snapshot_generated_at is None
    snapshot_staleness_seconds = _staleness_seconds(generated_at=snapshot_generated_at, now=now)
    snapshot_query_count = None if snapshot_payload is None else _int_or_default(
        snapshot_payload.get("query_count")
    )
    snapshot_query_budget = (
        descriptor.query_budget
        if snapshot_payload is None
        else _int_or_default(snapshot_payload.get("query_budget"), descriptor.query_budget or 0)
    )
    if (
        descriptor.query_budget is None
        and snapshot_payload is not None
        and snapshot_payload.get("query_budget") is None
    ):
        snapshot_query_budget = None
    snapshot_query_budget_ok = (
        None if snapshot_payload is None else _bool_or_none(snapshot_payload.get("query_budget_ok"))
    )
    if (
        snapshot_query_budget_ok is None
        and snapshot_query_budget is not None
        and snapshot_query_count is not None
    ):
        snapshot_query_budget_ok = snapshot_query_count <= snapshot_query_budget
    snapshot_payload_bytes = None if snapshot_payload is None else _int_or_default(
        snapshot_payload.get("payload_bytes")
    )
    snapshot_payload_budget = (
        descriptor.payload_budget
        if snapshot_payload is None
        else _int_or_default(snapshot_payload.get("payload_budget"), descriptor.payload_budget or 0)
    )
    if (
        descriptor.payload_budget is None
        and snapshot_payload is not None
        and snapshot_payload.get("payload_budget") is None
    ):
        snapshot_payload_budget = None
    snapshot_payload_budget_ok = (
        None
        if snapshot_payload is None
        else _bool_or_none(snapshot_payload.get("payload_budget_ok"))
    )
    if (
        snapshot_payload_budget_ok is None
        and snapshot_payload_budget is not None
        and snapshot_payload_bytes is not None
    ):
        snapshot_payload_budget_ok = snapshot_payload_bytes <= snapshot_payload_budget
    snapshot_build_duration_ms = None if snapshot_payload is None else _int_or_default(
        snapshot_payload.get("build_duration_ms")
    )

    live_query_count = (
        None if live_payload is None else _int_or_default(live_payload.get("query_count"))
    )
    live_query_budget = None if live_payload is None else _int_or_default(
        live_payload.get("query_budget"),
        descriptor.query_budget or 0,
    )
    if live_payload is not None and live_payload.get("query_budget") is None:
        live_query_budget = None
    live_query_budget_ok = None if live_payload is None else _bool_or_none(
        live_payload.get("query_budget_ok")
    )
    live_payload_bytes = (
        None if live_payload is None else _int_or_default(live_payload.get("payload_bytes"))
    )
    live_payload_budget = None if live_payload is None else _int_or_default(
        live_payload.get("payload_budget"),
        descriptor.payload_budget or 0,
    )
    if live_payload is not None and live_payload.get("payload_budget") is None:
        live_payload_budget = None
    live_payload_budget_ok = None if live_payload is None else _bool_or_none(
        live_payload.get("payload_budget_ok")
    )
    live_build_duration_ms = None if live_payload is None else _int_or_default(
        live_payload.get("build_duration_ms")
    )
    live_generated_at_raw = None if live_payload is None else live_payload.get("generated_at")
    live_generated_at = None
    if isinstance(live_generated_at_raw, str):
        try:
            live_generated_at = ensure_aware_utc(datetime.fromisoformat(live_generated_at_raw))
        except ValueError:
            live_generated_at = None

    query_count_delta = (
        None
        if snapshot_query_count is None or live_query_count is None
        else live_query_count - snapshot_query_count
    )
    payload_bytes_delta = (
        None
        if snapshot_payload_bytes is None or live_payload_bytes is None
        else live_payload_bytes - snapshot_payload_bytes
    )
    build_duration_ms_delta = (
        None
        if snapshot_build_duration_ms is None or live_build_duration_ms is None
        else live_build_duration_ms - snapshot_build_duration_ms
    )
    budget_regressed = (
        (snapshot_query_budget_ok is not False and live_query_budget_ok is False)
        or (snapshot_payload_budget_ok is not False and live_payload_budget_ok is False)
    )
    has_regression = budget_regressed or any(
        delta is not None and delta > 0
        for delta in (query_count_delta, payload_bytes_delta, build_duration_ms_delta)
    )
    has_improvement = any(
        delta is not None and delta < 0
        for delta in (query_count_delta, payload_bytes_delta, build_duration_ms_delta)
    )
    if snapshot_missing:
        status = READ_MODEL_STATUS_MISSING
        status_label = "Snapshot missing"
        note = "No stored snapshot metadata is available for comparison yet."
    elif has_regression:
        status = READ_MODEL_STATUS_REGRESSION
        status_label = "Live drifted up"
        reasons: list[str] = []
        if budget_regressed:
            reasons.append("budget regression")
        if query_count_delta is not None and query_count_delta > 0:
            reasons.append(f"+{query_count_delta} queries")
        if payload_bytes_delta is not None and payload_bytes_delta > 0:
            reasons.append(f"+{payload_bytes_delta} bytes")
        if build_duration_ms_delta is not None and build_duration_ms_delta > 0:
            reasons.append(f"+{build_duration_ms_delta} ms")
        note = "Live build drifted above snapshot baseline: " + ", ".join(reasons) + "."
    elif has_improvement:
        status = READ_MODEL_STATUS_IMPROVED
        status_label = "Live improved"
        reasons = []
        if query_count_delta is not None and query_count_delta < 0:
            reasons.append(f"{query_count_delta} queries")
        if payload_bytes_delta is not None and payload_bytes_delta < 0:
            reasons.append(f"{payload_bytes_delta} bytes")
        if build_duration_ms_delta is not None and build_duration_ms_delta < 0:
            reasons.append(f"{build_duration_ms_delta} ms")
        note = (
            "Live build is lighter than the stored snapshot baseline: "
            + ", ".join(reasons)
            + "."
        )
    else:
        status = READ_MODEL_STATUS_OK
        status_label = "Stable"
        note = "Live build stays within the stored snapshot envelope."

    drift_score = 0
    if snapshot_missing:
        drift_score += 1_000_000
    if budget_regressed:
        drift_score += 100_000
    if query_count_delta is not None and query_count_delta > 0:
        drift_score += query_count_delta * 1_000
    if payload_bytes_delta is not None and payload_bytes_delta > 0:
        drift_score += payload_bytes_delta // 10
    if build_duration_ms_delta is not None and build_duration_ms_delta > 0:
        drift_score += build_duration_ms_delta * 20

    improvement_score = 0
    if query_count_delta is not None and query_count_delta < 0:
        improvement_score += abs(query_count_delta) * 1_000
    if payload_bytes_delta is not None and payload_bytes_delta < 0:
        improvement_score += abs(payload_bytes_delta) // 10
    if build_duration_ms_delta is not None and build_duration_ms_delta < 0:
        improvement_score += abs(build_duration_ms_delta) * 20

    return {
        "id": descriptor.identity,
        "group": descriptor.storage_group,
        "group_label": descriptor.storage_group.title(),
        "key": descriptor.storage_key,
        "scope_key": descriptor.scope_key,
        "scope_label": _model_scope_label(descriptor),
        "label": descriptor.label,
        "cadence_minutes": descriptor.cadence_minutes,
        "snapshot_missing": snapshot_missing,
        "snapshot_generated_at": (
            ensure_aware_utc(snapshot_generated_at).isoformat() if snapshot_generated_at else None
        ),
        "snapshot_generated_at_label": (
            format_datetime(snapshot_generated_at, settings.timezone)
            if snapshot_generated_at is not None
            else "Missing"
        ),
        "snapshot_staleness_seconds": snapshot_staleness_seconds,
        "snapshot_query_count": snapshot_query_count,
        "snapshot_query_budget": snapshot_query_budget,
        "snapshot_query_budget_ok": snapshot_query_budget_ok,
        "snapshot_payload_bytes": snapshot_payload_bytes,
        "snapshot_payload_budget": snapshot_payload_budget,
        "snapshot_payload_budget_ok": snapshot_payload_budget_ok,
        "snapshot_build_duration_ms": snapshot_build_duration_ms,
        "live_generated_at": live_generated_at.isoformat() if live_generated_at else None,
        "live_generated_at_label": (
            format_datetime(live_generated_at, settings.timezone)
            if live_generated_at is not None
            else "Unavailable"
        ),
        "live_query_count": live_query_count,
        "live_query_budget": live_query_budget,
        "live_query_budget_ok": live_query_budget_ok,
        "live_payload_bytes": live_payload_bytes,
        "live_payload_budget": live_payload_budget,
        "live_payload_budget_ok": live_payload_budget_ok,
        "live_build_duration_ms": live_build_duration_ms,
        "query_count_delta": query_count_delta,
        "payload_bytes_delta": payload_bytes_delta,
        "build_duration_ms_delta": build_duration_ms_delta,
        "budget_regressed": budget_regressed,
        "status": status,
        "status_label": status_label,
        "status_tone": _drift_tone(status),
        "note": note,
        "severity_score": drift_score,
        "improvement_score": improvement_score,
    }
