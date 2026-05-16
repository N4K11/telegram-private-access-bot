from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.web_admin_dashboard_limits import (
    ADMIN_DETAIL_DEFAULT_LIMIT,
    clamp_admin_detail_limit,
)
from app.services.web_admin_dashboard_read_model_actions import _with_overview_focus
from app.services.web_admin_dashboard_read_model_descriptors import _all_descriptors
from app.services.web_admin_dashboard_read_model_serializers import (
    READ_MODEL_VIEW_LABELS,
    READ_MODEL_VIEW_OVERVIEW,
    _available_read_model_views,
    _build_model_item,
    _int_or_default,
    _leader_item,
    _sort_items,
)
from app.services.web_admin_dashboard_read_model_store import (
    _load_snapshot_payload_lookups,
    _lookup_descriptor_snapshot,
)
from app.utils.datetime import ensure_aware_utc, format_datetime


async def _build_web_admin_read_models_payload_live(
    session: AsyncSession,
    *,
    settings: Settings,
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

    items = []
    for descriptor in descriptors:
        payload, generated_at = _lookup_descriptor_snapshot(
            descriptor,
            analytics_lookup=analytics_lookup,
            lifecycle_lookup=lifecycle_lookup,
            support_lookup=support_lookup,
        )
        items.append(
            _build_model_item(
                descriptor,
                payload=payload,
                generated_at=generated_at,
                now=current_time,
                settings=settings,
            )
        )

    sorted_items = _sort_items(items)
    missing_count = sum(1 for item in sorted_items if item["is_missing"])
    stale_count = sum(1 for item in sorted_items if item["is_stale"])
    budget_exceeded_count = sum(1 for item in sorted_items if item["query_budget_ok"] is False)
    available_count = len(sorted_items) - missing_count
    total_payload_bytes = sum(_int_or_default(item.get("payload_bytes")) for item in sorted_items)
    total_query_count = sum(_int_or_default(item.get("query_count")) for item in sorted_items)
    top_attention_item = sorted_items[0] if sorted_items else None
    top_payload_item = _leader_item(sorted_items, field="payload_bytes")
    top_query_item = _leader_item(sorted_items, field="query_count")
    top_build_item = _leader_item(sorted_items, field="build_duration_ms")
    top_stale_item = _leader_item(sorted_items, field="staleness_seconds")

    overview_payload = {
        "view": READ_MODEL_VIEW_OVERVIEW,
        "view_label": READ_MODEL_VIEW_LABELS[READ_MODEL_VIEW_OVERVIEW],
        "available_views": _available_read_model_views(),
        "generated_at_label": format_datetime(current_time, settings.timezone),
        "limit": normalized_limit,
        "tracked_count": len(sorted_items),
        "available_count": available_count,
        "missing_count": missing_count,
        "stale_count": stale_count,
        "budget_exceeded_count": budget_exceeded_count,
        "total_payload_bytes": total_payload_bytes,
        "total_query_count": total_query_count,
        "top_attention_item": top_attention_item,
        "top_payload_item": top_payload_item,
        "top_query_item": top_query_item,
        "top_build_item": top_build_item,
        "top_stale_item": top_stale_item,
        "items": sorted_items[:normalized_limit],
    }
    return _with_overview_focus(overview_payload)
