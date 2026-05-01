# ruff: noqa: E501
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.routers.user.profile import payment_history_section, profile_section
from app.config import Settings
from app.db.base import Base
from app.db.models import Channel, Payment, Subscription, Tariff, User
from app.db.session import create_async_engine, create_session_factory


class DummyUser:
    def __init__(self, user_id: int = 42, first_name: str = "Anna", username: str = "anna") -> None:
        self.id = user_id
        self.first_name = first_name
        self.username = username


class DummyMessage:
    def __init__(self) -> None:
        self.edit_calls: list[tuple[str, object | None]] = []
        self.answer_calls: list[tuple[str, object | None]] = []
        self.media_calls: list[tuple[object, object | None]] = []
        self.photo = None

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edit_calls.append((text, reply_markup))

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))

    async def edit_media(self, media, reply_markup=None) -> None:
        self.media_calls.append((media, reply_markup))


class DummyCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.from_user = DummyUser()
        self.message = DummyMessage()
        self.answer_count = 0
        self.answer_texts: list[str] = []

    async def answer(self, text: str | None = None, **kwargs) -> None:
        self.answer_count += 1
        if text is not None:
            self.answer_texts.append(text)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


async def _seed_user_channel_tariff(session: AsyncSession) -> tuple[User, Channel, Tariff]:
    user = User(
        telegram_id=42,
        username="anna",
        first_name="Anna",
        role="user",
        referral_code="R16",
        pending_referral_reward_days=2,
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


def _flatten_button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


async def test_profile_callback_renders_profile_and_history_button(session: AsyncSession) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    user, channel, tariff = await _seed_user_channel_tariff(session)
    session.add(
        Subscription(
            user_id=user.id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            status="active",
            source="purchase",
            started_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=30),
        )
    )
    session.add(
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
            paid_at=now,
            status="paid",
        )
    )
    await session.commit()

    callback = DummyCallback("menu:user:profile")
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181], "timezone": "UTC"})

    await profile_section(callback, session, settings)

    assert callback.message.edit_calls
    text, markup = callback.message.edit_calls[0]
    assert "Мой профиль" in text
    assert "Статус: ✅ Активна" in text
    assert "📜 История платежей" in _flatten_button_texts(markup)
    assert callback.answer_count == 1


async def test_profile_callback_renders_expired_status(session: AsyncSession) -> None:
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
            expires_at=now - timedelta(hours=6),
        )
    )
    await session.commit()

    callback = DummyCallback("menu:user:profile")
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181], "timezone": "UTC"})

    await profile_section(callback, session, settings)

    text, _ = callback.message.edit_calls[0]
    assert "Статус: ⏳ Истекла" in text
    assert "Осталось: Истекла" in text


async def test_payment_history_callback_renders_stars_and_crypto(session: AsyncSession) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    user, channel, tariff = await _seed_user_channel_tariff(session)
    session.add_all(
        [
            Payment(
                user_id=user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                amount=250,
                currency="XTR",
                provider="telegram_stars",
                telegram_payment_charge_id="tg-stars-2",
                provider_payment_charge_id="provider-stars-2",
                invoice_payload="stars:tariff:2",
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
                telegram_payment_charge_id="tg-crypto-2",
                provider_payment_charge_id="provider-crypto-2",
                invoice_payload="crypto:invoice:2",
                paid_at=now - timedelta(hours=1),
                status="paid",
            ),
        ]
    )
    await session.commit()

    callback = DummyCallback("menu:user:payment-history")
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181], "timezone": "UTC"})

    await payment_history_section(callback, session, settings)

    assert callback.message.edit_calls
    text, markup = callback.message.edit_calls[0]
    assert "История платежей" in text
    assert "Telegram Stars" in text
    assert "Crypto Pay" in text
    assert "250 XTR" in text
    assert "1.25 USDT" in text
    assert _flatten_button_texts(markup) == ["⬅️ Назад", "🏠 Главное меню"]


async def test_payment_history_callback_handles_no_payments(session: AsyncSession) -> None:
    user, _, _ = await _seed_user_channel_tariff(session)
    await session.commit()

    callback = DummyCallback("menu:user:payment-history")
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181], "timezone": "UTC"})

    await payment_history_section(callback, session, settings)

    assert callback.message.edit_calls
    text, _ = callback.message.edit_calls[0]
    assert "Пока нет успешных оплат через Stars." in text
    assert "Пока нет успешных оплат через Crypto Pay." in text
