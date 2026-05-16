# ruff: noqa: E501
from __future__ import annotations

from datetime import datetime

from app.config import Settings
from app.db.models import SupportTicket
from app.services.observability import sanitize_observability_text
from app.services.support import (
    SUPPORT_PRIORITY_HIGH,
    SUPPORT_PRIORITY_URGENT,
    SUPPORT_SLA_BUCKET_BREACH,
    SUPPORT_SLA_BUCKET_LABELS,
    SUPPORT_SLA_BUCKET_WARNING,
    support_action_lane,
    support_action_lane_label,
    support_canned_reply_pack_key,
    support_canned_reply_pack_label,
    support_canned_reply_pack_titles,
    support_category_label,
    support_close_reason_label,
    support_escalation_action_label,
    support_escalation_lane,
    support_escalation_lane_label,
    support_priority_label,
    support_sla_bucket,
    support_sla_due_hours,
    support_status_label,
)
from app.services.support_catalog import SUPPORT_WAITING_STATE_LABELS
from app.services.web_admin_dashboard_common import _display_name, _dt, _plain
from app.utils.datetime import ensure_aware_utc


def _serialize_support_close_reason_analytics(
    counts: dict[str, int],
) -> dict[str, object]:
    total_closed = sum(counts.values())
    items = [
        {
            "key": key,
            "label": support_close_reason_label(key),
            "count": count,
            "share_percent": round((count / total_closed) * 100, 1)
            if total_closed
            else 0.0,
        }
        for key, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], support_close_reason_label(item[0])),
        )
    ]
    top_item = items[0] if items else None
    return {
        "total_closed": total_closed,
        "top_close_reason": top_item["key"] if top_item is not None else None,
        "top_close_reason_label": top_item["label"] if top_item is not None else None,
        "top_close_reason_count": top_item["count"] if top_item is not None else 0,
        "top_close_reason_share_percent": (
            top_item["share_percent"] if top_item is not None else 0.0
        ),
        "items": items,
    }


def _serialize_support_ticket_list_item(
    ticket: SupportTicket,
    *,
    settings: Settings,
    stale_before: datetime | None = None,
    reference_time: datetime | None = None,
) -> dict[str, object]:
    waiting_state = _support_waiting_state(ticket)
    sla_bucket = support_sla_bucket(ticket, now=reference_time)
    action_lane = support_action_lane(ticket, now=reference_time)
    escalation_lane = support_escalation_lane(ticket, now=reference_time)
    triage_pack_key = support_canned_reply_pack_key(ticket)
    return {
        "id": ticket.id,
        "user_id": ticket.user_id,
        "telegram_id": ticket.user.telegram_id if ticket.user is not None else None,
        "user_display_name": _display_name(ticket.user),
        "category": ticket.category,
        "category_label": support_category_label(ticket.category),
        "status": ticket.status,
        "status_label": support_status_label(ticket.status),
        "priority": ticket.priority,
        "priority_label": support_priority_label(ticket.priority),
        "close_reason": ticket.close_reason,
        "close_reason_label": support_close_reason_label(ticket.close_reason),
        "waiting_state": waiting_state,
        "waiting_state_label": SUPPORT_WAITING_STATE_LABELS.get(
            waiting_state,
            waiting_state,
        ),
        "action_lane_key": action_lane,
        "action_lane_label": support_action_lane_label(action_lane),
        "escalation_lane_key": escalation_lane,
        "escalation_lane_label": support_escalation_lane_label(escalation_lane),
        "triage_pack_key": triage_pack_key,
        "triage_pack_label": support_canned_reply_pack_label(triage_pack_key),
        "triage_route_label": support_escalation_action_label(
            escalation_lane,
            action_lane,
        ),
        "triage_sample_titles": support_canned_reply_pack_titles(triage_pack_key),
        "sla_bucket": sla_bucket,
        "sla_bucket_label": SUPPORT_SLA_BUCKET_LABELS.get(sla_bucket, sla_bucket),
        "sla_due_hours": support_sla_due_hours(ticket),
        "updated_at_label": _dt(ticket.updated_at, settings.timezone),
        "created_at_label": _dt(ticket.created_at, settings.timezone),
        "closed_at_label": _dt(ticket.closed_at, settings.timezone),
        "message_count": len(ticket.messages or []),
        "last_message_preview": _support_last_message_preview(ticket),
        "is_open": ticket.status == "open",
        "is_stale": _is_support_ticket_stale(ticket, stale_before=stale_before),
    }


def _support_search_blob(ticket: SupportTicket) -> str:
    return " ".join(
        part.casefold()
        for part in (
            str(ticket.id),
            str(ticket.user_id),
            str(ticket.user.telegram_id) if ticket.user is not None else "",
            ticket.user.username
            if ticket.user is not None and ticket.user.username
            else "",
            ticket.user.first_name
            if ticket.user is not None and ticket.user.first_name
            else "",
            ticket.user.last_name
            if ticket.user is not None and ticket.user.last_name
            else "",
            ticket.category,
            support_category_label(ticket.category),
            ticket.status,
            support_status_label(ticket.status),
            ticket.priority,
            support_priority_label(ticket.priority),
            ticket.close_reason or "",
            support_close_reason_label(ticket.close_reason),
        )
        if part
    )


def _support_last_message_preview(ticket: SupportTicket) -> str | None:
    if not ticket.messages:
        return None
    preview = sanitize_observability_text(_plain(ticket.messages[-1].body))
    return _truncate(preview, limit=160)


def _matches_support_queue(
    ticket: SupportTicket,
    *,
    queue: str,
    stale_before: datetime,
    reference_time: datetime | None = None,
) -> bool:
    if queue == "all":
        return True
    if queue == "awaiting_admin":
        return _support_waiting_state(ticket) == "awaiting_admin"
    if queue == "awaiting_user":
        return _support_waiting_state(ticket) == "awaiting_user"
    if queue == "priority_high":
        return ticket.priority in {SUPPORT_PRIORITY_HIGH, SUPPORT_PRIORITY_URGENT}
    if queue == "sla_warning":
        return (
            support_sla_bucket(ticket, now=reference_time)
            == SUPPORT_SLA_BUCKET_WARNING
        )
    if queue == "sla_breach":
        return (
            support_sla_bucket(ticket, now=reference_time) == SUPPORT_SLA_BUCKET_BREACH
        )
    if queue == "stale":
        return _is_support_ticket_stale(ticket, stale_before=stale_before)
    return True


def _support_queue_counts(
    tickets: list[SupportTicket],
    *,
    stale_before: datetime,
    reference_time: datetime | None = None,
) -> dict[str, int]:
    return {
        "all": len(tickets),
        "awaiting_admin": sum(
            1 for ticket in tickets if _support_waiting_state(ticket) == "awaiting_admin"
        ),
        "awaiting_user": sum(
            1 for ticket in tickets if _support_waiting_state(ticket) == "awaiting_user"
        ),
        "priority_high": sum(
            1
            for ticket in tickets
            if ticket.priority in {SUPPORT_PRIORITY_HIGH, SUPPORT_PRIORITY_URGENT}
        ),
        "sla_warning": sum(
            1
            for ticket in tickets
            if support_sla_bucket(ticket, now=reference_time)
            == SUPPORT_SLA_BUCKET_WARNING
        ),
        "sla_breach": sum(
            1
            for ticket in tickets
            if support_sla_bucket(ticket, now=reference_time)
            == SUPPORT_SLA_BUCKET_BREACH
        ),
        "stale": sum(
            1
            for ticket in tickets
            if _is_support_ticket_stale(ticket, stale_before=stale_before)
        ),
    }


def _is_support_ticket_stale(
    ticket: SupportTicket,
    *,
    stale_before: datetime | None,
) -> bool:
    if stale_before is None or ticket.status != "open" or ticket.updated_at is None:
        return False
    return ensure_aware_utc(ticket.updated_at) < stale_before


def _truncate(value: str | None, *, limit: int) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)].rstrip() + "?"


def _support_waiting_state(ticket) -> str:
    if ticket.status != "open":
        return "closed"
    if ticket.last_user_message_at and (
        ticket.last_admin_message_at is None
        or ticket.last_user_message_at > ticket.last_admin_message_at
    ):
        return "awaiting_admin"
    if ticket.last_admin_message_at is not None:
        return "awaiting_user"
    return "new"
