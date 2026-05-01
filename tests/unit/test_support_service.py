from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import AuditLog, SupportMessage, SupportTicket, User
from app.db.session import create_async_engine, create_session_factory
from app.services.support import (
    SUPPORT_CATEGORY_PAYMENT,
    SUPPORT_CATEGORY_TECHNICAL,
    SupportTicketError,
    add_admin_ticket_reply,
    close_support_ticket,
    create_support_ticket,
    reopen_support_ticket,
)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


async def _seed_users(session: AsyncSession) -> tuple[User, User]:
    user = User(telegram_id=101, first_name="Руслан", role="user")
    admin = User(telegram_id=755815181, first_name="Admin", is_admin=True, role="owner")
    session.add_all([user, admin])
    await session.commit()
    return user, admin


async def test_create_support_ticket_persists_thread_and_blocks_second_open_ticket(
    session: AsyncSession,
) -> None:
    user, _ = await _seed_users(session)
    now = datetime(2026, 5, 2, 10, 0, tzinfo=UTC)

    thread = await create_support_ticket(
        session,
        user_id=user.id,
        category=SUPPORT_CATEGORY_PAYMENT,
        body="Платеж прошел, доступа нет",
        now=now,
    )
    await session.commit()

    tickets = list((await session.execute(select(SupportTicket))).scalars())
    messages = list((await session.execute(select(SupportMessage))).scalars())
    audits = list((await session.execute(select(AuditLog))).scalars())

    assert thread.ticket.id == tickets[0].id
    assert tickets[0].status == "open"
    assert messages[0].body == "Платеж прошел, доступа нет"
    assert any(log.action == "support_ticket_created" for log in audits)

    with pytest.raises(SupportTicketError, match="открытое обращение"):
        await create_support_ticket(
            session,
            user_id=user.id,
            category=SUPPORT_CATEGORY_PAYMENT,
            body="Еще одно сообщение",
            now=now + timedelta(minutes=5),
        )


async def test_admin_reply_close_and_reopen_support_ticket(
    session: AsyncSession,
) -> None:
    user, admin = await _seed_users(session)
    created_at = datetime(2026, 5, 2, 11, 0, tzinfo=UTC)
    thread = await create_support_ticket(
        session,
        user_id=user.id,
        category=SUPPORT_CATEGORY_TECHNICAL,
        body="Бот не отвечает",
        now=created_at,
    )
    await session.commit()

    replied = await add_admin_ticket_reply(
        session,
        ticket_id=thread.ticket.id,
        admin_user_id=admin.id,
        body="Проверили, уже исправляем.",
        now=created_at + timedelta(minutes=10),
    )
    closed = await close_support_ticket(
        session,
        ticket_id=thread.ticket.id,
        actor_user_id=admin.id,
        now=created_at + timedelta(minutes=20),
    )
    closed_status = closed.ticket.status
    reopened = await reopen_support_ticket(
        session,
        ticket_id=thread.ticket.id,
        actor_user_id=admin.id,
    )
    await session.commit()

    assert len(replied.messages) == 2
    assert replied.messages[-1].is_admin is True
    assert closed_status == "closed"
    assert reopened.ticket.status == "open"


async def test_support_ticket_daily_rate_limit_after_three_recent_tickets(
    session: AsyncSession,
) -> None:
    user, admin = await _seed_users(session)
    base_time = datetime(2026, 5, 2, 12, 0, tzinfo=UTC)

    for index in range(3):
        thread = await create_support_ticket(
            session,
            user_id=user.id,
            category=SUPPORT_CATEGORY_PAYMENT,
            body=f"Сообщение {index}",
            now=base_time + timedelta(hours=index),
        )
        await close_support_ticket(
            session,
            ticket_id=thread.ticket.id,
            actor_user_id=admin.id,
            now=base_time + timedelta(hours=index, minutes=15),
        )
        await session.commit()

    with pytest.raises(SupportTicketError, match="Лимит новых обращений"):
        await create_support_ticket(
            session,
            user_id=user.id,
            category=SUPPORT_CATEGORY_PAYMENT,
            body="Четвертое обращение",
            now=base_time + timedelta(hours=5),
        )
