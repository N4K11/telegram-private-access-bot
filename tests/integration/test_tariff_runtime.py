# ruff: noqa: E501
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.routers.user.payments import (
    buy_product_section,
    buy_section,
    buy_tariff,
    tariffs_product_section,
    tariffs_section,
)
from app.config import Settings
from app.db.base import Base
from app.db.models import Channel, Subscription, Tariff, User
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.tariffs import TariffRepository
from app.db.session import create_async_engine, create_session_factory

DIAMOND = "\U0001f48e"
PRODUCT = "\U0001f4c1"
BACK = "\u2b05\ufe0f"


class DummyUser:
    def __init__(self, user_id: int = 42, first_name: str = "Anna", username: str = "anna") -> None:
        self.id = user_id
        self.first_name = first_name
        self.username = username
        self.last_name = None
        self.language_code = "ru"


class DummyMessage:
    def __init__(self) -> None:
        self.edit_calls: list[tuple[str, object | None]] = []
        self.answer_calls: list[tuple[str, object | None]] = []
        self.invoice_calls: list[dict[str, object]] = []
        self.photo = None

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edit_calls.append((text, reply_markup))

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))

    async def answer_invoice(self, **kwargs):
        self.invoice_calls.append(kwargs)
        return self


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


async def _seed_user_channel(session: AsyncSession) -> tuple[User, Channel]:
    user = User(telegram_id=42, username="anna", first_name="Anna", role="user")
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


async def _seed_second_channel(session: AsyncSession, *, title: str = "VIP chat") -> Channel:
    channel = Channel(
        telegram_chat_id=-1009999999999,
        title=title,
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add(channel)
    await session.flush()
    return channel


def _flatten_button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


async def test_tariffs_section_orders_by_sort_and_hides_archived(session: AsyncSession) -> None:
    _, channel = await _seed_user_channel(session)
    first = Tariff(
        name="Standard",
        price_stars=250,
        duration_days=30,
        sort_order=20,
        is_active=True,
        channel_id=channel.id,
    )
    second = Tariff(
        name="Best",
        badge="BEST",
        price_stars=400,
        duration_days=90,
        sort_order=10,
        is_active=True,
        channel_id=channel.id,
    )
    archived = Tariff(
        name="Old",
        price_stars=100,
        duration_days=7,
        sort_order=1,
        is_active=False,
        archived_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        channel_id=channel.id,
    )
    session.add_all([first, second, archived])
    await session.commit()

    callback = DummyCallback("menu:user:tariffs")
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181], "timezone": "UTC", "crypto_pay_enabled": False})

    await tariffs_section(callback, session, settings)

    assert callback.message.edit_calls
    text, markup = callback.message.edit_calls[0]
    assert "Best" in text
    assert "Old" not in text
    texts = _flatten_button_texts(markup)
    assert texts[0].startswith(f"{DIAMOND} [BEST] Best")
    assert "Old" not in " ".join(texts)


async def test_buy_section_switches_to_product_picker_when_multiple_channels(session: AsyncSession) -> None:
    _, main_channel = await _seed_user_channel(session)
    vip_channel = await _seed_second_channel(session)
    session.add_all(
        [
            Tariff(
                name="Main 30",
                price_stars=250,
                duration_days=30,
                sort_order=10,
                is_active=True,
                channel_id=main_channel.id,
            ),
            Tariff(
                name="VIP 90",
                price_stars=700,
                duration_days=90,
                sort_order=20,
                is_active=True,
                channel_id=vip_channel.id,
            ),
        ]
    )
    await session.commit()

    callback = DummyCallback("menu:user:buy")
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181], "timezone": "UTC", "crypto_pay_enabled": False})

    await buy_section(callback, session, settings)

    text, markup = callback.message.edit_calls[0]
    button_texts = _flatten_button_texts(markup)
    assert "📁 Продукт: Main channel" in text
    assert "📁 Продукт: VIP chat" in text
    assert any(value.startswith(f"{PRODUCT} Main channel") for value in button_texts)
    assert any(value.startswith(f"{PRODUCT} VIP chat") for value in button_texts)
    assert not any("Main 30" in value for value in button_texts)
    assert not any("VIP 90" in value and value.startswith(f"{DIAMOND}") for value in button_texts)

async def test_buy_product_section_filters_tariffs_by_selected_channel(session: AsyncSession) -> None:
    _, main_channel = await _seed_user_channel(session)
    vip_channel = await _seed_second_channel(session)
    session.add_all(
        [
            Tariff(
                name="Main 30",
                price_stars=250,
                duration_days=30,
                sort_order=10,
                is_active=True,
                channel_id=main_channel.id,
            ),
            Tariff(
                name="VIP 90",
                price_stars=700,
                duration_days=90,
                sort_order=20,
                is_active=True,
                channel_id=vip_channel.id,
            ),
        ]
    )
    await session.commit()

    callback = DummyCallback(f"menu:user:buy:product:{vip_channel.id}")
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181], "timezone": "UTC", "crypto_pay_enabled": False})

    await buy_product_section(callback, session, settings)

    text, markup = callback.message.edit_calls[0]
    button_texts = _flatten_button_texts(markup)
    assert "📁 Продукт: VIP chat" in text
    assert any("VIP 90" in value for value in button_texts)
    assert all("Main 30" not in value for value in button_texts)
    assert BACK in button_texts[-2]


async def test_tariffs_product_section_filters_browse_list(session: AsyncSession) -> None:
    _, main_channel = await _seed_user_channel(session)
    vip_channel = await _seed_second_channel(session)
    session.add_all(
        [
            Tariff(
                name="Main 30",
                price_stars=250,
                duration_days=30,
                sort_order=10,
                is_active=True,
                channel_id=main_channel.id,
            ),
            Tariff(
                name="VIP 90",
                price_stars=700,
                duration_days=90,
                sort_order=20,
                is_active=True,
                channel_id=vip_channel.id,
            ),
        ]
    )
    await session.commit()

    callback = DummyCallback(f"menu:user:tariffs:product:{main_channel.id}")
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181], "timezone": "UTC", "crypto_pay_enabled": False})

    await tariffs_product_section(callback, session, settings)

    text, markup = callback.message.edit_calls[0]
    button_texts = _flatten_button_texts(markup)
    assert "📁 Продукт: Main channel" in text
    assert any(value.startswith(f"{DIAMOND} Main 30") for value in button_texts)
    assert all("VIP 90" not in value for value in button_texts)


async def test_archived_tariff_cannot_be_purchased(session: AsyncSession) -> None:
    _, channel = await _seed_user_channel(session)
    tariff = Tariff(
        name="Archived",
        price_stars=250,
        duration_days=30,
        sort_order=10,
        is_active=False,
        archived_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        channel_id=channel.id,
    )
    session.add(tariff)
    await session.commit()

    callback = DummyCallback(f"menu:user:buy:stars:{tariff.id}")
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181], "timezone": "UTC"})

    await buy_tariff(callback, session, settings)

    assert callback.answer_texts == ["Тариф недоступен."]
    assert callback.message.invoice_calls == []


async def test_active_old_subscription_remains_valid_after_tariff_archive(session: AsyncSession) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    user, channel = await _seed_user_channel(session)
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
    subscription = Subscription(
        user_id=user.id,
        tariff_id=tariff.id,
        channel_id=channel.id,
        status="active",
        source="purchase",
        started_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=20),
    )
    session.add(subscription)
    await session.commit()

    repository = TariffRepository(session)
    tariff = await repository.get_by_id(tariff.id)
    assert tariff is not None
    await repository.archive(tariff, archived_at=now)
    await session.commit()

    active = await SubscriptionRepository(session).list_current_for_user(user.id, at_time=now)

    assert len(active) == 1
    assert active[0].id == subscription.id
