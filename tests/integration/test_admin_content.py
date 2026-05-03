from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.routers.admin.content import admin_content, content_detail, start_content_edit
from app.bot.routers.admin.texts import receive_text_value
from app.bot.states.admin import AdminTextEditor
from app.config import Settings
from app.db.base import Base
from app.db.models import TextTemplate, User
from app.db.session import create_async_engine, create_session_factory
from app.services.admin_roles import PERMISSION_TEXTS
from app.services.texts import ensure_default_text_templates


class DummyUser:
    def __init__(self, user_id: int = 755815181, first_name: str = 'Admin') -> None:
        self.id = user_id
        self.first_name = first_name
        self.username = 'admin'
        self.last_name = None
        self.language_code = 'ru'


class DummyMessage:
    def __init__(self, text: str | None = None) -> None:
        self.text = text
        self.from_user = DummyUser()
        self.answer_calls: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))


class DummyCallbackMessage:
    def __init__(self) -> None:
        self.edit_calls: list[tuple[str, object | None]] = []
        self.answer_calls: list[tuple[str, object | None]] = []

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edit_calls.append((text, reply_markup))

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))


class DummyCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = DummyCallbackMessage()
        self.from_user = DummyUser()
        self.answer_count = 0

    async def answer(self, *args, **kwargs) -> None:
        self.answer_count += 1


class FakeState:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}
        self.state_name = None

    async def clear(self) -> None:
        self.data.clear()
        self.state_name = None

    async def set_state(self, state) -> None:
        self.state_name = state

    async def update_data(self, **kwargs) -> None:
        self.data.update(kwargs)

    async def get_data(self) -> dict[str, object]:
        return dict(self.data)


def _flatten_button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        db_session.add(User(telegram_id=755815181, first_name='Admin', is_admin=True, role='owner'))
        await db_session.commit()
        yield db_session

    await engine.dispose()


async def test_admin_content_command_renders_sections(session: AsyncSession) -> None:
    await ensure_default_text_templates(session)
    await session.commit()
    message = DummyMessage()

    await admin_content(message, session)

    assert message.answer_calls
    text, markup = message.answer_calls[0]
    assert 'Content / FAQ CMS' in text
    assert 'FAQ' in text
    assert 'Оферта' in text
    assert '🟢 FAQ' in _flatten_button_texts(markup)


async def test_admin_content_detail_and_edit_flow(session: AsyncSession) -> None:
    await ensure_default_text_templates(session)
    await session.commit()
    callback = DummyCallback('menu:admin:content:view:faq')

    await content_detail(callback, session)

    assert callback.message.edit_calls
    text, markup = callback.message.edit_calls[0]
    assert 'Key: <code>faq</code>' in text
    assert _flatten_button_texts(markup) == [
        '✏️ Редактировать материал',
        '🧾 Открыть шаблон',
        '⬅️ Назад',
        '🏠 Админ-панель',
    ]

    state = FakeState()
    edit_callback = DummyCallback('menu:admin:content:edit:faq')
    await start_content_edit(edit_callback, session, state)
    assert state.state_name == AdminTextEditor.waiting_for_value
    assert state.data['text_template_key'] == 'faq'
    assert state.data['text_template_origin_slug'] == 'faq'

    message = DummyMessage(text='Новый FAQ для пользователей')
    await receive_text_value(message, state, session)

    updated = await session.scalar(select(TextTemplate).where(TextTemplate.key == 'faq'))
    assert updated is not None
    assert updated.body == 'Новый FAQ для пользователей'
    assert 'Шаблон обновлён' in message.answer_calls[0][0]
    assert _flatten_button_texts(message.answer_calls[0][1]) == [
        '✏️ Редактировать материал',
        '🧾 Открыть шаблон',
        '⬅️ Назад',
        '🏠 Админ-панель',
    ]


async def test_admin_content_filter_rejects_non_admin() -> None:
    event = type('Event', (), {'from_user': DummyUser(user_id=1)})()
    settings = Settings.model_validate({'bot_token': '123:token', 'admin_ids': [755815181]})

    result = await AdminFilter(PERMISSION_TEXTS)(event, settings)

    assert result is False
