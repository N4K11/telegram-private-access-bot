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
    support_category_label,
    support_escalation_lane_label,
    support_priority_label,
    support_sla_hotspot_label,
)
from app.services.support_models import (
    SupportActionLane,
    SupportSlaAction,
    SupportSlaActionQueue,
    SupportSlaHotspot,
)
from app.services.support_queue_ranking import (
    _support_counter_top_key,
    _support_ticket_queue_rank_key,
    _support_top_lane_sample_ticket_ids,
)
from app.services.support_sla import (
    _support_action_lane_order,
    _support_escalation_lane_order,
    _support_priority_order,
    support_action_lane,
    support_escalation_lane,
    support_sla_action_note,
    support_sla_action_queue_note,
    support_sla_bucket,
)
from app.utils.datetime import ensure_aware_utc


def _build_support_sla_hotspots(
    open_tickets: list[SupportTicket],
    *,
    now: datetime,
) -> list[SupportSlaHotspot]:
    stale_threshold = now - timedelta(hours=SUPPORT_STALE_HOURS)
    counter: Counter[tuple[str, str, str]] = Counter()
    for ticket in open_tickets:
        bucket = support_sla_bucket(ticket, now=now)
        if bucket == SUPPORT_SLA_BUCKET_BREACH:
            counter[(SUPPORT_SLA_HOTSPOT_BREACH, ticket.category, ticket.priority)] += 1
        elif bucket == SUPPORT_SLA_BUCKET_WARNING:
            counter[(SUPPORT_SLA_HOTSPOT_WARNING, ticket.category, ticket.priority)] += 1
        if ensure_aware_utc(ticket.updated_at) < stale_threshold:
            counter[(SUPPORT_SLA_HOTSPOT_STALE, ticket.category, ticket.priority)] += 1

    items = [
        SupportSlaHotspot(kind=kind, category=category, priority=priority, count=count)
        for (kind, category, priority), count in counter.items()
    ]
    order = {
        SUPPORT_SLA_HOTSPOT_BREACH: 0,
        SUPPORT_SLA_HOTSPOT_STALE: 1,
        SUPPORT_SLA_HOTSPOT_WARNING: 2,
    }
    return sorted(
        items,
        key=lambda item: (
            -item.count,
            order.get(item.kind, 99),
            support_category_label(item.category),
            support_priority_label(item.priority),
        ),
    )


def _build_support_sla_actions(
    open_tickets: list[SupportTicket],
    *,
    now: datetime,
) -> list[SupportSlaAction]:
    stale_threshold = now - timedelta(hours=SUPPORT_STALE_HOURS)
    counter: Counter[tuple[str, str, str]] = Counter()
    action_counters: dict[tuple[str, str, str], Counter[str]] = {}
    escalation_counters: dict[tuple[str, str, str], Counter[str]] = {}
    hotspot_order = {
        SUPPORT_SLA_HOTSPOT_BREACH: 0,
        SUPPORT_SLA_HOTSPOT_STALE: 1,
        SUPPORT_SLA_HOTSPOT_WARNING: 2,
    }
    for ticket in open_tickets:
        bucket = support_sla_bucket(ticket, now=now)
        action_lane = support_action_lane(ticket, now=now)
        escalation_lane = support_escalation_lane(ticket, now=now)
        hotspot_keys: list[str] = []
        if bucket == SUPPORT_SLA_BUCKET_BREACH:
            hotspot_keys.append(SUPPORT_SLA_HOTSPOT_BREACH)
        elif bucket == SUPPORT_SLA_BUCKET_WARNING:
            hotspot_keys.append(SUPPORT_SLA_HOTSPOT_WARNING)
        if ensure_aware_utc(ticket.updated_at) < stale_threshold:
            hotspot_keys.append(SUPPORT_SLA_HOTSPOT_STALE)
        for hotspot_kind in hotspot_keys:
            key = (hotspot_kind, ticket.category, ticket.priority)
            counter[key] += 1
            action_counters.setdefault(key, Counter())[action_lane] += 1
            escalation_counters.setdefault(key, Counter())[escalation_lane] += 1

    items: list[SupportSlaAction] = []
    for (kind, category, priority), count in counter.items():
        top_action = action_counters[(kind, category, priority)].most_common(1)[0][0]
        top_escalation = escalation_counters[(kind, category, priority)].most_common(1)[0][0]
        items.append(
            SupportSlaAction(
                kind=kind,
                category=category,
                priority=priority,
                count=count,
                action_key=top_action,
                escalation_key=top_escalation,
                note=support_sla_action_note(kind, top_action, top_escalation),
            )
        )
    return sorted(
        items,
        key=lambda item: (
            -item.count,
            hotspot_order.get(item.kind, 99),
            _support_priority_order(item.priority),
            _support_action_lane_order(item.action_key),
            support_category_label(item.category),
        ),
    )


def _build_support_sla_action_queue(
    open_tickets: list[SupportTicket],
    *,
    now: datetime,
) -> list[SupportSlaActionQueue]:
    stale_threshold = now - timedelta(hours=SUPPORT_STALE_HOURS)
    lane_counters: dict[str, Counter[str]] = {}
    lane_kinds: dict[str, Counter[str]] = {}
    lane_priorities: dict[str, Counter[str]] = {}
    lane_categories: dict[str, Counter[str]] = {}
    lane_escalations: dict[str, Counter[str]] = {}
    lane_ticket_ids: dict[
        str, list[tuple[str, tuple[int, int, int, datetime, int], int]]
    ] = {}
    hotspot_order = {
        SUPPORT_SLA_HOTSPOT_BREACH: 0,
        SUPPORT_SLA_HOTSPOT_STALE: 1,
        SUPPORT_SLA_HOTSPOT_WARNING: 2,
    }
    for ticket in open_tickets:
        hotspot_kind = _support_hotspot_kind_for_ticket(ticket, now=now)
        if hotspot_kind is None:
            continue
        lane = support_action_lane(ticket, now=now)
        escalation_lane = support_escalation_lane(ticket, now=now)
        counter = lane_counters.setdefault(lane, Counter())
        counter["count"] += 1
        if ticket.priority in {SUPPORT_PRIORITY_HIGH, SUPPORT_PRIORITY_URGENT}:
            counter["high_priority"] += 1
        if ensure_aware_utc(ticket.updated_at) < stale_threshold:
            counter["stale"] += 1
        if hotspot_kind == SUPPORT_SLA_HOTSPOT_BREACH:
            counter["sla_breach"] += 1
        lane_kinds.setdefault(lane, Counter())[hotspot_kind] += 1
        lane_priorities.setdefault(lane, Counter())[ticket.priority] += 1
        lane_categories.setdefault(lane, Counter())[ticket.category] += 1
        lane_escalations.setdefault(lane, Counter())[escalation_lane] += 1
        if ticket.id is not None:
            lane_ticket_ids.setdefault(lane, []).append(
                (escalation_lane, _support_ticket_queue_rank_key(ticket, now=now), ticket.id)
            )

    items: list[SupportSlaActionQueue] = []
    for lane, counter in lane_counters.items():
        top_kind = _support_counter_top_key(
            lane_kinds.get(lane, Counter()),
            order_key=lambda value: (
                hotspot_order.get(value, 99),
                support_sla_hotspot_label(value),
            ),
        )
        top_priority = _support_counter_top_key(
            lane_priorities.get(lane, Counter()),
            order_key=lambda value: (
                _support_priority_order(value),
                support_priority_label(value),
            ),
        )
        top_category = _support_counter_top_key(
            lane_categories.get(lane, Counter()),
            order_key=support_category_label,
        )
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
            SupportSlaActionQueue(
                key=lane,
                sample_ticket_ids=sample_ticket_ids,
                count=counter["count"],
                high_priority_count=counter["high_priority"],
                stale_count=counter["stale"],
                sla_breach_count=counter["sla_breach"],
                top_kind=top_kind,
                top_priority=top_priority,
                top_category=top_category,
                top_escalation_lane=top_escalation_lane,
                note=support_sla_action_queue_note(
                    top_kind or SUPPORT_SLA_HOTSPOT_STALE,
                    lane,
                    top_escalation_lane,
                ),
            )
        )
    return sorted(
        items,
        key=lambda item: (
            -item.sla_breach_count,
            -item.high_priority_count,
            -item.count,
            hotspot_order.get(item.top_kind or SUPPORT_SLA_HOTSPOT_WARNING, 99),
            _support_action_lane_order(item.key),
            support_action_lane_label(item.key),
        ),
    )


def _build_support_action_lanes(
    open_tickets: list[SupportTicket],
    *,
    now: datetime,
) -> list[SupportActionLane]:
    stale_threshold = now - timedelta(hours=SUPPORT_STALE_HOURS)
    lane_counters: dict[str, Counter[str]] = {}
    lane_categories: dict[str, Counter[str]] = {}
    for ticket in open_tickets:
        lane = support_action_lane(ticket, now=now)
        counter = lane_counters.setdefault(lane, Counter())
        counter["count"] += 1
        if ticket.priority in {SUPPORT_PRIORITY_HIGH, SUPPORT_PRIORITY_URGENT}:
            counter["high_priority"] += 1
        if ensure_aware_utc(ticket.updated_at) < stale_threshold:
            counter["stale"] += 1
        bucket = support_sla_bucket(ticket, now=now)
        if bucket == SUPPORT_SLA_BUCKET_BREACH:
            counter["sla_breach"] += 1
        elif bucket == SUPPORT_SLA_BUCKET_WARNING:
            counter["sla_warning"] += 1
        lane_categories.setdefault(lane, Counter())[ticket.category] += 1

    items: list[SupportActionLane] = []
    for lane, counter in lane_counters.items():
        top_category = None
        if lane_categories.get(lane):
            top_category = lane_categories[lane].most_common(1)[0][0]
        items.append(
            SupportActionLane(
                key=lane,
                count=counter["count"],
                high_priority_count=counter["high_priority"],
                stale_count=counter["stale"],
                sla_warning_count=counter["sla_warning"],
                sla_breach_count=counter["sla_breach"],
                top_category=top_category,
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


def _support_hotspot_kind_for_ticket(
    ticket: SupportTicket,
    *,
    now: datetime,
) -> str | None:
    stale_threshold = now - timedelta(hours=SUPPORT_STALE_HOURS)
    bucket = support_sla_bucket(ticket, now=now)
    is_stale = ensure_aware_utc(ticket.updated_at) < stale_threshold
    if bucket == SUPPORT_SLA_BUCKET_BREACH:
        return SUPPORT_SLA_HOTSPOT_BREACH
    if is_stale:
        return SUPPORT_SLA_HOTSPOT_STALE
    if bucket == SUPPORT_SLA_BUCKET_WARNING:
        return SUPPORT_SLA_HOTSPOT_WARNING
    return None
