from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import Channel, Payment, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.services.onboarding import (
    advance_onboarding,
    get_pending_onboarding_step,
    render_onboarding_text,
    skip_onboarding,
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


async def test_new_user_gets_first_onboarding_step(session: AsyncSession) -> None:
    user = User(telegram_id=1001, first_name="Руслан", role="user")
    session.add(user)
    await session.commit()

    snapshot = await get_pending_onboarding_step(
        session,
        user=user,
        at_time=datetime(2026, 5, 2, 10, 0, tzinfo=UTC),
    )

    assert snapshot is not None
    assert snapshot.step_number == 1
    assert snapshot.is_last is False
    text = render_onboarding_text(snapshot, first_name=user.first_name)
    assert "Шаг 1/3" in text
    assert "Привет, Руслан" in text


async def test_onboarding_progress_persists_between_steps(session: AsyncSession) -> None:
    user = User(telegram_id=1002, first_name="Анна", role="user")
    session.add(user)
    await session.commit()

    snapshot = await advance_onboarding(
        session,
        user=user,
        at_time=datetime(2026, 5, 2, 11, 0, tzinfo=UTC),
    )
    await session.commit()
    await session.refresh(user)

    assert snapshot is not None
    assert snapshot.step_number == 2
    assert user.onboarding_step == 1

    resumed = await get_pending_onboarding_step(
        session,
        user=user,
        at_time=datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
    )
    assert resumed is not None
    assert resumed.step_number == 2


async def test_skip_marks_onboarding_completed(session: AsyncSession) -> None:
    user = User(telegram_id=1003, first_name="Иван", role="user")
    session.add(user)
    await session.commit()

    await skip_onboarding(
        user=user,
        at_time=datetime(2026, 5, 2, 13, 0, tzinfo=UTC),
    )
    await session.commit()

    assert user.onboarding_completed_at is not None
    assert (
        await get_pending_onboarding_step(
            session,
            user=user,
            at_time=datetime(2026, 5, 2, 13, 5, tzinfo=UTC),
        )
        is None
    )


async def test_paid_user_is_auto_completed_and_does_not_see_onboarding(
    session: AsyncSession,
) -> None:
    user = User(telegram_id=1004, first_name="Олег", role="user")
    channel = Channel(
        telegram_chat_id=-1001234500001,
        title="Onboarding channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add_all([user, channel])
    await session.flush()
    tariff = Tariff(
        name="VIP",
        price_stars=199,
        price_crypto=Decimal("1.99"),
        duration_days=30,
        sort_order=10,
        is_active=True,
        channel_id=channel.id,
    )
    session.add(tariff)
    await session.flush()
    session.add(
        Payment(
            user_id=user.id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            amount=199,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="tg-onboarding-1",
            provider_payment_charge_id="provider-onboarding-1",
            invoice_payload="subscription:1004",
            paid_at=datetime(2026, 5, 2, 14, 0, tzinfo=UTC),
            status="paid",
        )
    )
    await session.commit()

    snapshot = await get_pending_onboarding_step(
        session,
        user=user,
        at_time=datetime(2026, 5, 2, 14, 5, tzinfo=UTC),
    )

    assert snapshot is None
    assert user.onboarding_completed_at is not None