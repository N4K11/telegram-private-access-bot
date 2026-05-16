from __future__ import annotations

from app.services.support import (
    support_action_lane_label,
    support_canned_reply_pack_label,
    support_category_label,
    support_close_reason_label,
    support_escalation_lane_label,
    support_priority_label,
)


def _serialize_support_escalation_lanes(
    insights,
    *,
    open_total: int,
) -> list[dict[str, object]]:
    return [
        {
            "key": item.key,
            "label": support_escalation_lane_label(item.key),
            "count": item.count,
            "share_percent": round((item.count / open_total) * 100, 1)
            if open_total
            else 0.0,
            "high_priority_count": item.high_priority_count,
            "stale_count": item.stale_count,
            "sla_breach_count": item.sla_breach_count,
            "top_category": item.top_category,
            "top_category_label": support_category_label(item.top_category)
            if item.top_category
            else None,
        }
        for item in insights.escalation_lanes
    ]


def _serialize_support_escalation_actions(
    insights,
    *,
    open_total: int,
) -> list[dict[str, object]]:
    return [
        {
            "key": item.key,
            "label": (
                f"{support_escalation_lane_label(item.escalation_key)} -> "
                f"{support_action_lane_label(item.action_key)}"
            ),
            "escalation_key": item.escalation_key,
            "escalation_label": support_escalation_lane_label(item.escalation_key),
            "action_key": item.action_key,
            "action_label": support_action_lane_label(item.action_key),
            "count": item.count,
            "share_percent": round((item.count / open_total) * 100, 1)
            if open_total
            else 0.0,
            "high_priority_count": item.high_priority_count,
            "stale_count": item.stale_count,
            "sla_breach_count": item.sla_breach_count,
            "top_category": item.top_category,
            "top_category_label": support_category_label(item.top_category)
            if item.top_category
            else None,
        }
        for item in insights.escalation_actions
    ]


def _serialize_support_priority_focus(
    insights,
    *,
    open_total: int,
) -> list[dict[str, object]]:
    return [
        {
            "key": item.key,
            "label": support_priority_label(item.key),
            "count": item.count,
            "share_percent": round((item.count / open_total) * 100, 1)
            if open_total
            else 0.0,
            "awaiting_admin_count": item.awaiting_admin_count,
            "awaiting_user_count": item.awaiting_user_count,
            "stale_count": item.stale_count,
            "sla_warning_count": item.sla_warning_count,
            "sla_breach_count": item.sla_breach_count,
            "top_category": item.top_category,
            "top_category_label": support_category_label(item.top_category)
            if item.top_category
            else None,
            "top_action_lane": item.top_action_lane,
            "top_action_lane_label": support_action_lane_label(item.top_action_lane)
            if item.top_action_lane
            else None,
            "top_escalation_lane": item.top_escalation_lane,
            "top_escalation_lane_label": support_escalation_lane_label(
                item.top_escalation_lane,
            )
            if item.top_escalation_lane
            else None,
        }
        for item in insights.priority_focus
    ]


def _serialize_support_escalation_watchlist(
    insights,
    *,
    open_total: int,
) -> list[dict[str, object]]:
    return [
        {
            "key": item.key,
            "label": support_escalation_lane_label(item.key),
            "count": item.count,
            "share_percent": round((item.count / open_total) * 100, 1)
            if open_total
            else 0.0,
            "awaiting_admin_count": item.awaiting_admin_count,
            "awaiting_user_count": item.awaiting_user_count,
            "high_priority_count": item.high_priority_count,
            "stale_count": item.stale_count,
            "sla_breach_count": item.sla_breach_count,
            "top_priority": item.top_priority,
            "top_priority_label": support_priority_label(item.top_priority)
            if item.top_priority
            else None,
            "top_category": item.top_category,
            "top_category_label": support_category_label(item.top_category)
            if item.top_category
            else None,
            "top_action_lane": item.top_action_lane,
            "top_action_lane_label": support_action_lane_label(item.top_action_lane)
            if item.top_action_lane
            else None,
            "watch_score": item.watch_score,
            "note": item.note,
        }
        for item in insights.escalation_watchlist
    ]


def _serialize_support_escalation_trends(insights) -> list[dict[str, object]]:
    return [
        {
            "key": item.key,
            "label": support_escalation_lane_label(item.key),
            "current_count": item.current_count,
            "previous_count": item.previous_count,
            "delta": item.delta,
        }
        for item in insights.escalation_trends
    ]


def _serialize_support_operator_action_trends(insights) -> list[dict[str, object]]:
    return [
        {
            "key": item.key,
            "label": (
                f"{support_canned_reply_pack_label(item.pack_key)} -> "
                f"{support_action_lane_label(item.action_key)}"
            ),
            "pack_key": item.pack_key,
            "pack_label": support_canned_reply_pack_label(item.pack_key),
            "close_reason": item.close_reason,
            "close_reason_label": support_close_reason_label(item.close_reason),
            "action_key": item.action_key,
            "action_label": support_action_lane_label(item.action_key),
            "current_count": item.current_count,
            "previous_count": item.previous_count,
            "delta": item.delta,
            "note": item.note,
        }
        for item in insights.operator_action_trends
    ]


def _build_support_escalation_lane_summary(
    escalation_lanes: list[dict[str, object]],
) -> dict[str, object]:
    top_escalation_lane = escalation_lanes[0] if escalation_lanes else None
    return {
        "top_escalation_lane": top_escalation_lane["key"]
        if top_escalation_lane is not None
        else None,
        "top_escalation_lane_label": top_escalation_lane["label"]
        if top_escalation_lane is not None
        else None,
        "top_escalation_lane_count": top_escalation_lane["count"]
        if top_escalation_lane is not None
        else 0,
        "top_escalation_lane_share_percent": top_escalation_lane["share_percent"]
        if top_escalation_lane is not None
        else 0.0,
    }


def _build_support_escalation_action_summary(
    escalation_actions: list[dict[str, object]],
) -> dict[str, object]:
    top_escalation_action = escalation_actions[0] if escalation_actions else None
    return {
        "top_escalation_action": top_escalation_action["key"]
        if top_escalation_action is not None
        else None,
        "top_escalation_action_label": top_escalation_action["label"]
        if top_escalation_action is not None
        else None,
        "top_escalation_action_count": top_escalation_action["count"]
        if top_escalation_action is not None
        else 0,
        "top_escalation_action_share_percent": top_escalation_action["share_percent"]
        if top_escalation_action is not None
        else 0.0,
    }


def _build_support_priority_focus_summary(
    priority_focus: list[dict[str, object]],
) -> dict[str, object]:
    top_priority_focus = priority_focus[0] if priority_focus else None
    return {
        "top_priority": top_priority_focus["key"]
        if top_priority_focus is not None
        else None,
        "top_priority_label": top_priority_focus["label"]
        if top_priority_focus is not None
        else None,
        "top_priority_count": top_priority_focus["count"]
        if top_priority_focus is not None
        else 0,
        "top_priority_share_percent": top_priority_focus["share_percent"]
        if top_priority_focus is not None
        else 0.0,
        "top_priority_sla_breach_count": top_priority_focus["sla_breach_count"]
        if top_priority_focus is not None
        else 0,
    }


def _build_support_escalation_watchlist_summary(
    escalation_watchlist: list[dict[str, object]],
) -> dict[str, object]:
    top_escalation_watch = escalation_watchlist[0] if escalation_watchlist else None
    return {
        "top_watch_key": top_escalation_watch["key"]
        if top_escalation_watch is not None
        else None,
        "top_watch_label": top_escalation_watch["label"]
        if top_escalation_watch is not None
        else None,
        "top_watch_score": top_escalation_watch["watch_score"]
        if top_escalation_watch is not None
        else 0,
        "top_watch_count": top_escalation_watch["count"]
        if top_escalation_watch is not None
        else 0,
    }


def _build_support_escalation_trend_summary(
    escalation_trends: list[dict[str, object]],
) -> dict[str, object]:
    top_escalation_trend = escalation_trends[0] if escalation_trends else None
    return {
        "top_trend_key": top_escalation_trend["key"]
        if top_escalation_trend is not None
        else None,
        "top_trend_label": top_escalation_trend["label"]
        if top_escalation_trend is not None
        else None,
        "top_trend_delta": top_escalation_trend["delta"]
        if top_escalation_trend is not None
        else 0,
        "top_trend_current_count": top_escalation_trend["current_count"]
        if top_escalation_trend is not None
        else 0,
    }


def _build_support_operator_action_trend_summary(
    operator_action_trends: list[dict[str, object]],
) -> dict[str, object]:
    top_operator_action_trend = (
        operator_action_trends[0] if operator_action_trends else None
    )
    return {
        "top_operator_action_key": top_operator_action_trend["key"]
        if top_operator_action_trend is not None
        else None,
        "top_operator_action_label": top_operator_action_trend["label"]
        if top_operator_action_trend is not None
        else None,
        "top_pack_key": top_operator_action_trend["pack_key"]
        if top_operator_action_trend is not None
        else None,
        "top_pack_label": top_operator_action_trend["pack_label"]
        if top_operator_action_trend is not None
        else None,
        "top_close_reason": top_operator_action_trend["close_reason"]
        if top_operator_action_trend is not None
        else None,
        "top_close_reason_label": top_operator_action_trend["close_reason_label"]
        if top_operator_action_trend is not None
        else None,
        "top_action_key": top_operator_action_trend["action_key"]
        if top_operator_action_trend is not None
        else None,
        "top_action_label": top_operator_action_trend["action_label"]
        if top_operator_action_trend is not None
        else None,
        "top_delta": top_operator_action_trend["delta"]
        if top_operator_action_trend is not None
        else 0,
        "top_current_count": top_operator_action_trend["current_count"]
        if top_operator_action_trend is not None
        else 0,
    }
