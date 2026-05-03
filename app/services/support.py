from __future__ import annotations

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


class SupportTicketError(ValueError):
    """Raised when support ticket state is invalid for the requested action."""


@dataclass(slots=True)
class SupportUserDashboard:
    open_ticket: SupportTicket | None
    recent_tickets: list[SupportTicket]
    open_count: int
    closed_count: int


@dataclass(slots=True)
class SupportAdminInbox:
    status: str
    tickets: list[SupportTicket]
    open_count: int
    closed_count: int
    awaiting_admin_count: int
    awaiting_user_count: int
    stale_open_count: int


@dataclass(slots=True)
class SupportTicketThread:
    ticket: SupportTicket
    messages: list[SupportMessage]


def list_support_categories() -> list[tuple[str, str]]:
    return list(SUPPORT_CATEGORY_LABELS.items())


def support_category_label(category: str) -> str:
    return SUPPORT_CATEGORY_LABELS.get(category, category)


def support_status_label(status: str) -> str:
    return SUPPORT_STATUS_LABELS.get(status, status)


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
    tickets = await repository.list_by_status(status, limit=limit)
    return SupportAdminInbox(
        status=status,
        tickets=tickets,
        open_count=await repository.count_by_status(SUPPORT_STATUS_OPEN),
        closed_count=await repository.count_by_status(SUPPORT_STATUS_CLOSED),
        awaiting_admin_count=await repository.count_open_waiting_on_admin(),
        awaiting_user_count=await repository.count_open_waiting_on_user(),
        stale_open_count=await repository.count_stale_open(
            since=event_time - timedelta(hours=SUPPORT_STALE_HOURS)
        ),
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
        payload={"ticket_id": ticket.id, "category": category},
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
) -> SupportTicketThread:
    event_time = ensure_aware_utc(now or utcnow())
    repository = SupportTicketRepository(session)
    ticket = await _require_ticket(session, ticket_id=ticket_id)
    if ticket.status != SUPPORT_STATUS_CLOSED:
        await repository.set_status(
            ticket,
            status=SUPPORT_STATUS_CLOSED,
            closed_at=event_time,
            closed_by_user_id=actor_user_id,
        )
        ticket.updated_at = event_time
        await write_audit_log(
            session,
            action="support_ticket_closed",
            actor_user_id=actor_user_id,
            target_user_id=ticket.user_id,
            payload={"ticket_id": ticket.id},
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