from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from aiogram.types import SuccessfulPayment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.routers.user.payments import successful_payment_handler
from app.bot.routers.user.start import start_handler
from app.config import Settings
from app.db.base import Base
from app.db.models import AuditLog, Channel, Subscription, Tariff, User
from app.db.repositories.users import UserRepository
from app.db.session import create_async_engine, create_session_factory
from app.services.payments.stars import build_stars_invoice_payload
from app.utils.datetime import ensure_aware_utc
from app.utils.referrals import build_referral_code, build_referral_payload


class DummyUser:
    def __init__(
        self,
        user_id: int,
        *,
        first_name: str,
        username: str | None = None,
    ) -> None:
        self.id = user_id
        self.first_name = first_name
        self.username = username
        self.last_name = None
        self.language_code = "ru"


class DummyMessage:
    def __init__(
        self,
        text: str,
        *,
        user_id: int,
        first_name: str,
        username: str | None = None,
    ) -> None:
        self.text = text
        self.from_user = DummyUser(user_id, first_name=first_name, username=username)
        self.answer_calls: list[tuple[str, object | None]] = []
        self.photo_calls: list[tuple[object, str | None, object | None]] = []
        self.successful_payment: SuccessfulPayment | None = None
        self.date = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))

    async def answer_photo(self, photo, caption: str | None = None, reply_markup=None) -> None:
        self.photo_calls.append((photo, caption, reply_markup))


class DummyInvite:
    def __init__(self, invite_link: str, expire_date: datetime, member_limit: int = 1) -> None:
        self.invite_link = invite_link
        self.expire_date = expire_date
        self.member_limit = member_limit


class FakeBot:
    def __init__(self) -> None:
        self.invite_calls: list[dict[str, object]] = []

    async def create_chat_invite_link(self, **kwargs):
        self.invite_calls.append(kwargs)
        return DummyInvite(
            invite_link="https://t.me/+referral-invite",
            expire_date=kwargs["expire_date"],
            member_limit=kwargs.get("member_limit") or 1,
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


@pytest.fixture
def settings() -> Settings:
    return Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "default_invite_link_ttl_hours": 24,
            "referral_reward_days": 7,
            "timezone": "UTC",
        }
    )


async def _seed_tariff(session: AsyncSession) -> Tariff:
    channel = Channel(
        telegram_chat_id=-1009876543210,
        title="Referral channel",
        username="ref_channel",
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
    await session.commit()
    return tariff


async def test_start_handler_binds_referral_payload_and_shows_notice(
    session: AsyncSession,
    settings: Settings,
) -> None:
    referrer = User(
        telegram_id=1001,
        first_name="Referrer",
        username="referrer",
        referral_code=build_referral_code(1001),
        role="user",
    )
    session.add(referrer)
    await session.commit()

    message = DummyMessage(
        f"/start {build_referral_payload(referrer.referral_code)}",
        user_id=2002,
        first_name="Friend",
        username="friend",
    )

    await start_handler(message, session, settings)

    referred = await UserRepository(session).get_by_telegram_id(2002)

    assert referred is not None
    assert referred.referred_by_user_id == referrer.id
    assert len(message.photo_calls) == 1
    _, caption, _ = message.photo_calls[0]
    assert caption is not None
    assert "Реферальный код принят" in caption


async def test_referral_reward_is_granted_once_and_applied_to_next_payment(
    session: AsyncSession,
    settings: Settings,
) -> None:
    tariff_id = (await _seed_tariff(session)).id
    referrer = User(
        telegram_id=3003,
        first_name="Referrer",
        username="referrer",
        referral_code=build_referral_code(3003),
        role="user",
    )
    referred = User(
        telegram_id=4004,
        first_name="Friend",
        username="friend",
        role="user",
    )
    session.add_all([referrer, referred])
    await session.flush()
    referred.referred_by_user_id = referrer.id
    referred.referred_at = datetime(2026, 5, 1, 11, 0, tzinfo=UTC)
    await session.commit()

    bot = FakeBot()
    first_paid = DummyMessage("paid", user_id=4004, first_name="Friend", username="friend")
    first_paid.successful_payment = SuccessfulPayment(
        currency="XTR",
        total_amount=250,
        invoice_payload=build_stars_invoice_payload(tariff_id),
        telegram_payment_charge_id="tg-ref-1",
        provider_payment_charge_id="provider-ref-1",
    )
    first_paid.date = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)

    await successful_payment_handler(first_paid, session, settings, bot)

    await session.refresh(referrer)
    await session.refresh(referred)

    assert referrer.pending_referral_reward_days == 7
    assert ensure_aware_utc(referred.referral_reward_granted_at) == first_paid.date

    second_paid = DummyMessage("paid-2", user_id=4004, first_name="Friend", username="friend")
    second_paid.successful_payment = SuccessfulPayment(
        currency="XTR",
        total_amount=250,
        invoice_payload=build_stars_invoice_payload(tariff_id),
        telegram_payment_charge_id="tg-ref-2",
        provider_payment_charge_id="provider-ref-2",
    )
    second_paid.date = datetime(2026, 5, 2, 12, 0, tzinfo=UTC)

    await successful_payment_handler(second_paid, session, settings, bot)
    await session.refresh(referrer)

    assert referrer.pending_referral_reward_days == 7

    referrer_paid = DummyMessage("paid-3", user_id=3003, first_name="Referrer", username="referrer")
    referrer_paid.successful_payment = SuccessfulPayment(
        currency="XTR",
        total_amount=250,
        invoice_payload=build_stars_invoice_payload(tariff_id),
        telegram_payment_charge_id="tg-referrer-1",
        provider_payment_charge_id="provider-referrer-1",
    )
    referrer_paid.date = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)

    await successful_payment_handler(referrer_paid, session, settings, bot)

    await session.refresh(referrer)
    subscriptions = list(
        (
            await session.execute(
                select(Subscription)
                .where(Subscription.user_id == referrer.id)
                .order_by(Subscription.expires_at.desc(), Subscription.id.desc())
            )
        ).scalars()
    )
    audits = list((await session.execute(select(AuditLog))).scalars())

    assert referrer.pending_referral_reward_days == 0
    assert subscriptions
    assert ensure_aware_utc(subscriptions[0].expires_at) == referrer_paid.date + timedelta(days=37)
    assert len([log for log in audits if log.action == "referral_reward_granted"]) == 1
    assert len([log for log in audits if log.action == "referral_reward_applied"]) == 1
