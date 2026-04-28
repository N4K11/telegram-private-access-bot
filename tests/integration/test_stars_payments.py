from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aiogram.types import SuccessfulPayment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import Channel, Payment, Subscription, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.services.payments.stars import (
    build_stars_invoice_payload,
    process_successful_stars_payment,
)
from app.services.subscriptions import activate_or_extend_subscription


async def _create_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    session = session_factory()
    session._test_engine = engine  # type: ignore[attr-defined]
    return session


async def _close_session(session: AsyncSession) -> None:
    engine = session._test_engine  # type: ignore[attr-defined]
    await session.close()
    await engine.dispose()


async def _seed_user_channel_tariff(session: AsyncSession) -> tuple[User, Channel, Tariff]:
    user = User(telegram_id=42, first_name="Anna", is_admin=False, role="user")
    channel = Channel(
        telegram_chat_id=-1001234567890,
        title="Основной канал",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add_all([user, channel])
    await session.flush()

    tariff = Tariff(
        name="VIP 30",
        price_stars=250,
        duration_days=30,
        sort_order=10,
        is_active=True,
        channel_id=channel.id,
    )
    session.add(tariff)
    await session.commit()
    return user, channel, tariff


def _successful_payment(
    *,
    tariff_id: int,
    amount: int,
    charge_id: str,
    provider_charge_id: str = "provider-1",
) -> SuccessfulPayment:
    return SuccessfulPayment(
        currency="XTR",
        total_amount=amount,
        invoice_payload=build_stars_invoice_payload(tariff_id),
        telegram_payment_charge_id=charge_id,
        provider_payment_charge_id=provider_charge_id,
    )


async def test_duplicate_payment_does_not_extend_twice() -> None:
    session = await _create_session()
    try:
        user, _, tariff = await _seed_user_channel_tariff(session)
        paid_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
        successful_payment = _successful_payment(
            tariff_id=tariff.id,
            amount=tariff.price_stars,
            charge_id="tg-charge-1",
        )

        first = await process_successful_stars_payment(
            session,
            user_id=user.id,
            tariff=tariff,
            successful_payment=successful_payment,
            paid_at=paid_at,
        )
        await session.commit()
        first_expires_at = first.subscription.expires_at

        second = await process_successful_stars_payment(
            session,
            user_id=user.id,
            tariff=tariff,
            successful_payment=successful_payment,
            paid_at=paid_at,
        )
        await session.commit()

        payments = list((await session.execute(select(Payment))).scalars())

        assert len(payments) == 1
        assert second.is_duplicate is True
        assert second.subscription is not None
        assert second.subscription.expires_at == first_expires_at
    finally:
        await _close_session(session)


async def test_active_subscription_extends_from_current_expiration() -> None:
    session = await _create_session()
    try:
        user, channel, tariff = await _seed_user_channel_tariff(session)
        paid_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
        current = Subscription(
            user_id=user.id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            status="active",
            source="purchase",
            started_at=paid_at - timedelta(days=5),
            expires_at=paid_at + timedelta(days=10),
        )
        session.add(current)
        await session.commit()

        change = await activate_or_extend_subscription(
            session,
            user_id=user.id,
            tariff=tariff,
            paid_at=paid_at,
        )

        assert change.is_extension is True
        assert change.subscription.id == current.id
        assert change.starts_at == paid_at - timedelta(days=5)
        assert change.subscription.expires_at == paid_at + timedelta(days=40)
    finally:
        await _close_session(session)


async def test_expired_subscription_restarts_from_current_time() -> None:
    session = await _create_session()
    try:
        user, channel, tariff = await _seed_user_channel_tariff(session)
        paid_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
        expired = Subscription(
            user_id=user.id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            status="active",
            source="purchase",
            started_at=paid_at - timedelta(days=40),
            expires_at=paid_at - timedelta(days=1),
        )
        session.add(expired)
        await session.commit()

        change = await activate_or_extend_subscription(
            session,
            user_id=user.id,
            tariff=tariff,
            paid_at=paid_at,
        )
        await session.flush()

        refreshed = await session.get(Subscription, expired.id)

        assert change.is_extension is False
        assert change.subscription.id != expired.id
        assert change.subscription.started_at == paid_at
        assert change.subscription.expires_at == paid_at + timedelta(days=30)
        assert refreshed is not None
        assert refreshed.status == "expired"
    finally:
        await _close_session(session)