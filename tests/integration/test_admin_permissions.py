from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.routers.admin.roles import admin_role_set
from app.bot.routers.admin.users import start_manual_grant
from app.config import Settings
from app.db.base import Base
from app.db.models import AuditLog, Channel, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.services.admin_roles import PERMISSION_BROADCASTS, PERMISSION_SETTINGS, ROLE_SUPPORT


class DummyUser:
    def __init__(self, user_id: int, *, first_name: str = "Admin") -> None:
        self.id = user_id
        self.first_name = first_name
        self.username = f"user{user_id}"
        self.last_name = None
        self.language_code = "ru"


class DummyMessage:
    def __init__(self) -> None:
        self.edit_calls: list[tuple[str, object | None]] = []
        self.answer_calls: list[tuple[str, object | None]] = []

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edit_calls.append((text, reply_markup))

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))


class DummyCallback:
    def __init__(self, data: str, *, user_id: int) -> None:
        self.data = data
        self.from_user = DummyUser(user_id)
        self.message = DummyMessage()
        self.answer_calls: list[tuple[str | None, bool]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answer_calls.append((text, show_alert))


class FakeState:
    async def clear(self) -> None:
        return None


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
    return Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181]})


async def test_owner_fallback_from_admin_ids_passes_admin_filter(settings: Settings) -> None:
    event = type("Event", (), {"from_user": DummyUser(755815181)})()

    result = await AdminFilter(PERMISSION_SETTINGS)(event, settings)

    assert result is True


async def test_support_cannot_start_manual_grant(
    session: AsyncSession,
    settings: Settings,
) -> None:
    support_user = User(telegram_id=2001, first_name="Support", role=ROLE_SUPPORT, is_admin=True)
    target_user = User(telegram_id=3001, first_name="Client", role="user", is_admin=False)
    channel = Channel(
        telegram_chat_id=-1001234567890,
        title="Основной канал",
        username="main_channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add_all([support_user, target_user, channel])
    await session.flush()
    session.add(
        Tariff(
            name="VIP 30",
            price_stars=250,
            duration_days=30,
            sort_order=10,
            is_active=True,
            channel_id=channel.id,
        )
    )
    await session.commit()

    callback = DummyCallback(
        f"menu:admin:users:grant:{target_user.id}:all:1",
        user_id=support_user.telegram_id,
    )

    await start_manual_grant(callback, session, settings, FakeState())

    assert callback.answer_calls == [
        ("Недостаточно прав для управления пользователями.", False)
    ]
    assert callback.message.edit_calls == []


async def test_analyst_cannot_access_broadcast_permission(
    session: AsyncSession,
    settings: Settings,
) -> None:
    analyst = User(telegram_id=4001, first_name="Analyst", role="analyst", is_admin=True)
    session.add(analyst)
    await session.commit()
    event = type("Event", (), {"from_user": DummyUser(analyst.telegram_id)})()

    result = await AdminFilter(PERMISSION_BROADCASTS)(event, settings, session=session)

    assert result is False


async def test_owner_can_change_role_and_audit_is_written(
    session: AsyncSession,
    settings: Settings,
) -> None:
    owner = User(telegram_id=755815181, first_name="Owner", role="owner", is_admin=True)
    target = User(telegram_id=5001, first_name="Helper", role="user", is_admin=False)
    session.add_all([owner, target])
    await session.commit()

    callback = DummyCallback(
        f"menu:admin:roles:set:{target.id}:support",
        user_id=owner.telegram_id,
    )

    await admin_role_set(callback, session, settings)

    refreshed = await session.get(User, target.id)
    assert refreshed is not None
    assert refreshed.role == "support"
    assert refreshed.is_admin is True
    assert callback.message.edit_calls

    audit_rows = list(
        (
            await session.execute(
                select(AuditLog).where(AuditLog.action == "admin_role_changed")
            )
        ).scalars()
    )
    assert len(audit_rows) == 1
    payload = json.loads(audit_rows[0].payload or "{}")
    assert payload["old_role"] == "user"
    assert payload["new_role"] == "support"
