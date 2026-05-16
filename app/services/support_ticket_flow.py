from __future__ import annotations

from datetime import datetime, timedelta
from html import escape

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SupportTicket
from app.db.repositories.support_tickets import SupportTicketRepository
from app.services.audit import write_audit_log
from app.services.support_catalog import (
    SUPPORT_CATEGORY_LABELS,
    SUPPORT_CLOSE_REASON_LABELS,
    SUPPORT_CLOSE_REASON_RESOLVED,
    SUPPORT_CLOSE_REASON_UNSPECIFIED,
    SUPPORT_MESSAGE_LIMIT,
    SUPPORT_PRIORITY_LABELS,
    SUPPORT_STATUS_CLOSED,
    SUPPORT_STATUS_OPEN,
    SUPPORT_TICKET_DAILY_LIMIT,
    default_support_priority_for_category,
    support_category_label,
    support_status_label,
)
from app.services.support_models import SupportTicketThread, SupportUserDashboard
from app.utils.datetime import ensure_aware_utc, format_datetime, utcnow


class SupportTicketError(ValueError):
    """Raised when support ticket state is invalid for the requested action."""


def build_support_admin_reply_notification_text(
    thread: SupportTicketThread,
    *,
    timezone: str,
) -> str:
    latest_message = thread.messages[-1]
    category_label = support_category_label(thread.ticket.category)
    status_label = support_status_label(thread.ticket.status)
    created_label = format_datetime(latest_message.created_at, timezone)
    return "\n".join(
        [
            f"✉️ Ответ по обращению #{thread.ticket.id}",
            "",
            f"Категория: {category_label}",
            f"Статус: {status_label}",
            f"Время: {created_label}",
            "",
            escape(latest_message.body),
        ]
    )


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
