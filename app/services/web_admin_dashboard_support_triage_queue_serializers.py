# ruff: noqa: E501
from __future__ import annotations

from app.services.support import (
    build_support_canned_replies_for_pack,
    support_action_lane_label,
    support_canned_reply_pack_label,
    support_canned_reply_pack_titles,
    support_escalation_action_label,
    support_escalation_lane_label,
    support_priority_label,
    support_sla_hotspot_label,
)


def _support_triage_confirm_label(
    *, primary_reply_title: str | None, pack_label: str
) -> str:
    if primary_reply_title:
        return f'Preview "{primary_reply_title}"'
    return f"Preview {pack_label}"


def _support_triage_confirm_scope_label(*, count: int, route_label: str | None) -> str:
    ticket_label = "ticket" if count == 1 else "tickets"
    return f"{count} {ticket_label} / {route_label or 'route'}"


def _support_triage_confirm_note(
    *,
    primary_reply_title: str | None,
    route_label: str | None,
    sample_ticket_ids: list[int],
) -> str:
    primary_label = primary_reply_title or "the primary canned reply"
    sample_ids = ", ".join(f"#{ticket_id}" for ticket_id in sample_ticket_ids[:3])
    sample_note = (
        f"Review {sample_ids} before replying."
        if sample_ids
        else "Review sample tickets before replying."
    )
    return (
        f'Preview "{primary_label}" for {route_label or "the current route"} first. '
        f"{sample_note} This is read-only confirmation, not a bulk send."
    )


def _build_support_triage_queue(
    insights,
    *,
    open_total: int,
) -> list[dict[str, object]]:
    return [
        {
            "key": item.key,
            "label": support_canned_reply_pack_label(item.pack_key),
            "pack_key": item.pack_key,
            "pack_label": support_canned_reply_pack_label(item.pack_key),
            "sample_titles": support_canned_reply_pack_titles(item.pack_key),
            "sample_ticket_ids": list(item.sample_ticket_ids),
            "route_label": support_escalation_action_label(
                item.escalation_key,
                item.action_key,
            ),
            "escalation_key": item.escalation_key,
            "escalation_label": support_escalation_lane_label(item.escalation_key),
            "action_key": item.action_key,
            "action_label": support_action_lane_label(item.action_key),
            "count": item.count,
            "share_percent": round((item.count / open_total) * 100, 1)
            if open_total
            else 0.0,
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
            "top_kind": item.top_kind,
            "top_kind_label": support_sla_hotspot_label(item.top_kind)
            if item.top_kind
            else None,
            "note": item.note,
        }
        for item in insights.triage_queue
    ]


def _build_support_triage_plans(
    triage_queue: list[dict[str, object]],
) -> list[dict[str, object]]:
    triage_plans = []
    for item in triage_queue:
        suggested_replies = [
            {
                "key": reply.key,
                "title": reply.title,
                "body": reply.body,
                "kind": reply.kind,
            }
            for reply in build_support_canned_replies_for_pack(
                item["pack_key"],
                limit=3,
            )
        ]
        primary_reply = suggested_replies[0] if suggested_replies else None
        triage_plans.append(
            {
                **item,
                "route_key": f'{item["escalation_key"]}:{item["action_key"]}',
                "primary_reply_key": primary_reply["key"]
                if primary_reply is not None
                else None,
                "primary_reply_title": primary_reply["title"]
                if primary_reply is not None
                else None,
                "primary_reply_body": primary_reply["body"]
                if primary_reply is not None
                else None,
                "primary_reply_kind": primary_reply["kind"]
                if primary_reply is not None
                else None,
                "suggested_replies": suggested_replies,
            }
        )
    return triage_plans


def _build_support_triage_confirm(
    triage_plans: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        {
            **item,
            "confirm_key": item["key"],
            "confirm_label": _support_triage_confirm_label(
                primary_reply_title=item["primary_reply_title"],
                pack_label=item["pack_label"],
            ),
            "confirm_mode": "preview_only",
            "confirm_mode_label": "Preview only",
            "confirm_scope_label": _support_triage_confirm_scope_label(
                count=item["count"],
                route_label=item["route_label"],
            ),
            "confirm_note": _support_triage_confirm_note(
                primary_reply_title=item["primary_reply_title"],
                route_label=item["route_label"],
                sample_ticket_ids=list(item["sample_ticket_ids"]),
            ),
        }
        for item in triage_plans
    ]
