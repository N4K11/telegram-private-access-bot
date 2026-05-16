from __future__ import annotations

from app.services.web_admin_dashboard_read_model_core import (
    READ_MODEL_STATUS_BUDGET,
    READ_MODEL_STATUS_MISSING,
    READ_MODEL_STATUS_STALE,
)
from app.services.web_admin_dashboard_read_model_watchlist import _sort_watchlist_items


def _int_or_default(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return default


def _read_model_action_category_label(action_category: str) -> str:
    return {
        "snapshot": "Snapshot hygiene",
        "budget": "Budget pressure",
        "drift": "Live drift",
    }.get(str(action_category).strip().lower(), "Read-model action")


def _join_labels(items: list[str]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    return " + ".join(dict.fromkeys(cleaned))


def _recommended_read_model_action(
    item: dict[str, object],
    *,
    watch_kinds: set[str],
) -> tuple[str, str, str, str]:
    watch_kind = str(item.get("watch_kind") or "").strip().lower()
    query_count = _int_or_default(item.get("query_count"))
    query_budget = item.get("query_budget")
    payload_bytes = _int_or_default(item.get("payload_bytes"))
    payload_budget = item.get("payload_budget")
    query_count_delta = _int_or_default(item.get("query_count_delta"))
    payload_bytes_delta = _int_or_default(item.get("payload_bytes_delta"))
    build_duration_ms_delta = _int_or_default(item.get("build_duration_ms_delta"))
    query_over_budget = (
        query_budget is not None and query_count > _int_or_default(query_budget)
    )
    payload_over_budget = (
        payload_budget is not None and payload_bytes > _int_or_default(payload_budget)
    )
    if watch_kind == READ_MODEL_STATUS_MISSING:
        return (
            "materialize_snapshot",
            "Materialize snapshot",
            "snapshot",
            "Snapshot is missing. Force a refresh before relying on this summary.",
        )
    if watch_kind == READ_MODEL_STATUS_STALE:
        return (
            "refresh_snapshot",
            "Refresh snapshot cadence",
            "snapshot",
            "Snapshot is stale. Rebuild it and verify the scheduled cadence keeps up.",
        )
    if watch_kind in {READ_MODEL_STATUS_BUDGET, "budget_regression"}:
        if query_over_budget and payload_over_budget:
            return (
                "trim_query_and_payload",
                "Trim query and payload",
                "budget",
                "Both query count and payload size are over budget. "
                "Reduce joins and shrink the response shape together.",
            )
        if query_over_budget:
            return (
                "trim_query_path",
                "Trim query path",
                "budget",
                "Query count is over budget. Collapse duplicate reads or "
                "push more data to the snapshot layer.",
            )
        return (
            "trim_payload",
            "Trim payload",
            "budget",
            "Payload size is over budget. Move secondary lists into lazy "
            "views or cut summary detail.",
        )
    if (
        "budget_regression" in watch_kinds
        or payload_over_budget
        or payload_bytes_delta >= max(1_024, query_count_delta * 512)
    ):
        return (
            "review_payload_growth",
            "Review payload growth",
            "drift",
            "Live payload grew materially above the stored snapshot baseline. "
            "Check new fields and oversized lists.",
        )
    if query_count_delta > 0:
        return (
            "review_query_growth",
            "Review query growth",
            "drift",
            "Live query count drifted up. Inspect fresh joins, nested "
            "lookups, and missing snapshot reuse.",
        )
    if build_duration_ms_delta > 0:
        return (
            "review_build_latency",
            "Review build latency",
            "drift",
            "Build time drifted up even without a strong query signal. "
            "Inspect serializer work and Python-side aggregation.",
        )
    return (
        "review_live_drift",
        "Review live drift",
        "drift",
        "Live build drifted above the snapshot baseline. Compare the latest "
        "live path against the stored read-model shape.",
    )


def _build_action_digest_items(
    watchlist_items: list[dict[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for item in watchlist_items:
        label = str(item.get("label") or "Read model").strip() or "Read model"
        grouped.setdefault(label, []).append(item)

    action_items: list[dict[str, object]] = []
    for label, grouped_items in grouped.items():
        sorted_items = _sort_watchlist_items(grouped_items)
        primary = sorted_items[0]
        watch_kinds = {
            str(item.get("watch_kind") or "").strip().lower()
            for item in sorted_items
            if item.get("watch_kind")
        }
        source_mode_labels = sorted(
            {
                str(item.get("source_mode_label") or "").strip()
                for item in sorted_items
                if str(item.get("source_mode_label") or "").strip()
            }
        )
        watch_kind_labels = sorted(
            {
                str(item.get("watch_kind_label") or "").strip()
                for item in sorted_items
                if str(item.get("watch_kind_label") or "").strip()
            }
        )
        action_key, action_label, action_category, action_note = (
            _recommended_read_model_action(
                primary,
                watch_kinds=watch_kinds,
            )
        )
        action_items.append(
            {
                "id": f"action:{label.lower().replace(' ', '_')}",
                "label": label,
                "issue_count": len(sorted_items),
                "issue_labels": watch_kind_labels,
                "issue_summary_label": _join_labels(watch_kind_labels),
                "primary_issue_key": primary.get("watch_kind"),
                "primary_issue_label": primary.get("watch_kind_label"),
                "source_modes": source_mode_labels,
                "source_mode_label": _join_labels(source_mode_labels),
                "action_key": action_key,
                "action_label": action_label,
                "action_category": action_category,
                "action_category_label": _read_model_action_category_label(
                    action_category
                ),
                "action_note": action_note,
                "status": primary.get("status"),
                "status_label": primary.get("status_label"),
                "query_count": primary.get("query_count"),
                "query_budget": primary.get("query_budget"),
                "payload_bytes": primary.get("payload_bytes"),
                "payload_budget": primary.get("payload_budget"),
                "build_duration_ms": primary.get("build_duration_ms"),
                "staleness_seconds": primary.get("staleness_seconds"),
                "query_count_delta": primary.get("query_count_delta"),
                "payload_bytes_delta": primary.get("payload_bytes_delta"),
                "build_duration_ms_delta": primary.get("build_duration_ms_delta"),
                "severity_score": _int_or_default(primary.get("severity_score"))
                + (len(sorted_items) * 1_000),
            }
        )
    return sorted(
        action_items,
        key=lambda item: (
            _int_or_default(item.get("severity_score")),
            _int_or_default(item.get("issue_count")),
            _int_or_default(item.get("query_count")),
            _int_or_default(item.get("payload_bytes")),
        ),
        reverse=True,
    )
