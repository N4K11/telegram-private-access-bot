# ruff: noqa: E501
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
        title="\u041e\u0441\u043d\u043e\u0432\u043d\u043e\u0439 \u043a\u0430\u043d\u0430\u043b",
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
    assert "\u041a\u0430\u043d\u0430\u043b\u044b" in text
    assert "\u041e\u0441\u043d\u043e\u0432\u043d\u043e\u0439 \u043a\u0430\u043d\u0430\u043b" in text
    assert _flatten_button_texts(markup) == [
        "\u2705 \u041e\u0441\u043d\u043e\u0432\u043d\u043e\u0439 \u043a\u0430\u043d\u0430\u043b",
        "\u2795 \u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043a\u0430\u043d\u0430\u043b",
        "\U0001f3e0 \u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c",
    ]


async def test_channel_detail_renders_actions(
    session: AsyncSession,
    seeded_records: tuple[Channel, Tariff],
) -> None:
    channel, _ = seeded_records
    callback = DummyCallback(f"menu:admin:channels:view:{channel.id}")

    await channel_detail(callback, session)

    text, markup = callback.message.edit_calls[0]
    assert f"\u041a\u0430\u043d\u0430\u043b #{channel.id}" in text
    assert _flatten_button_texts(markup) == [
        "\u270f\ufe0f \u041f\u0435\u0440\u0435\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u0442\u044c",
        "\u23f8 \u0412\u044b\u043a\u043b\u044e\u0447\u0438\u0442\u044c",
        "\U0001f504 \u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443",
        "\u2b05\ufe0f \u041d\u0430\u0437\u0430\u0434",
        "\U0001f3e0 \u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c",
    ]


async def test_tariffs_index_renders_existing_tariff(
    session: AsyncSession,
    seeded_records: tuple[Channel, Tariff],
) -> None:
    callback = DummyCallback("menu:admin:tariffs")

    await tariffs_index(callback, session)

    text, markup = callback.message.edit_calls[0]
    assert "\u0422\u0430\u0440\u0438\u0444\u044b" in text
    assert "VIP 30" in text
    assert _flatten_button_texts(markup) == [
        "\u2705 VIP 30",
        "\u2795 \u0421\u043e\u0437\u0434\u0430\u0442\u044c \u0442\u0430\u0440\u0438\u0444",
        "\U0001f3e0 \u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c",
    ]


async def test_tariff_detail_renders_actions(
    session: AsyncSession,
    seeded_records: tuple[Channel, Tariff],
) -> None:
    _, tariff = seeded_records
    callback = DummyCallback(f"menu:admin:tariffs:view:{tariff.id}")

    await tariff_detail(callback, session)

    text, markup = callback.message.edit_calls[0]
    assert f"\u0422\u0430\u0440\u0438\u0444 #{tariff.id}" in text
    assert _flatten_button_texts(markup) == [
        "\u270f\ufe0f \u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435",
        "\U0001f4b3 \u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0446\u0435\u043d\u0443",
        "\U0001f4c5 \u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0434\u043b\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u0441\u0442\u044c",
        "\U0001f4e3 \u0421\u043c\u0435\u043d\u0438\u0442\u044c \u043a\u0430\u043d\u0430\u043b",
        "\u2195\ufe0f \u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0441\u043e\u0440\u0442\u0438\u0440\u043e\u0432\u043a\u0443",
        "\u23f8 \u0412\u044b\u043a\u043b\u044e\u0447\u0438\u0442\u044c",
        "\U0001f5c4 \u0410\u0440\u0445\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u0442\u044c",
        "\u2b05\ufe0f \u041d\u0430\u0437\u0430\u0434",
        "\U0001f3e0 \u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c",
    ]
