from __future__ import annotations

from collections import Counter
from datetime import datetime

from app.db.models import SupportTicket
from app.services.support_catalog import (
    SUPPORT_SLA_BUCKET_BREACH,
    SUPPORT_SLA_BUCKET_CLOSED,
    SUPPORT_SLA_BUCKET_FRESH,
    SUPPORT_SLA_BUCKET_WARNING,
)
from app.services.support_sla import (
    _support_priority_order,
    support_sla_bucket,
    support_waiting_state,
)
from app.utils.datetime import ensure_aware_utc


def _support_counter_top_key(counter: Counter[str], *, order_key) -> str | None:
    if not counter:
        return None
    return sorted(counter.items(), key=lambda item: (-item[1], order_key(item[0])))[0][0]


def _support_ticket_queue_rank_key(
    ticket: SupportTicket,
    *,
    now: datetime,
) -> tuple[int, int, int, datetime, int]:
    waiting_state_order = {
        "awaiting_admin": 0,
        "awaiting_user": 1,
        "new": 2,
        "closed": 3,
    }
    sla_order = {
        SUPPORT_SLA_BUCKET_BREACH: 0,
        SUPPORT_SLA_BUCKET_WARNING: 1,
        SUPPORT_SLA_BUCKET_FRESH: 2,
        SUPPORT_SLA_BUCKET_CLOSED: 3,
    }
    waiting_state = support_waiting_state(ticket)
    sla_bucket = support_sla_bucket(ticket, now=now)
    updated_at = ensure_aware_utc(ticket.updated_at)
    return (
        waiting_state_order.get(waiting_state, 99),
        sla_order.get(sla_bucket, 99),
        _support_priority_order(ticket.priority),
        updated_at,
        ticket.id or 0,
    )


def _support_top_sample_ticket_ids(
    ranked_ticket_ids: list[tuple[tuple[int, int, int, datetime, int], int]],
    *,
    limit: int = 3,
) -> tuple[int, ...]:
    return tuple(ticket_id for _, ticket_id in sorted(ranked_ticket_ids)[:limit] if ticket_id > 0)


def _support_top_lane_sample_ticket_ids(
    ranked_ticket_ids: list[tuple[str, tuple[int, int, int, datetime, int], int]],
    *,
    preferred_lane: str | None,
    limit: int = 3,
) -> tuple[int, ...]:
    ranked = sorted(
        ranked_ticket_ids,
        key=lambda item: (
            0 if preferred_lane is not None and item[0] == preferred_lane else 1,
            item[1],
            item[2],
        ),
    )
    return tuple(ticket_id for _, _, ticket_id in ranked[:limit] if ticket_id > 0)
