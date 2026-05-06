# ruff: noqa: E501
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SupportMessage, SupportTicket
from app.db.repositories.support_tickets import SupportTicketRepository
from app.services.audit import write_audit_log
from app.utils.datetime import ensure_aware_utc, utcnow

SUPPORT_STATUS_OPEN = "open"
SUPPORT_STATUS_CLOSED = "closed"
SUPPORT_MESSAGE_LIMIT = 1500
SUPPORT_TICKET_DAILY_LIMIT = 3
SUPPORT_STALE_HOURS = 24

SUPPORT_CATEGORY_PAYMENT = "payment"
SUPPORT_CATEGORY_ACCESS = "access"
SUPPORT_CATEGORY_TECHNICAL = "technical"
SUPPORT_CATEGORY_OTHER = "other"

SUPPORT_CATEGORY_LABELS: dict[str, str] = {
    SUPPORT_CATEGORY_PAYMENT: "Оплата",
    SUPPORT_CATEGORY_ACCESS: "Доступ",
    SUPPORT_CATEGORY_TECHNICAL: "Технический вопрос",
    SUPPORT_CATEGORY_OTHER: "Другое",
}

SUPPORT_STATUS_LABELS: dict[str, str] = {
    SUPPORT_STATUS_OPEN: "Открыт",
    SUPPORT_STATUS_CLOSED: "Закрыт",
}

SUPPORT_PRIORITY_LOW = "low"
SUPPORT_PRIORITY_NORMAL = "normal"
SUPPORT_PRIORITY_HIGH = "high"
SUPPORT_PRIORITY_URGENT = "urgent"

SUPPORT_PRIORITY_LABELS: dict[str, str] = {
    SUPPORT_PRIORITY_LOW: "Низкий",
    SUPPORT_PRIORITY_NORMAL: "Обычный",
    SUPPORT_PRIORITY_HIGH: "Высокий",
    SUPPORT_PRIORITY_URGENT: "Срочный",
}

SUPPORT_PRIORITY_BY_CATEGORY: dict[str, str] = {
    SUPPORT_CATEGORY_PAYMENT: SUPPORT_PRIORITY_HIGH,
    SUPPORT_CATEGORY_ACCESS: SUPPORT_PRIORITY_HIGH,
    SUPPORT_CATEGORY_TECHNICAL: SUPPORT_PRIORITY_NORMAL,
    SUPPORT_CATEGORY_OTHER: SUPPORT_PRIORITY_NORMAL,
}

SUPPORT_SLA_HOURS_BY_PRIORITY: dict[str, int] = {
    SUPPORT_PRIORITY_LOW: 48,
    SUPPORT_PRIORITY_NORMAL: 24,
    SUPPORT_PRIORITY_HIGH: 12,
    SUPPORT_PRIORITY_URGENT: 4,
}

SUPPORT_SLA_BUCKET_FRESH = "fresh"
SUPPORT_SLA_BUCKET_WARNING = "warning"
SUPPORT_SLA_BUCKET_BREACH = "breach"
SUPPORT_SLA_BUCKET_CLOSED = "closed"

SUPPORT_SLA_BUCKET_LABELS: dict[str, str] = {
    SUPPORT_SLA_BUCKET_FRESH: "В SLA",
    SUPPORT_SLA_BUCKET_WARNING: "Скоро SLA",
    SUPPORT_SLA_BUCKET_BREACH: "SLA нарушен",
    SUPPORT_SLA_BUCKET_CLOSED: "Закрыт",
}

SUPPORT_CLOSE_REASON_RESOLVED = "resolved"
SUPPORT_CLOSE_REASON_USER_CONFIRMED = "user_confirmed"
SUPPORT_CLOSE_REASON_NO_RESPONSE = "no_response"
SUPPORT_CLOSE_REASON_DUPLICATE = "duplicate"
SUPPORT_CLOSE_REASON_POLICY = "policy"
SUPPORT_CLOSE_REASON_OTHER = "other"
SUPPORT_CLOSE_REASON_UNSPECIFIED = "unspecified"

SUPPORT_CLOSE_REASON_LABELS: dict[str, str] = {
    SUPPORT_CLOSE_REASON_RESOLVED: "Решено",
    SUPPORT_CLOSE_REASON_USER_CONFIRMED: "Подтверждено пользователем",
    SUPPORT_CLOSE_REASON_NO_RESPONSE: "Нет ответа",
    SUPPORT_CLOSE_REASON_DUPLICATE: "Дубликат",
    SUPPORT_CLOSE_REASON_POLICY: "Вне политики",
    SUPPORT_CLOSE_REASON_OTHER: "Другая причина",
    SUPPORT_CLOSE_REASON_UNSPECIFIED: "Без причины",
}


SUPPORT_WAITING_STATE_LABELS: dict[str, str] = {
    "awaiting_admin": "\u0416\u0434\u0451\u0442 \u0430\u0434\u043c\u0438\u043d\u0430",
    "awaiting_user": "\u0416\u0434\u0451\u0442 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f",
    "new": "\u041d\u043e\u0432\u044b\u0439",
    "closed": "\u0417\u0430\u043a\u0440\u044b\u0442",
}

SUPPORT_INSIGHTS_RECENT_CLOSE_DAYS = 7
SUPPORT_PACK_OUTCOME_DAYS = 30

SUPPORT_SLA_HOTSPOT_BREACH = "breach"
SUPPORT_SLA_HOTSPOT_WARNING = "warning"
SUPPORT_SLA_HOTSPOT_STALE = "stale"

SUPPORT_CANNED_REPLY_KIND_ACK = "ack"
SUPPORT_CANNED_REPLY_KIND_CLARIFY = "clarify"
SUPPORT_CANNED_REPLY_KIND_RESOLVE = "resolve"
SUPPORT_CANNED_REPLY_KIND_FOLLOW_UP = "follow_up"

SUPPORT_ACTION_LANE_REPLY_NOW = "reply_now"
SUPPORT_ACTION_LANE_PAYMENT_REVIEW = "payment_review"
SUPPORT_ACTION_LANE_ACCESS_REVIEW = "access_review"
SUPPORT_ACTION_LANE_TECHNICAL_TRIAGE = "technical_triage"
SUPPORT_ACTION_LANE_CLARIFY_REQUEST = "clarify_request"
SUPPORT_ACTION_LANE_WAITING_USER_FOLLOWUP = "waiting_user_followup"
SUPPORT_ACTION_LANE_NEW_TICKET_REVIEW = "new_ticket_review"

SUPPORT_ACTION_LANE_LABELS: dict[str, str] = {
    SUPPORT_ACTION_LANE_REPLY_NOW: "Срочно ответить",
    SUPPORT_ACTION_LANE_PAYMENT_REVIEW: "Проверить оплату",
    SUPPORT_ACTION_LANE_ACCESS_REVIEW: "Проверить доступ",
    SUPPORT_ACTION_LANE_TECHNICAL_TRIAGE: "Тех. разбор",
    SUPPORT_ACTION_LANE_CLARIFY_REQUEST: "Уточнить запрос",
    SUPPORT_ACTION_LANE_WAITING_USER_FOLLOWUP: "Ждём ответ пользователя",
    SUPPORT_ACTION_LANE_NEW_TICKET_REVIEW: "Новый тикет",
}

SUPPORT_ESCALATION_LANE_PAYMENT_BLOCKER = "payment_blocker"
SUPPORT_ESCALATION_LANE_ACCESS_BLOCKER = "access_blocker"
SUPPORT_ESCALATION_LANE_TECHNICAL_WATCH = "technical_watch"
SUPPORT_ESCALATION_LANE_WAITING_USER_RISK = "waiting_user_risk"
SUPPORT_ESCALATION_LANE_STALE_HIGH_PRIORITY = "stale_high_priority"
SUPPORT_ESCALATION_LANE_REPLY_BREACH = "reply_breach"
SUPPORT_ESCALATION_LANE_HIGH_PRIORITY_WATCH = "high_priority_watch"
SUPPORT_ESCALATION_LANE_ROUTINE_QUEUE = "routine_queue"

SUPPORT_ESCALATION_LANE_LABELS: dict[str, str] = {
    SUPPORT_ESCALATION_LANE_PAYMENT_BLOCKER: "Платёжный блокер",
    SUPPORT_ESCALATION_LANE_ACCESS_BLOCKER: "Блокер доступа",
    SUPPORT_ESCALATION_LANE_TECHNICAL_WATCH: "Тех. эскалация",
    SUPPORT_ESCALATION_LANE_WAITING_USER_RISK: "Риск ожидания пользователя",
    SUPPORT_ESCALATION_LANE_STALE_HIGH_PRIORITY: "Просроченный high-priority",
    SUPPORT_ESCALATION_LANE_REPLY_BREACH: "SLA breach",
    SUPPORT_ESCALATION_LANE_HIGH_PRIORITY_WATCH: "Высокий приоритет",
    SUPPORT_ESCALATION_LANE_ROUTINE_QUEUE: "Обычная очередь",
}

SUPPORT_CANNED_REPLY_PACK_LABELS: dict[str, str] = {
    "open:payment": "Оплата: новый тикет",
    "open:access": "Доступ: новый тикет",
    "open:technical": "Технический: новый тикет",
    "open:other": "Другое: новый тикет",
    "awaiting_user:payment": "Оплата: ждём пользователя",
    "awaiting_user:access": "Доступ: ждём пользователя",
    "awaiting_user:technical": "Технический: ждём пользователя",
    "awaiting_user:other": "Другое: ждём пользователя",
    "closed:any": "Закрытый тикет",
}
SUPPORT_CANNED_REPLY_PACKS: dict[str, tuple[tuple[str, str, str, str], ...]] = {
    "open:payment": (
        (
            "payment_ack_review",
            "\u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u044c \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443 \u043e\u043f\u043b\u0430\u0442\u044b",
            "\u0412\u0438\u0436\u0443 \u0442\u0438\u043a\u0435\u0442 \u043f\u043e \u043e\u043f\u043b\u0430\u0442\u0435. \u041f\u0440\u043e\u0432\u0435\u0440\u044f\u044e \u043f\u043b\u0430\u0442\u0451\u0436 \u0438 \u0434\u043e\u0441\u0442\u0443\u043f, \u0432\u0435\u0440\u043d\u0443\u0441\u044c \u0441 \u043e\u0442\u0432\u0435\u0442\u043e\u043c \u0432 \u044d\u0442\u043e\u043c \u0442\u0440\u0435\u0434\u0435.",
            SUPPORT_CANNED_REPLY_KIND_ACK,
        ),
        (
            "payment_request_receipt",
            "\u0417\u0430\u043f\u0440\u043e\u0441\u0438\u0442\u044c \u0447\u0435\u043a \u0438 \u0432\u0440\u0435\u043c\u044f \u043e\u043f\u043b\u0430\u0442\u044b",
            "\u041f\u0440\u0438\u0448\u043b\u0438, \u043f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430, \u0441\u043a\u0440\u0438\u043d \u043e\u043f\u043b\u0430\u0442\u044b, \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u0442\u0430\u0440\u0438\u0444\u0430 \u0438 \u0432\u0440\u0435\u043c\u044f \u043f\u043b\u0430\u0442\u0435\u0436\u0430. \u0422\u0430\u043a \u044f \u0431\u044b\u0441\u0442\u0440\u0435\u0435 \u0441\u0432\u0435\u0440\u044e \u043f\u043b\u0430\u0442\u0451\u0436.",
            SUPPORT_CANNED_REPLY_KIND_CLARIFY,
        ),
        (
            "payment_manual_access_fix",
            "\u0421\u043e\u043e\u0431\u0449\u0438\u0442\u044c \u043e \u0440\u0443\u0447\u043d\u043e\u0439 \u0430\u043a\u0442\u0438\u0432\u0430\u0446\u0438\u0438",
            "\u041f\u043b\u0430\u0442\u0451\u0436 \u043d\u0430\u0439\u0434\u0435\u043d. \u0415\u0441\u043b\u0438 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0430\u044f \u0430\u043a\u0442\u0438\u0432\u0430\u0446\u0438\u044f \u043d\u0435 \u043f\u0440\u043e\u0448\u043b\u0430, \u0441\u0435\u0439\u0447\u0430\u0441 \u0430\u043a\u0442\u0438\u0432\u0438\u0440\u0443\u044e \u0434\u043e\u0441\u0442\u0443\u043f \u0432\u0440\u0443\u0447\u043d\u0443\u044e \u0438 \u043f\u0440\u0438\u0448\u043b\u044e \u043e\u0431\u043d\u043e\u0432\u043b\u0451\u043d\u043d\u0443\u044e \u0441\u0441\u044b\u043b\u043a\u0443, \u0435\u0441\u043b\u0438 \u043e\u043d\u0430 \u043f\u043e\u043d\u0430\u0434\u043e\u0431\u0438\u0442\u0441\u044f.",
            SUPPORT_CANNED_REPLY_KIND_RESOLVE,
        ),
    ),
    "open:access": (
        (
            "access_ack_review",
            "\u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u044c \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443 \u0434\u043e\u0441\u0442\u0443\u043f\u0430",
            "\u0412\u0438\u0436\u0443 \u0442\u0438\u043a\u0435\u0442 \u043f\u043e \u0434\u043e\u0441\u0442\u0443\u043f\u0443. \u041f\u0440\u043e\u0432\u0435\u0440\u044f\u044e \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0443, \u0438\u043d\u0432\u0430\u0439\u0442 \u0438 \u043f\u0440\u0430\u0432\u0430 \u0431\u043e\u0442\u0430. \u0412\u0435\u0440\u043d\u0443\u0441\u044c \u0441 \u043e\u0442\u0432\u0435\u0442\u043e\u043c \u0437\u0434\u0435\u0441\u044c.",
            SUPPORT_CANNED_REPLY_KIND_ACK,
        ),
        (
            "access_request_join_context",
            "\u0423\u0442\u043e\u0447\u043d\u0438\u0442\u044c \u0441\u0442\u0430\u0442\u0443\u0441 \u0432\u0441\u0442\u0443\u043f\u043b\u0435\u043d\u0438\u044f",
            "\u041d\u0430\u043f\u0438\u0448\u0438, \u043f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430, \u0447\u0442\u043e \u0438\u043c\u0435\u043d\u043d\u043e \u043d\u0435 \u043f\u043e\u043b\u0443\u0447\u0430\u0435\u0442\u0441\u044f: \u0441\u0441\u044b\u043b\u043a\u0430 \u043d\u0435 \u043e\u0442\u043a\u0440\u044b\u0432\u0430\u0435\u0442\u0441\u044f, \u043a\u0430\u043d\u0430\u043b \u043d\u0435 \u043f\u0443\u0441\u043a\u0430\u0435\u0442 \u0438\u043b\u0438 \u0431\u043e\u0442 \u043f\u0438\u0448\u0435\u0442 \u043e\u0431 \u043e\u0448\u0438\u0431\u043a\u0435.",
            SUPPORT_CANNED_REPLY_KIND_CLARIFY,
        ),
        (
            "access_resend_link",
            "\u0421\u043e\u043e\u0431\u0449\u0438\u0442\u044c \u043e \u043f\u043e\u0432\u0442\u043e\u0440\u043d\u043e\u0439 \u0441\u0441\u044b\u043b\u043a\u0435",
            "\u0415\u0441\u043b\u0438 \u0441\u0442\u0430\u0440\u0430\u044f \u0441\u0441\u044b\u043b\u043a\u0430 \u043d\u0435 \u0441\u0440\u0430\u0431\u0430\u0442\u044b\u0432\u0430\u0435\u0442, \u0441\u0435\u0439\u0447\u0430\u0441 \u043f\u0440\u043e\u0432\u0435\u0440\u044e \u0434\u043e\u0441\u0442\u0443\u043f \u0438 \u043f\u0440\u0438 \u043d\u0435\u043e\u0431\u0445\u043e\u0434\u0438\u043c\u043e\u0441\u0442\u0438 \u043f\u0440\u0438\u0448\u043b\u044e \u043d\u043e\u0432\u0443\u044e \u0441\u0441\u044b\u043b\u043a\u0443 \u043d\u0430 \u0432\u0445\u043e\u0434.",
            SUPPORT_CANNED_REPLY_KIND_RESOLVE,
        ),
    ),
    "open:technical": (
        (
            "technical_ack_review",
            "\u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u044c \u0440\u0430\u0437\u0431\u043e\u0440 \u043e\u0448\u0438\u0431\u043a\u0438",
            "\u0412\u0438\u0436\u0443 \u0442\u0435\u0445\u043d\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u0442\u0438\u043a\u0435\u0442. \u0411\u0435\u0440\u0443 \u0435\u0433\u043e \u0432 \u0440\u0430\u0431\u043e\u0442\u0443 \u0438 \u0432\u0435\u0440\u043d\u0443\u0441\u044c \u0441 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u043e\u043c \u0432 \u044d\u0442\u043e\u043c \u0447\u0430\u0442\u0435.",
            SUPPORT_CANNED_REPLY_KIND_ACK,
        ),
        (
            "technical_request_steps",
            "\u0417\u0430\u043f\u0440\u043e\u0441\u0438\u0442\u044c \u0448\u0430\u0433\u0438 \u0438 \u0441\u043a\u0440\u0438\u043d",
            "\u041f\u0440\u0438\u0448\u043b\u0438, \u043f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430, \u0447\u0442\u043e \u0442\u044b \u043d\u0430\u0436\u0438\u043c\u0430\u043b \u043f\u0435\u0440\u0435\u0434 \u043e\u0448\u0438\u0431\u043a\u043e\u0439, \u0441\u043a\u0440\u0438\u043d \u044d\u043a\u0440\u0430\u043d\u0430 \u0438 \u0432\u0435\u0440\u0441\u0438\u044e Telegram / \u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u044b. \u0422\u0430\u043a \u043f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u044c \u0441\u0431\u043e\u0439 \u0431\u0443\u0434\u0435\u0442 \u043f\u0440\u043e\u0449\u0435.",
            SUPPORT_CANNED_REPLY_KIND_CLARIFY,
        ),
        (
            "technical_fix_in_progress",
            "\u0421\u043e\u043e\u0431\u0449\u0438\u0442\u044c \u043e \u0444\u0438\u043a\u0441\u0435 \u0432 \u0440\u0430\u0431\u043e\u0442\u0435",
            "\u041e\u0448\u0438\u0431\u043a\u0443 \u043b\u043e\u043a\u0430\u043b\u0438\u0437\u043e\u0432\u0430\u043b\u0438. \u0421\u0435\u0439\u0447\u0430\u0441 \u0434\u043e\u043a\u0440\u0443\u0447\u0438\u0432\u0430\u0435\u043c \u0444\u0438\u043a\u0441 \u0438 \u0434\u0430\u043c \u0437\u043d\u0430\u0442\u044c, \u043a\u043e\u0433\u0434\u0430 \u043c\u043e\u0436\u043d\u043e \u0431\u0443\u0434\u0435\u0442 \u043f\u0435\u0440\u0435\u043f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c.",
            SUPPORT_CANNED_REPLY_KIND_RESOLVE,
        ),
    ),
    "open:other": (
        (
            "other_ack_review",
            "\u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u044c \u043f\u0440\u0438\u0451\u043c \u043e\u0431\u0440\u0430\u0449\u0435\u043d\u0438\u044f",
            "\u0412\u0438\u0436\u0443 \u0442\u0432\u043e\u0451 \u043e\u0431\u0440\u0430\u0449\u0435\u043d\u0438\u0435. \u0411\u0435\u0440\u0443 \u0435\u0433\u043e \u0432 \u0440\u0430\u0431\u043e\u0442\u0443 \u0438 \u0432\u0435\u0440\u043d\u0443\u0441\u044c \u0441 \u043e\u0442\u0432\u0435\u0442\u043e\u043c \u0432 \u044d\u0442\u043e\u043c \u0442\u0440\u0435\u0434\u0435.",
            SUPPORT_CANNED_REPLY_KIND_ACK,
        ),
        (
            "other_request_details",
            "\u0423\u0442\u043e\u0447\u043d\u0438\u0442\u044c \u0434\u0435\u0442\u0430\u043b\u0438",
            "\u041e\u043f\u0438\u0448\u0438, \u043f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430, \u0441\u0438\u0442\u0443\u0430\u0446\u0438\u044e \u0447\u0443\u0442\u044c \u043f\u043e\u0434\u0440\u043e\u0431\u043d\u0435\u0435: \u0447\u0442\u043e \u0438\u043c\u0435\u043d\u043d\u043e \u043d\u0443\u0436\u043d\u043e \u0441\u0434\u0435\u043b\u0430\u0442\u044c \u0438 \u043a\u0430\u043a\u043e\u0439 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442 \u0442\u044b \u043e\u0436\u0438\u0434\u0430\u0435\u0448\u044c.",
            SUPPORT_CANNED_REPLY_KIND_CLARIFY,
        ),
        (
            "other_follow_up_summary",
            "\u041f\u043e\u0434\u0432\u0435\u0441\u0442\u0438 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0439 \u0448\u0430\u0433",
            "\u0421\u043f\u0430\u0441\u0438\u0431\u043e, \u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u0438 \u0443\u0436\u0435 \u0434\u043e\u0441\u0442\u0430\u0442\u043e\u0447\u043d\u043e. \u0421\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u043c \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435\u043c \u0434\u0430\u043c \u043b\u0438\u0431\u043e \u0440\u0435\u0448\u0435\u043d\u0438\u0435, \u043b\u0438\u0431\u043e \u0442\u043e\u0447\u043d\u044b\u0439 \u0430\u043f\u0434\u0435\u0439\u0442 \u043f\u043e \u0441\u0440\u043e\u043a\u0443.",
            SUPPORT_CANNED_REPLY_KIND_FOLLOW_UP,
        ),
    ),
    "awaiting_user:payment": (
        (
            "payment_follow_up_receipt",
            "\u041d\u0430\u043f\u043e\u043c\u043d\u0438\u0442\u044c \u043f\u0440\u043e \u0447\u0435\u043a",
            "\u041f\u043e\u043a\u0430 \u043d\u0435 \u0432\u0438\u0436\u0443 \u0434\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0445 \u0434\u0430\u043d\u043d\u044b\u0445. \u0415\u0441\u043b\u0438 \u0432\u043e\u043f\u0440\u043e\u0441 \u0435\u0449\u0451 \u0430\u043a\u0442\u0443\u0430\u043b\u0435\u043d, \u043f\u0440\u0438\u0448\u043b\u0438 \u0441\u043a\u0440\u0438\u043d \u043e\u043f\u043b\u0430\u0442\u044b \u0438 \u0432\u0440\u0435\u043c\u044f \u043f\u043b\u0430\u0442\u0435\u0436\u0430.",
            SUPPORT_CANNED_REPLY_KIND_FOLLOW_UP,
        ),
        (
            "payment_follow_up_status",
            "\u0423\u0442\u043e\u0447\u043d\u0438\u0442\u044c, \u0430\u043a\u0442\u0443\u0430\u043b\u0435\u043d \u043b\u0438 \u0432\u043e\u043f\u0440\u043e\u0441",
            "\u0415\u0441\u043b\u0438 \u0434\u043e\u0441\u0442\u0443\u043f \u0443\u0436\u0435 \u043f\u043e\u044f\u0432\u0438\u043b\u0441\u044f, \u043d\u0430\u043f\u0438\u0448\u0438 \u043c\u043d\u0435 \u0437\u0434\u0435\u0441\u044c, \u0438 \u044f \u0437\u0430\u043a\u0440\u043e\u044e \u0442\u0438\u043a\u0435\u0442 \u0431\u0435\u0437 \u043b\u0438\u0448\u043d\u0435\u0439 \u043f\u0435\u0440\u0435\u043f\u0438\u0441\u043a\u0438.",
            SUPPORT_CANNED_REPLY_KIND_FOLLOW_UP,
        ),
        (
            "payment_follow_up_close",
            "\u041f\u0440\u0435\u0434\u0443\u043f\u0440\u0435\u0434\u0438\u0442\u044c \u043e \u0437\u0430\u043a\u0440\u044b\u0442\u0438\u0438",
            "\u0415\u0441\u043b\u0438 \u043e\u0442\u0432\u0435\u0442\u0430 \u043d\u0435 \u0431\u0443\u0434\u0435\u0442, \u044f \u0437\u0430\u043a\u0440\u043e\u044e \u0442\u0438\u043a\u0435\u0442 \u043a\u0430\u043a \u043d\u0435\u0430\u043a\u0442\u0443\u0430\u043b\u044c\u043d\u044b\u0439, \u043d\u043e \u0442\u044b \u0441\u043c\u043e\u0436\u0435\u0448\u044c \u043e\u0442\u043a\u0440\u044b\u0442\u044c \u043d\u043e\u0432\u044b\u0439 \u0432 \u043b\u044e\u0431\u043e\u0439 \u043c\u043e\u043c\u0435\u043d\u0442.",
            SUPPORT_CANNED_REPLY_KIND_RESOLVE,
        ),
    ),
    "awaiting_user:access": (
        (
            "access_follow_up_link",
            "\u0423\u0442\u043e\u0447\u043d\u0438\u0442\u044c \u0441\u0442\u0430\u0442\u0443\u0441 \u0441\u0441\u044b\u043b\u043a\u0438",
            "\u041d\u0430\u043f\u0438\u0448\u0438, \u043f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430, \u0441\u0440\u0430\u0431\u043e\u0442\u0430\u043b\u0430 \u043b\u0438 \u043d\u043e\u0432\u0430\u044f \u0441\u0441\u044b\u043b\u043a\u0430 \u0438 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043b\u0438 \u0432\u043e\u0439\u0442\u0438 \u0432 \u043a\u0430\u043d\u0430\u043b.",
            SUPPORT_CANNED_REPLY_KIND_FOLLOW_UP,
        ),
        (
            "access_follow_up_join",
            "\u0423\u0442\u043e\u0447\u043d\u0438\u0442\u044c \u0441\u0442\u0430\u0442\u0443\u0441 \u0432\u0441\u0442\u0443\u043f\u043b\u0435\u043d\u0438\u044f",
            "\u0415\u0441\u043b\u0438 \u0441\u0441\u044b\u043b\u043a\u0430 \u043e\u0442\u043a\u0440\u044b\u0432\u0430\u0435\u0442\u0441\u044f, \u043d\u043e \u043a\u0430\u043d\u0430\u043b \u043d\u0435 \u043f\u0443\u0441\u043a\u0430\u0435\u0442, \u043f\u0440\u0438\u0448\u043b\u0438 \u0441\u043a\u0440\u0438\u043d \u043e\u0448\u0438\u0431\u043a\u0438 \u0438\u043b\u0438 \u0442\u0435\u043a\u0441\u0442 Telegram, \u043a\u043e\u0442\u043e\u0440\u044b\u0439 \u0432\u0438\u0434\u0438\u0448\u044c.",
            SUPPORT_CANNED_REPLY_KIND_CLARIFY,
        ),
        (
            "access_follow_up_close",
            "\u041f\u0440\u0435\u0434\u043b\u043e\u0436\u0438\u0442\u044c \u0437\u0430\u043a\u0440\u044b\u0442\u044c \u0442\u0438\u043a\u0435\u0442",
            "\u0415\u0441\u043b\u0438 \u0434\u043e\u0441\u0442\u0443\u043f \u0443\u0436\u0435 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442, \u0434\u0430\u0439 \u043c\u043d\u0435 \u043a\u043e\u0440\u043e\u0442\u043a\u043e\u0435 \u00ab\u043e\u043a\u00bb \u0432 \u044d\u0442\u043e\u043c \u0442\u0440\u0435\u0434\u0435, \u0438 \u044f \u0437\u0430\u043a\u0440\u043e\u044e \u0435\u0433\u043e \u043a\u0430\u043a \u0440\u0435\u0448\u0451\u043d\u043d\u044b\u0439.",
            SUPPORT_CANNED_REPLY_KIND_RESOLVE,
        ),
    ),
    "awaiting_user:technical": (
        (
            "technical_follow_up_steps",
            "\u041d\u0430\u043f\u043e\u043c\u043d\u0438\u0442\u044c \u043f\u0440\u043e \u0448\u0430\u0433\u0438 \u0438 \u0441\u043a\u0440\u0438\u043d",
            "\u041f\u043e\u043a\u0430 \u043d\u0435 \u0445\u0432\u0430\u0442\u0430\u0435\u0442 \u0434\u0435\u0442\u0430\u043b\u0435\u0439 \u0434\u043b\u044f \u043f\u043e\u0432\u0442\u043e\u0440\u0435\u043d\u0438\u044f \u0441\u0431\u043e\u044f. \u041f\u0440\u0438\u0448\u043b\u0438, \u043f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430, \u0441\u043a\u0440\u0438\u043d \u0438 \u0448\u0430\u0433\u0438, \u043f\u043e\u0441\u043b\u0435 \u043a\u043e\u0442\u043e\u0440\u044b\u0445 \u043f\u043e\u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f \u043e\u0448\u0438\u0431\u043a\u0430.",
            SUPPORT_CANNED_REPLY_KIND_FOLLOW_UP,
        ),
        (
            "technical_follow_up_retry",
            "\u041f\u043e\u043f\u0440\u043e\u0441\u0438\u0442\u044c \u043f\u0435\u0440\u0435\u043f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c",
            "\u041c\u043e\u0436\u0435\u0448\u044c \u0435\u0449\u0451 \u0440\u0430\u0437 \u043f\u0440\u043e\u0439\u0442\u0438 \u0442\u0435 \u0436\u0435 \u0448\u0430\u0433\u0438 \u0438 \u043d\u0430\u043f\u0438\u0441\u0430\u0442\u044c, \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u043b\u0430\u0441\u044c \u043b\u0438 \u043e\u0448\u0438\u0431\u043a\u0430 \u0441\u0435\u0439\u0447\u0430\u0441? \u042d\u0442\u043e \u043f\u043e\u043c\u043e\u0436\u0435\u0442 \u043f\u043e\u043d\u044f\u0442\u044c, \u0441\u0440\u0430\u0431\u043e\u0442\u0430\u043b \u043b\u0438 \u0444\u0438\u043a\u0441.",
            SUPPORT_CANNED_REPLY_KIND_FOLLOW_UP,
        ),
        (
            "technical_follow_up_close",
            "\u041f\u0440\u0435\u0434\u0443\u043f\u0440\u0435\u0434\u0438\u0442\u044c \u043e \u0437\u0430\u043a\u0440\u044b\u0442\u0438\u0438",
            "\u0415\u0441\u043b\u0438 \u043e\u0448\u0438\u0431\u043a\u0430 \u0443\u0436\u0435 \u0438\u0441\u0447\u0435\u0437\u043b\u0430, \u0434\u0430\u0439 \u043c\u043d\u0435 \u0437\u043d\u0430\u0442\u044c, \u0438 \u044f \u0437\u0430\u043a\u0440\u043e\u044e \u0442\u0438\u043a\u0435\u0442 \u043a\u0430\u043a \u0440\u0435\u0448\u0451\u043d\u043d\u044b\u0439.",
            SUPPORT_CANNED_REPLY_KIND_RESOLVE,
        ),
    ),
    "awaiting_user:other": (
        (
            "other_follow_up_ping",
            "\u041d\u0430\u043f\u043e\u043c\u043d\u0438\u0442\u044c \u043f\u0440\u043e \u0442\u0438\u043a\u0435\u0442",
            "\u0415\u0441\u043b\u0438 \u0432\u043e\u043f\u0440\u043e\u0441 \u0435\u0449\u0451 \u0430\u043a\u0442\u0443\u0430\u043b\u0435\u043d, \u0434\u0430\u0439 \u043c\u043d\u0435 \u043a\u043e\u0440\u043e\u0442\u043a\u0438\u0439 ?????? \u0432 \u044d\u0442\u043e\u043c \u0442\u0440\u0435\u0434\u0435, \u0447\u0442\u043e\u0431\u044b \u044f \u0434\u0432\u0438\u043d\u0443\u043b\u0441\u044f \u0434\u0430\u043b\u044c\u0448\u0435.",
            SUPPORT_CANNED_REPLY_KIND_FOLLOW_UP,
        ),
        (
            "other_follow_up_close",
            "\u041f\u0440\u0435\u0434\u0443\u043f\u0440\u0435\u0434\u0438\u0442\u044c \u043e \u0437\u0430\u043a\u0440\u044b\u0442\u0438\u0438",
            "\u0415\u0441\u043b\u0438 \u0432\u043e\u043f\u0440\u043e\u0441 \u0443\u0436\u0435 \u043d\u0435\u0430\u043a\u0442\u0443\u0430\u043b\u0435\u043d, \u043d\u0430\u043f\u0438\u0448\u0438 \u043c\u043d\u0435 \u043e\u0431 \u044d\u0442\u043e\u043c, \u0438 \u044f \u0430\u043a\u043a\u0443\u0440\u0430\u0442\u043d\u043e \u0437\u0430\u043a\u0440\u043e\u044e \u0442\u0438\u043a\u0435\u0442.",
            SUPPORT_CANNED_REPLY_KIND_RESOLVE,
        ),
    ),
    "closed:any": (
        (
            "closed_resolution_summary",
            "\u041a\u043e\u0440\u043e\u0442\u043a\u043e \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u044c \u0440\u0435\u0448\u0435\u043d\u0438\u0435",
            "\u0422\u0438\u043a\u0435\u0442 \u0437\u0430\u043a\u0440\u044b\u0442 \u043a\u0430\u043a \u0440\u0435\u0448\u0451\u043d\u043d\u044b\u0439. \u0415\u0441\u043b\u0438 \u0441\u0438\u0442\u0443\u0430\u0446\u0438\u044f \u043f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u0441\u044f, \u043c\u043e\u0436\u043d\u043e \u043e\u0442\u043a\u0440\u044b\u0442\u044c \u043d\u043e\u0432\u043e\u0435 \u043e\u0431\u0440\u0430\u0449\u0435\u043d\u0438\u0435 \u0432 \u043b\u044e\u0431\u043e\u0439 \u043c\u043e\u043c\u0435\u043d\u0442.",
            SUPPORT_CANNED_REPLY_KIND_RESOLVE,
        ),
        (
            "closed_reopen_guidance",
            "\u041f\u043e\u044f\u0441\u043d\u0438\u0442\u044c \u043f\u0440\u043e \u043d\u043e\u0432\u044b\u0439 \u0442\u0438\u043a\u0435\u0442",
            "\u0415\u0441\u043b\u0438 \u043f\u043e \u0442\u0435\u043c\u0435 \u043d\u0443\u0436\u0435\u043d \u043d\u043e\u0432\u044b\u0439 \u0440\u0430\u0437\u0431\u043e\u0440, \u043f\u0440\u043e\u0449\u0435 \u043e\u0442\u043a\u0440\u044b\u0442\u044c \u043d\u043e\u0432\u043e\u0435 \u043e\u0431\u0440\u0430\u0449\u0435\u043d\u0438\u0435 \u0441 \u0430\u043a\u0442\u0443\u0430\u043b\u044c\u043d\u044b\u043c\u0438 \u0434\u0435\u0442\u0430\u043b\u044f\u043c\u0438.",
            SUPPORT_CANNED_REPLY_KIND_CLARIFY,
        ),
    ),
}


class SupportTicketError(ValueError):
    """Raised when support ticket state is invalid for the requested action."""


@dataclass(slots=True)
class SupportUserDashboard:
    open_ticket: SupportTicket | None
    recent_tickets: list[SupportTicket]
    open_count: int
    closed_count: int


@dataclass(slots=True)
class SupportInsightPackOutcome:
    pack_key: str
    ticket_count: int
    resolved_count: int
    no_response_count: int
    duplicate_count: int
    other_count: int
    resolved_rate_percent: float
    no_response_rate_percent: float
    duplicate_rate_percent: float


@dataclass(slots=True)
class SupportCloseReasonTrend:
    reason: str
    current_count: int
    previous_count: int
    delta: int


@dataclass(slots=True)
class SupportSlaHotspot:
    kind: str
    category: str
    priority: str
    count: int


@dataclass(slots=True)
class SupportSlaAction:
    kind: str
    category: str
    priority: str
    count: int
    action_key: str
    escalation_key: str
    note: str


@dataclass(slots=True)
class SupportActionLane:
    key: str
    count: int
    high_priority_count: int
    stale_count: int
    sla_warning_count: int
    sla_breach_count: int
    top_category: str | None


@dataclass(slots=True)
class SupportEscalationLane:
    key: str
    count: int
    high_priority_count: int
    stale_count: int
    sla_breach_count: int
    top_category: str | None


@dataclass(slots=True)
class SupportEscalationAction:
    key: str
    escalation_key: str
    action_key: str
    count: int
    high_priority_count: int
    stale_count: int
    sla_breach_count: int
    top_category: str | None


@dataclass(slots=True)
class SupportPriorityFocus:
    key: str
    count: int
    awaiting_admin_count: int
    awaiting_user_count: int
    stale_count: int
    sla_warning_count: int
    sla_breach_count: int
    top_category: str | None
    top_action_lane: str | None
    top_escalation_lane: str | None


@dataclass(slots=True)
class SupportEscalationWatch:
    key: str
    count: int
    awaiting_admin_count: int
    awaiting_user_count: int
    high_priority_count: int
    stale_count: int
    sla_breach_count: int
    top_priority: str | None
    top_category: str | None
    top_action_lane: str | None
    watch_score: int
    note: str


@dataclass(slots=True)
class SupportEscalationTrend:
    key: str
    current_count: int
    previous_count: int
    delta: int


@dataclass(slots=True)
class SupportOperatorActionTrend:
    key: str
    pack_key: str
    close_reason: str
    action_key: str
    current_count: int
    previous_count: int
    delta: int
    note: str


@dataclass(slots=True)
class SupportInsights:
    priority_counts: dict[str, int]
    waiting_state_counts: dict[str, int]
    category_counts: dict[str, int]
    canned_reply_pack_counts: dict[str, int]
    recent_close_reason_counts: dict[str, int]
    previous_close_reason_counts: dict[str, int]
    recent_close_total: int
    previous_close_total: int
    recent_close_days: int
    pack_outcome_days: int
    canned_reply_pack_outcomes: list[SupportInsightPackOutcome]
    close_reason_trends: list[SupportCloseReasonTrend]
    sla_hotspots: list[SupportSlaHotspot]
    sla_actions: list[SupportSlaAction]
    action_lanes: list[SupportActionLane]
    escalation_lanes: list[SupportEscalationLane]
    escalation_actions: list[SupportEscalationAction]
    priority_focus: list[SupportPriorityFocus]
    escalation_watchlist: list[SupportEscalationWatch]
    operator_action_trends: list[SupportOperatorActionTrend]
    escalation_trends: list[SupportEscalationTrend]


@dataclass(slots=True)
class SupportAdminInbox:
    status: str
    tickets: list[SupportTicket]
    open_count: int
    closed_count: int
    awaiting_admin_count: int
    awaiting_user_count: int
    stale_open_count: int
    high_priority_open_count: int
    sla_warning_count: int
    sla_breach_count: int
    close_reason_counts: dict[str, int]
    insights: SupportInsights


@dataclass(slots=True)
class SupportTicketThread:
    ticket: SupportTicket
    messages: list[SupportMessage]

@dataclass(slots=True)
class SupportCannedReply:
    key: str
    title: str
    body: str
    kind: str



def list_support_categories() -> list[tuple[str, str]]:
    return list(SUPPORT_CATEGORY_LABELS.items())


def support_category_label(category: str) -> str:
    return SUPPORT_CATEGORY_LABELS.get(category, category)


def support_status_label(status: str) -> str:
    return SUPPORT_STATUS_LABELS.get(status, status)


def support_priority_label(priority: str) -> str:
    return SUPPORT_PRIORITY_LABELS.get(priority, priority)


def support_close_reason_label(reason: str | None) -> str:
    if not reason:
        return SUPPORT_CLOSE_REASON_LABELS[SUPPORT_CLOSE_REASON_UNSPECIFIED]
    return SUPPORT_CLOSE_REASON_LABELS.get(reason, reason)


def support_waiting_state_label(state: str) -> str:
    return SUPPORT_WAITING_STATE_LABELS.get(state, state)


def support_canned_reply_pack_label(pack_key: str) -> str:
    return SUPPORT_CANNED_REPLY_PACK_LABELS.get(pack_key, pack_key)


def default_support_priority_for_category(category: str) -> str:
    return SUPPORT_PRIORITY_BY_CATEGORY.get(category, SUPPORT_PRIORITY_NORMAL)


def normalize_support_priority(priority: str | None, *, category: str) -> str:
    normalized = (priority or default_support_priority_for_category(category)).strip().casefold()
    if normalized not in SUPPORT_PRIORITY_LABELS:
        raise SupportTicketError(
            "\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439 "
            "\u043f\u0440\u0438\u043e\u0440\u0438\u0442\u0435\u0442 "
            "\u043e\u0431\u0440\u0430\u0449\u0435\u043d\u0438\u044f."
        )
    return normalized


def normalize_support_close_reason(reason: str | None) -> str:
    normalized = (reason or SUPPORT_CLOSE_REASON_RESOLVED).strip().casefold()
    if (
        normalized not in SUPPORT_CLOSE_REASON_LABELS
        or normalized == SUPPORT_CLOSE_REASON_UNSPECIFIED
    ):
        raise SupportTicketError(
            "\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u0430\u044f "
            "\u043f\u0440\u0438\u0447\u0438\u043d\u0430 "
            "\u0437\u0430\u043a\u0440\u044b\u0442\u0438\u044f "
            "\u043e\u0431\u0440\u0430\u0449\u0435\u043d\u0438\u044f."
        )
    return normalized


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


def support_sla_hotspot_label(kind: str) -> str:
    if kind == SUPPORT_SLA_HOTSPOT_BREACH:
        return "\u0421\u043b\u043e\u043c\u0430\u043d SLA"
    if kind == SUPPORT_SLA_HOTSPOT_WARNING:
        return "\u0420\u0438\u0441\u043a SLA"
    if kind == SUPPORT_SLA_HOTSPOT_STALE:
        return "\u041f\u0440\u043e\u0441\u0440\u043e\u0447\u0435\u043d\u043e >24\u0447"
    return kind


def support_sla_action_note(kind: str, action_lane: str, escalation_lane: str) -> str:
    if kind == SUPPORT_SLA_HOTSPOT_BREACH:
        return (
            f"First move: {support_action_lane_label(action_lane)}. "
            f"Escalate through {support_escalation_lane_label(escalation_lane)} if the blocker stays open."
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


def support_action_lane_label(lane: str) -> str:
    return SUPPORT_ACTION_LANE_LABELS.get(lane, lane)


def support_escalation_lane_label(lane: str) -> str:
    return SUPPORT_ESCALATION_LANE_LABELS.get(lane, lane)


def support_escalation_action_label(escalation_lane: str, action_lane: str) -> str:
    return (
        f"{support_escalation_lane_label(escalation_lane)} -> "
        f"{support_action_lane_label(action_lane)}"
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

    is_stale = ensure_aware_utc(ticket.updated_at) < event_time - timedelta(hours=SUPPORT_STALE_HOURS)
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
        closed_reference = ensure_aware_utc(ticket.closed_at or ticket.updated_at or ticket.created_at)
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
        closed_reference = ensure_aware_utc(ticket.closed_at or ticket.updated_at or ticket.created_at)
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
        key=lambda item: (-abs(item.delta), -item.current_count, support_close_reason_label(item.reason))
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


def _historical_support_escalation_lane(ticket: SupportTicket) -> str:
    reference_time = ensure_aware_utc(ticket.closed_at or ticket.updated_at or ticket.created_at)
    waiting_state = _historical_support_waiting_state(ticket)
    last_activity = ensure_aware_utc(
        max(
            [value for value in [ticket.last_user_message_at, ticket.last_admin_message_at, ticket.created_at] if value is not None]
        )
    )
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
    last_activity = ensure_aware_utc(
        max(
            [value for value in [ticket.last_user_message_at, ticket.last_admin_message_at, ticket.created_at] if value is not None]
        )
    )
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
        closed_reference = ensure_aware_utc(ticket.closed_at or ticket.updated_at or ticket.created_at)
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
        closed_reference = ensure_aware_utc(ticket.closed_at or ticket.updated_at or ticket.created_at)
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


def build_support_canned_replies(
    ticket: SupportTicket,
    *,
    limit: int = 3,
) -> list[SupportCannedReply]:
    pack_key, fallback_key = _support_canned_reply_pack_keys(ticket)
    raw_items = SUPPORT_CANNED_REPLY_PACKS.get(pack_key) or SUPPORT_CANNED_REPLY_PACKS.get(
        fallback_key,
        (),
    )

    replies: list[SupportCannedReply] = []
    seen_keys: set[str] = set()
    for key, title, body, kind in raw_items:
        if key in seen_keys:
            continue
        replies.append(SupportCannedReply(key=key, title=title, body=body, kind=kind))
        seen_keys.add(key)
        if len(replies) >= limit:
            break
    return replies


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
    action_lanes = _build_support_action_lanes(open_tickets, now=event_time)
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
        action_lanes=action_lanes,
        escalation_lanes=escalation_lanes,
        escalation_actions=escalation_actions,
        priority_focus=priority_focus,
        escalation_watchlist=escalation_watchlist,
        operator_action_trends=operator_action_trends,
        escalation_trends=escalation_trends,
    )


async def build_user_support_dashboard(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int = 10,
) -> SupportUserDashboard:
    repository = SupportTicketRepository(session)
    open_ticket = await repository.get_open_for_user(user_id)
    recent_tickets = await repository.list_for_user(user_id, limit=limit)
    open_count = sum(1 for item in recent_tickets if item.status == SUPPORT_STATUS_OPEN)
    closed_count = sum(1 for item in recent_tickets if item.status == SUPPORT_STATUS_CLOSED)
    return SupportUserDashboard(
        open_ticket=open_ticket,
        recent_tickets=recent_tickets,
        open_count=open_count,
        closed_count=closed_count,
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


async def get_user_ticket_thread(
    session: AsyncSession,
    *,
    ticket_id: int,
    user_id: int,
) -> SupportTicketThread:
    ticket = await _require_ticket(session, ticket_id=ticket_id)
    if ticket.user_id != user_id:
        raise SupportTicketError("Это обращение тебе недоступно.")
    return SupportTicketThread(ticket=ticket, messages=list(ticket.messages))


async def get_admin_ticket_thread(
    session: AsyncSession,
    *,
    ticket_id: int,
) -> SupportTicketThread:
    ticket = await _require_ticket(session, ticket_id=ticket_id)
    return SupportTicketThread(ticket=ticket, messages=list(ticket.messages))


async def create_support_ticket(
    session: AsyncSession,
    *,
    user_id: int,
    category: str,
    body: str,
    now: datetime | None = None,
    priority: str | None = None,
) -> SupportTicketThread:
    if category not in SUPPORT_CATEGORY_LABELS:
        raise SupportTicketError("Неизвестная категория обращения.")

    event_time = ensure_aware_utc(now or utcnow())
    normalized_body = normalize_support_message(body)
    repository = SupportTicketRepository(session)

    existing_open = await repository.get_open_for_user(user_id)
    if existing_open is not None:
        raise SupportTicketError(
            f"У тебя уже есть открытое обращение #{existing_open.id}. "
            "Открой его и добавь сообщение туда."
        )

    daily_count = await repository.count_created_since(
        user_id,
        since=event_time - timedelta(days=1),
    )
    if daily_count >= SUPPORT_TICKET_DAILY_LIMIT:
        raise SupportTicketError("Лимит новых обращений на сегодня исчерпан. Попробуй позже.")

    ticket = await repository.create_ticket(
        user_id=user_id,
        category=category,
        priority=normalize_support_priority(priority, category=category),
        created_at=event_time,
    )
    await repository.add_message(
        ticket_id=ticket.id,
        sender_user_id=user_id,
        body=normalized_body,
        is_admin=False,
        created_at=event_time,
    )
    ticket.updated_at = event_time
    await write_audit_log(
        session,
        action="support_ticket_created",
        actor_user_id=user_id,
        target_user_id=user_id,
        payload={
            "ticket_id": ticket.id,
            "category": category,
            "priority": ticket.priority,
        },
    )
    refreshed = await _require_ticket(session, ticket_id=ticket.id)
    return SupportTicketThread(ticket=refreshed, messages=list(refreshed.messages))


async def add_user_ticket_message(
    session: AsyncSession,
    *,
    ticket_id: int,
    user_id: int,
    body: str,
    now: datetime | None = None,
) -> SupportTicketThread:
    event_time = ensure_aware_utc(now or utcnow())
    normalized_body = normalize_support_message(body)
    repository = SupportTicketRepository(session)
    ticket = await _require_ticket(session, ticket_id=ticket_id)
    if ticket.user_id != user_id:
        raise SupportTicketError("Это обращение тебе недоступно.")
    if ticket.status != SUPPORT_STATUS_OPEN:
        raise SupportTicketError("Обращение уже закрыто. Дождись переоткрытия от администратора.")

    await repository.add_message(
        ticket_id=ticket.id,
        sender_user_id=user_id,
        body=normalized_body,
        is_admin=False,
        created_at=event_time,
    )
    ticket.last_user_message_at = event_time
    ticket.updated_at = event_time
    await write_audit_log(
        session,
        action="support_ticket_user_message_added",
        actor_user_id=user_id,
        target_user_id=user_id,
        payload={"ticket_id": ticket.id},
    )
    refreshed = await _require_ticket(session, ticket_id=ticket.id)
    return SupportTicketThread(ticket=refreshed, messages=list(refreshed.messages))


async def add_admin_ticket_reply(
    session: AsyncSession,
    *,
    ticket_id: int,
    admin_user_id: int | None,
    body: str,
    now: datetime | None = None,
) -> SupportTicketThread:
    event_time = ensure_aware_utc(now or utcnow())
    normalized_body = normalize_support_message(body)
    repository = SupportTicketRepository(session)
    ticket = await _require_ticket(session, ticket_id=ticket_id)
    if ticket.status != SUPPORT_STATUS_OPEN:
        raise SupportTicketError("Сначала переоткрой обращение, потом отвечай.")

    await repository.add_message(
        ticket_id=ticket.id,
        sender_user_id=admin_user_id or ticket.user_id,
        body=normalized_body,
        is_admin=True,
        created_at=event_time,
    )
    ticket.last_admin_message_at = event_time
    ticket.updated_at = event_time
    await write_audit_log(
        session,
        action="support_ticket_admin_reply",
        actor_user_id=admin_user_id,
        target_user_id=ticket.user_id,
        payload={"ticket_id": ticket.id},
    )
    refreshed = await _require_ticket(session, ticket_id=ticket.id)
    return SupportTicketThread(ticket=refreshed, messages=list(refreshed.messages))


async def close_support_ticket(
    session: AsyncSession,
    *,
    ticket_id: int,
    actor_user_id: int | None,
    now: datetime | None = None,
    close_reason: str = SUPPORT_CLOSE_REASON_RESOLVED,
) -> SupportTicketThread:
    event_time = ensure_aware_utc(now or utcnow())
    normalized_close_reason = normalize_support_close_reason(close_reason)
    repository = SupportTicketRepository(session)
    ticket = await _require_ticket(session, ticket_id=ticket_id)
    if ticket.status != SUPPORT_STATUS_CLOSED:
        await repository.set_status(
            ticket,
            status=SUPPORT_STATUS_CLOSED,
            closed_at=event_time,
            closed_by_user_id=actor_user_id,
            close_reason=normalized_close_reason,
        )
        ticket.updated_at = event_time
        await write_audit_log(
            session,
            action="support_ticket_closed",
            actor_user_id=actor_user_id,
            target_user_id=ticket.user_id,
            payload={"ticket_id": ticket.id, "close_reason": normalized_close_reason},
        )
    refreshed = await _require_ticket(session, ticket_id=ticket.id)
    return SupportTicketThread(ticket=refreshed, messages=list(refreshed.messages))


async def reopen_support_ticket(
    session: AsyncSession,
    *,
    ticket_id: int,
    actor_user_id: int | None,
    now: datetime | None = None,
) -> SupportTicketThread:
    event_time = ensure_aware_utc(now or utcnow())
    repository = SupportTicketRepository(session)
    ticket = await _require_ticket(session, ticket_id=ticket_id)
    if ticket.status != SUPPORT_STATUS_OPEN:
        await repository.set_status(
            ticket,
            status=SUPPORT_STATUS_OPEN,
            closed_at=None,
            closed_by_user_id=None,
            close_reason=None,
        )
        ticket.updated_at = event_time
        await write_audit_log(
            session,
            action="support_ticket_reopened",
            actor_user_id=actor_user_id,
            target_user_id=ticket.user_id,
            payload={"ticket_id": ticket.id},
        )
    refreshed = await _require_ticket(session, ticket_id=ticket.id)
    return SupportTicketThread(ticket=refreshed, messages=list(refreshed.messages))


def normalize_support_message(raw_text: str) -> str:
    normalized_lines = [line.rstrip() for line in raw_text.splitlines()]
    normalized = "\n".join(normalized_lines).strip()
    if not normalized:
        raise SupportTicketError("Текст обращения не должен быть пустым.")
    if len(normalized) > SUPPORT_MESSAGE_LIMIT:
        raise SupportTicketError(
            f"Сообщение слишком длинное. Максимум: {SUPPORT_MESSAGE_LIMIT} символов."
        )
    return normalized


async def _require_ticket(session: AsyncSession, *, ticket_id: int) -> SupportTicket:
    ticket = await SupportTicketRepository(session).get_by_id(ticket_id, with_messages=True)
    if ticket is None:
        raise SupportTicketError("Обращение не найдено.")
    return ticket
