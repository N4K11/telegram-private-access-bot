# ruff: noqa: E501
from __future__ import annotations

from app.services.support import (
    support_canned_reply_pack_label,
    support_canned_reply_pack_titles,
    support_category_label,
    support_priority_label,
)
from app.services.support_catalog import SUPPORT_WAITING_STATE_LABELS
from app.services.web_admin_dashboard_support_action_insight_serializers import (
    _build_support_action_lane_summary as _build_support_action_lane_summary,
)
from app.services.web_admin_dashboard_support_action_insight_serializers import (
    _build_support_action_route_summary as _build_support_action_route_summary,
)
from app.services.web_admin_dashboard_support_action_insight_serializers import (
    _build_support_next_action_summary as _build_support_next_action_summary,
)
from app.services.web_admin_dashboard_support_action_insight_serializers import (
    _build_support_sla_action_summary as _build_support_sla_action_summary,
)
from app.services.web_admin_dashboard_support_action_insight_serializers import (
    _build_support_sla_hotspot_summary as _build_support_sla_hotspot_summary,
)
from app.services.web_admin_dashboard_support_action_insight_serializers import (
    _build_support_sla_queue_summary as _build_support_sla_queue_summary,
)
from app.services.web_admin_dashboard_support_action_insight_serializers import (
    _serialize_support_action_lanes as _serialize_support_action_lanes,
)
from app.services.web_admin_dashboard_support_action_insight_serializers import (
    _serialize_support_action_routes as _serialize_support_action_routes,
)
from app.services.web_admin_dashboard_support_action_insight_serializers import (
    _serialize_support_next_action_queue as _serialize_support_next_action_queue,
)
from app.services.web_admin_dashboard_support_action_insight_serializers import (
    _serialize_support_sla_action_queue as _serialize_support_sla_action_queue,
)
from app.services.web_admin_dashboard_support_action_insight_serializers import (
    _serialize_support_sla_actions as _serialize_support_sla_actions,
)
from app.services.web_admin_dashboard_support_action_insight_serializers import (
    _serialize_support_sla_hotspots as _serialize_support_sla_hotspots,
)
from app.services.web_admin_dashboard_support_closed_insight_serializers import (
    _build_support_close_reason_trend_summary as _build_support_close_reason_trend_summary,
)
from app.services.web_admin_dashboard_support_closed_insight_serializers import (
    _build_support_pack_outcome_summary as _build_support_pack_outcome_summary,
)
from app.services.web_admin_dashboard_support_closed_insight_serializers import (
    _build_support_recent_close_summary as _build_support_recent_close_summary,
)
from app.services.web_admin_dashboard_support_closed_insight_serializers import (
    _serialize_support_canned_reply_pack_outcomes as _serialize_support_canned_reply_pack_outcomes,
)
from app.services.web_admin_dashboard_support_closed_insight_serializers import (
    _serialize_support_close_reason_trends as _serialize_support_close_reason_trends,
)
from app.services.web_admin_dashboard_support_closed_insight_serializers import (
    _serialize_support_close_reason_windows as _serialize_support_close_reason_windows,
)
from app.services.web_admin_dashboard_support_closed_insight_serializers import (
    _serialize_support_distribution as _serialize_support_distribution,
)
from app.services.web_admin_dashboard_support_escalation_insight_serializers import (
    _build_support_escalation_action_summary as _build_support_escalation_action_summary,
)
from app.services.web_admin_dashboard_support_escalation_insight_serializers import (
    _build_support_escalation_lane_summary as _build_support_escalation_lane_summary,
)
from app.services.web_admin_dashboard_support_escalation_insight_serializers import (
    _build_support_escalation_trend_summary as _build_support_escalation_trend_summary,
)
from app.services.web_admin_dashboard_support_escalation_insight_serializers import (
    _build_support_escalation_watchlist_summary as _build_support_escalation_watchlist_summary,
)
from app.services.web_admin_dashboard_support_escalation_insight_serializers import (
    _build_support_operator_action_trend_summary as _build_support_operator_action_trend_summary,
)
from app.services.web_admin_dashboard_support_escalation_insight_serializers import (
    _build_support_priority_focus_summary as _build_support_priority_focus_summary,
)
from app.services.web_admin_dashboard_support_escalation_insight_serializers import (
    _serialize_support_escalation_actions as _serialize_support_escalation_actions,
)
from app.services.web_admin_dashboard_support_escalation_insight_serializers import (
    _serialize_support_escalation_lanes as _serialize_support_escalation_lanes,
)
from app.services.web_admin_dashboard_support_escalation_insight_serializers import (
    _serialize_support_escalation_trends as _serialize_support_escalation_trends,
)
from app.services.web_admin_dashboard_support_escalation_insight_serializers import (
    _serialize_support_escalation_watchlist as _serialize_support_escalation_watchlist,
)
from app.services.web_admin_dashboard_support_escalation_insight_serializers import (
    _serialize_support_operator_action_trends as _serialize_support_operator_action_trends,
)
from app.services.web_admin_dashboard_support_escalation_insight_serializers import (
    _serialize_support_priority_focus as _serialize_support_priority_focus,
)
from app.services.web_admin_dashboard_support_triage_apply_serializers import (
    _build_support_triage_summary_views as _build_support_triage_summary_views,
)
from app.services.web_admin_dashboard_support_triage_apply_serializers import (
    _build_support_triage_views as _build_support_triage_views,
)
from app.services.web_admin_dashboard_support_triage_apply_serializers import (
    _support_triage_apply_effectiveness_coverage_label as _support_triage_apply_effectiveness_coverage_label,
)
from app.services.web_admin_dashboard_support_triage_apply_serializers import (
    _support_triage_confirm_label as _support_triage_confirm_label,
)
from app.services.web_admin_dashboard_support_triage_apply_serializers import (
    _support_triage_confirm_note as _support_triage_confirm_note,
)
from app.services.web_admin_dashboard_support_triage_apply_serializers import (
    _support_triage_confirm_scope_label as _support_triage_confirm_scope_label,
)


def _serialize_support_insights(insights) -> dict[str, object]:
    open_total = sum(insights.priority_counts.values())
    priority_items = _serialize_support_distribution(
        insights.priority_counts,
        label_resolver=support_priority_label,
        total=open_total,
    )
    waiting_state_items = _serialize_support_distribution(
        insights.waiting_state_counts,
        label_resolver=lambda key: SUPPORT_WAITING_STATE_LABELS.get(key, key),
        total=sum(insights.waiting_state_counts.values()),
    )
    category_items = _serialize_support_distribution(
        insights.category_counts,
        label_resolver=support_category_label,
        total=sum(insights.category_counts.values()),
    )
    pack_total = sum(insights.canned_reply_pack_counts.values())
    canned_reply_packs = [
        {
            "key": key,
            "label": support_canned_reply_pack_label(key),
            "count": count,
            "share_percent": round((count / pack_total) * 100, 1) if pack_total else 0.0,
            "sample_titles": support_canned_reply_pack_titles(key),
        }
        for key, count in sorted(
            insights.canned_reply_pack_counts.items(),
            key=lambda item: (-item[1], support_canned_reply_pack_label(item[0])),
        )
    ]
    recent_close_reasons, previous_close_reasons = _serialize_support_close_reason_windows(insights)
    close_reason_trends = _serialize_support_close_reason_trends(insights)
    canned_reply_pack_outcomes = _serialize_support_canned_reply_pack_outcomes(insights)
    sla_hotspots = _serialize_support_sla_hotspots(insights, open_total=open_total)
    sla_actions = _serialize_support_sla_actions(insights, open_total=open_total)
    sla_action_queue = _serialize_support_sla_action_queue(
        insights,
        open_total=open_total,
    )
    action_lanes = _serialize_support_action_lanes(insights, open_total=open_total)
    next_action_queue = _serialize_support_next_action_queue(
        insights,
        open_total=open_total,
    )
    action_routes = _serialize_support_action_routes(insights, open_total=open_total)
    triage_views = _build_support_triage_views(insights, open_total=open_total)
    triage_queue = triage_views["triage_queue"]
    triage_plans = triage_views["triage_plans"]
    triage_confirm = triage_views["triage_confirm"]
    triage_apply_history = triage_views["triage_apply_history"]
    triage_apply_routes = triage_views["triage_apply_routes"]
    triage_apply_actors = triage_views["triage_apply_actors"]
    triage_apply_replies = triage_views["triage_apply_replies"]
    triage_apply_actor_replies = triage_views["triage_apply_actor_replies"]
    triage_apply_route_actors = triage_views["triage_apply_route_actors"]
    triage_apply_reply_packs = triage_views["triage_apply_reply_packs"]
    triage_apply_route_reply_actors = triage_views["triage_apply_route_reply_actors"]
    triage_apply_focus = triage_views["triage_apply_focus"]
    triage_apply_effectiveness = triage_views["triage_apply_effectiveness"]
    triage_summaries = _build_support_triage_summary_views(triage_views)
    escalation_lanes = _serialize_support_escalation_lanes(
        insights,
        open_total=open_total,
    )
    escalation_actions = _serialize_support_escalation_actions(
        insights,
        open_total=open_total,
    )
    priority_focus = _serialize_support_priority_focus(
        insights,
        open_total=open_total,
    )
    escalation_watchlist = _serialize_support_escalation_watchlist(
        insights,
        open_total=open_total,
    )
    escalation_trends = _serialize_support_escalation_trends(insights)
    operator_action_trends = _serialize_support_operator_action_trends(insights)
    return {
        "priority_counts": priority_items,
        "waiting_state_counts": waiting_state_items,
        "category_counts": category_items,
        "canned_reply_packs": canned_reply_packs,
        "recent_close_reasons": recent_close_reasons,
        "previous_close_reasons": previous_close_reasons,
        "close_reason_trends": close_reason_trends,
        "canned_reply_pack_outcomes": canned_reply_pack_outcomes,
        "sla_hotspots": sla_hotspots,
        "sla_action_queue": sla_action_queue,
        "sla_actions": sla_actions,
        "action_lanes": action_lanes,
        "next_action_queue": next_action_queue,
        "action_routes": action_routes,
        "triage_queue": triage_queue,
        "triage_plans": triage_plans,
        "triage_confirm": triage_confirm,
        "triage_apply_history": triage_apply_history,
        "triage_apply_routes": triage_apply_routes,
        "triage_apply_actors": triage_apply_actors,
        "triage_apply_replies": triage_apply_replies,
        "triage_apply_actor_replies": triage_apply_actor_replies,
        "triage_apply_route_actors": triage_apply_route_actors,
        "triage_apply_reply_packs": triage_apply_reply_packs,
        "triage_apply_route_reply_actors": triage_apply_route_reply_actors,
        "triage_apply_focus": triage_apply_focus,
        "triage_apply_effectiveness": triage_apply_effectiveness,
        "escalation_lanes": escalation_lanes,
        "escalation_actions": escalation_actions,
        "priority_focus": priority_focus,
        "escalation_watchlist": escalation_watchlist,
        "escalation_trends": escalation_trends,
        "operator_action_trends": operator_action_trends,
        "recent_close_summary": _build_support_recent_close_summary(
            insights,
            recent_close_reasons,
        ),
        "trend_summary": _build_support_close_reason_trend_summary(close_reason_trends),
        "pack_outcome_summary": _build_support_pack_outcome_summary(
            insights,
            canned_reply_pack_outcomes,
        ),
        "sla_hotspot_summary": _build_support_sla_hotspot_summary(sla_hotspots),
        "sla_queue_summary": _build_support_sla_queue_summary(sla_action_queue),
        "sla_action_summary": _build_support_sla_action_summary(sla_actions),
        "action_lane_summary": _build_support_action_lane_summary(action_lanes),
        "next_action_summary": _build_support_next_action_summary(next_action_queue),
        "action_route_summary": _build_support_action_route_summary(action_routes),
        **triage_summaries,
        "escalation_lane_summary": _build_support_escalation_lane_summary(
            escalation_lanes,
        ),
        "escalation_action_summary": _build_support_escalation_action_summary(
            escalation_actions,
        ),
        "priority_focus_summary": _build_support_priority_focus_summary(
            priority_focus,
        ),
        "escalation_watchlist_summary": _build_support_escalation_watchlist_summary(
            escalation_watchlist,
        ),
        "escalation_trend_summary": _build_support_escalation_trend_summary(
            escalation_trends,
        ),
        "operator_action_trend_summary": _build_support_operator_action_trend_summary(
            operator_action_trends,
        ),
    }
