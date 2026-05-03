# ruff: noqa: E501
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
    has_mojibake,
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


def _to_mojibake(value: str) -> str:
    return value.encode("utf-8").decode("cp1251")


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
    assert {"start", "profile", "tariffs", "payment_success", "support", "payment_support", "terms", "privacy", "refund_policy", "faq", "channel_rules", "after_payment_guide", "crypto_payment_guide", "offer"}.issubset(keys)
    assert all(not has_mojibake(template.title) for template in templates)
    assert all(not has_mojibake(template.body) for template in templates)

    rendered = await render_text(session, "start", first_name="\u0410\u043d\u043d\u0430")
    assert rendered.startswith("\U0001f44b \u041f\u0440\u0438\u0432\u0435\u0442, \u0410\u043d\u043d\u0430!")


async def test_render_text_falls_back_when_custom_template_is_invalid(
    session: AsyncSession,
) -> None:
    await ensure_default_text_templates(session)
    template = await get_text_template_record(session, "start")
    assert template is not None

    template.body = "\u041f\u0440\u0438\u0432\u0435\u0442, {first_name"
    await session.commit()

    rendered = await render_text(session, "start", first_name="\u0410\u043d\u043d\u0430")
    assert rendered.startswith("\U0001f44b \u041f\u0440\u0438\u0432\u0435\u0442, \u0410\u043d\u043d\u0430!")

    template.body = "\u041f\u0440\u0438\u0432\u0435\u0442, {first_name}! {missing_placeholder}"
    await session.commit()

    rendered_with_missing = await render_text(session, "start", first_name="\u0410\u043d\u043d\u0430")
    assert rendered_with_missing == "\u041f\u0440\u0438\u0432\u0435\u0442, \u0410\u043d\u043d\u0430! {missing_placeholder}"


async def test_admin_text_editor_updates_and_resets_template(
    session: AsyncSession,
) -> None:
    await ensure_default_text_templates(session)
    await session.commit()

    state = FakeState()
    callback = DummyCallback("menu:admin:texts:edit:terms")
    await start_text_edit(callback, session, state)

    assert state.state_name == AdminTextEditor.waiting_for_value

    message = DummyMessage(text="\u041d\u043e\u0432\u044b\u0435 \u0443\u0441\u043b\u043e\u0432\u0438\u044f \u0434\u043b\u044f {first_name}")
    await receive_text_value(message, state, session)

    updated = await session.scalar(select(TextTemplate).where(TextTemplate.key == "terms"))
    assert updated is not None
    assert updated.body == "\u041d\u043e\u0432\u044b\u0435 \u0443\u0441\u043b\u043e\u0432\u0438\u044f \u0434\u043b\u044f {first_name}"
    assert "\u0428\u0430\u0431\u043b\u043e\u043d \u043e\u0431\u043d\u043e\u0432\u043b\u0451\u043d" in message.answer_calls[0][0]

    reset_callback = DummyCallback("menu:admin:texts:reset:terms")
    await reset_text(reset_callback, session)

    reset_template = await session.scalar(select(TextTemplate).where(TextTemplate.key == "terms"))
    assert reset_template is not None
    assert reset_template.body == DEFAULT_TEXT_TEMPLATES["terms"].body


async def test_admin_text_editor_rejects_mojibake_input(
    session: AsyncSession,
) -> None:
    await ensure_default_text_templates(session)
    await session.commit()

    state = FakeState()
    await state.set_state(AdminTextEditor.waiting_for_value)
    await state.update_data(text_template_key="support")

    message = DummyMessage(text=_to_mojibake("\u041f\u043e\u043b\u043e\u043c\u0430\u043d\u043d\u044b\u0439 \u0442\u0435\u043a\u0441\u0442"))
    await receive_text_value(message, state, session)

    template = await session.scalar(select(TextTemplate).where(TextTemplate.key == "support"))
    assert template is not None
    assert template.body == DEFAULT_TEXT_TEMPLATES["support"].body
    assert "\u043a\u0440\u0430\u043a\u043e\u0437\u044f\u0431\u0440\u044b" in message.answer_calls[0][0]
