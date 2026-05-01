# ruff: noqa: E501
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.routers.admin.audit import (
    admin_audit,
    admin_audit_detail,
    admin_audit_export,
    admin_audit_prompt_target,
    admin_audit_receive_target,
)
from app.config import Settings
from app.db.base import Base
from app.db.models import AuditLog, User
from app.db.session import create_async_engine, create_session_factory


class DummyUser:
    def __init__(self, user_id: int = 755815181, first_name: str = "Admin") -> None:
        self.id = user_id
        self.first_name = first_name
        self.username = "admin"
        self.last_name = None
        self.language_code = "ru"


class DummyMessage:
    def __init__(self, text: str | None = None, *, user_id: int = 755815181) -> None:
        self.text = text
        self.from_user = DummyUser(user_id=user_id)
        self.answer_calls: list[tuple[str, object | None]] = []
        self.photo_calls: list[tuple[object, str | None, object | None]] = []
        self.document_calls: list[tuple[object, str | None]] = []
        self.edit_calls: list[tuple[str, object | None]] = []
        self.media_calls: list[tuple[object, object | None]] = []
        self.photo = [object()]

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))

    async def answer_photo(self, photo, caption: str | None = None, reply_markup=None) -> None:
        self.photo_calls.append((photo, caption, reply_markup))

    async def answer_document(self, document, caption: str | None = None) -> None:
        self.document_calls.append((document, caption))

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edit_calls.append((text, reply_markup))

    async def edit_media(self, media, reply_markup=None) -> None:
        self.media_calls.append((media, reply_markup))


class DummyCallback:
    def __init__(self, data: str, *, user_id: int = 755815181) -> None:
        self.data = data
        self.message = DummyMessage(user_id=user_id)
        self.from_user = DummyUser(user_id=user_id)
        self.answer_calls: list[tuple[str | None, bool]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answer_calls.append((text, show_alert))


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


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        admin = User(
            telegram_id=755815181,
            first_name="Admin",
            username="admin",
            is_admin=True,
            role="owner",
        )
        user = User(telegram_id=1001, first_name="Руслан", username="ruslan", role="user")
        db_session.add_all([admin, user])
        await db_session.flush()
        now = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)
        db_session.add_all(
            [
                AuditLog(
                    action="payment_paid_stars",
                    actor_user_id=user.id,
                    target_user_id=user.id,
                    payload='{"tariff_id": 1}',
                    created_at=now - timedelta(hours=2),
                ),
                AuditLog(
                    action="admin_direct_message",
                    actor_user_id=admin.id,
                    target_user_id=user.id,
                    payload='{"text": "скрытый текст", "invite_link": "https://t.me/+PrivateInvite"}',
                    created_at=now - timedelta(hours=1),
                ),
            ]
        )
        await db_session.commit()
        yield db_session

    await engine.dispose()


@pytest_asyncio.fixture
async def settings() -> Settings:
    return Settings.model_validate(
        {"bot_token": "123:token", "admin_ids": [755815181], "timezone": "UTC"}
    )


def _flatten_button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


async def test_admin_audit_command_renders_banner(session: AsyncSession, settings: Settings) -> None:
    message = DummyMessage("/admin_audit")
    state = FakeState()

    await admin_audit(message, session, settings, state)

    assert message.photo_calls
    _, caption, markup = message.photo_calls[0]
    assert "Аудит действий" in caption
    assert "📤 CSV" in _flatten_button_texts(markup)


async def test_admin_audit_target_filter_and_export(session: AsyncSession, settings: Settings) -> None:
    state = FakeState()
    start_message = DummyMessage("/admin_audit")
    await admin_audit(start_message, session, settings, state)

    prompt_callback = DummyCallback("menu:admin:audit:prompt:target")
    await admin_audit_prompt_target(prompt_callback, state)
    assert state.state_name is not None
    assert prompt_callback.message.answer_calls

    filter_message = DummyMessage("1001")
    await admin_audit_receive_target(filter_message, session, settings, state)
    assert filter_message.answer_calls
    overview_text, _ = filter_message.answer_calls[-1]
    assert "Руслан" in overview_text
    assert "Цель:" in overview_text

    export_callback = DummyCallback("menu:admin:audit:export")
    await admin_audit_export(export_callback, session, settings, state)
    assert export_callback.message.document_calls
    document, caption = export_callback.message.document_calls[0]
    csv_text = document.data.decode("utf-8")
    assert document.filename.startswith("audit-report-")
    assert "скрытый текст" not in csv_text
    assert "https://t.me/+PrivateInvite" not in csv_text
    assert "[REDACTED]" in csv_text
    assert caption is not None and caption.startswith("CSV аудита")


async def test_admin_audit_detail_links_to_user_profile(session: AsyncSession, settings: Settings) -> None:
    callback = DummyCallback("menu:admin:audit:view:2")

    await admin_audit_detail(callback, session, settings)

    assert callback.message.media_calls
    media, markup = callback.message.media_calls[0]
    assert "Событие аудита #2" in media.caption
    buttons = _flatten_button_texts(markup)
    assert "👤 Профиль цели" in buttons
    assert "🛡 Профиль актора" in buttons


async def test_admin_audit_filter_rejects_non_admin() -> None:
    event = type("Event", (), {"from_user": DummyUser(user_id=1)})()
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181]})

    result = await AdminFilter()(event, settings)

    assert result is False
