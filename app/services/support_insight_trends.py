from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from app.db.models import SupportTicket
from app.services.support_catalog import (
    SUPPORT_ACTION_LANE_ACCESS_REVIEW,
    SUPPORT_ACTION_LANE_CLARIFY_REQUEST,
    SUPPORT_ACTION_LANE_NEW_TICKET_REVIEW,
    SUPPORT_ACTION_LANE_PAYMENT_REVIEW,
    SUPPORT_ACTION_LANE_REPLY_NOW,
    SUPPORT_ACTION_LANE_TECHNICAL_TRIAGE,
    SUPPORT_ACTION_LANE_WAITING_USER_FOLLOWUP,
    SUPPORT_CATEGORY_ACCESS,
    SUPPORT_CATEGORY_OTHER,
    SUPPORT_CATEGORY_PAYMENT,
    SUPPORT_CATEGORY_TECHNICAL,
    SUPPORT_CLOSE_REASON_DUPLICATE,
    SUPPORT_CLOSE_REASON_NO_RESPONSE,
    SUPPORT_CLOSE_REASON_RESOLVED,
    SUPPORT_CLOSE_REASON_UNSPECIFIED,
    SUPPORT_ESCALATION_LANE_ACCESS_BLOCKER,
    SUPPORT_ESCALATION_LANE_HIGH_PRIORITY_WATCH,
    SUPPORT_ESCALATION_LANE_PAYMENT_BLOCKER,
    SUPPORT_ESCALATION_LANE_REPLY_BREACH,
    SUPPORT_ESCALATION_LANE_ROUTINE_QUEUE,
    SUPPORT_ESCALATION_LANE_STALE_HIGH_PRIORITY,
    SUPPORT_ESCALATION_LANE_TECHNICAL_WATCH,
    SUPPORT_ESCALATION_LANE_WAITING_USER_RISK,
    SUPPORT_PRIORITY_HIGH,
    SUPPORT_PRIORITY_URGENT,
    SUPPORT_STALE_HOURS,
    support_canned_reply_pack_label,
    support_close_reason_label,
    support_escalation_lane_label,
)
from app.services.support_models import (
    SupportCloseReasonTrend,
    SupportEscalationTrend,
    SupportInsightPackOutcome,
    SupportOperatorActionTrend,
)
from app.services.support_reply_packs import SUPPORT_CANNED_REPLY_PACKS
from app.services.support_sla import (
    _support_action_lane_order,
    _support_escalation_lane_order,
    support_operator_action_trend_note,
    support_sla_due_hours,
)
from app.utils.datetime import ensure_aware_utc


def _support_historical_pack_key(ticket: SupportTicket) -> str:
    phase = "awaiting_user" if ticket.last_admin_message_at is not None else "open"
    pack_key = f"{phase}:{ticket.category}"
    if pack_key in SUPPORT_CANNED_REPLY_PACKS:
        return pack_key
    return f"{phase}:{SUPPORT_CATEGORY_OTHER}"


def _build_support_pack_outcomes(
    closed_tickets: list[SupportTicket],
    *,
    now: datetime,
    recent_days: int,
) -> list[SupportInsightPackOutcome]:
    recent_threshold = now - timedelta(days=recent_days)
    counters: dict[str, Counter[str]] = {}
    for ticket in closed_tickets:
        closed_reference = ensure_aware_utc(
            ticket.closed_at or ticket.updated_at or ticket.created_at
        )
        if closed_reference < recent_threshold:
            continue
        pack_key = _support_historical_pack_key(ticket)
        counter = counters.setdefault(pack_key, Counter())
        counter["total"] += 1
        reason = ticket.close_reason or SUPPORT_CLOSE_REASON_UNSPECIFIED
        if reason == SUPPORT_CLOSE_REASON_RESOLVED:
            counter["resolved"] += 1
        elif reason == SUPPORT_CLOSE_REASON_NO_RESPONSE:
            counter["no_response"] += 1
        elif reason == SUPPORT_CLOSE_REASON_DUPLICATE:
            counter["duplicate"] += 1
        else:
            counter["other"] += 1

    items: list[SupportInsightPackOutcome] = []
    for pack_key, counter in counters.items():
        total = counter["total"]
        if total <= 0:
            continue
        items.append(
            SupportInsightPackOutcome(
                pack_key=pack_key,
                ticket_count=total,
                resolved_count=counter["resolved"],
                no_response_count=counter["no_response"],
                duplicate_count=counter["duplicate"],
                other_count=counter["other"],
                resolved_rate_percent=round((counter["resolved"] / total) * 100, 1),
                no_response_rate_percent=round((counter["no_response"] / total) * 100, 1),
                duplicate_rate_percent=round((counter["duplicate"] / total) * 100, 1),
            )
        )
    return sorted(
        items,
        key=lambda item: (
            -item.ticket_count,
            -item.no_response_rate_percent,
            -item.duplicate_rate_percent,
            item.resolved_rate_percent,
            support_canned_reply_pack_label(item.pack_key),
        ),
    )


def _build_support_close_reason_trends(
    closed_tickets: list[SupportTicket],
    *,
    now: datetime,
    recent_days: int,
) -> tuple[dict[str, int], dict[str, int], list[SupportCloseReasonTrend]]:
    current_threshold = now - timedelta(days=recent_days)
    previous_threshold = current_threshold - timedelta(days=recent_days)
    current_counts: Counter[str] = Counter()
    previous_counts: Counter[str] = Counter()
    for ticket in closed_tickets:
        closed_reference = ensure_aware_utc(
            ticket.closed_at or ticket.updated_at or ticket.created_at
        )
        reason = ticket.close_reason or SUPPORT_CLOSE_REASON_UNSPECIFIED
        if closed_reference >= current_threshold:
            current_counts[reason] += 1
        elif closed_reference >= previous_threshold:
            previous_counts[reason] += 1

    trend_items = [
        SupportCloseReasonTrend(
            reason=reason,
            current_count=current_counts.get(reason, 0),
            previous_count=previous_counts.get(reason, 0),
            delta=current_counts.get(reason, 0) - previous_counts.get(reason, 0),
        )
        for reason in set(current_counts) | set(previous_counts)
    ]
    trend_items.sort(
        key=lambda item: (
            -abs(item.delta),
            -item.current_count,
            support_close_reason_label(item.reason),
        )
    )
    return dict(current_counts), dict(previous_counts), trend_items


def _historical_support_waiting_state(ticket: SupportTicket) -> str:
    if ticket.last_user_message_at and (
        ticket.last_admin_message_at is None
        or ticket.last_user_message_at > ticket.last_admin_message_at
    ):
        return "awaiting_admin"
    if ticket.last_admin_message_at:
        return "awaiting_user"
    return "new"


def _last_historical_activity(ticket: SupportTicket) -> datetime:
    return ensure_aware_utc(
        max(
            value
            for value in (
                ticket.last_user_message_at,
                ticket.last_admin_message_at,
                ticket.created_at,
            )
            if value is not None
        )
    )


def _historical_support_escalation_lane(ticket: SupportTicket) -> str:
    reference_time = ensure_aware_utc(ticket.closed_at or ticket.updated_at or ticket.created_at)
    waiting_state = _historical_support_waiting_state(ticket)
    last_activity = _last_historical_activity(ticket)
    is_stale = last_activity < reference_time - timedelta(hours=SUPPORT_STALE_HOURS)
    is_high_priority = ticket.priority in {SUPPORT_PRIORITY_HIGH, SUPPORT_PRIORITY_URGENT}
    elapsed_hours = max((reference_time - last_activity).total_seconds() / 3600, 0)
    sla_breach = elapsed_hours >= support_sla_due_hours(ticket)

    if ticket.category == SUPPORT_CATEGORY_PAYMENT and waiting_state == "awaiting_admin":
        return SUPPORT_ESCALATION_LANE_PAYMENT_BLOCKER
    if ticket.category == SUPPORT_CATEGORY_ACCESS and waiting_state == "awaiting_admin":
        return SUPPORT_ESCALATION_LANE_ACCESS_BLOCKER
    if ticket.category == SUPPORT_CATEGORY_TECHNICAL and waiting_state == "awaiting_admin":
        return SUPPORT_ESCALATION_LANE_TECHNICAL_WATCH
    if waiting_state == "awaiting_user" and is_stale:
        return SUPPORT_ESCALATION_LANE_WAITING_USER_RISK
    if is_high_priority and is_stale:
        return SUPPORT_ESCALATION_LANE_STALE_HIGH_PRIORITY
    if sla_breach:
        return SUPPORT_ESCALATION_LANE_REPLY_BREACH
    if is_high_priority:
        return SUPPORT_ESCALATION_LANE_HIGH_PRIORITY_WATCH
    return SUPPORT_ESCALATION_LANE_ROUTINE_QUEUE


def _historical_support_action_lane(ticket: SupportTicket) -> str:
    waiting_state = _historical_support_waiting_state(ticket)
    if waiting_state == "new":
        return SUPPORT_ACTION_LANE_NEW_TICKET_REVIEW
    if waiting_state == "awaiting_user":
        return SUPPORT_ACTION_LANE_WAITING_USER_FOLLOWUP

    reference_time = ensure_aware_utc(ticket.closed_at or ticket.updated_at or ticket.created_at)
    last_activity = _last_historical_activity(ticket)
    elapsed_hours = max((reference_time - last_activity).total_seconds() / 3600, 0)
    if elapsed_hours >= support_sla_due_hours(ticket):
        return SUPPORT_ACTION_LANE_REPLY_NOW
    if ticket.category == SUPPORT_CATEGORY_PAYMENT:
        return SUPPORT_ACTION_LANE_PAYMENT_REVIEW
    if ticket.category == SUPPORT_CATEGORY_ACCESS:
        return SUPPORT_ACTION_LANE_ACCESS_REVIEW
    if ticket.category == SUPPORT_CATEGORY_TECHNICAL:
        return SUPPORT_ACTION_LANE_TECHNICAL_TRIAGE
    return SUPPORT_ACTION_LANE_CLARIFY_REQUEST


def _build_support_escalation_trends(
    closed_tickets: list[SupportTicket],
    *,
    now: datetime,
    recent_days: int,
) -> list[SupportEscalationTrend]:
    current_threshold = now - timedelta(days=recent_days)
    previous_threshold = current_threshold - timedelta(days=recent_days)
    current_counts: Counter[str] = Counter()
    previous_counts: Counter[str] = Counter()
    for ticket in closed_tickets:
        closed_reference = ensure_aware_utc(
            ticket.closed_at or ticket.updated_at or ticket.created_at
        )
        lane = _historical_support_escalation_lane(ticket)
        if closed_reference >= current_threshold:
            current_counts[lane] += 1
        elif closed_reference >= previous_threshold:
            previous_counts[lane] += 1

    items = [
        SupportEscalationTrend(
            key=key,
            current_count=current_counts.get(key, 0),
            previous_count=previous_counts.get(key, 0),
            delta=current_counts.get(key, 0) - previous_counts.get(key, 0),
        )
        for key in set(current_counts) | set(previous_counts)
    ]
    return sorted(
        items,
        key=lambda item: (
            -abs(item.delta),
            -item.current_count,
            _support_escalation_lane_order(item.key),
            support_escalation_lane_label(item.key),
        ),
    )


def _build_support_operator_action_trends(
    closed_tickets: list[SupportTicket],
    *,
    now: datetime,
    recent_days: int,
) -> list[SupportOperatorActionTrend]:
    current_threshold = now - timedelta(days=recent_days)
    previous_threshold = current_threshold - timedelta(days=recent_days)
    current_counts: Counter[tuple[str, str, str]] = Counter()
    previous_counts: Counter[tuple[str, str, str]] = Counter()
    for ticket in closed_tickets:
        closed_reference = ensure_aware_utc(
            ticket.closed_at or ticket.updated_at or ticket.created_at
        )
        pack_key = _support_historical_pack_key(ticket)
        close_reason = ticket.close_reason or SUPPORT_CLOSE_REASON_UNSPECIFIED
        action_key = _historical_support_action_lane(ticket)
        key = (pack_key, close_reason, action_key)
        if closed_reference >= current_threshold:
            current_counts[key] += 1
        elif closed_reference >= previous_threshold:
            previous_counts[key] += 1

    items = [
        SupportOperatorActionTrend(
            key=f"{pack_key}:{close_reason}:{action_key}",
            pack_key=pack_key,
            close_reason=close_reason,
            action_key=action_key,
            current_count=current_counts.get((pack_key, close_reason, action_key), 0),
            previous_count=previous_counts.get((pack_key, close_reason, action_key), 0),
            delta=(
                current_counts.get((pack_key, close_reason, action_key), 0)
                - previous_counts.get((pack_key, close_reason, action_key), 0)
            ),
            note=support_operator_action_trend_note(pack_key, close_reason, action_key),
        )
        for pack_key, close_reason, action_key in set(current_counts) | set(previous_counts)
    ]
    return sorted(
        items,
        key=lambda item: (
            -item.current_count,
            -abs(item.delta),
            _support_action_lane_order(item.action_key),
            support_canned_reply_pack_label(item.pack_key),
            support_close_reason_label(item.close_reason),
        ),
    )
