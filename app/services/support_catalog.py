from __future__ import annotations

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
    "awaiting_user": (
        "\u0416\u0434\u0451\u0442 "
        "\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f"
    ),
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


def support_sla_bucket_label(bucket: str) -> str:
    return SUPPORT_SLA_BUCKET_LABELS.get(bucket, bucket)


def support_sla_hotspot_label(kind: str) -> str:
    if kind == SUPPORT_SLA_HOTSPOT_BREACH:
        return "Сломан SLA"
    if kind == SUPPORT_SLA_HOTSPOT_WARNING:
        return "Риск SLA"
    if kind == SUPPORT_SLA_HOTSPOT_STALE:
        return "Просрочено >24ч"
    return kind


def support_action_lane_label(lane: str) -> str:
    return SUPPORT_ACTION_LANE_LABELS.get(lane, lane)


def support_escalation_lane_label(lane: str) -> str:
    return SUPPORT_ESCALATION_LANE_LABELS.get(lane, lane)


def support_escalation_action_label(escalation_lane: str, action_lane: str) -> str:
    return (
        f"{support_escalation_lane_label(escalation_lane)} -> "
        f"{support_action_lane_label(action_lane)}"
    )


def support_triage_route_label(route_key: str) -> str:
    escalation_key, _, action_key = route_key.partition(":")
    if escalation_key and action_key:
        return support_escalation_action_label(escalation_key, action_key)
    return route_key


def default_support_priority_for_category(category: str) -> str:
    return SUPPORT_PRIORITY_BY_CATEGORY.get(category, SUPPORT_PRIORITY_NORMAL)
