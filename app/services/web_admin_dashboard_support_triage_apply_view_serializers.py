# ruff: noqa: E501
from __future__ import annotations

from app.services.support import (
    support_canned_reply_pack_label,
    support_triage_route_label,
)
from app.utils.datetime import format_datetime


def _support_triage_apply_effectiveness_coverage_label(
    source_key: str,
    coverage_count: int,
) -> str:
    if source_key == "route_reply_actor":
        return f"{coverage_count} exact path"
    if source_key == "route_actor":
        return f"{coverage_count} replies"
    if source_key == "actor_reply":
        return f"{coverage_count} routes"
    if source_key == "reply_pack":
        return f"{coverage_count} actors"
    return str(coverage_count)


def _build_support_triage_apply_views(insights) -> dict[str, list[dict[str, object]]]:
    return {
        "triage_apply_history": [
            {
                "audit_log_id": item.audit_log_id,
                "actor_user_id": item.actor_user_id,
                "actor_label": item.actor_label,
                "triage_key": item.triage_key,
                "pack_key": item.pack_key,
                "pack_label": support_canned_reply_pack_label(item.pack_key),
                "route_key": item.route_key,
                "route_label": support_triage_route_label(item.route_key),
                "reply_key": item.reply_key,
                "reply_title": item.reply_title,
                "ticket_ids": list(item.ticket_ids),
                "count": item.count,
                "created_at_label": format_datetime(item.created_at, "UTC"),
                "note": item.note,
            }
            for item in insights.triage_apply_history
        ],
        "triage_apply_routes": [
            {
                "key": item.key,
                "route_key": item.route_key,
                "route_label": support_triage_route_label(item.route_key),
                "pack_key": item.pack_key,
                "pack_label": support_canned_reply_pack_label(item.pack_key),
                "reply_key": item.reply_key,
                "reply_title": item.reply_title,
                "sample_ticket_ids": list(item.sample_ticket_ids),
                "apply_count": item.apply_count,
                "ticket_count": item.ticket_count,
                "actor_count": item.actor_count,
                "top_actor_label": item.top_actor_label,
                "latest_applied_at_label": format_datetime(item.latest_applied_at, "UTC"),
                "note": item.note,
            }
            for item in insights.triage_apply_routes
        ],
        "triage_apply_actors": [
            {
                "actor_user_id": item.actor_user_id,
                "actor_label": item.actor_label,
                "sample_ticket_ids": list(item.sample_ticket_ids),
                "apply_count": item.apply_count,
                "ticket_count": item.ticket_count,
                "route_count": item.route_count,
                "top_route_key": item.top_route_key,
                "top_route_label": support_triage_route_label(item.top_route_key)
                if item.top_route_key
                else None,
                "top_reply_key": item.top_reply_key,
                "top_reply_title": item.top_reply_title,
                "latest_applied_at_label": format_datetime(item.latest_applied_at, "UTC"),
                "note": item.note,
            }
            for item in insights.triage_apply_actors
        ],
        "triage_apply_replies": [
            {
                "reply_key": item.reply_key,
                "reply_title": item.reply_title,
                "sample_ticket_ids": list(item.sample_ticket_ids),
                "apply_count": item.apply_count,
                "ticket_count": item.ticket_count,
                "actor_count": item.actor_count,
                "route_count": item.route_count,
                "top_actor_label": item.top_actor_label,
                "top_route_key": item.top_route_key,
                "top_route_label": support_triage_route_label(item.top_route_key)
                if item.top_route_key
                else None,
                "top_pack_key": item.top_pack_key,
                "top_pack_label": support_canned_reply_pack_label(item.top_pack_key)
                if item.top_pack_key
                else None,
                "latest_applied_at_label": format_datetime(item.latest_applied_at, "UTC"),
                "note": item.note,
            }
            for item in insights.triage_apply_replies
        ],
        "triage_apply_actor_replies": [
            {
                "actor_user_id": item.actor_user_id,
                "actor_label": item.actor_label,
                "reply_key": item.reply_key,
                "reply_title": item.reply_title,
                "sample_ticket_ids": list(item.sample_ticket_ids),
                "apply_count": item.apply_count,
                "ticket_count": item.ticket_count,
                "route_count": item.route_count,
                "top_route_key": item.top_route_key,
                "top_route_label": support_triage_route_label(item.top_route_key)
                if item.top_route_key
                else None,
                "top_pack_key": item.top_pack_key,
                "top_pack_label": support_canned_reply_pack_label(item.top_pack_key)
                if item.top_pack_key
                else None,
                "latest_applied_at_label": format_datetime(item.latest_applied_at, "UTC"),
                "note": item.note,
            }
            for item in insights.triage_apply_actor_replies
        ],
        "triage_apply_route_actors": [
            {
                "route_key": item.route_key,
                "route_label": support_triage_route_label(item.route_key),
                "actor_user_id": item.actor_user_id,
                "actor_label": item.actor_label,
                "sample_ticket_ids": list(item.sample_ticket_ids),
                "apply_count": item.apply_count,
                "ticket_count": item.ticket_count,
                "reply_count": item.reply_count,
                "top_reply_key": item.top_reply_key,
                "top_reply_title": item.top_reply_title,
                "top_pack_key": item.top_pack_key,
                "top_pack_label": support_canned_reply_pack_label(item.top_pack_key)
                if item.top_pack_key
                else None,
                "latest_applied_at_label": format_datetime(item.latest_applied_at, "UTC"),
                "note": item.note,
            }
            for item in insights.triage_apply_route_actors
        ],
        "triage_apply_reply_packs": [
            {
                "reply_key": item.reply_key,
                "reply_title": item.reply_title,
                "pack_key": item.pack_key,
                "pack_label": support_canned_reply_pack_label(item.pack_key),
                "sample_ticket_ids": list(item.sample_ticket_ids),
                "apply_count": item.apply_count,
                "ticket_count": item.ticket_count,
                "actor_count": item.actor_count,
                "top_actor_label": item.top_actor_label,
                "top_route_key": item.top_route_key,
                "top_route_label": support_triage_route_label(item.top_route_key)
                if item.top_route_key
                else None,
                "latest_applied_at_label": format_datetime(item.latest_applied_at, "UTC"),
                "note": item.note,
            }
            for item in insights.triage_apply_reply_packs
        ],
        "triage_apply_route_reply_actors": [
            {
                "route_key": item.route_key,
                "route_label": support_triage_route_label(item.route_key),
                "reply_key": item.reply_key,
                "reply_title": item.reply_title,
                "actor_user_id": item.actor_user_id,
                "actor_label": item.actor_label,
                "sample_ticket_ids": list(item.sample_ticket_ids),
                "apply_count": item.apply_count,
                "ticket_count": item.ticket_count,
                "top_pack_key": item.top_pack_key,
                "top_pack_label": support_canned_reply_pack_label(item.top_pack_key)
                if item.top_pack_key
                else None,
                "latest_applied_at_label": format_datetime(item.latest_applied_at, "UTC"),
                "note": item.note,
            }
            for item in insights.triage_apply_route_reply_actors
        ],
        "triage_apply_focus": [
            {
                "key": item.key,
                "source_key": item.source_key,
                "source_label": item.source_label,
                "title": item.title,
                "secondary_label": item.secondary_label,
                "sample_ticket_ids": list(item.sample_ticket_ids),
                "apply_count": item.apply_count,
                "ticket_count": item.ticket_count,
                "focus_score": item.focus_score,
                "latest_applied_at_label": format_datetime(item.latest_applied_at, "UTC"),
                "note": item.note,
            }
            for item in insights.triage_apply_focus
        ],
        "triage_apply_effectiveness": [
            {
                "key": item.key,
                "source_key": item.source_key,
                "source_label": item.source_label,
                "title": item.title,
                "secondary_label": item.secondary_label,
                "route_key": item.route_key,
                "route_label": support_triage_route_label(item.route_key)
                if item.route_key
                else None,
                "reply_key": item.reply_key,
                "reply_title": item.reply_title,
                "actor_user_id": item.actor_user_id,
                "actor_label": item.actor_label,
                "pack_key": item.pack_key,
                "pack_label": support_canned_reply_pack_label(item.pack_key)
                if item.pack_key
                else None,
                "sample_ticket_ids": list(item.sample_ticket_ids),
                "apply_count": item.apply_count,
                "ticket_count": item.ticket_count,
                "coverage_count": item.coverage_count,
                "coverage_label": _support_triage_apply_effectiveness_coverage_label(
                    item.source_key,
                    item.coverage_count,
                ),
                "effectiveness_score": item.effectiveness_score,
                "latest_applied_at_label": format_datetime(item.latest_applied_at, "UTC"),
                "note": item.note,
            }
            for item in insights.triage_apply_effectiveness
        ],
    }
