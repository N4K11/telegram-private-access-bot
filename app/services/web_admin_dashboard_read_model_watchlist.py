from __future__ import annotations

from app.services.web_admin_dashboard_read_model_core import (
    READ_MODEL_STATUS_BUDGET,
    READ_MODEL_STATUS_MISSING,
    READ_MODEL_STATUS_REGRESSION,
    READ_MODEL_STATUS_STALE,
    _int_or_default,
)


def _positive_leader_item(
    items: list[dict[str, object]],
    *,
    field: str,
) -> dict[str, object] | None:
    candidates = [
        item
        for item in items
        if isinstance(item.get(field), int) and _int_or_default(item.get(field)) > 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: _int_or_default(item.get(field)))


def _improvement_leader_item(items: list[dict[str, object]]) -> dict[str, object] | None:
    candidates = [
        item for item in items if _int_or_default(item.get("improvement_score")) > 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: _int_or_default(item.get("improvement_score")))


def _build_watchlist_item_from_overview(
    item: dict[str, object],
) -> dict[str, object] | None:
    status = str(item.get("status") or "").strip().lower()
    if status not in {
        READ_MODEL_STATUS_MISSING,
        READ_MODEL_STATUS_STALE,
        READ_MODEL_STATUS_BUDGET,
    }:
        return None
    watch_kind_label = {
        READ_MODEL_STATUS_MISSING: "Missing snapshot",
        READ_MODEL_STATUS_STALE: "Stale snapshot",
        READ_MODEL_STATUS_BUDGET: "Budget exceeded",
    }[status]
    return {
        "id": f"snapshot:{item.get('id')}",
        "label": item.get("label"),
        "status": status,
        "status_label": item.get("status_label"),
        "watch_kind": status,
        "watch_kind_label": watch_kind_label,
        "source_mode": "snapshot",
        "source_mode_label": "Snapshot",
        "note": item.get("note"),
        "query_count": item.get("query_count"),
        "query_budget": item.get("query_budget"),
        "payload_bytes": item.get("payload_bytes"),
        "payload_budget": item.get("payload_budget"),
        "build_duration_ms": item.get("build_duration_ms"),
        "staleness_seconds": item.get("staleness_seconds"),
        "severity_score": _int_or_default(item.get("severity_score")),
    }


def _build_watchlist_item_from_drift(
    item: dict[str, object],
) -> dict[str, object] | None:
    status = str(item.get("status") or "").strip().lower()
    budget_regressed = bool(item.get("budget_regressed"))
    if status != READ_MODEL_STATUS_REGRESSION and not budget_regressed:
        return None
    watch_kind = "budget_regression" if budget_regressed else READ_MODEL_STATUS_REGRESSION
    watch_kind_label = "Budget regression" if budget_regressed else "Live drift regression"
    return {
        "id": f"drift:{item.get('id')}",
        "label": item.get("label"),
        "status": status,
        "status_label": item.get("status_label"),
        "watch_kind": watch_kind,
        "watch_kind_label": watch_kind_label,
        "source_mode": "live",
        "source_mode_label": "Live compare",
        "note": item.get("note"),
        "query_count": item.get("live_query_count"),
        "query_budget": item.get("live_query_budget"),
        "payload_bytes": item.get("live_payload_bytes"),
        "payload_budget": item.get("live_payload_budget"),
        "build_duration_ms": item.get("live_build_duration_ms"),
        "staleness_seconds": None,
        "query_count_delta": item.get("query_count_delta"),
        "payload_bytes_delta": item.get("payload_bytes_delta"),
        "build_duration_ms_delta": item.get("build_duration_ms_delta"),
        "budget_regressed": budget_regressed,
        "severity_score": _int_or_default(item.get("severity_score")),
    }


def _sort_watchlist_items(items: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        items,
        key=lambda item: (
            _int_or_default(item.get("severity_score")),
            _int_or_default(item.get("query_count")),
            _int_or_default(item.get("payload_bytes")),
            _int_or_default(item.get("build_duration_ms")),
        ),
        reverse=True,
    )
