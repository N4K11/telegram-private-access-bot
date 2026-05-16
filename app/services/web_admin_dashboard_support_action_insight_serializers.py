# ruff: noqa: E501
from __future__ import annotations

from app.services.support import (
    support_action_lane_label,
    support_category_label,
    support_escalation_action_label,
    support_escalation_lane_label,
    support_priority_label,
    support_sla_hotspot_label,
)


def _serialize_support_sla_hotspots(
    insights,
    *,
    open_total: int,
) -> list[dict[str, object]]:
    return [
        {
            "kind": item.kind,
            "kind_label": support_sla_hotspot_label(item.kind),
            "category": item.category,
            "category_label": support_category_label(item.category),
            "priority": item.priority,
            "priority_label": support_priority_label(item.priority),
            "count": item.count,
            "share_percent": round((item.count / open_total) * 100, 1) if open_total else 0.0,
        }
        for item in insights.sla_hotspots
    ]


def _serialize_support_sla_actions(
    insights,
    *,
    open_total: int,
) -> list[dict[str, object]]:
    return [
        {
            "key": f"{item.kind}:{item.category}:{item.priority}",
            "label": f"{support_sla_hotspot_label(item.kind)} -> {support_action_lane_label(item.action_key)}",
            "kind": item.kind,
            "kind_label": support_sla_hotspot_label(item.kind),
            "category": item.category,
            "category_label": support_category_label(item.category),
            "priority": item.priority,
            "priority_label": support_priority_label(item.priority),
            "count": item.count,
            "share_percent": round((item.count / open_total) * 100, 1) if open_total else 0.0,
            "action_key": item.action_key,
            "action_label": support_action_lane_label(item.action_key),
            "escalation_key": item.escalation_key,
            "escalation_label": support_escalation_lane_label(item.escalation_key),
            "note": item.note,
        }
        for item in insights.sla_actions
    ]


def _serialize_support_sla_action_queue(
    insights,
    *,
    open_total: int,
) -> list[dict[str, object]]:
    return [
        {
            "key": item.key,
            "label": support_action_lane_label(item.key),
            "sample_ticket_ids": list(item.sample_ticket_ids),
            "count": item.count,
            "share_percent": round((item.count / open_total) * 100, 1) if open_total else 0.0,
            "high_priority_count": item.high_priority_count,
            "stale_count": item.stale_count,
            "sla_breach_count": item.sla_breach_count,
            "top_kind": item.top_kind,
            "top_kind_label": support_sla_hotspot_label(item.top_kind)
            if item.top_kind
            else None,
            "top_priority": item.top_priority,
            "top_priority_label": support_priority_label(item.top_priority)
            if item.top_priority
            else None,
            "top_category": item.top_category,
            "top_category_label": support_category_label(item.top_category)
            if item.top_category
            else None,
            "top_escalation_lane": item.top_escalation_lane,
            "top_escalation_lane_label": support_escalation_lane_label(
                item.top_escalation_lane
            )
            if item.top_escalation_lane
            else None,
            "note": item.note,
        }
        for item in insights.sla_action_queue
    ]


def _serialize_support_action_lanes(
    insights,
    *,
    open_total: int,
) -> list[dict[str, object]]:
    return [
        {
            "key": item.key,
            "label": support_action_lane_label(item.key),
            "count": item.count,
            "share_percent": round((item.count / open_total) * 100, 1) if open_total else 0.0,
            "high_priority_count": item.high_priority_count,
            "stale_count": item.stale_count,
            "sla_warning_count": item.sla_warning_count,
            "sla_breach_count": item.sla_breach_count,
            "top_category": item.top_category,
            "top_category_label": support_category_label(item.top_category)
            if item.top_category
            else None,
        }
        for item in insights.action_lanes
    ]


def _serialize_support_next_action_queue(
    insights,
    *,
    open_total: int,
) -> list[dict[str, object]]:
    return [
        {
            "key": item.key,
            "label": support_action_lane_label(item.key),
            "sample_ticket_ids": list(item.sample_ticket_ids),
            "count": item.count,
            "share_percent": round((item.count / open_total) * 100, 1) if open_total else 0.0,
            "awaiting_admin_count": item.awaiting_admin_count,
            "awaiting_user_count": item.awaiting_user_count,
            "high_priority_count": item.high_priority_count,
            "stale_count": item.stale_count,
            "sla_breach_count": item.sla_breach_count,
            "top_category": item.top_category,
            "top_category_label": support_category_label(item.top_category)
            if item.top_category
            else None,
            "top_escalation_lane": item.top_escalation_lane,
            "top_escalation_lane_label": support_escalation_lane_label(
                item.top_escalation_lane
            )
            if item.top_escalation_lane
            else None,
            "note": item.note,
        }
        for item in insights.next_action_queue
    ]


def _serialize_support_action_routes(
    insights,
    *,
    open_total: int,
) -> list[dict[str, object]]:
    return [
        {
            "key": item.key,
            "label": support_escalation_action_label(item.escalation_key, item.action_key),
            "escalation_key": item.escalation_key,
            "escalation_label": support_escalation_lane_label(item.escalation_key),
            "action_key": item.action_key,
            "action_label": support_action_lane_label(item.action_key),
            "sample_ticket_ids": list(item.sample_ticket_ids),
            "count": item.count,
            "share_percent": round((item.count / open_total) * 100, 1) if open_total else 0.0,
            "awaiting_admin_count": item.awaiting_admin_count,
            "awaiting_user_count": item.awaiting_user_count,
            "high_priority_count": item.high_priority_count,
            "stale_count": item.stale_count,
            "sla_warning_count": item.sla_warning_count,
            "sla_breach_count": item.sla_breach_count,
            "top_priority": item.top_priority,
            "top_priority_label": support_priority_label(item.top_priority)
            if item.top_priority
            else None,
            "top_category": item.top_category,
            "top_category_label": support_category_label(item.top_category)
            if item.top_category
            else None,
            "top_kind": item.top_kind,
            "top_kind_label": support_sla_hotspot_label(item.top_kind)
            if item.top_kind
            else None,
            "note": item.note,
        }
        for item in insights.action_routes
    ]


def _build_support_sla_hotspot_summary(
    sla_hotspots: list[dict[str, object]],
) -> dict[str, object]:
    top_hotspot = sla_hotspots[0] if sla_hotspots else None
    return {
        "top_kind": top_hotspot["kind"] if top_hotspot is not None else None,
        "top_kind_label": top_hotspot["kind_label"] if top_hotspot is not None else None,
        "top_category_label": top_hotspot["category_label"]
        if top_hotspot is not None
        else None,
        "top_priority_label": top_hotspot["priority_label"]
        if top_hotspot is not None
        else None,
        "top_count": top_hotspot["count"] if top_hotspot is not None else 0,
    }


def _build_support_sla_queue_summary(
    sla_action_queue: list[dict[str, object]],
) -> dict[str, object]:
    top_sla_queue_action = sla_action_queue[0] if sla_action_queue else None
    return {
        "top_sla_queue_action": top_sla_queue_action["key"]
        if top_sla_queue_action is not None
        else None,
        "top_sla_queue_action_label": top_sla_queue_action["label"]
        if top_sla_queue_action is not None
        else None,
        "top_kind": top_sla_queue_action["top_kind"]
        if top_sla_queue_action is not None
        else None,
        "top_kind_label": top_sla_queue_action["top_kind_label"]
        if top_sla_queue_action is not None
        else None,
        "top_escalation_lane": top_sla_queue_action["top_escalation_lane"]
        if top_sla_queue_action is not None
        else None,
        "top_escalation_lane_label": top_sla_queue_action["top_escalation_lane_label"]
        if top_sla_queue_action is not None
        else None,
        "top_count": top_sla_queue_action["count"]
        if top_sla_queue_action is not None
        else 0,
        "top_share_percent": top_sla_queue_action["share_percent"]
        if top_sla_queue_action is not None
        else 0.0,
        "top_note": top_sla_queue_action["note"]
        if top_sla_queue_action is not None
        else None,
        "top_sample_ticket_ids": top_sla_queue_action["sample_ticket_ids"]
        if top_sla_queue_action is not None
        else [],
    }


def _build_support_sla_action_summary(
    sla_actions: list[dict[str, object]],
) -> dict[str, object]:
    top_sla_action = sla_actions[0] if sla_actions else None
    return {
        "top_sla_action_key": top_sla_action["key"] if top_sla_action is not None else None,
        "top_sla_action_label": top_sla_action["label"]
        if top_sla_action is not None
        else None,
        "top_kind": top_sla_action["kind"] if top_sla_action is not None else None,
        "top_action_key": top_sla_action["action_key"]
        if top_sla_action is not None
        else None,
        "top_action_label": top_sla_action["action_label"]
        if top_sla_action is not None
        else None,
        "top_escalation_key": top_sla_action["escalation_key"]
        if top_sla_action is not None
        else None,
        "top_escalation_label": top_sla_action["escalation_label"]
        if top_sla_action is not None
        else None,
        "top_count": top_sla_action["count"] if top_sla_action is not None else 0,
    }


def _build_support_action_lane_summary(
    action_lanes: list[dict[str, object]],
) -> dict[str, object]:
    top_action_lane = action_lanes[0] if action_lanes else None
    return {
        "top_action_lane": top_action_lane["key"] if top_action_lane is not None else None,
        "top_action_lane_label": top_action_lane["label"]
        if top_action_lane is not None
        else None,
        "top_action_lane_count": top_action_lane["count"]
        if top_action_lane is not None
        else 0,
        "top_action_lane_share_percent": top_action_lane["share_percent"]
        if top_action_lane is not None
        else 0.0,
    }


def _build_support_next_action_summary(
    next_action_queue: list[dict[str, object]],
) -> dict[str, object]:
    top_next_action = next_action_queue[0] if next_action_queue else None
    return {
        "top_next_action": top_next_action["key"] if top_next_action is not None else None,
        "top_next_action_label": top_next_action["label"]
        if top_next_action is not None
        else None,
        "top_next_action_count": top_next_action["count"]
        if top_next_action is not None
        else 0,
        "top_next_action_share_percent": top_next_action["share_percent"]
        if top_next_action is not None
        else 0.0,
        "top_next_action_note": top_next_action["note"]
        if top_next_action is not None
        else None,
        "top_next_escalation_lane": top_next_action["top_escalation_lane"]
        if top_next_action is not None
        else None,
        "top_next_escalation_lane_label": top_next_action["top_escalation_lane_label"]
        if top_next_action is not None
        else None,
        "top_sample_ticket_ids": top_next_action["sample_ticket_ids"]
        if top_next_action is not None
        else [],
    }


def _build_support_action_route_summary(
    action_routes: list[dict[str, object]],
) -> dict[str, object]:
    top_action_route = action_routes[0] if action_routes else None
    return {
        "top_action_route": top_action_route["key"] if top_action_route is not None else None,
        "top_action_route_label": top_action_route["label"]
        if top_action_route is not None
        else None,
        "top_action_route_count": top_action_route["count"]
        if top_action_route is not None
        else 0,
        "top_action_route_share_percent": top_action_route["share_percent"]
        if top_action_route is not None
        else 0.0,
        "top_action_route_note": top_action_route["note"]
        if top_action_route is not None
        else None,
        "top_action_route_hotspot": top_action_route["top_kind"]
        if top_action_route is not None
        else None,
        "top_action_route_hotspot_label": top_action_route["top_kind_label"]
        if top_action_route is not None
        else None,
        "top_action_route_priority": top_action_route["top_priority"]
        if top_action_route is not None
        else None,
        "top_action_route_priority_label": top_action_route["top_priority_label"]
        if top_action_route is not None
        else None,
        "top_sample_ticket_ids": top_action_route["sample_ticket_ids"]
        if top_action_route is not None
        else [],
    }
