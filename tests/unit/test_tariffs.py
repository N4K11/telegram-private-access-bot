# ruff: noqa: E501
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import Channel, Subscription, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.services.subscriptions import activate_or_extend_subscription
from app.services.tariffs import (
    LIFETIME_EXPIRES_AT,
    TariffValidationError,
    effective_crypto_asset,
    effective_crypto_price,
    ensure_tariff_purchase_allowed,
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


async def _seed_user_channel(session: AsyncSession) -> tuple[User, Channel]:
    user = User(telegram_id=42, first_name="Anna", role="user")
    channel = Channel(
        telegram_chat_id=-1001234567890,
        title="Main channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add_all([user, channel])
    await session.flush()
    return user, channel


async def test_trial_tariff_can_be_used_only_once(session: AsyncSession) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    user, channel = await _seed_user_channel(session)
    first_trial = Tariff(
        name="Trial 7",
        price_stars=1,
        duration_days=7,
        sort_order=10,
        is_active=True,
        is_trial=True,
        channel_id=channel.id,
    )
    second_trial = Tariff(
        name="Trial 3",
        price_stars=1,
        duration_days=3,
        sort_order=20,
        is_active=True,
        is_trial=True,
        channel_id=channel.id,
    )
    session.add_all([first_trial, second_trial])
    await session.flush()

    await ensure_tariff_purchase_allowed(session, user_id=user.id, tariff=first_trial, now=now)
    session.add(
        Subscription(
            user_id=user.id,
            tariff_id=first_trial.id,
            channel_id=channel.id,
            status="expired",
            source="purchase",
            started_at=now - timedelta(days=10),
            expires_at=now - timedelta(days=3),
        )
    )
    await session.commit()

    with pytest.raises(TariffValidationError):
        await ensure_tariff_purchase_allowed(session, user_id=user.id, tariff=second_trial, now=now)


async def test_lifetime_subscription_uses_far_future_expiration(session: AsyncSession) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    user, channel = await _seed_user_channel(session)
    tariff = Tariff(
        name="Lifetime",
        price_stars=999,
        duration_days=365,
        sort_order=10,
        is_active=True,
        is_lifetime=True,
        channel_id=channel.id,
    )
    session.add(tariff)
    await session.commit()

    change = await activate_or_extend_subscription(
        session,
        user_id=user.id,
        tariff=tariff,
        paid_at=now,
    )

    assert change.subscription.expires_at == LIFETIME_EXPIRES_AT
    assert change.subscription.status == "active"


async def test_effective_crypto_price_prefers_new_override(session: AsyncSession) -> None:
    _, channel = await _seed_user_channel(session)
    tariff = Tariff(
        name="VIP",
        price_stars=250,
        price_crypto=Decimal("1.25"),
        crypto_price_amount=Decimal("2.50"),
        crypto_asset="TON",
        duration_days=30,
        sort_order=10,
        is_active=True,
        channel_id=channel.id,
    )
    session.add(tariff)
    await session.commit()

    assert effective_crypto_price(tariff) == Decimal("2.50")
    assert effective_crypto_asset(tariff, ["USDT"]) == "TON"
