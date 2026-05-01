
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import AuditLog, Channel, Payment, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.services.referral_service import (
    bind_referrer_for_user,
    build_admin_referral_snapshot,
    build_user_referral_dashboard,
    grant_referral_reward_for_first_payment,
)
from app.utils.referrals import build_referral_code, build_referral_payload


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


async def _seed_tariff(session: AsyncSession) -> Tariff:
    channel = Channel(
        telegram_chat_id=-1001234500001,
        title="Referral dashboard channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add(channel)
    await session.flush()
    tariff = Tariff(
        name="Referral 30",
        price_stars=250,
        duration_days=30,
        sort_order=10,
        is_active=True,
        channel_id=channel.id,
    )
    session.add(tariff)
    await session.flush()
    return tariff


async def test_build_user_referral_dashboard_counts_and_link() -> None:
    session = await _create_session()
    try:
        tariff = await _seed_tariff(session)
        referrer = User(
            telegram_id=1010,
            first_name="Referrer",
            username="referrer",
            referral_code=build_referral_code(1010),
            pending_referral_reward_days=4,
            role="user",
        )
        invited_paid = User(
            telegram_id=2020,
            first_name="Paid Friend",
            role="user",
            referred_by_user_id=1,
            referred_at=datetime(2026, 5, 1, 8, 0, tzinfo=UTC),
        )
        invited_free = User(
            telegram_id=3030,
            first_name="Free Friend",
            role="user",
            referred_by_user_id=1,
            referred_at=datetime(2026, 5, 2, 8, 0, tzinfo=UTC),
        )
        session.add(referrer)
        await session.flush()
        invited_paid.referred_by_user_id = referrer.id
        invited_free.referred_by_user_id = referrer.id
        session.add_all([invited_paid, invited_free])
        await session.flush()

        payment = Payment(
            user_id=invited_paid.id,
            tariff_id=tariff.id,
            channel_id=tariff.channel_id,
            amount=250,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="dash-tg-1",
            provider_payment_charge_id="dash-provider-1",
            invoice_payload="subscription:2020",
            status="paid",
            paid_at=datetime(2026, 5, 3, 8, 0, tzinfo=UTC),
        )
        session.add(payment)
        await session.flush()
        await grant_referral_reward_for_first_payment(
            session,
            referred_user_id=invited_paid.id,
            payment=payment,
            reward_days=7,
            paid_at=payment.paid_at,
        )

        dashboard = await build_user_referral_dashboard(
            session,
            user_id=referrer.id,
            bot_username="PrivatAir_bot",
        )

        assert dashboard is not None
        assert dashboard.referral_payload == build_referral_payload(referrer.referral_code)
        assert dashboard.referral_link == (
            f"https://t.me/PrivatAir_bot?start={dashboard.referral_payload}"
        )
        assert dashboard.invited_users_count == 2
        assert dashboard.paid_referrals_count == 1
        assert dashboard.earned_days == 7
        assert dashboard.pending_reward_days == 11
    finally:
        await _close_session(session)

async def test_build_admin_referral_snapshot_includes_top_and_suspicious() -> None:
    session = await _create_session()
    try:
        tariff = await _seed_tariff(session)
        top_referrer = User(
            telegram_id=4040,
            first_name="Top",
            username="topper",
            referral_code=build_referral_code(4040),
            role="user",
        )
        second_referrer = User(
            telegram_id=5050,
            first_name="Second",
            username="second",
            referral_code=build_referral_code(5050),
            role="user",
        )
        victim = User(
            telegram_id=6060,
            first_name="Victim",
            role="user",
        )
        session.add_all([top_referrer, second_referrer, victim])
        await session.flush()

        invited_top = []
        for index in range(2):
            invited = User(
                telegram_id=7000 + index,
                first_name=f"Top Friend {index}",
                role="user",
                referred_by_user_id=top_referrer.id,
                referred_at=datetime(2026, 5, 4, 8 + index, 0, tzinfo=UTC),
            )
            session.add(invited)
            invited_top.append(invited)
        invited_second = User(
            telegram_id=8001,
            first_name="Second Friend",
            role="user",
            referred_by_user_id=second_referrer.id,
            referred_at=datetime(2026, 5, 4, 11, 0, tzinfo=UTC),
        )
        session.add(invited_second)
        await session.flush()

        paid_payment = Payment(
            user_id=invited_top[0].id,
            tariff_id=tariff.id,
            channel_id=tariff.channel_id,
            amount=250,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="snap-tg-1",
            provider_payment_charge_id="snap-provider-1",
            invoice_payload="subscription:7000",
            status="paid",
            paid_at=datetime(2026, 5, 5, 9, 0, tzinfo=UTC),
        )
        session.add(paid_payment)
        await session.flush()
        await grant_referral_reward_for_first_payment(
            session,
            referred_user_id=invited_top[0].id,
            payment=paid_payment,
            reward_days=7,
            paid_at=paid_payment.paid_at,
        )
        await session.commit()

        before_count = len(list((await session.execute(select(AuditLog))).scalars()))
        first_bind = await bind_referrer_for_user(
            session,
            user=victim,
            raw_code=top_referrer.referral_code or "",
        )
        duplicate = await bind_referrer_for_user(
            session,
            user=victim,
            raw_code=second_referrer.referral_code or "",
        )
        snapshot = await build_admin_referral_snapshot(session, limit=10)
        after_count = len(list((await session.execute(select(AuditLog))).scalars()))

        assert first_bind.status == "bound"
        assert duplicate.status == "already_bound"
        assert snapshot.total_invited_users == 4
        assert snapshot.total_paid_referrals == 1
        assert snapshot.rewards_issued_count == 1
        assert snapshot.reward_days_issued == 7
        assert snapshot.conversion_percent == 25
        assert snapshot.top_referrers
        assert snapshot.top_referrers[0].user.id == top_referrer.id
        assert snapshot.top_referrers[0].invited_users_count == 3
        assert snapshot.top_referrers[0].paid_referrals_count == 1
        assert snapshot.suspicious_events
        assert snapshot.suspicious_events[0].reason == "already_bound"
        assert after_count == before_count + 2
    finally:
        await _close_session(session)
