from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import AuditLog, Channel, Payment, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.services.referral_service import (
    bind_referrer_for_user,
    consume_pending_referral_reward_days,
    get_pending_referral_reward_days,
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
        telegram_chat_id=-1001234567890,
        title="Referral channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add(channel)
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
    await session.flush()
    return tariff


async def test_bind_referrer_for_first_unpaid_user() -> None:
    session = await _create_session()
    try:
        referrer = User(
            telegram_id=1001,
            first_name="Referrer",
            referral_code=build_referral_code(1001),
            role="user",
        )
        referred = User(telegram_id=2002, first_name="Friend", role="user")
        session.add_all([referrer, referred])
        await session.commit()

        result = await bind_referrer_for_user(
            session,
            user=referred,
            raw_code=build_referral_payload(referrer.referral_code),
            at_time=datetime(2026, 5, 1, 8, 0, tzinfo=UTC),
        )
        await session.flush()

        audits = list((await session.execute(select(AuditLog))).scalars())

        assert result.status == "bound"
        assert referred.referred_by_user_id == referrer.id
        assert referred.referred_at == datetime(2026, 5, 1, 8, 0, tzinfo=UTC)
        assert any(log.action == "referral_bound" for log in audits)
    finally:
        await _close_session(session)


async def test_bind_referrer_rejects_self_and_paid_customer() -> None:
    session = await _create_session()
    try:
        tariff = await _seed_tariff(session)
        referrer = User(
            telegram_id=3003,
            first_name="Self",
            referral_code=build_referral_code(3003),
            role="user",
        )
        paid_user = User(telegram_id=4004, first_name="Paid", role="user")
        session.add_all([referrer, paid_user])
        await session.flush()
        session.add(
            Payment(
                user_id=paid_user.id,
                tariff_id=tariff.id,
                channel_id=tariff.channel_id,
                amount=250,
                currency="XTR",
                provider="telegram_stars",
                telegram_payment_charge_id="paid-user-charge",
                provider_payment_charge_id="provider-paid-user-charge",
                invoice_payload="stars:tariff:1",
                status="paid",
                paid_at=datetime(2026, 5, 1, 9, 0, tzinfo=UTC),
            )
        )
        await session.commit()

        self_result = await bind_referrer_for_user(
            session,
            user=referrer,
            raw_code=referrer.referral_code or "",
        )
        paid_result = await bind_referrer_for_user(
            session,
            user=paid_user,
            raw_code=referrer.referral_code or "",
        )

        assert self_result.status == "self_referral"
        assert paid_result.status == "already_customer"
        assert paid_user.referred_by_user_id is None
    finally:
        await _close_session(session)


async def test_grant_reward_and_consume_bonus_once() -> None:
    session = await _create_session()
    try:
        tariff = await _seed_tariff(session)
        referrer = User(
            telegram_id=5005,
            first_name="Referrer",
            referral_code=build_referral_code(5005),
            role="user",
        )
        referred = User(
            telegram_id=6006,
            first_name="Referred",
            role="user",
            referred_by_user_id=1,
            referred_at=datetime(2026, 5, 1, 10, 0, tzinfo=UTC),
        )
        session.add(referrer)
        await session.flush()
        referred.referred_by_user_id = referrer.id
        session.add(referred)
        await session.flush()

        referred_payment = Payment(
            user_id=referred.id,
            tariff_id=tariff.id,
            channel_id=tariff.channel_id,
            amount=250,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="referral-charge-1",
            provider_payment_charge_id="provider-referral-charge-1",
            invoice_payload="stars:tariff:1",
            status="paid",
            paid_at=datetime(2026, 5, 1, 10, 30, tzinfo=UTC),
        )
        session.add(referred_payment)
        await session.flush()

        first = await grant_referral_reward_for_first_payment(
            session,
            referred_user_id=referred.id,
            payment=referred_payment,
            reward_days=7,
            paid_at=referred_payment.paid_at,
        )
        second = await grant_referral_reward_for_first_payment(
            session,
            referred_user_id=referred.id,
            payment=referred_payment,
            reward_days=7,
            paid_at=referred_payment.paid_at,
        )

        assert first.is_granted is True
        assert second.is_granted is False
        assert await get_pending_referral_reward_days(session, user_id=referrer.id) == 7
        assert referred.referral_reward_granted_at == referred_payment.paid_at

        referrer_payment = Payment(
            user_id=referrer.id,
            tariff_id=tariff.id,
            channel_id=tariff.channel_id,
            amount=250,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="referral-charge-2",
            provider_payment_charge_id="provider-referral-charge-2",
            invoice_payload="stars:tariff:1",
            status="paid",
            paid_at=datetime(2026, 5, 1, 11, 0, tzinfo=UTC),
        )
        session.add(referrer_payment)
        await session.flush()

        consumed = await consume_pending_referral_reward_days(
            session,
            user_id=referrer.id,
            payment=referrer_payment,
            consumed_days=7,
            consumed_at=referrer_payment.paid_at,
        )
        audits = list((await session.execute(select(AuditLog))).scalars())

        assert consumed == 7
        assert await get_pending_referral_reward_days(session, user_id=referrer.id) == 0
        assert any(log.action == "referral_reward_granted" for log in audits)
        assert any(log.action == "referral_reward_applied" for log in audits)
    finally:
        await _close_session(session)
