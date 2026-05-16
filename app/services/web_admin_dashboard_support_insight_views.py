from __future__ import annotations

SUPPORT_INSIGHT_VIEWS = {
    "hotspots": "SLA hotspots",
    "sla_queue": "SLA queue",
    "sla_actions": "SLA actions",
    "pack_outcomes": "Reply-pack outcomes",
    "close_trends": "Close-reason trends",
    "action_lanes": "Action lanes",
    "next_actions": "Next actions",
    "action_routes": "Action routes",
    "triage_queue": "Triage queue",
    "triage_plans": "Triage plans",
    "triage_confirm": "Triage confirm",
    "triage_apply_history": "Triage apply history",
    "triage_apply_routes": "Triage apply routes",
    "triage_apply_actors": "Triage apply actors",
    "triage_apply_replies": "Triage apply replies",
    "triage_apply_actor_replies": "Triage apply actor replies",
    "triage_apply_route_actors": "Triage apply route actors",
    "triage_apply_reply_packs": "Triage apply reply packs",
    "triage_apply_route_reply_actors": "Triage apply route reply actors",
    "triage_apply_focus": "Triage apply focus",
    "triage_apply_effectiveness": "Triage apply effectiveness",
    "escalation_lanes": "Escalation lanes",
    "escalation_actions": "Escalation actions",
    "priority_focus": "Priority handling",
    "escalation_watchlist": "Escalation watchlist",
    "escalation_trends": "Escalation trends",
    "operator_action_trends": "Operator action trends",
}

SUPPORT_INSIGHT_VIEW_SOURCE_KEYS = {
    "hotspots": "sla_hotspots",
    "sla_queue": "sla_action_queue",
    "sla_actions": "sla_actions",
    "pack_outcomes": "canned_reply_pack_outcomes",
    "close_trends": "close_reason_trends",
    "action_lanes": "action_lanes",
    "next_actions": "next_action_queue",
    "action_routes": "action_routes",
    "triage_queue": "triage_queue",
    "triage_plans": "triage_plans",
    "triage_confirm": "triage_confirm",
    "triage_apply_history": "triage_apply_history",
    "triage_apply_routes": "triage_apply_routes",
    "triage_apply_actors": "triage_apply_actors",
    "triage_apply_replies": "triage_apply_replies",
    "triage_apply_actor_replies": "triage_apply_actor_replies",
    "triage_apply_route_actors": "triage_apply_route_actors",
    "triage_apply_reply_packs": "triage_apply_reply_packs",
    "triage_apply_route_reply_actors": "triage_apply_route_reply_actors",
    "triage_apply_focus": "triage_apply_focus",
    "triage_apply_effectiveness": "triage_apply_effectiveness",
    "escalation_lanes": "escalation_lanes",
    "escalation_actions": "escalation_actions",
    "priority_focus": "priority_focus",
    "escalation_watchlist": "escalation_watchlist",
    "escalation_trends": "escalation_trends",
    "operator_action_trends": "operator_action_trends",
}


def _normalize_support_insight_view(view: str | None) -> str:
    normalized = (view or "hotspots").strip()
    return normalized if normalized in SUPPORT_INSIGHT_VIEWS else "hotspots"


def _support_insight_items_for_view(
    insights: dict[str, object], *, view: str
) -> list[dict[str, object]]:
    source_key = SUPPORT_INSIGHT_VIEW_SOURCE_KEYS[view]
    items = insights.get(source_key, [])
    return list(items) if isinstance(items, list) else []
