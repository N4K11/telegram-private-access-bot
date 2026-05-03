from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.db.models import Base, Channel, SupportMessage, SupportTicket, User
from app.db.session import create_async_engine, create_session_factory
from app.runtime_state import record_critical_error, reset_runtime_state
from app.services.admin_home import build_admin_home_snapshot
from app.services.admin_roles import ROLE_OWNER


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


@pytest.mark.asyncio
async def test_admin_home_snapshot_collects_badges_and_summary(session) -> None:
    reset_runtime_state()
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "use_webhook": True,
            "public_webhook_url": "https://example.com",
            "webhook_secret_token": "secret-token",
        }
    )
    now = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)
    user = User(telegram_id=77, first_name="Guest")
    session.add(user)
    await session.flush()
    session.add(
        Channel(
            title="Private Channel",
            telegram_chat_id="-1001",
            is_active=True,
            invite_users_permission=False,
            ban_users_permission=True,
        )
    )
    await session.flush()
    ticket = SupportTicket(
        user_id=user.id,
        category="payment",
        status="open",
        last_user_message_at=now - timedelta(hours=1),
        last_admin_message_at=None,
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=2),
    )
    session.add(ticket)
    await session.flush()
    session.add(
        SupportMessage(
            ticket_id=ticket.id,
            sender_user_id=user.id,
            body="Need help",
            is_admin=False,
            created_at=now - timedelta(days=2),
        )
    )
    await session.commit()
    record_critical_error(
        "channel_guard_alert",
        "Channel permissions drift detected",
        source="channel_guard",
        at=now,
    )

    snapshot = await build_admin_home_snapshot(
        session,
        role=ROLE_OWNER,
        settings=settings,
        now=now,
    )

    assert snapshot.section_badges == {"support": 1, "diagnostics": 1}
    assert "Runtime: webhook" in snapshot.summary_block
    assert "Mini App: /cabinet" in snapshot.summary_block
    assert "Тикеты ждут ответа: 1" in snapshot.summary_block
    assert "Просрочено >24ч: 1" in snapshot.summary_block
    assert "Каналы с рисками доступа: 1" in snapshot.summary_block
    assert "Критических событий: 1" in snapshot.summary_block

    reset_runtime_state()
