from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.web_admin_dashboard_limits import (
    ADMIN_DETAIL_DEFAULT_LIMIT,
    clamp_admin_detail_limit,
)
from app.services.web_admin_dashboard_read_model_actions import (
    _build_read_model_actions_payload_from_watchlist,
    _build_watchlist_item_from_drift,
    _build_watchlist_item_from_overview,
    _improvement_leader_item,
    _positive_leader_item,
    _sort_watchlist_items,
    _with_read_model_focus,
)
from app.services.web_admin_dashboard_read_model_descriptors import (
    _all_descriptors,
)
from app.services.web_admin_dashboard_read_model_live_descriptors import (
    _build_live_admin_analytics_text_body as _build_live_admin_analytics_text_body,
)
from app.services.web_admin_dashboard_read_model_live_descriptors import (
    _build_live_admin_analytics_text_payload as _build_live_admin_analytics_text_payload,
)
from app.services.web_admin_dashboard_read_model_live_descriptors import (
    _build_live_descriptor_payload as _build_live_descriptor_payload,
)
from app.services.web_admin_dashboard_read_model_live_overview import (
    _build_web_admin_read_models_payload_live as _build_web_admin_read_models_payload_live,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    READ_MODEL_STATUS_BUDGET,
    READ_MODEL_STATUS_IMPROVED,
    READ_MODEL_STATUS_MISSING,
    READ_MODEL_STATUS_REGRESSION,
    READ_MODEL_STATUS_STALE,
    READ_MODEL_VIEW_DRIFT,
    READ_MODEL_VIEW_LABELS,
    READ_MODEL_VIEW_WATCHLIST,
    _available_read_model_views,
    _build_drift_item,
    _build_model_item,
    _int_or_default,
    _sort_items,
)
from app.services.web_admin_dashboard_read_model_store import (
    _load_snapshot_payload_lookups,
    _lookup_descriptor_snapshot,
)
from app.utils.datetime import ensure_aware_utc, format_datetime


async def _build_web_admin_read_model_watchlist_payload_live(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    limit: int,
    now: datetime,
) -> dict[str, object]:
    current_time = ensure_aware_utc(now)
    normalized_limit = clamp_admin_detail_limit(limit)
    descriptors = _all_descriptors(settings)
    analytics_lookup, lifecycle_lookup, support_lookup = await _load_snapshot_payload_lookups(
        session,
        descriptors=descriptors,
        fact_date=current_time,
    )

    watchlist_items: list[dict[str, object]] = []
    for descriptor in descriptors:
        snapshot_payload, snapshot_generated_at = _lookup_descriptor_snapshot(
            descriptor,
            analytics_lookup=analytics_lookup,
            lifecycle_lookup=lifecycle_lookup,
            support_lookup=support_lookup,
        )
        overview_item = _build_model_item(
            descriptor,
            payload=snapshot_payload,
            generated_at=snapshot_generated_at,
            now=current_time,
            settings=settings,
        )
        overview_watch_item = _build_watchlist_item_from_overview(overview_item)
        if overview_watch_item is not None:
            watchlist_items.append(overview_watch_item)

        if snapshot_payload is None or snapshot_generated_at is None:
            continue
        drift_item = _build_drift_item(
            descriptor,
            snapshot_payload=snapshot_payload,
            snapshot_generated_at=snapshot_generated_at,
            live_payload=await _build_live_descriptor_payload(
                session,
                descriptor=descriptor,
                settings=settings,
                viewer_role=viewer_role,
                now=current_time,
            ),
            settings=settings,
            now=current_time,
        )
        drift_watch_item = _build_watchlist_item_from_drift(drift_item)
        if drift_watch_item is not None:
            watchlist_items.append(drift_watch_item)

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
    regression_count = sum(
        1 for item in sorted_items if item["watch_kind"] == READ_MODEL_STATUS_REGRESSION
    )
    top_attention_item = sorted_items[0] if sorted_items else None
    top_regression_item = next(
        (item for item in sorted_items if item["watch_kind"] == READ_MODEL_STATUS_REGRESSION),
        None,
    )
    top_budget_item = next(
        (
            item
            for item in sorted_items
            if item["watch_kind"] in {READ_MODEL_STATUS_BUDGET, "budget_regression"}
        ),
        None,
    )
    watchlist_payload = {
        "view": READ_MODEL_VIEW_WATCHLIST,
        "view_label": READ_MODEL_VIEW_LABELS[READ_MODEL_VIEW_WATCHLIST],
        "available_views": _available_read_model_views(),
        "generated_at_label": format_datetime(current_time, settings.timezone),
        "limit": normalized_limit,
        "tracked_count": len(descriptors),
        "alert_item_count": len(sorted_items),
        "missing_count": missing_count,
        "stale_count": stale_count,
        "budget_exceeded_count": budget_count,
        "regression_count": regression_count,
        "top_attention_item": top_attention_item,
        "top_regression_item": top_regression_item,
        "top_budget_item": top_budget_item,
        "items": sorted_items[:normalized_limit],
    }
    return _with_read_model_focus(
        watchlist_payload,
        watchlist_payload=watchlist_payload,
    )


async def _build_web_admin_read_model_actions_payload_live(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    limit: int,
    now: datetime,
) -> dict[str, object]:
    watchlist_payload = await _build_web_admin_read_model_watchlist_payload_live(
        session,
        settings=settings,
        viewer_role=viewer_role,
        limit=clamp_admin_detail_limit(50),
        now=now,
    )
    actions_payload = _build_read_model_actions_payload_from_watchlist(
        watchlist_payload,
        limit=limit,
    )
    return _with_read_model_focus(
        actions_payload,
        action_payload=actions_payload,
    )


async def _build_web_admin_read_model_drift_payload_live(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
    now: datetime,
) -> dict[str, object]:
    current_time = ensure_aware_utc(now)
    normalized_limit = clamp_admin_detail_limit(limit)
    descriptors = _all_descriptors(settings)
    analytics_lookup, lifecycle_lookup, support_lookup = await _load_snapshot_payload_lookups(
        session,
        descriptors=descriptors,
        fact_date=current_time,
    )

    items: list[dict[str, object]] = []
    for descriptor in descriptors:
        snapshot_payload, snapshot_generated_at = _lookup_descriptor_snapshot(
            descriptor,
            analytics_lookup=analytics_lookup,
            lifecycle_lookup=lifecycle_lookup,
            support_lookup=support_lookup,
        )
        live_payload = None
        if snapshot_payload is not None and snapshot_generated_at is not None:
            live_payload = await _build_live_descriptor_payload(
                session,
                descriptor=descriptor,
                settings=settings,
                viewer_role=viewer_role,
                now=current_time,
            )
        items.append(
            _build_drift_item(
                descriptor,
                snapshot_payload=snapshot_payload,
                snapshot_generated_at=snapshot_generated_at,
                live_payload=live_payload,
                settings=settings,
                now=current_time,
            )
        )

    sorted_items = _sort_items(items)
    missing_snapshot_count = sum(1 for item in sorted_items if item["snapshot_missing"])
    compared_count = len(sorted_items) - missing_snapshot_count
    regression_count = sum(
        1 for item in sorted_items if item["status"] == READ_MODEL_STATUS_REGRESSION
    )
    improvement_count = sum(
        1 for item in sorted_items if item["status"] == READ_MODEL_STATUS_IMPROVED
    )
    budget_regression_count = sum(1 for item in sorted_items if item["budget_regressed"])
    query_regression_count = sum(
        1 for item in sorted_items if _int_or_default(item.get("query_count_delta")) > 0
    )
    payload_regression_count = sum(
        1 for item in sorted_items if _int_or_default(item.get("payload_bytes_delta")) > 0
    )
    build_regression_count = sum(
        1 for item in sorted_items if _int_or_default(item.get("build_duration_ms_delta")) > 0
    )
    total_live_payload_bytes = sum(
        _int_or_default(item.get("live_payload_bytes")) for item in sorted_items
    )
    total_live_query_count = sum(
        _int_or_default(item.get("live_query_count")) for item in sorted_items
    )
    top_regression_item = next(
        (item for item in sorted_items if item["status"] == READ_MODEL_STATUS_REGRESSION),
        None,
    )
    top_improvement_item = _improvement_leader_item(sorted_items)
    top_query_regression_item = _positive_leader_item(sorted_items, field="query_count_delta")
    top_payload_regression_item = _positive_leader_item(sorted_items, field="payload_bytes_delta")
    top_build_regression_item = _positive_leader_item(
        sorted_items,
        field="build_duration_ms_delta",
    )
    top_budget_regression_item = next(
        (item for item in sorted_items if item["budget_regressed"]),
        None,
    )

    drift_payload = {
        "view": READ_MODEL_VIEW_DRIFT,
        "view_label": READ_MODEL_VIEW_LABELS[READ_MODEL_VIEW_DRIFT],
        "comparison_mode": "snapshot_vs_live",
        "available_views": _available_read_model_views(),
        "generated_at_label": format_datetime(current_time, settings.timezone),
        "limit": normalized_limit,
        "tracked_count": len(sorted_items),
        "compared_count": compared_count,
        "missing_snapshot_count": missing_snapshot_count,
        "regression_count": regression_count,
        "improvement_count": improvement_count,
        "budget_regression_count": budget_regression_count,
        "query_regression_count": query_regression_count,
        "payload_regression_count": payload_regression_count,
        "build_regression_count": build_regression_count,
        "total_live_payload_bytes": total_live_payload_bytes,
        "total_live_query_count": total_live_query_count,
        "top_regression_item": top_regression_item,
        "top_improvement_item": top_improvement_item,
        "top_query_regression_item": top_query_regression_item,
        "top_payload_regression_item": top_payload_regression_item,
        "top_build_regression_item": top_build_regression_item,
        "top_budget_regression_item": top_budget_regression_item,
        "items": sorted_items[:normalized_limit],
    }
    return _with_read_model_focus(
        drift_payload,
        drift_payload=drift_payload,
    )
