from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.routers.admin.support import (
    admin_support_close,
    admin_support_receive_reply,
    admin_support_reopen,
    admin_support_reply_prompt,
)
from app.bot.routers.user.support import (
    choose_support_category,
    receive_support_message,
    show_user_ticket,
)
from app.config import Settings
from app.db.base import Base
from app.db.models import AuditLog, SupportMessage, SupportTicket, User
from app.db.session import create_async_engine, create_session_factory
from app.services.support import (
    SUPPORT_CATEGORY_PAYMENT,
    close_support_ticket,
    create_support_ticket,
)


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
        self.date = datetime(2026, 5, 2, 12, 0, tzinfo=UTC)

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))


class DummyCallbackMessage:
    def __init__(self) -> None:
        self.photo = [object()]
        self.edit_text_calls: list[tuple[str, object | None]] = []
        self.media_calls: list[tuple[object, object | None]] = []
        self.answer_calls: list[tuple[str, object | None]] = []

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edit_text_calls.append((text, reply_markup))

    async def edit_media(self, media, reply_markup=None) -> None:
        self.media_calls.append((media, reply_markup))

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))


class DummyCallback:
    def __init__(
        self,
        data: str,
        *,
        user_id: int,
        first_name: str,
        username: str | None = None,
    ) -> None:
        self.data = data
        self.from_user = DummyUser(user_id, first_name=first_name, username=username)
        self.message = DummyCallbackMessage()
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


class FakeBot:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent_messages.append((chat_id, text))


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
def settings() -> Settings:
    return Settings.model_validate(
        {"bot_token": "123:token", "admin_ids": [755815181], "timezone": "UTC"}
    )


async def _seed_users(session: AsyncSession) -> tuple[User, User]:
    user = User(telegram_id=1001, first_name="Руслан", username="ruslan", role="user")
    admin = User(
        telegram_id=755815181,
        first_name="Admin",
        username="admin",
        is_admin=True,
        role="owner",
    )
    session.add_all([user, admin])
    await session.commit()
    return user, admin


async def test_user_ticket_creation_flow_notifies_admin(
    session: AsyncSession,
    settings: Settings,
) -> None:
    user, _ = await _seed_users(session)
    state = FakeState()
    category_callback = DummyCallback(
        "menu:user:support:category:payment",
        user_id=user.telegram_id,
        first_name="Руслан",
        username="ruslan",
    )
    await choose_support_category(category_callback, state)

    bot = FakeBot()
    message = DummyMessage(
        "Платеж прошел, ссылки нет",
        user_id=user.telegram_id,
        first_name="Руслан",
        username="ruslan",
    )

    await receive_support_message(message, state, session, bot, settings)

    tickets = list((await session.execute(select(SupportTicket))).scalars())
    audits = list((await session.execute(select(AuditLog))).scalars())

    assert len(tickets) == 1
    assert tickets[0].category == SUPPORT_CATEGORY_PAYMENT
    assert message.answer_calls
    assert "Обращение создано" in message.answer_calls[-1][0]
    assert bot.sent_messages and bot.sent_messages[0][0] == 755815181
    assert any(log.action == "support_ticket_created" for log in audits)


async def test_admin_reply_flow_sends_message_to_user(
    session: AsyncSession,
    settings: Settings,
) -> None:
    user, admin = await _seed_users(session)
    thread = await create_support_ticket(
        session,
        user_id=user.id,
        category=SUPPORT_CATEGORY_PAYMENT,
        body="Нужна помощь по оплате",
        now=datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
    )
    await session.commit()

    state = FakeState()
    callback = DummyCallback(
        f"menu:admin:support:reply:{thread.ticket.id}:open",
        user_id=admin.telegram_id,
        first_name="Admin",
        username="admin",
    )
    await admin_support_reply_prompt(callback, session, state)

    bot = FakeBot()
    message = DummyMessage(
        "Проблему проверили, доступ уже активирован.",
        user_id=admin.telegram_id,
        first_name="Admin",
        username="admin",
    )
    message.date = datetime(2026, 5, 2, 12, 10, tzinfo=UTC)

    await admin_support_receive_reply(message, state, session, settings, bot)

    messages = list((await session.execute(select(SupportMessage))).scalars())
    assert len(messages) == 2
    assert messages[-1].is_admin is True
    assert message.answer_calls
    assert "Ответ отправлен пользователю" in message.answer_calls[-1][0]
    assert bot.sent_messages and bot.sent_messages[0][0] == user.telegram_id


async def test_admin_can_close_and_reopen_ticket(
    session: AsyncSession,
    settings: Settings,
) -> None:
    user, admin = await _seed_users(session)
    thread = await create_support_ticket(
        session,
        user_id=user.id,
        category=SUPPORT_CATEGORY_PAYMENT,
        body="Надо закрыть тикет",
        now=datetime(2026, 5, 2, 13, 0, tzinfo=UTC),
    )
    await session.commit()

    close_callback = DummyCallback(
        f"menu:admin:support:close:{thread.ticket.id}:open",
        user_id=admin.telegram_id,
        first_name="Admin",
        username="admin",
    )
    await admin_support_close(close_callback, session, settings)
    closed_status = (await session.get(SupportTicket, thread.ticket.id)).status

    reopen_callback = DummyCallback(
        f"menu:admin:support:reopen:{thread.ticket.id}:closed",
        user_id=admin.telegram_id,
        first_name="Admin",
        username="admin",
    )
    await admin_support_reopen(reopen_callback, session, settings)
    reopened = await session.get(SupportTicket, thread.ticket.id)

    assert closed_status == "closed"
    assert reopened is not None and reopened.status == "open"


async def test_other_user_cannot_view_foreign_ticket(
    session: AsyncSession,
    settings: Settings,
) -> None:
    user, _ = await _seed_users(session)
    other = User(telegram_id=2002, first_name="Другой", role="user")
    session.add(other)
    await session.commit()

    thread = await create_support_ticket(
        session,
        user_id=user.id,
        category=SUPPORT_CATEGORY_PAYMENT,
        body="Чужой тикет",
        now=datetime(2026, 5, 2, 14, 0, tzinfo=UTC),
    )
    await session.commit()

    callback = DummyCallback(
        f"menu:user:support:view:{thread.ticket.id}",
        user_id=other.telegram_id,
        first_name="Другой",
    )
    await show_user_ticket(callback, session, settings=settings)

    assert callback.answer_calls == [("Это обращение тебе недоступно.", True)]
    assert callback.message.edit_text_calls == []
    assert callback.message.media_calls == []


async def test_ticket_creation_rate_limit_is_reported_to_user(
    session: AsyncSession,
    settings: Settings,
) -> None:
    user, admin = await _seed_users(session)
    base_time = datetime(2026, 5, 2, 15, 0, tzinfo=UTC)
    for index in range(3):
        thread = await create_support_ticket(
            session,
            user_id=user.id,
            category=SUPPORT_CATEGORY_PAYMENT,
            body=f"История {index}",
            now=base_time + timedelta(hours=index),
        )
        await close_support_ticket(
            session,
            ticket_id=thread.ticket.id,
            actor_user_id=admin.id,
            now=base_time + timedelta(hours=index, minutes=10),
        )
        await session.commit()

    state = FakeState()
    await state.update_data(support_mode="create", support_category="payment")
    bot = FakeBot()
    message = DummyMessage(
        "Четвертая попытка",
        user_id=user.telegram_id,
        first_name="Руслан",
        username="ruslan",
    )
    message.date = base_time + timedelta(hours=5)

    await receive_support_message(message, state, session, bot, settings)

    assert message.answer_calls
    assert "Лимит новых обращений" in message.answer_calls[-1][0]
