# ruff: noqa: E501
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import AuditLog, User
from app.db.session import create_async_engine, create_session_factory
from app.services.audit import (
    AuditViewerFilters,
    build_audit_csv_report,
    build_audit_page,
    get_audit_event_detail,
    resolve_audit_user_reference,
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


async def _seed_audit_data(session: AsyncSession) -> dict[str, object]:
    now = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)
    admin = User(
        telegram_id=755815181,
        first_name="Админ",
        username="boss",
        is_admin=True,
        role="owner",
    )
    user = User(telegram_id=1001, first_name="Руслан", username="ruslan", role="user")
    other = User(telegram_id=2002, first_name="Анна", username="anna", role="user")
    session.add_all([admin, user, other])
    await session.flush()

    session.add_all(
        [
            AuditLog(
                action="payment_paid_stars",
                actor_user_id=user.id,
                target_user_id=user.id,
                payload='{"tariff_id": 1, "amount": 250}',
                created_at=now - timedelta(hours=2),
            ),
            AuditLog(
                action="admin_direct_message",
                actor_user_id=admin.id,
                target_user_id=user.id,
                payload=(
                    '{"text": "секретный текст", '
                    '"invite_link": "https://t.me/+PrivateInvite", '
                    '"token": "123456789:ABCDEFGHIJKLMNOPQRSTUV"}'
                ),
                created_at=now - timedelta(hours=1),
            ),
            AuditLog(
                action="support_ticket_closed",
                actor_user_id=admin.id,
                target_user_id=other.id,
                payload='{"ticket_id": 7, "closed_by": "admin"}',
                created_at=now - timedelta(days=10),
            ),
        ]
    )
    await session.commit()
    return {"now": now, "admin": admin, "user": user, "other": other}


async def test_build_audit_page_filters_and_redacts_payloads(session: AsyncSession) -> None:
    seeded = await _seed_audit_data(session)
    admin = seeded["admin"]
    now = seeded["now"]
    before_count = (
        await session.execute(select(AuditLog.id))
    ).scalars().all()

    page = await build_audit_page(
        session,
        filters=AuditViewerFilters(actor_user_id=admin.id, period="week"),
        now=now,
    )

    after_count = (
        await session.execute(select(AuditLog.id))
    ).scalars().all()

    assert before_count == after_count
    assert page.total_items == 1
    assert page.items[0].action == "admin_direct_message"
    assert page.items[0].actor is not None
    assert page.items[0].actor.display_name == "Админ"
    assert page.items[0].target is not None
    assert page.items[0].target.display_name == "Руслан"
    assert page.items[0].payload_preview is not None
    assert "[REDACTED]" in page.items[0].payload_preview
    assert "секретный текст" not in page.items[0].payload_preview
    assert "https://t.me/+PrivateInvite" not in page.items[0].payload_preview


async def test_resolve_audit_user_reference_supports_internal_and_telegram_ids(session: AsyncSession) -> None:
    seeded = await _seed_audit_data(session)
    admin = seeded["admin"]

    by_internal = await resolve_audit_user_reference(session, f"id:{admin.id}")
    by_telegram = await resolve_audit_user_reference(session, f"tg:{admin.telegram_id}")
    by_plain = await resolve_audit_user_reference(session, str(admin.telegram_id))

    assert by_internal.user_id == admin.id
    assert by_telegram.user_id == admin.id
    assert by_plain.user_id == admin.id


async def test_audit_csv_and_detail_hide_sensitive_payloads(session: AsyncSession) -> None:
    seeded = await _seed_audit_data(session)
    now = seeded["now"]

    report = await build_audit_csv_report(
        session,
        filters=AuditViewerFilters(action="admin_direct_message", period="all"),
        timezone="UTC",
        now=now,
    )
    detail = await get_audit_event_detail(session, audit_log_id=2)
    text = report.data.decode("utf-8")

    assert report.row_count == 1
    assert "admin_direct_message" in text
    assert "[REDACTED]" in text
    assert "секретный текст" not in text
    assert "https://t.me/+PrivateInvite" not in text
    assert "123456789:ABCDEFGHIJKLMNOPQRSTUV" not in text
    assert detail.payload_redacted is not None
    assert "[REDACTED]" in detail.payload_redacted
    assert "секретный текст" not in detail.payload_redacted
