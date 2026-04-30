from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.routers.admin.diagnostics import admin_channel_check, diagnostics_dashboard
from app.db.base import Base
from app.db.models import Channel
from app.db.session import create_async_engine, create_session_factory


class DummyUser:
    def __init__(self, user_id: int = 755815181, first_name: str = "Admin") -> None:
        self.id = user_id
        self.first_name = first_name


class DummyMessage:
    def __init__(self) -> None:
        self.from_user = DummyUser()
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

    async def answer(self, *args, **kwargs) -> None:
        self.answer_count += 1


class FakeBot:
    async def get_me(self):
        return SimpleNamespace(id=500, username="diag_bot")

    async def get_chat(self, reference):
        return SimpleNamespace(id=-1001234567890, title="Основной канал", username="main_channel")

    async def get_chat_member(self, chat_id, user_id):
        return SimpleNamespace(
            status="administrator",
            can_invite_users=True,
            can_restrict_members=True,
            can_manage_chat=True,
        )


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


async def test_admin_channel_check_command_renders_report(session: AsyncSession) -> None:
    session.add(
        Channel(
            telegram_chat_id=-1001234567890,
            title="Основной канал",
            username="main_channel",
            invite_users_permission=True,
            ban_users_permission=True,
            is_active=True,
        )
    )
    await session.commit()

    message = DummyMessage()
    await admin_channel_check(message, session, FakeBot())

    assert message.answer_calls
    text, markup = message.answer_calls[0]
    assert "🧪 Проверка каналов" in text
    assert "✅ Бот подключен: @diag_bot" in text
    assert "Основной канал" in text
    assert _flatten_button_texts(markup) == ["⬅️ Назад", "🏠 Админ-панель"]


async def test_diagnostics_dashboard_callback_renders_report(session: AsyncSession) -> None:
    session.add(
        Channel(
            telegram_chat_id=-1001234567890,
            title="Основной канал",
            username="main_channel",
            invite_users_permission=True,
            ban_users_permission=True,
            is_active=True,
        )
    )
    await session.commit()

    callback = DummyCallback("menu:admin:diagnostics")
    await diagnostics_dashboard(callback, session, FakeBot())

    assert callback.message.edit_calls
    text, markup = callback.message.edit_calls[0]
    assert "🧪 Проверка каналов" in text
    assert "Итог: всё готово." in text
    assert _flatten_button_texts(markup) == ["⬅️ Назад", "🏠 Админ-панель"]
    assert callback.answer_count == 1


async def test_admin_channel_check_handles_empty_configuration(session: AsyncSession) -> None:
    message = DummyMessage()

    await admin_channel_check(message, session, FakeBot())

    assert message.answer_calls
    text, _ = message.answer_calls[0]
    assert "Каналы ещё не добавлены." in text
