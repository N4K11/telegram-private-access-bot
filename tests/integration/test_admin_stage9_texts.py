from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.routers.admin.texts import receive_text_value, reset_text, start_text_edit
from app.bot.states.admin import AdminTextEditor
from app.db.base import Base
from app.db.models import TextTemplate, User
from app.db.session import create_async_engine, create_session_factory
from app.services.texts import (
    DEFAULT_TEXT_TEMPLATES,
    ensure_default_text_templates,
    get_text_template_record,
    render_text,
)


class DummyUser:
    def __init__(self, user_id: int = 755815181, first_name: str = "Admin") -> None:
        self.id = user_id
        self.first_name = first_name
        self.username = "admin"
        self.last_name = None
        self.language_code = "ru"


class DummyMessage:
    def __init__(self, text: str | None = None) -> None:
        self.text = text
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
        self.answer_payloads: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args, **kwargs) -> None:
        self.answer_count += 1
        self.answer_payloads.append((args, kwargs))


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


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        db_session.add(
            User(
                telegram_id=755815181,
                first_name="Admin",
                is_admin=True,
                role="owner",
            )
        )
        await db_session.commit()
        yield db_session

    await engine.dispose()


async def test_stage9_default_templates_seed_and_render_clean(
    session: AsyncSession,
) -> None:
    created = await ensure_default_text_templates(session)
    await session.commit()

    templates = list((await session.execute(select(TextTemplate))).scalars())
    keys = {template.key for template in templates}

    assert created == len(DEFAULT_TEXT_TEMPLATES)
    assert {"start", "profile", "tariffs", "payment_success", "support"}.issubset(keys)
    assert all("Рџ" not in template.body for template in templates)
    assert all("Ð" not in template.body for template in templates)
    assert all("Ñ" not in template.body for template in templates)
    assert all("�" not in template.body for template in templates)

    rendered = await render_text(session, "start", first_name="Анна")
    assert rendered.startswith("Здравствуйте, Анна.")


async def test_render_text_falls_back_when_custom_template_is_invalid(
    session: AsyncSession,
) -> None:
    await ensure_default_text_templates(session)
    template = await get_text_template_record(session, "start")
    assert template is not None

    template.body = "Привет, {first_name"
    await session.commit()

    rendered = await render_text(session, "start", first_name="Анна")
    assert rendered.startswith("Здравствуйте, Анна.")

    template.body = "Привет, {first_name}! {missing_placeholder}"
    await session.commit()

    rendered_with_missing = await render_text(session, "start", first_name="Анна")
    assert rendered_with_missing == "Привет, Анна! {missing_placeholder}"


async def test_admin_text_editor_updates_and_resets_template(
    session: AsyncSession,
) -> None:
    await ensure_default_text_templates(session)
    await session.commit()

    state = FakeState()
    callback = DummyCallback("menu:admin:texts:edit:support")
    await start_text_edit(callback, session, state)

    assert state.state_name == AdminTextEditor.waiting_for_value

    message = DummyMessage(text="Новая поддержка для {first_name}")
    await receive_text_value(message, state, session)

    updated = await session.scalar(select(TextTemplate).where(TextTemplate.key == "support"))
    assert updated is not None
    assert updated.body == "Новая поддержка для {first_name}"
    assert "Шаблон обновлён" in message.answer_calls[0][0]

    reset_callback = DummyCallback("menu:admin:texts:reset:support")
    await reset_text(reset_callback, session)

    reset_template = await session.scalar(select(TextTemplate).where(TextTemplate.key == "support"))
    assert reset_template is not None
    assert reset_template.body == DEFAULT_TEXT_TEMPLATES["support"].body


async def test_admin_text_editor_rejects_mojibake_input(
    session: AsyncSession,
) -> None:
    await ensure_default_text_templates(session)
    await session.commit()

    state = FakeState()
    await state.set_state(AdminTextEditor.waiting_for_value)
    await state.update_data(text_template_key="support")

    message = DummyMessage(text="ÐŸÐ¾Ð»Ð¾Ð¼Ð°Ð½Ð½Ñ‹Ð¹ Ñ‚ÐµÐºÑÑ‚")
    await receive_text_value(message, state, session)

    template = await session.scalar(select(TextTemplate).where(TextTemplate.key == "support"))
    assert template is not None
    assert template.body == DEFAULT_TEXT_TEMPLATES["support"].body
    assert "кракозябры" in message.answer_calls[0][0]