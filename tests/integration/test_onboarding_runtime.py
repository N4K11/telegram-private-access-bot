from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.routers.user.payments import buy_section
from app.bot.routers.user.start import onboarding_next, onboarding_skip, start_handler
from app.config import Settings
from app.db.base import Base
from app.db.models import AuditLog, Channel, Tariff, User
from app.db.repositories.users import UserRepository
from app.db.session import create_async_engine, create_session_factory


class DummyUser:
    def __init__(self, user_id: int, *, first_name: str, username: str | None = None) -> None:
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
        self.date = datetime(2026, 5, 2, 12, 0, tzinfo=UTC)

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))

    async def answer_photo(self, photo, caption: str | None = None, reply_markup=None) -> None:
        self.photo_calls.append((photo, caption, reply_markup))


class DummyCallbackMessage:
    def __init__(self) -> None:
        self.photo = None
        self.date = datetime(2026, 5, 2, 12, 5, tzinfo=UTC)
        self.edit_text_calls: list[tuple[str, object | None]] = []
        self.answer_calls: list[tuple[str, object | None]] = []

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edit_text_calls.append((text, reply_markup))

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))


class DummyCallback:
    def __init__(self, data: str, *, user_id: int, first_name: str) -> None:
        self.data = data
        self.from_user = DummyUser(user_id, first_name=first_name, username="ruslan")
        self.message = DummyCallbackMessage()
        self.answer_calls: list[tuple[str | None, bool]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answer_calls.append((text, show_alert))


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


@pytest_asyncio.fixture
async def settings() -> Settings:
    return Settings.model_validate(
        {"bot_token": "123:token", "admin_ids": [755815181], "timezone": "UTC"}
    )


def _flatten_button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


async def _seed_tariff(
    session: AsyncSession,
    *,
    channel_title: str = "Main channel",
    price_stars: int = 250,
    duration_days: int = 30,
) -> Channel:
    channel = Channel(
        telegram_chat_id=-1001234567000 - price_stars,
        title=channel_title,
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add(channel)
    await session.flush()
    session.add(
        Tariff(
            name=f"{channel_title} {duration_days}",
            price_stars=price_stars,
            duration_days=duration_days,
            sort_order=10,
            is_active=True,
            channel_id=channel.id,
        )
    )
    await session.commit()
    return channel


async def test_start_handler_shows_onboarding_to_new_user(
    session: AsyncSession,
    settings: Settings,
) -> None:
    message = DummyMessage("/start", user_id=2001, first_name="Р СѓСЃР»Р°РЅ", username="ruslan")

    await start_handler(message, session, settings)

    assert len(message.photo_calls) == 1
    _, caption, markup = message.photo_calls[0]
    assert caption is not None
    assert "Шаг 1/3" in caption
    assert _flatten_button_texts(markup) == ["➡️ Дальше", "⏭ Пропустить"]


async def test_onboarding_next_persists_progress(
    session: AsyncSession,
    settings: Settings,
) -> None:
    await start_handler(
        DummyMessage("/start", user_id=2002, first_name="Р СѓСЃР»Р°РЅ", username="ruslan"),
        session,
        settings,
    )
    callback = DummyCallback("menu:user:onboarding:next", user_id=2002, first_name="Р СѓСЃР»Р°РЅ")

    await onboarding_next(callback, session, settings)

    assert len(callback.message.edit_text_calls) == 1
    text, _ = callback.message.edit_text_calls[0]
    assert "Шаг 2/3" in text
    user = await UserRepository(session).get_by_telegram_id(2002)
    assert user is not None
    assert user.onboarding_step == 1
    assert callback.answer_calls == [(None, False)]


async def test_onboarding_skip_stops_repeat_on_future_start(
    session: AsyncSession,
    settings: Settings,
) -> None:
    await start_handler(
        DummyMessage("/start", user_id=2003, first_name="Р СѓСЃР»Р°РЅ", username="ruslan"),
        session,
        settings,
    )
    callback = DummyCallback("menu:user:onboarding:skip", user_id=2003, first_name="Р СѓСЃР»Р°РЅ")

    await onboarding_skip(callback, session, settings)

    assert len(callback.message.edit_text_calls) == 1
    text, _ = callback.message.edit_text_calls[0]
    assert "Шаг 1/3" not in text
    user = await UserRepository(session).get_by_telegram_id(2003)
    assert user is not None
    assert user.onboarding_completed_at is not None

    follow_up = DummyMessage("/start", user_id=2003, first_name="Р СѓСЃР»Р°РЅ", username="ruslan")
    await start_handler(follow_up, session, settings)

    assert len(follow_up.photo_calls) == 1
    _, follow_up_caption, _ = follow_up.photo_calls[0]
    assert follow_up_caption is not None
    assert "Шаг 1/3" not in follow_up_caption


async def test_completed_existing_user_does_not_see_onboarding(
    session: AsyncSession,
    settings: Settings,
) -> None:
    user = User(
        telegram_id=2004,
        first_name="Старый",
        username="old",
        role="user",
        onboarding_completed_at=datetime(2026, 5, 1, 9, 0, tzinfo=UTC),
    )
    session.add(user)
    await session.commit()

    message = DummyMessage("/start", user_id=2004, first_name="Старый", username="old")
    await start_handler(message, session, settings)

    assert len(message.photo_calls) == 1
    _, caption, _ = message.photo_calls[0]
    assert caption is not None
    assert "Шаг 1/3" not in caption


async def test_start_buy_deep_link_bypasses_onboarding(
    session: AsyncSession,
    settings: Settings,
) -> None:
    await _seed_tariff(session)

    message = DummyMessage("/start buy", user_id=2005, first_name="Р СѓСЃР»Р°РЅ", username="ruslan")
    await start_handler(message, session, settings)

    assert len(message.photo_calls) == 1
    _, caption, markup = message.photo_calls[0]
    assert caption is not None
    assert "Шаг 1/3" not in caption
    assert "Купить" in caption
    assert any("Купить" in text for text in _flatten_button_texts(markup))


async def test_start_buy_product_deep_link_renders_selected_product(
    session: AsyncSession,
    settings: Settings,
) -> None:
    await _seed_tariff(session, channel_title="Main channel", price_stars=250, duration_days=30)
    vip_channel = await _seed_tariff(
        session,
        channel_title="VIP chat",
        price_stars=700,
        duration_days=90,
    )

    message = DummyMessage(
        f"/start buy_{vip_channel.id}",
        user_id=2006,
        first_name="Р СѓСЃР»Р°РЅ",
        username="ruslan",
    )
    await start_handler(message, session, settings)

    assert len(message.photo_calls) == 1
    _, caption, _ = message.photo_calls[0]
    assert caption is not None
    assert "Шаг 1/3" not in caption
    assert "VIP chat" in caption

async def test_onboarding_buy_entrypoint_is_tracked_with_onboarding_source(
    session: AsyncSession,
    settings: Settings,
) -> None:
    await _seed_tariff(session)
    await start_handler(
        DummyMessage("/start", user_id=2010, first_name="Руслан", username="ruslan"),
        session,
        settings,
    )
    callback = DummyCallback("menu:user:buy", user_id=2010, first_name="Руслан")

    await buy_section(callback, session, settings)

    result = await session.execute(
        select(AuditLog.payload)
        .where(AuditLog.action == "buy_screen_viewed")
        .order_by(AuditLog.id.desc())
        .limit(1)
    )
    payload = result.scalar_one()
    assert payload is not None
    assert '"source": "onboarding"' in payload

