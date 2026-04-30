from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from aiogram.types import SuccessfulPayment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.routers.admin.promos import (
    admin_promo_create,
    admin_promo_disable,
    admin_promo_stats,
)
from app.bot.routers.user.payments import buy_tariff, successful_payment_handler
from app.bot.routers.user.promos import promo_command
from app.config import Settings
from app.db.base import Base
from app.db.models import (
    AuditLog,
    Channel,
    Payment,
    PromoCode,
    PromoRedemption,
    Subscription,
    Tariff,
    User,
)
from app.db.session import create_async_engine, create_session_factory


class DummyUser:
    def __init__(
        self,
        user_id: int = 42,
        *,
        first_name: str = "Anna",
        username: str | None = "anna",
    ) -> None:
        self.id = user_id
        self.first_name = first_name
        self.username = username
        self.last_name = None
        self.language_code = "ru"


class DummyMessage:
    def __init__(self, text: str, *, user_id: int = 42, first_name: str = "Anna") -> None:
        self.text = text
        self.from_user = DummyUser(user_id=user_id, first_name=first_name)
        self.answer_calls: list[tuple[str, object | None]] = []
        self.invoice_calls: list[dict[str, object]] = []
        self.successful_payment: SuccessfulPayment | None = None
        self.date = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))

    async def answer_invoice(self, **kwargs):
        self.invoice_calls.append(kwargs)
        return kwargs


class DummyCallback:
    def __init__(self, data: str, *, user_id: int = 42) -> None:
        self.data = data
        self.from_user = DummyUser(user_id=user_id)
        self.message = DummyMessage("callback", user_id=user_id)
        self.answer_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args, **kwargs) -> None:
        self.answer_calls.append((args, kwargs))


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
            invite_link="https://t.me/+promo-invite",
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
            "timezone": "UTC",
        }
    )


async def _seed_tariff(
    session: AsyncSession,
    *,
    telegram_id: int = 42,
) -> tuple[User, Tariff]:
    user = User(
        telegram_id=telegram_id,
        first_name="Anna",
        username="anna",
        is_admin=False,
        role="user",
    )
    channel = Channel(
        telegram_chat_id=-1001234567890 - telegram_id,
        title="Основной канал",
        username=f"main_channel_{telegram_id}",
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
    return user, tariff


async def test_promo_command_grants_free_days_without_fake_payment(
    session: AsyncSession,
    settings: Settings,
) -> None:
    _, tariff = await _seed_tariff(session)
    session.add(
        PromoCode(
            code="FREE7",
            promo_type="free_days",
            value=7,
            max_uses=1,
            tariff_id=tariff.id,
            is_active=True,
        )
    )
    await session.commit()

    message = DummyMessage("/promo FREE7")
    bot = FakeBot()

    await promo_command(message, session, settings, bot)

    subscriptions = list((await session.execute(select(Subscription))).scalars())
    payments = list((await session.execute(select(Payment))).scalars())
    audits = list((await session.execute(select(AuditLog))).scalars())
    redemptions = list((await session.execute(select(PromoRedemption))).scalars())

    assert message.answer_calls
    text, _ = message.answer_calls[-1]
    assert "Промокод FREE7 активирован" in text
    assert "Ссылка доступа: https://t.me/+promo-invite" in text
    assert len(subscriptions) == 1
    assert len(payments) == 0
    assert len(redemptions) == 1
    assert redemptions[0].status == "consumed"
    assert any(log.action == "promo_applied_free_days" for log in audits)


async def test_discount_promo_changes_invoice_amount_and_is_consumed_after_payment(
    session: AsyncSession,
    settings: Settings,
) -> None:
    user, tariff = await _seed_tariff(session)
    session.add(
        PromoCode(
            code="SAVE50",
            promo_type="discount_stars",
            value=50,
            max_uses=5,
            tariff_id=tariff.id,
            is_active=True,
        )
    )
    await session.commit()

    bot = FakeBot()
    promo_message = DummyMessage("/promo SAVE50", user_id=user.telegram_id)
    await promo_command(promo_message, session, settings, bot)

    callback = DummyCallback(f"menu:user:buy:{tariff.id}", user_id=user.telegram_id)
    await buy_tariff(callback, session)

    assert callback.message.invoice_calls
    invoice = callback.message.invoice_calls[0]
    assert invoice["prices"][0].amount == 200
    assert str(invoice["payload"]).startswith(f"stars:tariff:{tariff.id}:promo:")

    paid_message = DummyMessage("paid", user_id=user.telegram_id)
    paid_message.successful_payment = SuccessfulPayment(
        currency="XTR",
        total_amount=200,
        invoice_payload=str(invoice["payload"]),
        telegram_payment_charge_id="tg-promo-1",
        provider_payment_charge_id="provider-promo-1",
    )
    paid_message.date = datetime(2026, 5, 1, 12, 30, tzinfo=UTC)

    await successful_payment_handler(paid_message, session, settings, bot)

    payments = list((await session.execute(select(Payment))).scalars())
    redemptions = list((await session.execute(select(PromoRedemption))).scalars())
    audits = list((await session.execute(select(AuditLog))).scalars())

    assert len(payments) == 1
    assert payments[0].amount == 200
    assert len(redemptions) == 1
    assert redemptions[0].status == "consumed"
    assert redemptions[0].amount_before == 250
    assert redemptions[0].amount_after == 200
    assert any(log.action == "promo_applied_pending" for log in audits)
    assert any(log.action == "payment_paid_stars" for log in audits)


async def test_admin_promo_commands_create_disable_and_show_stats(
    session: AsyncSession,
    settings: Settings,
) -> None:
    admin = User(telegram_id=755815181, first_name="Admin", is_admin=True, role="owner")
    channel = Channel(
        telegram_chat_id=-100999,
        title="Admin channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add_all([admin, channel])
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

    create_message = DummyMessage(
        f"/admin_promo_create ADMIN20 discount_percent 20 3 {tariff.id} 5",
        user_id=755815181,
        first_name="Admin",
    )
    create_message.from_user.username = "admin"
    await admin_promo_create(create_message, session, settings)

    stats_message = DummyMessage(
        "/admin_promo_stats ADMIN20",
        user_id=755815181,
        first_name="Admin",
    )
    stats_message.from_user.username = "admin"
    await admin_promo_stats(stats_message, session, settings)

    disable_message = DummyMessage(
        "/admin_promo_disable ADMIN20",
        user_id=755815181,
        first_name="Admin",
    )
    disable_message.from_user.username = "admin"
    await admin_promo_disable(disable_message, session, settings)

    promo_query = select(PromoCode).where(PromoCode.code == "ADMIN20")
    promo = (await session.execute(promo_query)).scalar_one()
    audits = list((await session.execute(select(AuditLog))).scalars())

    assert create_message.answer_calls
    assert "Промокод создан" in create_message.answer_calls[0][0]
    assert stats_message.answer_calls
    assert "Статистика промокода" in stats_message.answer_calls[0][0]
    assert disable_message.answer_calls
    assert "отключён" in disable_message.answer_calls[0][0]
    assert promo.is_active is False
    assert any(log.action == "promo_created" for log in audits)
    assert any(log.action == "promo_disabled" for log in audits)
