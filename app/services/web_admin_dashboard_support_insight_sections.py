from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.admin_read_models import (
    PAYLOAD_BUDGET_ADMIN_SUPPORT_INSIGHTS,
    QUERY_BUDGET_ADMIN_SUPPORT_INSIGHTS,
    load_support_queue_fact_payload,
    normalize_read_model_source,
    timed_read_model_payload,
)
from app.services.support import build_admin_support_inbox
from app.services.web_admin_dashboard_limits import (
    ADMIN_DETAIL_DEFAULT_LIMIT,
    clamp_admin_detail_limit,
)
from app.services.web_admin_dashboard_support_insight_serializers import (
    _serialize_support_insights,
)
from app.services.web_admin_dashboard_support_insight_views import (
    SUPPORT_INSIGHT_VIEWS as SUPPORT_INSIGHT_VIEWS,
)
from app.services.web_admin_dashboard_support_insight_views import (
    _normalize_support_insight_view as _normalize_support_insight_view,
)
from app.services.web_admin_dashboard_support_insight_views import (
    _support_insight_items_for_view as _support_insight_items_for_view,
)
from app.utils.datetime import ensure_aware_utc, format_datetime, utcnow


async def build_web_admin_support_insights_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    view: str = "hotspots",
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
    now: datetime | None = None,
    source: str = "snapshot",
) -> dict[str, object]:
    del viewer_role
    current_time = ensure_aware_utc(now or utcnow())
    normalized_view = _normalize_support_insight_view(view)
    normalized_source = normalize_read_model_source(source)
    if normalized_source != "live":
        snapshot_payload = await load_support_queue_fact_payload(
            session,
            view_key=normalized_view,
            now=current_time,
        )
        if snapshot_payload is not None:
            return snapshot_payload
    return await timed_read_model_payload(
        lambda: _build_web_admin_support_insights_payload_live(
            session,
            settings=settings,
            view=normalized_view,
            limit=limit,
            now=current_time,
        ),
        session=session,
        query_budget=QUERY_BUDGET_ADMIN_SUPPORT_INSIGHTS,
        payload_budget=PAYLOAD_BUDGET_ADMIN_SUPPORT_INSIGHTS,
        now=current_time,
    )


async def _build_web_admin_support_insights_payload_live(
    session: AsyncSession,
    *,
    settings: Settings,
    view: str = "hotspots",
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
    now: datetime | None = None,
    support_inbox=None,
) -> dict[str, object]:
    current_time = ensure_aware_utc(now or utcnow())
    normalized_view = _normalize_support_insight_view(view)
    normalized_limit = clamp_admin_detail_limit(limit)
    inbox = support_inbox or await build_admin_support_inbox(
        session,
        status="open",
        limit=1,
        now=current_time,
    )
    support_insights = _serialize_support_insights(inbox.insights)
    all_items = _support_insight_items_for_view(
        support_insights,
        view=normalized_view,
    )
    return {
        "view": normalized_view,
        "view_label": SUPPORT_INSIGHT_VIEWS[normalized_view],
        "generated_at_label": format_datetime(current_time, settings.timezone),
        "available_views": [
            {"key": key, "label": label}
            for key, label in SUPPORT_INSIGHT_VIEWS.items()
        ],
        "limit": normalized_limit,
        "total_items": len(all_items),
        "open_count": inbox.open_count,
        "awaiting_admin_count": inbox.awaiting_admin_count,
        "awaiting_user_count": inbox.awaiting_user_count,
        "stale_open_count": inbox.stale_open_count,
        "high_priority_open_count": inbox.high_priority_open_count,
        "sla_warning_count": inbox.sla_warning_count,
        "sla_breach_count": inbox.sla_breach_count,
        "recent_close_summary": support_insights.get("recent_close_summary", {}),
        "trend_summary": support_insights.get("trend_summary", {}),
        "pack_outcome_summary": support_insights.get("pack_outcome_summary", {}),
        "sla_hotspot_summary": support_insights.get("sla_hotspot_summary", {}),
        "sla_queue_summary": support_insights.get("sla_queue_summary", {}),
        "sla_action_summary": support_insights.get("sla_action_summary", {}),
        "action_lane_summary": support_insights.get("action_lane_summary", {}),
        "next_action_summary": support_insights.get("next_action_summary", {}),
        "action_route_summary": support_insights.get("action_route_summary", {}),
        "triage_queue_summary": support_insights.get("triage_queue_summary", {}),
        "triage_plan_summary": support_insights.get("triage_plan_summary", {}),
        "triage_confirm_summary": support_insights.get("triage_confirm_summary", {}),
        "triage_apply_summary": support_insights.get("triage_apply_summary", {}),
        "triage_apply_route_summary": support_insights.get(
            "triage_apply_route_summary",
            {},
        ),
        "triage_apply_actor_summary": support_insights.get(
            "triage_apply_actor_summary",
            {},
        ),
        "triage_apply_reply_summary": support_insights.get(
            "triage_apply_reply_summary",
            {},
        ),
        "triage_apply_actor_reply_summary": support_insights.get(
            "triage_apply_actor_reply_summary",
            {},
        ),
        "triage_apply_route_actor_summary": support_insights.get(
            "triage_apply_route_actor_summary",
            {},
        ),
        "triage_apply_reply_pack_summary": support_insights.get(
            "triage_apply_reply_pack_summary",
            {},
        ),
        "triage_apply_route_reply_actor_summary": support_insights.get(
            "triage_apply_route_reply_actor_summary",
            {},
        ),
        "triage_apply_focus_summary": support_insights.get(
            "triage_apply_focus_summary",
            {},
        ),
        "triage_apply_effectiveness_summary": support_insights.get(
            "triage_apply_effectiveness_summary",
            {},
        ),
        "escalation_lane_summary": support_insights.get(
            "escalation_lane_summary",
            {},
        ),
        "escalation_action_summary": support_insights.get(
            "escalation_action_summary",
            {},
        ),
        "priority_focus_summary": support_insights.get("priority_focus_summary", {}),
        "escalation_watchlist_summary": support_insights.get(
            "escalation_watchlist_summary",
            {},
        ),
        "escalation_trend_summary": support_insights.get(
            "escalation_trend_summary",
            {},
        ),
        "operator_action_trend_summary": support_insights.get(
            "operator_action_trend_summary",
            {},
        ),
        "items": all_items[:normalized_limit],
    }
