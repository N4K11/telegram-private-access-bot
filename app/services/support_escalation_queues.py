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
    SUPPORT_STALE_HOURS,
    support_escalation_action_label,
    support_escalation_lane_label,
    support_priority_label,
)
from app.services.support_models import (
    SupportEscalationAction,
    SupportEscalationLane,
    SupportEscalationWatch,
    SupportPriorityFocus,
)
from app.services.support_sla import (
    _support_action_lane_order,
    _support_escalation_lane_order,
    _support_priority_order,
    support_action_lane,
    support_escalation_lane,
    support_escalation_watch_note,
    support_sla_bucket,
    support_waiting_state,
)
from app.utils.datetime import ensure_aware_utc


def _build_support_escalation_lanes(
    open_tickets: list[SupportTicket],
    *,
    now: datetime,
) -> list[SupportEscalationLane]:
    stale_threshold = now - timedelta(hours=SUPPORT_STALE_HOURS)
    lane_counters: dict[str, Counter[str]] = {}
    lane_categories: dict[str, Counter[str]] = {}
    for ticket in open_tickets:
        lane = support_escalation_lane(ticket, now=now)
        counter = lane_counters.setdefault(lane, Counter())
        counter["count"] += 1
        if ticket.priority in {SUPPORT_PRIORITY_HIGH, SUPPORT_PRIORITY_URGENT}:
            counter["high_priority"] += 1
        if ensure_aware_utc(ticket.updated_at) < stale_threshold:
            counter["stale"] += 1
        if support_sla_bucket(ticket, now=now) == SUPPORT_SLA_BUCKET_BREACH:
            counter["sla_breach"] += 1
        lane_categories.setdefault(lane, Counter())[ticket.category] += 1

    items: list[SupportEscalationLane] = []
    for lane, counter in lane_counters.items():
        top_category = None
        if lane_categories.get(lane):
            top_category = lane_categories[lane].most_common(1)[0][0]
        items.append(
            SupportEscalationLane(
                key=lane,
                count=counter["count"],
                high_priority_count=counter["high_priority"],
                stale_count=counter["stale"],
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
            _support_escalation_lane_order(item.key),
            support_escalation_lane_label(item.key),
        ),
    )


def _build_support_escalation_actions(
    open_tickets: list[SupportTicket],
    *,
    now: datetime,
) -> list[SupportEscalationAction]:
    stale_threshold = now - timedelta(hours=SUPPORT_STALE_HOURS)
    pair_counters: dict[tuple[str, str], Counter[str]] = {}
    pair_categories: dict[tuple[str, str], Counter[str]] = {}
    for ticket in open_tickets:
        escalation_key = support_escalation_lane(ticket, now=now)
        action_key = support_action_lane(ticket, now=now)
        pair_key = (escalation_key, action_key)
        counter = pair_counters.setdefault(pair_key, Counter())
        counter["count"] += 1
        if ticket.priority in {SUPPORT_PRIORITY_HIGH, SUPPORT_PRIORITY_URGENT}:
            counter["high_priority"] += 1
        if ensure_aware_utc(ticket.updated_at) < stale_threshold:
            counter["stale"] += 1
        if support_sla_bucket(ticket, now=now) == SUPPORT_SLA_BUCKET_BREACH:
            counter["sla_breach"] += 1
        pair_categories.setdefault(pair_key, Counter())[ticket.category] += 1

    items: list[SupportEscalationAction] = []
    for pair_key, counter in pair_counters.items():
        escalation_key, action_key = pair_key
        top_category = None
        if pair_categories.get(pair_key):
            top_category = pair_categories[pair_key].most_common(1)[0][0]
        items.append(
            SupportEscalationAction(
                key=f"{escalation_key}:{action_key}",
                escalation_key=escalation_key,
                action_key=action_key,
                count=counter["count"],
                high_priority_count=counter["high_priority"],
                stale_count=counter["stale"],
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
            _support_escalation_lane_order(item.escalation_key),
            _support_action_lane_order(item.action_key),
            support_escalation_action_label(item.escalation_key, item.action_key),
        ),
    )


def _build_support_priority_focus(
    open_tickets: list[SupportTicket],
    *,
    now: datetime,
) -> list[SupportPriorityFocus]:
    stale_threshold = now - timedelta(hours=SUPPORT_STALE_HOURS)
    priority_counters: dict[str, Counter[str]] = {}
    priority_categories: dict[str, Counter[str]] = {}
    priority_actions: dict[str, Counter[str]] = {}
    priority_escalations: dict[str, Counter[str]] = {}
    for ticket in open_tickets:
        priority = ticket.priority
        counter = priority_counters.setdefault(priority, Counter())
        counter["count"] += 1
        waiting_state = support_waiting_state(ticket)
        if waiting_state == "awaiting_admin":
            counter["awaiting_admin"] += 1
        elif waiting_state == "awaiting_user":
            counter["awaiting_user"] += 1
        if ensure_aware_utc(ticket.updated_at) < stale_threshold:
            counter["stale"] += 1
        bucket = support_sla_bucket(ticket, now=now)
        if bucket == SUPPORT_SLA_BUCKET_WARNING:
            counter["sla_warning"] += 1
        elif bucket == SUPPORT_SLA_BUCKET_BREACH:
            counter["sla_breach"] += 1
        priority_categories.setdefault(priority, Counter())[ticket.category] += 1
        priority_actions.setdefault(priority, Counter())[support_action_lane(ticket, now=now)] += 1
        priority_escalations.setdefault(priority, Counter())[support_escalation_lane(ticket, now=now)] += 1

    items: list[SupportPriorityFocus] = []
    for priority, counter in priority_counters.items():
        top_category = None
        if priority_categories.get(priority):
            top_category = priority_categories[priority].most_common(1)[0][0]
        top_action_lane = None
        if priority_actions.get(priority):
            top_action_lane = priority_actions[priority].most_common(1)[0][0]
        top_escalation_lane = None
        if priority_escalations.get(priority):
            top_escalation_lane = priority_escalations[priority].most_common(1)[0][0]
        items.append(
            SupportPriorityFocus(
                key=priority,
                count=counter["count"],
                awaiting_admin_count=counter["awaiting_admin"],
                awaiting_user_count=counter["awaiting_user"],
                stale_count=counter["stale"],
                sla_warning_count=counter["sla_warning"],
                sla_breach_count=counter["sla_breach"],
                top_category=top_category,
                top_action_lane=top_action_lane,
                top_escalation_lane=top_escalation_lane,
            )
        )
    return sorted(
        items,
        key=lambda item: (
            -item.sla_breach_count,
            -item.awaiting_admin_count,
            -item.count,
            _support_priority_order(item.key),
            support_priority_label(item.key),
        ),
    )


def _build_support_escalation_watchlist(
    open_tickets: list[SupportTicket],
    *,
    now: datetime,
) -> list[SupportEscalationWatch]:
    stale_threshold = now - timedelta(hours=SUPPORT_STALE_HOURS)
    lane_counters: dict[str, Counter[str]] = {}
    lane_categories: dict[str, Counter[str]] = {}
    lane_priorities: dict[str, Counter[str]] = {}
    lane_actions: dict[str, Counter[str]] = {}
    for ticket in open_tickets:
        lane = support_escalation_lane(ticket, now=now)
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
        lane_priorities.setdefault(lane, Counter())[ticket.priority] += 1
        lane_actions.setdefault(lane, Counter())[support_action_lane(ticket, now=now)] += 1

    items: list[SupportEscalationWatch] = []
    for lane, counter in lane_counters.items():
        top_category = None
        if lane_categories.get(lane):
            top_category = lane_categories[lane].most_common(1)[0][0]
        top_priority = None
        if lane_priorities.get(lane):
            top_priority = lane_priorities[lane].most_common(1)[0][0]
        top_action_lane = None
        if lane_actions.get(lane):
            top_action_lane = lane_actions[lane].most_common(1)[0][0]
        watch_score = (
            counter["sla_breach"] * 5
            + counter["high_priority"] * 3
            + counter["stale"] * 2
            + counter["awaiting_admin"]
        )
        items.append(
            SupportEscalationWatch(
                key=lane,
                count=counter["count"],
                awaiting_admin_count=counter["awaiting_admin"],
                awaiting_user_count=counter["awaiting_user"],
                high_priority_count=counter["high_priority"],
                stale_count=counter["stale"],
                sla_breach_count=counter["sla_breach"],
                top_priority=top_priority,
                top_category=top_category,
                top_action_lane=top_action_lane,
                watch_score=watch_score,
                note=support_escalation_watch_note(lane, top_action_lane),
            )
        )
    return sorted(
        items,
        key=lambda item: (
            -item.watch_score,
            -item.sla_breach_count,
            -item.high_priority_count,
            -item.count,
            _support_escalation_lane_order(item.key),
            support_escalation_lane_label(item.key),
        ),
    )
