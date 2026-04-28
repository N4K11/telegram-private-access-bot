from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.routers.admin.channels import channel_detail, channels_index
from app.bot.routers.admin.tariffs import tariff_detail, tariffs_index
from app.db.base import Base
from app.db.models import Channel, Tariff
from app.db.session import create_async_engine, create_session_factory


class DummyUser:
    def __init__(self, user_id: int = 755815181, first_name: str = "Admin") -> None:
        self.id = user_id
        self.first_name = first_name


class DummyMessage:
    def __init__(self) -> None:
        self.answer_calls: list[tuple[str, object | None]] = []
        self.edit_calls: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edit_calls.append((text, reply_markup))


class DummyCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = DummyMessage()
        self.from_user = DummyUser()
        self.answer_count = 0
        self.answer_payloads: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args, **kwargs) -> None:
        self.answer_count += 1
        self.answer_payloads.append((args, kwargs))



def _flatten_button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


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
async def seeded_records(session: AsyncSession) -> tuple[Channel, Tariff]:
    channel = Channel(
        telegram_chat_id=-1001234567890,
        title="Основной канал",
        username="demo_channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add(channel)
    await session.flush()

    tariff = Tariff(
        name="VIP 30",
        price_stars=150,
        duration_days=30,
        sort_order=10,
        is_active=True,
        channel_id=channel.id,
    )
    session.add(tariff)
    await session.commit()
    return channel, tariff


async def test_channels_index_renders_existing_channel(
    session: AsyncSession,
    seeded_records: tuple[Channel, Tariff],
) -> None:
    callback = DummyCallback("menu:admin:channels")

    await channels_index(callback, session)

    text, markup = callback.message.edit_calls[0]
    assert "Каналы" in text
    assert "Основной канал" in text
    assert _flatten_button_texts(markup) == [
        "✅ Основной канал",
        "➕ Добавить канал",
        "Главное меню",
    ]


async def test_channel_detail_renders_actions(
    session: AsyncSession,
    seeded_records: tuple[Channel, Tariff],
) -> None:
    channel, _ = seeded_records
    callback = DummyCallback(f"menu:admin:channels:view:{channel.id}")

    await channel_detail(callback, session)

    text, markup = callback.message.edit_calls[0]
    assert f"Канал #{channel.id}" in text
    assert _flatten_button_texts(markup) == [
        "✏️ Переименовать",
        "⏸ Выключить",
        "🔄 Обновить проверку",
        "Назад",
        "Главное меню",
    ]


async def test_tariffs_index_renders_existing_tariff(
    session: AsyncSession,
    seeded_records: tuple[Channel, Tariff],
) -> None:
    callback = DummyCallback("menu:admin:tariffs")

    await tariffs_index(callback, session)

    text, markup = callback.message.edit_calls[0]
    assert "Тарифы" in text
    assert "VIP 30" in text
    assert _flatten_button_texts(markup) == [
        "✅ VIP 30",
        "➕ Создать тариф",
        "Главное меню",
    ]


async def test_tariff_detail_renders_actions(
    session: AsyncSession,
    seeded_records: tuple[Channel, Tariff],
) -> None:
    _, tariff = seeded_records
    callback = DummyCallback(f"menu:admin:tariffs:view:{tariff.id}")

    await tariff_detail(callback, session)

    text, markup = callback.message.edit_calls[0]
    assert f"Тариф #{tariff.id}" in text
    assert _flatten_button_texts(markup) == [
        "✏️ Изменить название",
        "💳 Изменить цену",
        "📅 Изменить длительность",
        "📣 Сменить канал",
        "↕️ Изменить сортировку",
        "⏸ Выключить",
        "🗄 Архивировать",
        "Назад",
        "Главное меню",
    ]