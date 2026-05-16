from __future__ import annotations

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
    SUPPORT_ESCALATION_LANE_ACCESS_BLOCKER,
    SUPPORT_ESCALATION_LANE_HIGH_PRIORITY_WATCH,
    SUPPORT_ESCALATION_LANE_PAYMENT_BLOCKER,
    SUPPORT_ESCALATION_LANE_REPLY_BREACH,
    SUPPORT_ESCALATION_LANE_ROUTINE_QUEUE,
    SUPPORT_ESCALATION_LANE_STALE_HIGH_PRIORITY,
    SUPPORT_ESCALATION_LANE_TECHNICAL_WATCH,
    SUPPORT_ESCALATION_LANE_WAITING_USER_RISK,
    SUPPORT_PRIORITY_HIGH,
    SUPPORT_PRIORITY_LOW,
    SUPPORT_PRIORITY_NORMAL,
    SUPPORT_PRIORITY_URGENT,
    SUPPORT_SLA_BUCKET_BREACH,
    SUPPORT_SLA_BUCKET_CLOSED,
    SUPPORT_SLA_BUCKET_FRESH,
    SUPPORT_SLA_BUCKET_WARNING,
    SUPPORT_SLA_HOTSPOT_BREACH,
    SUPPORT_SLA_HOTSPOT_WARNING,
    SUPPORT_SLA_HOURS_BY_PRIORITY,
    SUPPORT_STALE_HOURS,
    SUPPORT_STATUS_OPEN,
    support_action_lane_label,
    support_canned_reply_pack_label,
    support_close_reason_label,
    support_escalation_lane_label,
)
from app.services.support_reply_packs import SUPPORT_CANNED_REPLY_PACKS
from app.utils.datetime import ensure_aware_utc, utcnow


def support_waiting_state(ticket: SupportTicket) -> str:
    if ticket.status != SUPPORT_STATUS_OPEN:
        return "closed"
    if ticket.last_user_message_at and (
        ticket.last_admin_message_at is None
        or ticket.last_user_message_at > ticket.last_admin_message_at
    ):
        return "awaiting_admin"
    if ticket.last_admin_message_at:
        return "awaiting_user"
    return "new"


def support_sla_due_hours(ticket: SupportTicket) -> int:
    return SUPPORT_SLA_HOURS_BY_PRIORITY.get(
        ticket.priority,
        SUPPORT_SLA_HOURS_BY_PRIORITY[SUPPORT_PRIORITY_NORMAL],
    )


def support_sla_bucket(ticket: SupportTicket, *, now: datetime | None = None) -> str:
    if ticket.status != SUPPORT_STATUS_OPEN:
        return SUPPORT_SLA_BUCKET_CLOSED
    reference_time = ensure_aware_utc(now or utcnow())
    updated_at = ensure_aware_utc(ticket.updated_at)
    elapsed_hours = max((reference_time - updated_at).total_seconds() / 3600, 0)
    due_hours = support_sla_due_hours(ticket)
    if elapsed_hours >= due_hours:
        return SUPPORT_SLA_BUCKET_BREACH
    if elapsed_hours >= max(due_hours / 2, 1):
        return SUPPORT_SLA_BUCKET_WARNING
    return SUPPORT_SLA_BUCKET_FRESH


def _support_canned_reply_pack_keys(ticket: SupportTicket) -> tuple[str, str]:
    waiting_state = support_waiting_state(ticket)
    if ticket.status != SUPPORT_STATUS_OPEN:
        pack_key = "closed:any"
    elif waiting_state == "awaiting_user":
        pack_key = f"awaiting_user:{ticket.category}"
    else:
        pack_key = f"open:{ticket.category}"
    fallback_key = (
        "closed:any"
        if ticket.status != SUPPORT_STATUS_OPEN
        else f"{pack_key.split(':', 1)[0]}:{SUPPORT_CATEGORY_OTHER}"
    )
    return pack_key, fallback_key


def support_canned_reply_pack_key(ticket: SupportTicket) -> str:
    pack_key, fallback_key = _support_canned_reply_pack_keys(ticket)
    if pack_key in SUPPORT_CANNED_REPLY_PACKS:
        return pack_key
    return fallback_key


def support_canned_reply_pack_titles(pack_key: str, *, limit: int = 2) -> list[str]:
    raw_items = SUPPORT_CANNED_REPLY_PACKS.get(pack_key, ())
    return [title for _, title, _, _ in raw_items[:limit]]

def support_sla_action_note(kind: str, action_lane: str, escalation_lane: str) -> str:
    if kind == SUPPORT_SLA_HOTSPOT_BREACH:
        return (
            f"First move: {support_action_lane_label(action_lane)}. "
            f"Escalate through {support_escalation_lane_label(escalation_lane)} "
            "if the blocker stays open."
        )
    if kind == SUPPORT_SLA_HOTSPOT_WARNING:
        return (
            f"Pre-breach queue: {support_action_lane_label(action_lane)} while keeping "
            f"{support_escalation_lane_label(escalation_lane)} under watch."
        )
    return (
        f"Stale queue: {support_action_lane_label(action_lane)} and re-check "
        f"{support_escalation_lane_label(escalation_lane)} before it drifts further."
    )


def support_sla_action_queue_note(
    kind: str,
    action_lane: str,
    escalation_lane: str | None,
) -> str:
    return support_sla_action_note(
        kind,
        action_lane,
        escalation_lane or SUPPORT_ESCALATION_LANE_ROUTINE_QUEUE,
    )

def support_operator_action_trend_note(
    pack_key: str,
    close_reason: str,
    action_key: str,
) -> str:
    return (
        f"{support_canned_reply_pack_label(pack_key)} most often closes as "
        f"{support_close_reason_label(close_reason)} after "
        f"{support_action_lane_label(action_key)}."
    )


def support_escalation_watch_note(escalation_lane: str, action_lane: str | None) -> str:
    if escalation_lane == SUPPORT_ESCALATION_LANE_PAYMENT_BLOCKER:
        return "??????? ??????, ?????? ??????? ? ??????, ????? ?????? ?????? ????? ???????."
    if escalation_lane == SUPPORT_ESCALATION_LANE_ACCESS_BLOCKER:
        return "??????? ????????, invite-?????? ? ????? ?????? ????? ??????? ????????????."
    if escalation_lane == SUPPORT_ESCALATION_LANE_TECHNICAL_WATCH:
        return "??? ??????????? ?????? ? ?? ???????? ????? ??? ??????? ?????? ?????? SLA-????."
    if escalation_lane == SUPPORT_ESCALATION_LANE_WAITING_USER_RISK:
        return "????? follow-up ???????????? ??? ?????????? ???????? ?? ?????????? ??????."
    if escalation_lane == SUPPORT_ESCALATION_LANE_STALE_HIGH_PRIORITY:
        return "????? ???????????? high-priority backlog ? ????? ????? ? ?????????????? ?????????."
    if escalation_lane == SUPPORT_ESCALATION_LANE_REPLY_BREACH:
        return "?????? ???????????? ?????? ? ????? ????? ??????? ? SLA."
    if escalation_lane == SUPPORT_ESCALATION_LANE_HIGH_PRIORITY_WATCH:
        return "????? ??????? ????????? ??? ??????????? ?? ?????????? ?????? ??? ?????."
    if action_lane:
        return f"????????? ???: {support_action_lane_label(action_lane)}."
    return "???????? ??????? ??? ????????? ?????????."


def support_next_action_label(ticket: SupportTicket, *, now: datetime | None = None) -> str:
    return support_action_lane_label(support_action_lane(ticket, now=now))


def support_next_action_severity(ticket: SupportTicket, *, now: datetime | None = None) -> str:
    action_lane = support_action_lane(ticket, now=now)
    escalation_lane = support_escalation_lane(ticket, now=now)
    if ticket.status != SUPPORT_STATUS_OPEN:
        return "info"
    if action_lane in {
        SUPPORT_ACTION_LANE_REPLY_NOW,
        SUPPORT_ACTION_LANE_PAYMENT_REVIEW,
        SUPPORT_ACTION_LANE_ACCESS_REVIEW,
    }:
        return "warn"
    if escalation_lane in {
        SUPPORT_ESCALATION_LANE_PAYMENT_BLOCKER,
        SUPPORT_ESCALATION_LANE_ACCESS_BLOCKER,
        SUPPORT_ESCALATION_LANE_REPLY_BREACH,
        SUPPORT_ESCALATION_LANE_STALE_HIGH_PRIORITY,
    }:
        return "warn"
    return "info"


def support_next_action_note(ticket: SupportTicket, *, now: datetime | None = None) -> str:
    event_time = ensure_aware_utc(now or utcnow())
    action_lane = support_action_lane(ticket, now=event_time)
    escalation_lane = support_escalation_lane(ticket, now=event_time)
    waiting_state = support_waiting_state(ticket)

    if ticket.status != SUPPORT_STATUS_OPEN:
        return (
            "Проверь причину закрытия и переоткрой тикет, если пользователь вернулся "
            "с новым сообщением или вопрос не закрыт."
        )
    if waiting_state == "new":
        return (
            "Прочитай первое сообщение, выбери нужный сценарий ответа и зафиксируй "
            "для пользователя следующий шаг."
        )
    if action_lane == SUPPORT_ACTION_LANE_REPLY_NOW:
        if ticket.category == SUPPORT_CATEGORY_PAYMENT:
            base_note = (
                "Сначала проверь последний платёж, затем сразу ответь пользователю "
                "со статусом оплаты и доступа."
            )
        elif ticket.category == SUPPORT_CATEGORY_ACCESS:
            base_note = (
                "Сначала проверь подписку, invite и состояние канала, затем сразу "
                "ответь пользователю по доступу."
            )
        elif ticket.category == SUPPORT_CATEGORY_TECHNICAL:
            base_note = (
                "Сначала подтверди текущий технический статус и сразу дай "
                "пользователю следующий шаг."
            )
        else:
            base_note = (
                "Сначала ответь пользователю и зафиксируй, какой шаг будет следующим."
            )
    elif action_lane == SUPPORT_ACTION_LANE_PAYMENT_REVIEW:
        base_note = (
            "Проверь платёж, промокод и выдачу доступа, затем дай пользователю "
            "конкретный статус."
        )
    elif action_lane == SUPPORT_ACTION_LANE_ACCESS_REVIEW:
        base_note = (
            "Проверь активную подписку, invite и права канала, затем сообщи "
            "пользователю, что именно мешает доступу."
        )
    elif action_lane == SUPPORT_ACTION_LANE_TECHNICAL_TRIAGE:
        base_note = (
            "Собери симптомы, проверь runtime и состояние канала, затем дай "
            "пользователю следующий технический шаг."
        )
    elif action_lane == SUPPORT_ACTION_LANE_CLARIFY_REQUEST:
        base_note = (
            "Уточни недостающие детали одним сообщением и явно зафиксируй, "
            "каких данных ждёшь от пользователя."
        )
    elif action_lane == SUPPORT_ACTION_LANE_WAITING_USER_FOLLOWUP:
        base_note = (
            "Отправь один follow-up и напомни, какие данные или действие "
            "ждёшь от пользователя дальше."
        )
    else:
        base_note = (
            "Прочитай первый запрос и переведи тикет в нужный рабочий сценарий: "
            "платёж, доступ, техника или уточнение."
        )
    return f"{base_note} Эскалация: {support_escalation_lane_label(escalation_lane)}."


def support_next_action_queue_note(action_lane: str, escalation_lane: str | None) -> str:
    action_label = support_action_lane_label(action_lane)
    escalation_label = (
        support_escalation_lane_label(escalation_lane)
        if escalation_lane
        else support_escalation_lane_label(SUPPORT_ESCALATION_LANE_ROUTINE_QUEUE)
    )
    if action_lane == SUPPORT_ACTION_LANE_REPLY_NOW:
        return (
            f"Сначала {action_label.lower()}, затем проверь, не остался ли открытым "
            f"контур {escalation_label}."
        )
    if action_lane == SUPPORT_ACTION_LANE_PAYMENT_REVIEW:
        return (
            "Сначала проверь оплату и выдачу доступа, затем прогоняй очередь через "
            f"{escalation_label}."
        )
    if action_lane == SUPPORT_ACTION_LANE_ACCESS_REVIEW:
        return (
            f"Сначала проверь подписку, invite и канал, затем веди тикет через {escalation_label}."
        )
    if action_lane == SUPPORT_ACTION_LANE_TECHNICAL_TRIAGE:
        return (
            "Сначала собери технические симптомы и зафиксируй следующий шаг по линии "
            f"{escalation_label}."
        )
    if action_lane == SUPPORT_ACTION_LANE_CLARIFY_REQUEST:
        return (
            f"Сначала уточни недостающие данные и держи под контролем {escalation_label}."
        )
    if action_lane == SUPPORT_ACTION_LANE_WAITING_USER_FOLLOWUP:
        return (
            f"Сначала отправь один follow-up и отслеживай риск {escalation_label}."
        )
    return f"Сначала разберите новый тикет и зафиксируйте очередь {escalation_label}."


def support_action_route_note(
    action_lane: str,
    escalation_lane: str,
    hotspot_kind: str | None,
) -> str:
    if hotspot_kind is not None:
        return support_sla_action_queue_note(hotspot_kind, action_lane, escalation_lane)
    return support_next_action_queue_note(action_lane, escalation_lane)


def support_triage_queue_note(
    pack_key: str,
    action_lane: str,
    escalation_lane: str,
    hotspot_kind: str | None,
) -> str:
    return (
        f"Use {support_canned_reply_pack_label(pack_key)} first. "
        f"{support_action_route_note(action_lane, escalation_lane, hotspot_kind)}"
    )


def support_action_lane(ticket: SupportTicket, *, now: datetime | None = None) -> str:
    waiting_state = support_waiting_state(ticket)
    if waiting_state == "closed":
        return SUPPORT_ACTION_LANE_NEW_TICKET_REVIEW
    if waiting_state == "new":
        return SUPPORT_ACTION_LANE_NEW_TICKET_REVIEW
    if waiting_state == "awaiting_user":
        return SUPPORT_ACTION_LANE_WAITING_USER_FOLLOWUP

    sla_bucket = support_sla_bucket(ticket, now=now)
    if sla_bucket == SUPPORT_SLA_BUCKET_BREACH:
        return SUPPORT_ACTION_LANE_REPLY_NOW
    if ticket.category == SUPPORT_CATEGORY_PAYMENT:
        return SUPPORT_ACTION_LANE_PAYMENT_REVIEW
    if ticket.category == SUPPORT_CATEGORY_ACCESS:
        return SUPPORT_ACTION_LANE_ACCESS_REVIEW
    if ticket.category == SUPPORT_CATEGORY_TECHNICAL:
        return SUPPORT_ACTION_LANE_TECHNICAL_TRIAGE
    return SUPPORT_ACTION_LANE_CLARIFY_REQUEST


def _support_action_lane_order(lane: str) -> int:
    order = {
        SUPPORT_ACTION_LANE_REPLY_NOW: 0,
        SUPPORT_ACTION_LANE_PAYMENT_REVIEW: 1,
        SUPPORT_ACTION_LANE_ACCESS_REVIEW: 2,
        SUPPORT_ACTION_LANE_TECHNICAL_TRIAGE: 3,
        SUPPORT_ACTION_LANE_CLARIFY_REQUEST: 4,
        SUPPORT_ACTION_LANE_WAITING_USER_FOLLOWUP: 5,
        SUPPORT_ACTION_LANE_NEW_TICKET_REVIEW: 6,
    }
    return order.get(lane, 99)


def support_escalation_lane(ticket: SupportTicket, *, now: datetime | None = None) -> str:
    event_time = ensure_aware_utc(now or utcnow())
    waiting_state = support_waiting_state(ticket)
    if waiting_state == "closed":
        return SUPPORT_ESCALATION_LANE_ROUTINE_QUEUE

    is_stale = ensure_aware_utc(ticket.updated_at) < event_time - timedelta(
        hours=SUPPORT_STALE_HOURS
    )
    is_high_priority = ticket.priority in {SUPPORT_PRIORITY_HIGH, SUPPORT_PRIORITY_URGENT}
    sla_bucket = support_sla_bucket(ticket, now=event_time)

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
    if sla_bucket == SUPPORT_SLA_BUCKET_BREACH:
        return SUPPORT_ESCALATION_LANE_REPLY_BREACH
    if is_high_priority:
        return SUPPORT_ESCALATION_LANE_HIGH_PRIORITY_WATCH
    return SUPPORT_ESCALATION_LANE_ROUTINE_QUEUE


def _support_escalation_lane_order(lane: str) -> int:
    order = {
        SUPPORT_ESCALATION_LANE_PAYMENT_BLOCKER: 0,
        SUPPORT_ESCALATION_LANE_ACCESS_BLOCKER: 1,
        SUPPORT_ESCALATION_LANE_TECHNICAL_WATCH: 2,
        SUPPORT_ESCALATION_LANE_WAITING_USER_RISK: 3,
        SUPPORT_ESCALATION_LANE_STALE_HIGH_PRIORITY: 4,
        SUPPORT_ESCALATION_LANE_REPLY_BREACH: 5,
        SUPPORT_ESCALATION_LANE_HIGH_PRIORITY_WATCH: 6,
        SUPPORT_ESCALATION_LANE_ROUTINE_QUEUE: 7,
    }
    return order.get(lane, 99)


def _support_priority_order(priority: str) -> int:
    order = {
        SUPPORT_PRIORITY_URGENT: 0,
        SUPPORT_PRIORITY_HIGH: 1,
        SUPPORT_PRIORITY_NORMAL: 2,
        SUPPORT_PRIORITY_LOW: 3,
    }
    return order.get(priority, 99)

