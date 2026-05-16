# ruff: noqa: E501
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from app.db.models import SupportTicket
from app.services.support_catalog import (
    SUPPORT_PRIORITY_HIGH,
    SUPPORT_PRIORITY_URGENT,
    SUPPORT_SLA_BUCKET_BREACH,
    SUPPORT_SLA_BUCKET_WARNING,
    SUPPORT_SLA_HOTSPOT_BREACH,
    SUPPORT_SLA_HOTSPOT_STALE,
    SUPPORT_SLA_HOTSPOT_WARNING,
    SUPPORT_STALE_HOURS,
    support_action_lane_label,
    support_canned_reply_pack_label,
    support_category_label,
    support_escalation_action_label,
    support_escalation_lane_label,
    support_priority_label,
    support_sla_hotspot_label,
)
from app.services.support_models import (
    SupportActionRoute,
    SupportNextActionQueue,
    SupportTriageQueueItem,
)
from app.services.support_queue_ranking import (
    _support_counter_top_key,
    _support_ticket_queue_rank_key,
    _support_top_lane_sample_ticket_ids,
    _support_top_sample_ticket_ids,
)
from app.services.support_sla import (
    _support_action_lane_order,
    _support_escalation_lane_order,
    _support_priority_order,
    support_action_lane,
    support_action_route_note,
    support_canned_reply_pack_key,
    support_escalation_lane,
    support_next_action_queue_note,
    support_sla_bucket,
    support_triage_queue_note,
    support_waiting_state,
)
from app.services.support_sla_queues import _support_hotspot_kind_for_ticket
from app.utils.datetime import ensure_aware_utc


def _build_support_next_action_queue(
    open_tickets: list[SupportTicket],
    *,
    now: datetime,
) -> list[SupportNextActionQueue]:
    stale_threshold = now - timedelta(hours=SUPPORT_STALE_HOURS)
    lane_counters: dict[str, Counter[str]] = {}
    lane_categories: dict[str, Counter[str]] = {}
    lane_escalations: dict[str, Counter[str]] = {}
    lane_ticket_ids: dict[
        str, list[tuple[str, tuple[int, int, int, datetime, int], int]]
    ] = {}
    for ticket in open_tickets:
        lane = support_action_lane(ticket, now=now)
        counter = lane_counters.setdefault(lane, Counter())
        counter["count"] += 1
        waiting_state = support_waiting_state(ticket)
        if waiting_state == "awaiting_admin":
            counter["awaiting_admin"] += 1
        elif waiting_state == "awaiting_user":
            counter["awaiting_user"] += 1
        if ticket.priority in {SUPPORT_PRIORITY_HIGH, SUPPORT_PRIORITY_URGENT}:
            counter["high_priority"] += 1
        if ensure_aware_utc(ticket.updated_at) < stale_threshold:
            counter["stale"] += 1
        if support_sla_bucket(ticket, now=now) == SUPPORT_SLA_BUCKET_BREACH:
            counter["sla_breach"] += 1
        lane_categories.setdefault(lane, Counter())[ticket.category] += 1
        escalation_lane = support_escalation_lane(ticket, now=now)
        lane_escalations.setdefault(lane, Counter())[escalation_lane] += 1
        if ticket.id is not None:
            lane_ticket_ids.setdefault(lane, []).append(
                (escalation_lane, _support_ticket_queue_rank_key(ticket, now=now), ticket.id)
            )

    items: list[SupportNextActionQueue] = []
    for lane, counter in lane_counters.items():
        top_category = None
        if lane_categories.get(lane):
            top_category = lane_categories[lane].most_common(1)[0][0]
        top_escalation_lane = _support_counter_top_key(
            lane_escalations.get(lane, Counter()),
            order_key=lambda value: (
                _support_escalation_lane_order(value),
                support_escalation_lane_label(value),
            ),
        )
        sample_ticket_ids = _support_top_lane_sample_ticket_ids(
            lane_ticket_ids.get(lane, []),
            preferred_lane=top_escalation_lane,
        )
        items.append(
            SupportNextActionQueue(
                key=lane,
                sample_ticket_ids=sample_ticket_ids,
                count=counter["count"],
                awaiting_admin_count=counter["awaiting_admin"],
                awaiting_user_count=counter["awaiting_user"],
                high_priority_count=counter["high_priority"],
                stale_count=counter["stale"],
                sla_breach_count=counter["sla_breach"],
                top_category=top_category,
                top_escalation_lane=top_escalation_lane,
                note=support_next_action_queue_note(lane, top_escalation_lane),
            )
        )
    return sorted(
        items,
        key=lambda item: (
            -item.sla_breach_count,
            -item.high_priority_count,
            -item.count,
            _support_action_lane_order(item.key),
            support_action_lane_label(item.key),
        ),
    )


def _build_support_action_routes(
    open_tickets: list[SupportTicket],
    *,
    now: datetime,
) -> list[SupportActionRoute]:
    stale_threshold = now - timedelta(hours=SUPPORT_STALE_HOURS)
    route_counters: dict[tuple[str, str], Counter[str]] = {}
    route_priorities: dict[tuple[str, str], Counter[str]] = {}
    route_categories: dict[tuple[str, str], Counter[str]] = {}
    route_kinds: dict[tuple[str, str], Counter[str]] = {}
    route_ticket_ids: dict[
        tuple[str, str], list[tuple[tuple[int, int, int, datetime, int], int]]
    ] = {}
    hotspot_order = {
        SUPPORT_SLA_HOTSPOT_BREACH: 0,
        SUPPORT_SLA_HOTSPOT_STALE: 1,
        SUPPORT_SLA_HOTSPOT_WARNING: 2,
    }
    for ticket in open_tickets:
        action_key = support_action_lane(ticket, now=now)
        escalation_key = support_escalation_lane(ticket, now=now)
        route_key = (escalation_key, action_key)
        counter = route_counters.setdefault(route_key, Counter())
        counter["count"] += 1
        waiting_state = support_waiting_state(ticket)
        if waiting_state == "awaiting_admin":
            counter["awaiting_admin"] += 1
        elif waiting_state == "awaiting_user":
            counter["awaiting_user"] += 1
        if ticket.priority in {SUPPORT_PRIORITY_HIGH, SUPPORT_PRIORITY_URGENT}:
            counter["high_priority"] += 1
        if ensure_aware_utc(ticket.updated_at) < stale_threshold:
            counter["stale"] += 1
        bucket = support_sla_bucket(ticket, now=now)
        if bucket == SUPPORT_SLA_BUCKET_WARNING:
            counter["sla_warning"] += 1
        elif bucket == SUPPORT_SLA_BUCKET_BREACH:
            counter["sla_breach"] += 1
        route_priorities.setdefault(route_key, Counter())[ticket.priority] += 1
        route_categories.setdefault(route_key, Counter())[ticket.category] += 1
        hotspot_kind = _support_hotspot_kind_for_ticket(ticket, now=now)
        if hotspot_kind is not None:
            route_kinds.setdefault(route_key, Counter())[hotspot_kind] += 1
        if ticket.id is not None:
            route_ticket_ids.setdefault(route_key, []).append(
                (_support_ticket_queue_rank_key(ticket, now=now), ticket.id)
            )

    items: list[SupportActionRoute] = []
    for route_key, counter in route_counters.items():
        escalation_key, action_key = route_key
        top_priority = _support_counter_top_key(
            route_priorities.get(route_key, Counter()),
            order_key=lambda value: (
                _support_priority_order(value),
                support_priority_label(value),
            ),
        )
        top_category = _support_counter_top_key(
            route_categories.get(route_key, Counter()),
            order_key=support_category_label,
        )
        top_kind = _support_counter_top_key(
            route_kinds.get(route_key, Counter()),
            order_key=lambda value: (
                hotspot_order.get(value, 99),
                support_sla_hotspot_label(value),
            ),
        )
        sample_ticket_ids = _support_top_sample_ticket_ids(route_ticket_ids.get(route_key, []))
        items.append(
            SupportActionRoute(
                key=f"{escalation_key}:{action_key}",
                escalation_key=escalation_key,
                action_key=action_key,
                sample_ticket_ids=sample_ticket_ids,
                count=counter["count"],
                awaiting_admin_count=counter["awaiting_admin"],
                awaiting_user_count=counter["awaiting_user"],
                high_priority_count=counter["high_priority"],
                stale_count=counter["stale"],
                sla_warning_count=counter["sla_warning"],
                sla_breach_count=counter["sla_breach"],
                top_priority=top_priority,
                top_category=top_category,
                top_kind=top_kind,
                note=support_action_route_note(action_key, escalation_key, top_kind),
            )
        )
    return sorted(
        items,
        key=lambda item: (
            -item.sla_breach_count,
            -item.high_priority_count,
            -item.awaiting_admin_count,
            -item.count,
            _support_escalation_lane_order(item.escalation_key),
            _support_action_lane_order(item.action_key),
            support_escalation_action_label(item.escalation_key, item.action_key),
        ),
    )


def _build_support_triage_queue(
    open_tickets: list[SupportTicket],
    *,
    now: datetime,
) -> list[SupportTriageQueueItem]:
    stale_threshold = now - timedelta(hours=SUPPORT_STALE_HOURS)
    queue_counters: dict[tuple[str, str, str], Counter[str]] = {}
    queue_priorities: dict[tuple[str, str, str], Counter[str]] = {}
    queue_kinds: dict[tuple[str, str, str], Counter[str]] = {}
    queue_ticket_ids: dict[tuple[str, str, str], list[tuple[tuple[int, int, int, datetime, int], int]]] = {}
    hotspot_order = {
        SUPPORT_SLA_HOTSPOT_BREACH: 0,
        SUPPORT_SLA_HOTSPOT_STALE: 1,
        SUPPORT_SLA_HOTSPOT_WARNING: 2,
    }
    for ticket in open_tickets:
        action_key = support_action_lane(ticket, now=now)
        escalation_key = support_escalation_lane(ticket, now=now)
        pack_key = support_canned_reply_pack_key(ticket)
        queue_key = (escalation_key, action_key, pack_key)
        counter = queue_counters.setdefault(queue_key, Counter())
        counter["count"] += 1
        waiting_state = support_waiting_state(ticket)
        if waiting_state == "awaiting_admin":
            counter["awaiting_admin"] += 1
        elif waiting_state == "awaiting_user":
            counter["awaiting_user"] += 1
        if ticket.priority in {SUPPORT_PRIORITY_HIGH, SUPPORT_PRIORITY_URGENT}:
            counter["high_priority"] += 1
        if ensure_aware_utc(ticket.updated_at) < stale_threshold:
            counter["stale"] += 1
        bucket = support_sla_bucket(ticket, now=now)
        if bucket == SUPPORT_SLA_BUCKET_WARNING:
            counter["sla_warning"] += 1
        elif bucket == SUPPORT_SLA_BUCKET_BREACH:
            counter["sla_breach"] += 1
        queue_priorities.setdefault(queue_key, Counter())[ticket.priority] += 1
        hotspot_kind = _support_hotspot_kind_for_ticket(ticket, now=now)
        if hotspot_kind is not None:
            queue_kinds.setdefault(queue_key, Counter())[hotspot_kind] += 1
        if ticket.id is not None:
            queue_ticket_ids.setdefault(queue_key, []).append(
                (_support_ticket_queue_rank_key(ticket, now=now), ticket.id)
            )

    items: list[SupportTriageQueueItem] = []
    for queue_key, counter in queue_counters.items():
        escalation_key, action_key, pack_key = queue_key
        top_priority = _support_counter_top_key(
            queue_priorities.get(queue_key, Counter()),
            order_key=lambda value: (
                _support_priority_order(value),
                support_priority_label(value),
            ),
        )
        top_kind = _support_counter_top_key(
            queue_kinds.get(queue_key, Counter()),
            order_key=lambda value: (
                hotspot_order.get(value, 99),
                support_sla_hotspot_label(value),
            ),
        )
        sample_ticket_ids = _support_top_sample_ticket_ids(queue_ticket_ids.get(queue_key, []))
        items.append(
            SupportTriageQueueItem(
                key=f"{escalation_key}:{action_key}:{pack_key}",
                escalation_key=escalation_key,
                action_key=action_key,
                pack_key=pack_key,
                sample_ticket_ids=sample_ticket_ids,
                count=counter["count"],
                awaiting_admin_count=counter["awaiting_admin"],
                awaiting_user_count=counter["awaiting_user"],
                high_priority_count=counter["high_priority"],
                stale_count=counter["stale"],
                sla_warning_count=counter["sla_warning"],
                sla_breach_count=counter["sla_breach"],
                top_priority=top_priority,
                top_kind=top_kind,
                note=support_triage_queue_note(
                    pack_key,
                    action_key,
                    escalation_key,
                    top_kind,
                ),
            )
        )
    return sorted(
        items,
        key=lambda item: (
            -item.awaiting_admin_count,
            -item.sla_breach_count,
            -item.high_priority_count,
            -item.count,
            _support_escalation_lane_order(item.escalation_key),
            _support_action_lane_order(item.action_key),
            support_canned_reply_pack_label(item.pack_key),
        ),
    )
