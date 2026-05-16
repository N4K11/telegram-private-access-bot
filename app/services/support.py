# ruff: noqa: E501
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SupportTicket
from app.db.repositories.support_tickets import SupportTicketRepository
from app.services.support_catalog import (
    SUPPORT_CATEGORY_ACCESS as SUPPORT_CATEGORY_ACCESS,
)
from app.services.support_catalog import (
    SUPPORT_CATEGORY_PAYMENT as SUPPORT_CATEGORY_PAYMENT,
)
from app.services.support_catalog import (
    SUPPORT_CATEGORY_TECHNICAL as SUPPORT_CATEGORY_TECHNICAL,
)
from app.services.support_catalog import (
    SUPPORT_CLOSE_REASON_RESOLVED as SUPPORT_CLOSE_REASON_RESOLVED,
)
from app.services.support_catalog import (
    SUPPORT_CLOSE_REASON_UNSPECIFIED,
    SUPPORT_INSIGHTS_RECENT_CLOSE_DAYS,
    SUPPORT_PACK_OUTCOME_DAYS,
    SUPPORT_PRIORITY_HIGH,
    SUPPORT_PRIORITY_URGENT,
    SUPPORT_SLA_BUCKET_BREACH,
    SUPPORT_SLA_BUCKET_WARNING,
    SUPPORT_STALE_HOURS,
    SUPPORT_STATUS_CLOSED,
    SUPPORT_STATUS_OPEN,
)
from app.services.support_catalog import (
    SUPPORT_SLA_BUCKET_LABELS as SUPPORT_SLA_BUCKET_LABELS,
)
from app.services.support_catalog import (
    list_support_categories as list_support_categories,
)
from app.services.support_catalog import (
    support_action_lane_label as support_action_lane_label,
)
from app.services.support_catalog import (
    support_canned_reply_pack_label as support_canned_reply_pack_label,
)
from app.services.support_catalog import (
    support_category_label as support_category_label,
)
from app.services.support_catalog import (
    support_close_reason_label as support_close_reason_label,
)
from app.services.support_catalog import (
    support_escalation_action_label as support_escalation_action_label,
)
from app.services.support_catalog import (
    support_escalation_lane_label as support_escalation_lane_label,
)
from app.services.support_catalog import (
    support_priority_label as support_priority_label,
)
from app.services.support_catalog import (
    support_sla_bucket_label as support_sla_bucket_label,
)
from app.services.support_catalog import (
    support_sla_hotspot_label as support_sla_hotspot_label,
)
from app.services.support_catalog import (
    support_status_label as support_status_label,
)
from app.services.support_catalog import (
    support_triage_route_label as support_triage_route_label,
)
from app.services.support_catalog import (
    support_waiting_state_label as support_waiting_state_label,
)
from app.services.support_insight_trends import (
    _build_support_close_reason_trends,
    _build_support_escalation_trends,
    _build_support_operator_action_trends,
    _build_support_pack_outcomes,
)
from app.services.support_models import (
    SupportAdminInbox,
    SupportInsights,
)
from app.services.support_models import (
    SupportTicketThread as SupportTicketThread,
)
from app.services.support_models import (
    SupportUserDashboard as SupportUserDashboard,
)
from app.services.support_open_queues import (
    _build_support_action_lanes as _build_support_action_lanes,
)
from app.services.support_open_queues import (
    _build_support_action_routes as _build_support_action_routes,
)
from app.services.support_open_queues import (
    _build_support_escalation_actions as _build_support_escalation_actions,
)
from app.services.support_open_queues import (
    _build_support_escalation_lanes as _build_support_escalation_lanes,
)
from app.services.support_open_queues import (
    _build_support_escalation_watchlist as _build_support_escalation_watchlist,
)
from app.services.support_open_queues import (
    _build_support_next_action_queue as _build_support_next_action_queue,
)
from app.services.support_open_queues import (
    _build_support_priority_focus as _build_support_priority_focus,
)
from app.services.support_open_queues import (
    _build_support_sla_action_queue as _build_support_sla_action_queue,
)
from app.services.support_open_queues import (
    _build_support_sla_actions as _build_support_sla_actions,
)
from app.services.support_open_queues import (
    _build_support_sla_hotspots as _build_support_sla_hotspots,
)
from app.services.support_open_queues import (
    _build_support_triage_queue as _build_support_triage_queue,
)
from app.services.support_open_queues import (
    _support_ticket_queue_rank_key as _support_ticket_queue_rank_key,
)
from app.services.support_open_queues import (
    _support_top_sample_ticket_ids as _support_top_sample_ticket_ids,
)
from app.services.support_reply_packs import (
    SUPPORT_CANNED_REPLY_PACKS as SUPPORT_CANNED_REPLY_PACKS,
)
from app.services.support_reply_packs import (
    build_support_canned_replies as build_support_canned_replies,
)
from app.services.support_reply_packs import (
    build_support_canned_replies_for_pack as build_support_canned_replies_for_pack,
)
from app.services.support_sla import (
    support_action_lane as support_action_lane,
)
from app.services.support_sla import (
    support_canned_reply_pack_key,
    support_sla_bucket,
    support_waiting_state,
)
from app.services.support_sla import (
    support_canned_reply_pack_titles as support_canned_reply_pack_titles,
)
from app.services.support_sla import (
    support_escalation_lane as support_escalation_lane,
)
from app.services.support_sla import (
    support_next_action_label as support_next_action_label,
)
from app.services.support_sla import (
    support_next_action_note as support_next_action_note,
)
from app.services.support_sla import (
    support_next_action_severity as support_next_action_severity,
)
from app.services.support_sla import (
    support_sla_due_hours as support_sla_due_hours,
)
from app.services.support_sla import (
    support_triage_queue_note as support_triage_queue_note,
)
from app.services.support_ticket_flow import SupportTicketError as SupportTicketError
from app.services.support_ticket_flow import add_admin_ticket_reply as add_admin_ticket_reply
from app.services.support_ticket_flow import add_user_ticket_message as add_user_ticket_message
from app.services.support_ticket_flow import (
    build_support_admin_reply_notification_text as build_support_admin_reply_notification_text,
)
from app.services.support_ticket_flow import (
    build_user_support_dashboard as build_user_support_dashboard,
)
from app.services.support_ticket_flow import close_support_ticket as close_support_ticket
from app.services.support_ticket_flow import create_support_ticket as create_support_ticket
from app.services.support_ticket_flow import get_admin_ticket_thread as get_admin_ticket_thread
from app.services.support_ticket_flow import get_user_ticket_thread as get_user_ticket_thread
from app.services.support_ticket_flow import (
    normalize_support_close_reason as normalize_support_close_reason,
)
from app.services.support_ticket_flow import (
    normalize_support_message as normalize_support_message,
)
from app.services.support_ticket_flow import (
    normalize_support_priority as normalize_support_priority,
)
from app.services.support_ticket_flow import reopen_support_ticket as reopen_support_ticket
from app.services.support_triage_apply import (
    _build_support_triage_apply_actor_replies as _build_support_triage_apply_actor_replies,
)
from app.services.support_triage_apply import (
    _build_support_triage_apply_actors as _build_support_triage_apply_actors,
)
from app.services.support_triage_apply import (
    _build_support_triage_apply_effectiveness as _build_support_triage_apply_effectiveness,
)
from app.services.support_triage_apply import (
    _build_support_triage_apply_focus as _build_support_triage_apply_focus,
)
from app.services.support_triage_apply import (
    _build_support_triage_apply_history as _build_support_triage_apply_history,
)
from app.services.support_triage_apply import (
    _build_support_triage_apply_replies as _build_support_triage_apply_replies,
)
from app.services.support_triage_apply import (
    _build_support_triage_apply_reply_packs as _build_support_triage_apply_reply_packs,
)
from app.services.support_triage_apply import (
    _build_support_triage_apply_route_actors as _build_support_triage_apply_route_actors,
)
from app.services.support_triage_apply import (
    _build_support_triage_apply_route_reply_actors as _build_support_triage_apply_route_reply_actors,
)
from app.services.support_triage_apply import (
    _build_support_triage_apply_routes as _build_support_triage_apply_routes,
)
from app.utils.datetime import ensure_aware_utc, utcnow


def build_support_insights(
    *,
    open_tickets: list[SupportTicket],
    closed_tickets: list[SupportTicket],
    now: datetime | None = None,
    recent_close_days: int = SUPPORT_INSIGHTS_RECENT_CLOSE_DAYS,
    pack_outcome_days: int = SUPPORT_PACK_OUTCOME_DAYS,
) -> SupportInsights:
    event_time = ensure_aware_utc(now or utcnow())
    priority_counts = Counter(ticket.priority for ticket in open_tickets)
    waiting_state_counts = Counter(support_waiting_state(ticket) for ticket in open_tickets)
    category_counts = Counter(ticket.category for ticket in open_tickets)
    canned_reply_pack_counts = Counter(
        support_canned_reply_pack_key(ticket) for ticket in open_tickets
    )
    recent_close_reason_counts, previous_close_reason_counts, close_reason_trends = (
        _build_support_close_reason_trends(
            closed_tickets,
            now=event_time,
            recent_days=recent_close_days,
        )
    )
    canned_reply_pack_outcomes = _build_support_pack_outcomes(
        closed_tickets,
        now=event_time,
        recent_days=pack_outcome_days,
    )
    sla_hotspots = _build_support_sla_hotspots(open_tickets, now=event_time)
    sla_actions = _build_support_sla_actions(open_tickets, now=event_time)
    sla_action_queue = _build_support_sla_action_queue(open_tickets, now=event_time)
    action_lanes = _build_support_action_lanes(open_tickets, now=event_time)
    next_action_queue = _build_support_next_action_queue(open_tickets, now=event_time)
    action_routes = _build_support_action_routes(open_tickets, now=event_time)
    triage_queue = _build_support_triage_queue(open_tickets, now=event_time)
    escalation_lanes = _build_support_escalation_lanes(open_tickets, now=event_time)
    escalation_actions = _build_support_escalation_actions(open_tickets, now=event_time)
    priority_focus = _build_support_priority_focus(open_tickets, now=event_time)
    escalation_watchlist = _build_support_escalation_watchlist(open_tickets, now=event_time)
    operator_action_trends = _build_support_operator_action_trends(
        closed_tickets,
        now=event_time,
        recent_days=recent_close_days,
    )
    escalation_trends = _build_support_escalation_trends(
        closed_tickets,
        now=event_time,
        recent_days=recent_close_days,
    )
    return SupportInsights(
        priority_counts=dict(priority_counts),
        waiting_state_counts=dict(waiting_state_counts),
        category_counts=dict(category_counts),
        canned_reply_pack_counts=dict(canned_reply_pack_counts),
        recent_close_reason_counts=recent_close_reason_counts,
        previous_close_reason_counts=previous_close_reason_counts,
        recent_close_total=sum(recent_close_reason_counts.values()),
        previous_close_total=sum(previous_close_reason_counts.values()),
        recent_close_days=recent_close_days,
        pack_outcome_days=pack_outcome_days,
        canned_reply_pack_outcomes=canned_reply_pack_outcomes,
        close_reason_trends=close_reason_trends,
        sla_hotspots=sla_hotspots,
        sla_actions=sla_actions,
        sla_action_queue=sla_action_queue,
        action_lanes=action_lanes,
        next_action_queue=next_action_queue,
        action_routes=action_routes,
        triage_queue=triage_queue,
        escalation_lanes=escalation_lanes,
        escalation_actions=escalation_actions,
        priority_focus=priority_focus,
        escalation_watchlist=escalation_watchlist,
        operator_action_trends=operator_action_trends,
        escalation_trends=escalation_trends,
    )


async def build_admin_support_inbox(
    session: AsyncSession,
    *,
    status: str = SUPPORT_STATUS_OPEN,
    limit: int = 20,
    now: datetime | None = None,
) -> SupportAdminInbox:
    repository = SupportTicketRepository(session)
    event_time = ensure_aware_utc(now or utcnow())
    open_tickets = await repository.list_by_status(SUPPORT_STATUS_OPEN, limit=5000)
    closed_tickets = await repository.list_by_status(SUPPORT_STATUS_CLOSED, limit=5000)
    tickets = (open_tickets if status == SUPPORT_STATUS_OPEN else closed_tickets)[:limit]
    close_reason_counts = Counter(
        ticket.close_reason or SUPPORT_CLOSE_REASON_UNSPECIFIED for ticket in closed_tickets
    )
    insights = build_support_insights(
        open_tickets=open_tickets,
        closed_tickets=closed_tickets,
        now=event_time,
    )
    insights.triage_apply_history = await _build_support_triage_apply_history(session, limit=10)
    insights.triage_apply_routes = _build_support_triage_apply_routes(
        insights.triage_apply_history
    )
    insights.triage_apply_actors = _build_support_triage_apply_actors(
        insights.triage_apply_history
    )
    insights.triage_apply_replies = _build_support_triage_apply_replies(
        insights.triage_apply_history
    )
    insights.triage_apply_actor_replies = _build_support_triage_apply_actor_replies(
        insights.triage_apply_history
    )
    insights.triage_apply_route_actors = _build_support_triage_apply_route_actors(
        insights.triage_apply_history
    )
    insights.triage_apply_reply_packs = _build_support_triage_apply_reply_packs(
        insights.triage_apply_history
    )
    insights.triage_apply_route_reply_actors = _build_support_triage_apply_route_reply_actors(
        insights.triage_apply_history
    )
    insights.triage_apply_focus = _build_support_triage_apply_focus(insights)
    insights.triage_apply_effectiveness = _build_support_triage_apply_effectiveness(insights)
    return SupportAdminInbox(
        status=status,
        tickets=tickets,
        open_count=len(open_tickets),
        closed_count=len(closed_tickets),
        awaiting_admin_count=sum(
            1 for ticket in open_tickets if support_waiting_state(ticket) == "awaiting_admin"
        ),
        awaiting_user_count=sum(
            1 for ticket in open_tickets if support_waiting_state(ticket) == "awaiting_user"
        ),
        stale_open_count=sum(
            1
            for ticket in open_tickets
            if ensure_aware_utc(ticket.updated_at)
            < event_time - timedelta(hours=SUPPORT_STALE_HOURS)
        ),
        high_priority_open_count=sum(
            1
            for ticket in open_tickets
            if ticket.priority in {
                SUPPORT_PRIORITY_HIGH,
                SUPPORT_PRIORITY_URGENT,
            }
        ),
        sla_warning_count=sum(
            1
            for ticket in open_tickets
            if support_sla_bucket(ticket, now=event_time)
            == SUPPORT_SLA_BUCKET_WARNING
        ),
        sla_breach_count=sum(
            1
            for ticket in open_tickets
            if support_sla_bucket(ticket, now=event_time)
            == SUPPORT_SLA_BUCKET_BREACH
        ),
        close_reason_counts=dict(close_reason_counts),
        insights=insights,
    )



