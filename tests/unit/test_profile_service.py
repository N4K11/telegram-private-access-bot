# ruff: noqa: E501
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import Channel, Payment, Subscription, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.services.profile import (
    build_user_profile_snapshot,
    render_user_payment_history,
    render_user_profile,
)
from app.utils.referrals import build_referral_payload


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


async def _seed_user_channel_tariff(
    session: AsyncSession,
    *,
    telegram_id: int = 42,
    referral_code: str | None = "R16",
    pending_reward_days: int = 0,
    rewarded_at: datetime | None = None,
) -> tuple[User, Channel, Tariff]:
    user = User(
        telegram_id=telegram_id,
        username="anna",
        first_name="Anna",
        role="user",
        referral_code=referral_code,
        pending_referral_reward_days=pending_reward_days,
        referral_reward_granted_at=rewarded_at,
    )
    channel = Channel(
        telegram_chat_id=-1001234567890,
        title="Main channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add_all([user, channel])
    await session.flush()

    tariff = Tariff(
        name="VIP 30",
        price_stars=250,
        price_crypto=Decimal("1.25"),
        duration_days=30,
        sort_order=10,
        is_active=True,
        channel_id=channel.id,
    )
    session.add(tariff)
    await session.flush()
    return user, channel, tariff


async def test_build_user_profile_snapshot_is_read_only(session: AsyncSession) -> None:
    user, _, _ = await _seed_user_channel_tariff(session)
    await session.commit()

    snapshot = await build_user_profile_snapshot(
        session,
        telegram_user_id=user.telegram_id,
        now=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )

    assert snapshot is not None
    assert not session.new
    assert not session.dirty
    assert not session.deleted


async def test_render_user_profile_shows_active_status_and_referral_info(
    session: AsyncSession,
) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    user, channel, tariff = await _seed_user_channel_tariff(
        session,
        pending_reward_days=3,
        rewarded_at=now,
    )
    referred_user = User(
        telegram_id=777,
        first_name="Ref",
        role="user",
        referred_by_user_id=user.id,
        referral_reward_granted_at=now,
    )
    session.add(referred_user)
    await session.flush()

    session.add(
        Subscription(
            user_id=user.id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            status="active",
            source="purchase",
            started_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=29, hours=6),
        )
    )
    session.add_all(
        [
            Payment(
                user_id=user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                amount=250,
                currency="XTR",
                provider="telegram_stars",
                telegram_payment_charge_id="tg-stars-1",
                provider_payment_charge_id="provider-stars-1",
                invoice_payload="stars:tariff:1",
                raw_payload='{"secret":"stars-token"}',
                paid_at=now,
                status="paid",
            ),
            Payment(
                user_id=user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                amount=125,
                currency="USDT",
                provider="crypto_pay",
                telegram_payment_charge_id="tg-crypto-1",
                provider_payment_charge_id="provider-crypto-1",
                invoice_payload="crypto:invoice:1",
                raw_payload='{"secret":"crypto-token"}',
                paid_at=now - timedelta(hours=2),
                status="paid",
            ),
        ]
    )
    await session.commit()

    snapshot = await build_user_profile_snapshot(session, telegram_user_id=user.telegram_id, now=now)

    assert snapshot is not None
    assert snapshot.status == "активен"
    assert snapshot.has_active_subscription is True
    assert snapshot.total_stars_amount == 250
    assert snapshot.total_crypto_amounts == {"USDT": Decimal("1.25")}
    assert snapshot.current_channel_label == "Main channel"

    text = render_user_profile(snapshot, timezone="UTC")

    assert "Статус: ✅ Активна" in text
    assert "Stars: 250 XTR" in text
    assert "Crypto Pay: 1.25 USDT" in text
    assert build_referral_payload(user.referral_code or "") in text
    assert "Бонус к следующей оплате: 3 дн." in text
    assert "Успешных друзей: 1" in text


async def test_render_user_profile_shows_expired_state(session: AsyncSession) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    user, channel, tariff = await _seed_user_channel_tariff(session)
    session.add(
        Subscription(
            user_id=user.id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            status="expired",
            source="purchase",
            started_at=now - timedelta(days=40),
            expires_at=now - timedelta(days=1),
        )
    )
    await session.commit()

    snapshot = await build_user_profile_snapshot(session, telegram_user_id=user.telegram_id, now=now)

    assert snapshot is not None
    assert snapshot.status == "истёк"
    assert snapshot.remaining_label == "Истекла"
    assert "(последний)" in snapshot.current_tariff_label

    text = render_user_profile(snapshot, timezone="UTC")

    assert "Статус: ⏳ Истекла" in text
    assert "Осталось: Истекла" in text


async def test_render_user_payment_history_handles_empty_state(session: AsyncSession) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    user, _, _ = await _seed_user_channel_tariff(session)
    await session.commit()

    snapshot = await build_user_profile_snapshot(session, telegram_user_id=user.telegram_id, now=now)

    assert snapshot is not None
    text = render_user_payment_history(snapshot, timezone="UTC")

    assert "Пока нет успешных оплат через Stars." in text
    assert "Пока нет успешных оплат через Crypto Pay." in text


async def test_render_user_payment_history_separates_providers_without_secret_leakage(
    session: AsyncSession,
) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    user, channel, tariff = await _seed_user_channel_tariff(session)
    session.add_all(
        [
            Payment(
                user_id=user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                amount=500,
                currency="XTR",
                provider="telegram_stars",
                telegram_payment_charge_id="tg-stars-2",
                provider_payment_charge_id="provider-stars-secret",
                invoice_payload="stars:tariff:secret",
                raw_payload='{"raw":"stars-secret"}',
                paid_at=now,
                status="paid",
            ),
            Payment(
                user_id=user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                amount=250,
                currency="USDT",
                provider="crypto_pay",
                telegram_payment_charge_id="tg-crypto-2",
                provider_payment_charge_id="provider-crypto-secret",
                invoice_payload="crypto:invoice:secret",
                raw_payload='{"raw":"crypto-secret"}',
                paid_at=now - timedelta(hours=1),
                status="paid",
            ),
        ]
    )
    await session.commit()

    snapshot = await build_user_profile_snapshot(session, telegram_user_id=user.telegram_id, now=now)

    assert snapshot is not None
    text = render_user_payment_history(snapshot, timezone="UTC")

    assert "Telegram Stars" in text
    assert "Crypto Pay" in text
    assert "500 XTR" in text
    assert "2.5 USDT" in text
    assert "stars-secret" not in text
    assert "crypto-secret" not in text
    assert "provider-stars-secret" not in text
    assert "provider-crypto-secret" not in text
    assert "stars:tariff:secret" not in text
    assert "crypto:invoice:secret" not in text
