from __future__ import annotations

from app.services.admin_read_model_reporting_models import (
    AdminReadModelActionItemSummary,
    AdminReadModelActionSummary,
    AdminReadModelAlertSummary,
    AdminReadModelDriftItemSummary,
    AdminReadModelDriftSummary,
    AdminReadModelWatchItemSummary,
    AdminReadModelWatchlistSummary,
)


def _int_field(payload: dict[str, object], key: str) -> int:
    try:
        return max(0, int(payload.get(key) or 0))
    except (TypeError, ValueError):
        return 0


def _str_field(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _item_field(
    payload: dict[str, object],
    item_key: str,
    value_key: str,
) -> str | None:
    item = payload.get(item_key)
    if not isinstance(item, dict):
        return None
    value = item.get(value_key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_alert_summary(payload: dict[str, object]) -> AdminReadModelAlertSummary:
    missing_count = _int_field(payload, "missing_count")
    stale_count = _int_field(payload, "stale_count")
    budget_exceeded_count = _int_field(payload, "budget_exceeded_count")
    return AdminReadModelAlertSummary(
        source=str(payload.get("source") or "snapshot"),
        generated_at_label=_str_field(payload, "generated_at_label"),
        staleness_seconds=_int_field(payload, "staleness_seconds"),
        tracked_count=_int_field(payload, "tracked_count"),
        available_count=_int_field(payload, "available_count"),
        missing_count=missing_count,
        stale_count=stale_count,
        budget_exceeded_count=budget_exceeded_count,
        alert_count=missing_count + stale_count + budget_exceeded_count,
        top_attention_label=_item_field(payload, "top_attention_item", "label"),
        top_attention_status_label=_item_field(
            payload,
            "top_attention_item",
            "status_label",
        ),
        top_attention_note=_item_field(payload, "top_attention_item", "note"),
    )


def _build_drift_summary(payload: dict[str, object]) -> AdminReadModelDriftSummary:
    raw_items = payload.get("items", [])
    top_items: list[AdminReadModelDriftItemSummary] = []
    if isinstance(raw_items, list):
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            label = _str_field(item, "label")
            if not label:
                continue
            query_count_delta = _int_field(item, "query_count_delta")
            payload_bytes_delta = _int_field(item, "payload_bytes_delta")
            build_duration_ms_delta = _int_field(item, "build_duration_ms_delta")
            budget_regressed = bool(item.get("budget_regressed"))
            has_regression = (
                budget_regressed
                or query_count_delta > 0
                or payload_bytes_delta > 0
                or build_duration_ms_delta > 0
            )
            if not has_regression:
                continue
            top_items.append(
                AdminReadModelDriftItemSummary(
                    label=label,
                    note=_str_field(item, "note"),
                    query_count_delta=query_count_delta,
                    payload_bytes_delta=payload_bytes_delta,
                    build_duration_ms_delta=build_duration_ms_delta,
                    budget_regressed=budget_regressed,
                )
            )
            if len(top_items) >= 3:
                break
    return AdminReadModelDriftSummary(
        source=str(payload.get("source") or "live"),
        generated_at_label=_str_field(payload, "generated_at_label"),
        staleness_seconds=_int_field(payload, "staleness_seconds"),
        compared_count=_int_field(payload, "compared_count"),
        missing_snapshot_count=_int_field(payload, "missing_snapshot_count"),
        regression_count=_int_field(payload, "regression_count"),
        improvement_count=_int_field(payload, "improvement_count"),
        budget_regression_count=_int_field(payload, "budget_regression_count"),
        query_regression_count=_int_field(payload, "query_regression_count"),
        payload_regression_count=_int_field(payload, "payload_regression_count"),
        build_regression_count=_int_field(payload, "build_regression_count"),
        top_regression_label=_item_field(payload, "top_regression_item", "label"),
        top_regression_note=_item_field(payload, "top_regression_item", "note"),
        top_budget_regression_label=_item_field(
            payload,
            "top_budget_regression_item",
            "label",
        ),
        top_query_regression_label=_item_field(
            payload,
            "top_query_regression_item",
            "label",
        ),
        top_payload_regression_label=_item_field(
            payload,
            "top_payload_regression_item",
            "label",
        ),
        top_build_regression_label=_item_field(
            payload,
            "top_build_regression_item",
            "label",
        ),
        top_items=tuple(top_items),
    )


def _build_action_summary(payload: dict[str, object]) -> AdminReadModelActionSummary:
    raw_items = payload.get("items", [])
    top_items: list[AdminReadModelActionItemSummary] = []
    if isinstance(raw_items, list):
        for item in raw_items[:3]:
            if not isinstance(item, dict):
                continue
            label = _str_field(item, "label")
            if not label:
                continue
            top_items.append(
                AdminReadModelActionItemSummary(
                    label=label,
                    action_label=_str_field(item, "action_label"),
                    action_note=_str_field(item, "action_note"),
                    issue_summary_label=_str_field(item, "issue_summary_label"),
                    action_category_label=_str_field(item, "action_category_label"),
                )
            )
    return AdminReadModelActionSummary(
        source=str(payload.get("source") or "snapshot"),
        generated_at_label=_str_field(payload, "generated_at_label"),
        staleness_seconds=_int_field(payload, "staleness_seconds"),
        tracked_count=_int_field(payload, "tracked_count"),
        surface_count=_int_field(payload, "surface_count"),
        alert_item_count=_int_field(payload, "alert_item_count"),
        snapshot_action_count=_int_field(payload, "snapshot_action_count"),
        budget_action_count=_int_field(payload, "budget_action_count"),
        drift_action_count=_int_field(payload, "drift_action_count"),
        top_action_label=_item_field(payload, "top_action_item", "label"),
        top_action_note=_item_field(payload, "top_action_item", "action_note"),
        top_budget_action_label=_item_field(
            payload,
            "top_budget_action_item",
            "label",
        ),
        top_drift_action_label=_item_field(
            payload,
            "top_drift_action_item",
            "label",
        ),
        top_items=tuple(top_items),
    )


def _build_watchlist_summary(payload: dict[str, object]) -> AdminReadModelWatchlistSummary:
    raw_items = payload.get("items", [])
    top_items: list[AdminReadModelWatchItemSummary] = []
    if isinstance(raw_items, list):
        for item in raw_items[:3]:
            if not isinstance(item, dict):
                continue
            label = _str_field(item, "label")
            if not label:
                continue
            top_items.append(
                AdminReadModelWatchItemSummary(
                    label=label,
                    watch_kind_label=_str_field(item, "watch_kind_label"),
                    source_mode_label=_str_field(item, "source_mode_label"),
                    note=_str_field(item, "note"),
                    status_label=_str_field(item, "status_label"),
                )
            )
    return AdminReadModelWatchlistSummary(
        source=str(payload.get("source") or "snapshot"),
        generated_at_label=_str_field(payload, "generated_at_label"),
        staleness_seconds=_int_field(payload, "staleness_seconds"),
        tracked_count=_int_field(payload, "tracked_count"),
        alert_item_count=_int_field(payload, "alert_item_count"),
        missing_count=_int_field(payload, "missing_count"),
        stale_count=_int_field(payload, "stale_count"),
        budget_exceeded_count=_int_field(payload, "budget_exceeded_count"),
        regression_count=_int_field(payload, "regression_count"),
        top_attention_label=_item_field(payload, "top_attention_item", "label"),
        top_attention_kind_label=_item_field(
            payload,
            "top_attention_item",
            "watch_kind_label",
        ),
        top_attention_note=_item_field(payload, "top_attention_item", "note"),
        top_regression_label=_item_field(payload, "top_regression_item", "label"),
        top_budget_label=_item_field(payload, "top_budget_item", "label"),
        top_items=tuple(top_items),
    )
