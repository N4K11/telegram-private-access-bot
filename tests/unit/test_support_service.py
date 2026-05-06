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
    SUPPORT_CLOSE_REASON_RESOLVED,
    SUPPORT_PRIORITY_HIGH,
    SupportTicketError,
    add_admin_ticket_reply,
    build_support_canned_replies,
    build_support_insights,
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
    assert tickets[0].priority == SUPPORT_PRIORITY_HIGH
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
    await close_support_ticket(
        session,
        ticket_id=thread.ticket.id,
        actor_user_id=admin.id,
        now=created_at + timedelta(minutes=20),
    )
    await session.flush()
    closed_snapshot = await session.get(SupportTicket, thread.ticket.id)
    assert closed_snapshot is not None
    closed_status = closed_snapshot.status
    closed_reason = closed_snapshot.close_reason

    reopened = await reopen_support_ticket(
        session,
        ticket_id=thread.ticket.id,
        actor_user_id=admin.id,
    )
    await session.commit()

    assert len(replied.messages) == 2
    assert replied.messages[-1].is_admin is True
    assert closed_reason == SUPPORT_CLOSE_REASON_RESOLVED
    assert closed_status == "closed"
    assert reopened.ticket.status == "open"
    assert reopened.ticket.close_reason is None


def test_build_support_insights_summarize_queue_and_recent_closures() -> None:
    now = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
    open_payment = SupportTicket(
        user_id=1,
        category=SUPPORT_CATEGORY_PAYMENT,
        priority=SUPPORT_PRIORITY_HIGH,
        status="open",
        created_at=now - timedelta(hours=5),
        updated_at=now - timedelta(hours=1),
        last_user_message_at=now - timedelta(hours=1),
    )
    open_technical = SupportTicket(
        user_id=2,
        category=SUPPORT_CATEGORY_TECHNICAL,
        priority="urgent",
        status="open",
        created_at=now - timedelta(hours=32),
        updated_at=now - timedelta(hours=30),
        last_admin_message_at=now - timedelta(hours=30),
    )
    recent_closed = SupportTicket(
        user_id=3,
        category=SUPPORT_CATEGORY_PAYMENT,
        priority=SUPPORT_PRIORITY_HIGH,
        status="closed",
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=1),
        closed_at=now - timedelta(days=1),
        close_reason=SUPPORT_CLOSE_REASON_RESOLVED,
    )
    previous_closed = SupportTicket(
        user_id=4,
        category=SUPPORT_CATEGORY_TECHNICAL,
        priority="normal",
        status="closed",
        created_at=now - timedelta(days=10),
        updated_at=now - timedelta(days=9),
        closed_at=now - timedelta(days=9),
        close_reason="no_response",
        last_admin_message_at=now - timedelta(days=9, hours=1),
    )
    old_closed = SupportTicket(
        user_id=5,
        category=SUPPORT_CATEGORY_TECHNICAL,
        priority="normal",
        status="closed",
        created_at=now - timedelta(days=20),
        updated_at=now - timedelta(days=19),
        closed_at=now - timedelta(days=19),
        close_reason="duplicate",
    )

    insights = build_support_insights(
        open_tickets=[open_payment, open_technical],
        closed_tickets=[recent_closed, previous_closed, old_closed],
        now=now,
    )

    assert insights.priority_counts == {SUPPORT_PRIORITY_HIGH: 1, "urgent": 1}
    assert insights.waiting_state_counts == {"awaiting_admin": 1, "awaiting_user": 1}
    assert insights.category_counts == {SUPPORT_CATEGORY_PAYMENT: 1, SUPPORT_CATEGORY_TECHNICAL: 1}
    assert insights.canned_reply_pack_counts == {"open:payment": 1, "awaiting_user:technical": 1}
    assert insights.recent_close_total == 1
    assert insights.previous_close_total == 1
    assert insights.recent_close_reason_counts == {SUPPORT_CLOSE_REASON_RESOLVED: 1}
    assert insights.previous_close_reason_counts == {"no_response": 1}
    assert insights.canned_reply_pack_outcomes[0].pack_key == "awaiting_user:technical"
    assert insights.canned_reply_pack_outcomes[0].no_response_rate_percent == 100.0
    assert any(
        item.reason == "no_response" and item.delta == -1
        for item in insights.close_reason_trends
    )
    assert insights.action_lanes[0].key == "waiting_user_followup"
    assert insights.action_lanes[0].sla_breach_count == 1
    assert any(item.key == "payment_review" for item in insights.action_lanes)
    assert insights.escalation_lanes[0].key == "waiting_user_risk"
    assert insights.escalation_lanes[0].sla_breach_count == 1
    assert any(item.key == "payment_blocker" for item in insights.escalation_lanes)
    assert insights.escalation_actions[0].key == "waiting_user_risk:waiting_user_followup"
    assert insights.escalation_actions[0].sla_breach_count == 1
    assert any(item.key == "payment_blocker:payment_review" for item in insights.escalation_actions)
    assert insights.priority_focus[0].key == "urgent"
    assert insights.priority_focus[0].awaiting_user_count == 1
    assert insights.priority_focus[0].top_action_lane == "waiting_user_followup"
    assert insights.priority_focus[0].top_escalation_lane == "waiting_user_risk"
    assert any(item.key == "high" for item in insights.priority_focus)
    assert insights.escalation_watchlist[0].key == "waiting_user_risk"
    assert insights.escalation_watchlist[0].watch_score == 10
    assert insights.escalation_watchlist[0].top_action_lane == "waiting_user_followup"
    assert any(item.key == "payment_blocker" for item in insights.escalation_watchlist)
    assert insights.escalation_trends[0].key == "reply_breach"
    assert insights.escalation_trends[0].current_count == 1
    assert insights.escalation_trends[0].previous_count == 0
    assert any(
        item.key == "routine_queue" and item.delta == -1
        for item in insights.escalation_trends
    )
    assert insights.operator_action_trends[0].pack_key == "open:payment"
    assert insights.operator_action_trends[0].close_reason == SUPPORT_CLOSE_REASON_RESOLVED
    assert insights.operator_action_trends[0].action_key == "new_ticket_review"
    assert any(
        item.close_reason == "no_response"
        and item.action_key == "waiting_user_followup"
        and item.delta == -1
        for item in insights.operator_action_trends
    )
    assert any(item.kind == "breach" for item in insights.sla_hotspots)
    assert insights.sla_actions[0].kind == "breach"
    assert insights.sla_actions[0].action_key == "waiting_user_followup"
    assert insights.sla_actions[0].escalation_key == "waiting_user_risk"
    assert any(item.kind == "stale" for item in insights.sla_actions)
    assert any(item.kind == "stale" for item in insights.sla_hotspots)


def test_build_support_canned_replies_follow_ticket_state() -> None:
    ticket = SupportTicket(
        user_id=1,
        category=SUPPORT_CATEGORY_PAYMENT,
        priority=SUPPORT_PRIORITY_HIGH,
        status="open",
        created_at=datetime(2026, 5, 2, 9, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 2, 9, 0, tzinfo=UTC),
        last_user_message_at=datetime(2026, 5, 2, 9, 0, tzinfo=UTC),
    )

    open_keys = [item.key for item in build_support_canned_replies(ticket)]
    assert open_keys[:2] == ["payment_ack_review", "payment_request_receipt"]

    ticket.last_admin_message_at = datetime(2026, 5, 2, 9, 5, tzinfo=UTC)
    waiting_user_keys = [item.key for item in build_support_canned_replies(ticket)]
    assert waiting_user_keys[0] == "payment_follow_up_receipt"

    ticket.status = "closed"
    closed_keys = [item.key for item in build_support_canned_replies(ticket)]
    assert closed_keys[0] == "closed_resolution_summary"


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
