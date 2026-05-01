from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.routers.admin.referrals import admin_referrals
from app.config import Settings
from app.db.base import Base
from app.db.models import Channel, Payment, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.services.referral_service import grant_referral_reward_for_first_payment
from app.utils.referrals import build_referral_code


class DummyAdminUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.is_bot = False
        self.first_name = "Admin"
        self.language_code = "ru"


class DummyAdminMessage:
    def __init__(self, user_id: int) -> None:
        self.from_user = DummyAdminUser(user_id)
        self.answer_calls: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))


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


async def test_admin_referrals_command_renders_snapshot() -> None:
    session = await _create_session()
    try:
        channel = Channel(
            telegram_chat_id=-1001234500200,
            title="Admin referrals",
            invite_users_permission=True,
            ban_users_permission=True,
            is_active=True,
        )
        session.add(channel)
        await session.flush()
        tariff = Tariff(
            name="VIP",
            price_stars=199,
            duration_days=30,
            sort_order=10,
            is_active=True,
            channel_id=channel.id,
        )
        session.add(tariff)
        await session.flush()
        referrer = User(
            telegram_id=123001,
            first_name="Referrer",
            username="ref",
            referral_code=build_referral_code(123001),
            role="user",
        )
        referred = User(
            telegram_id=123002,
            first_name="Friend",
            role="user",
            referred_by_user_id=1,
            referred_at=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        )
        session.add(referrer)
        await session.flush()
        referred.referred_by_user_id = referrer.id
        session.add(referred)
        await session.flush()
        payment = Payment(
            user_id=referred.id,
            tariff_id=tariff.id,
            channel_id=tariff.channel_id,
            amount=199,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="admin-ref-tg-1",
            provider_payment_charge_id="admin-ref-provider-1",
            invoice_payload="subscription:123002",
            status="paid",
            paid_at=datetime(2026, 5, 7, 13, 0, tzinfo=UTC),
        )
        session.add(payment)
        await session.flush()
        await grant_referral_reward_for_first_payment(
            session,
            referred_user_id=referred.id,
            payment=payment,
            reward_days=7,
            paid_at=payment.paid_at,
        )

        message = DummyAdminMessage(755815181)
        settings = Settings.model_validate(
            {"bot_token": "123:token", "admin_ids": [755815181], "timezone": "UTC"}
        )

        await admin_referrals(message, session, settings)

        assert len(message.answer_calls) == 1
        text, reply_markup = message.answer_calls[0]
        assert "Реферальная аналитика" in text
        assert "Всего приглашённых: 1" in text
        assert "Оплативших: 1" in text
        assert "Топ рефереров:" in text
        assert reply_markup is not None
    finally:
        await _close_session(session)
