from __future__ import annotations

from app.services.admin_read_model_reporting import (
    build_admin_read_model_focus_payload,
    build_admin_read_model_operator_digest_payload,
    build_admin_read_model_snapshot_digest_payload,
)
from app.services.web_admin_dashboard_limits import clamp_admin_detail_limit
from app.services.web_admin_dashboard_read_model_action_digest import (
    _build_action_digest_items as _build_action_digest_items,
)
from app.services.web_admin_dashboard_read_model_action_digest import (
    _join_labels as _join_labels,
)
from app.services.web_admin_dashboard_read_model_action_digest import (
    _read_model_action_category_label as _read_model_action_category_label,
)
from app.services.web_admin_dashboard_read_model_action_digest import (
    _recommended_read_model_action as _recommended_read_model_action,
)
from app.services.web_admin_dashboard_read_model_watchlist import (
    _build_watchlist_item_from_drift as _build_watchlist_item_from_drift,
)
from app.services.web_admin_dashboard_read_model_watchlist import (
    _build_watchlist_item_from_overview as _build_watchlist_item_from_overview,
)
from app.services.web_admin_dashboard_read_model_watchlist import (
    _improvement_leader_item as _improvement_leader_item,
)
from app.services.web_admin_dashboard_read_model_watchlist import (
    _positive_leader_item as _positive_leader_item,
)
from app.services.web_admin_dashboard_read_model_watchlist import (
    _sort_watchlist_items as _sort_watchlist_items,
)

READ_MODEL_VIEW_OVERVIEW = "overview"
READ_MODEL_VIEW_DRIFT = "drift"
READ_MODEL_VIEW_WATCHLIST = "watchlist"
READ_MODEL_VIEW_ACTIONS = "actions"
READ_MODEL_STATUS_STALE = "stale"
READ_MODEL_STATUS_BUDGET = "budget"
READ_MODEL_STATUS_MISSING = "missing"
READ_MODEL_STATUS_REGRESSION = "regression"

READ_MODEL_VIEW_LABELS = {
    READ_MODEL_VIEW_OVERVIEW: "Read-model diagnostics",
    READ_MODEL_VIEW_DRIFT: "Snapshot vs live drift",
    READ_MODEL_VIEW_WATCHLIST: "Read-model watchlist",
    READ_MODEL_VIEW_ACTIONS: "Read-model action digest",
}


def _int_or_default(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return default


def _available_read_model_views() -> list[dict[str, str]]:
    return [
        {"key": key, "label": label}
        for key, label in READ_MODEL_VIEW_LABELS.items()
    ]

def _build_read_model_actions_payload_from_watchlist(
    watchlist_payload: dict[str, object],
    *,
    limit: int,
) -> dict[str, object]:
    normalized_limit = clamp_admin_detail_limit(limit)
    watchlist_items = [
        item
        for item in watchlist_payload.get("items", [])
        if isinstance(item, dict)
    ]
    action_items = _build_action_digest_items(watchlist_items)
    snapshot_action_count = sum(
        1 for item in action_items if item["action_category"] == "snapshot"
    )
    budget_action_count = sum(
        1 for item in action_items if item["action_category"] == "budget"
    )
    drift_action_count = sum(
        1 for item in action_items if item["action_category"] == "drift"
    )
    top_action_item = action_items[0] if action_items else None
    top_snapshot_action_item = next(
        (item for item in action_items if item["action_category"] == "snapshot"),
        None,
    )
    top_budget_action_item = next(
        (item for item in action_items if item["action_category"] == "budget"),
        None,
    )
    top_drift_action_item = next(
        (item for item in action_items if item["action_category"] == "drift"),
        None,
    )
    payload = {
        "view": READ_MODEL_VIEW_ACTIONS,
        "view_label": READ_MODEL_VIEW_LABELS[READ_MODEL_VIEW_ACTIONS],
        "available_views": _available_read_model_views(),
        "limit": normalized_limit,
        "tracked_count": _int_or_default(watchlist_payload.get("tracked_count")),
        "surface_count": len(action_items),
        "alert_item_count": _int_or_default(watchlist_payload.get("alert_item_count")),
        "snapshot_action_count": snapshot_action_count,
        "budget_action_count": budget_action_count,
        "drift_action_count": drift_action_count,
        "top_action_item": top_action_item,
        "top_snapshot_action_item": top_snapshot_action_item,
        "top_budget_action_item": top_budget_action_item,
        "top_drift_action_item": top_drift_action_item,
        "items": action_items[:normalized_limit],
    }
    for field in (
        "source",
        "generated_at",
        "generated_at_label",
        "staleness_seconds",
        "build_duration_ms",
        "query_count",
        "query_budget",
        "query_budget_ok",
        "payload_bytes",
        "payload_budget",
        "payload_budget_ok",
    ):
        if field in watchlist_payload:
            payload[field] = watchlist_payload.get(field)
    return payload


def _apply_read_models_limit(
    payload: dict[str, object],
    *,
    limit: int,
) -> dict[str, object]:
    normalized_limit = clamp_admin_detail_limit(limit)
    adjusted_payload = dict(payload)
    items = adjusted_payload.get("items", [])
    if isinstance(items, list):
        adjusted_payload["items"] = items[:normalized_limit]
    adjusted_payload["limit"] = normalized_limit
    return adjusted_payload


def _with_read_model_focus(
    payload: dict[str, object],
    *,
    watchlist_payload: dict[str, object] | None = None,
    action_payload: dict[str, object] | None = None,
    drift_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    adjusted_payload = dict(payload)
    focus_summary = build_admin_read_model_focus_payload(
        watchlist_payload=watchlist_payload,
        action_payload=action_payload,
        drift_payload=drift_payload,
    )
    if focus_summary is not None:
        adjusted_payload["focus_summary"] = focus_summary
    operator_digest_summary = build_admin_read_model_operator_digest_payload(
        watchlist_payload=watchlist_payload,
        action_payload=action_payload,
        drift_payload=drift_payload,
    )
    if operator_digest_summary is not None:
        adjusted_payload["operator_digest_summary"] = operator_digest_summary
    return adjusted_payload


def _with_overview_focus(payload: dict[str, object]) -> dict[str, object]:
    watchlist_payload = _build_web_admin_read_model_watchlist_from_snapshot_payload(
        payload,
        limit=clamp_admin_detail_limit(50),
    )
    action_payload = _build_read_model_actions_payload_from_watchlist(
        watchlist_payload,
        limit=clamp_admin_detail_limit(50),
    )
    adjusted_payload = _with_read_model_focus(
        payload,
        watchlist_payload=watchlist_payload,
        action_payload=action_payload,
    )
    digest_summary = build_admin_read_model_snapshot_digest_payload(
        adjusted_payload,
        watchlist_payload=watchlist_payload,
        action_payload=action_payload,
    )
    if digest_summary is not None:
        adjusted_payload["digest_summary"] = digest_summary
    return adjusted_payload

def _build_web_admin_read_model_watchlist_from_snapshot_payload(
    payload: dict[str, object],
    *,
    limit: int,
) -> dict[str, object]:
    normalized_limit = clamp_admin_detail_limit(limit)
    source_items = payload.get("items", [])
    watchlist_items = []
    if isinstance(source_items, list):
        for item in source_items:
            if not isinstance(item, dict):
                continue
            watch_item = _build_watchlist_item_from_overview(item)
            if watch_item is not None:
                watchlist_items.append(watch_item)
    sorted_items = _sort_watchlist_items(watchlist_items)
    missing_count = sum(
        1 for item in sorted_items if item["watch_kind"] == READ_MODEL_STATUS_MISSING
    )
    stale_count = sum(
        1 for item in sorted_items if item["watch_kind"] == READ_MODEL_STATUS_STALE
    )
    budget_count = sum(
        1
        for item in sorted_items
        if item["watch_kind"] in {READ_MODEL_STATUS_BUDGET, "budget_regression"}
    )
    top_attention_item = sorted_items[0] if sorted_items else None
    watchlist_payload = {
        "view": READ_MODEL_VIEW_WATCHLIST,
        "view_label": READ_MODEL_VIEW_LABELS[READ_MODEL_VIEW_WATCHLIST],
        "available_views": _available_read_model_views(),
        "source": payload.get("source"),
        "generated_at": payload.get("generated_at"),
        "generated_at_label": payload.get("generated_at_label"),
        "staleness_seconds": payload.get("staleness_seconds"),
        "build_duration_ms": payload.get("build_duration_ms"),
        "query_count": payload.get("query_count"),
        "query_budget": payload.get("query_budget"),
        "query_budget_ok": payload.get("query_budget_ok"),
        "payload_bytes": payload.get("payload_bytes"),
        "payload_budget": payload.get("payload_budget"),
        "payload_budget_ok": payload.get("payload_budget_ok"),
        "limit": normalized_limit,
        "tracked_count": _int_or_default(payload.get("tracked_count")),
        "alert_item_count": len(sorted_items),
        "missing_count": missing_count,
        "stale_count": stale_count,
        "budget_exceeded_count": budget_count,
        "regression_count": 0,
        "top_attention_item": top_attention_item,
        "items": sorted_items[:normalized_limit],
    }
    return _with_read_model_focus(
        watchlist_payload,
        watchlist_payload=watchlist_payload,
    )
