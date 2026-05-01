from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.routers.admin.analytics import analytics_dashboard
from app.bot.routers.admin.users import (
    confirm_block_toggle,
    confirm_manual_grant,
    pick_tariff_filter,
    receive_direct_message,
    review_block_toggle,
    review_manual_grant,
    start_direct_message,
    users_index,
    users_list,
)
from app.config import Settings
from app.db.base import Base
from app.db.models import AuditLog, Channel, Payment, Subscription, Tariff, User
from app.db.session import create_async_engine, create_session_factory


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


class RecordingBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str):
        self.messages.append((chat_id, text))
        return True


ANALYTICS_TEXT = "\u0410\u043d\u0430\u043b\u0438\u0442\u0438\u043a\u0430"
USERS_TEXT = "Пользователи"
FILTER_ALL_TEXT = "Фильтр: Все"
FILTER_ACTIVE_TEXT = "Фильтр: Активные"
PAGE_TWO_TEXT = "Страница 2/2"
PICK_TARIFF_TEXT = (
    "Выберите тариф "
    "для фильтра "
    "списка пользователей."
)
CONFIRM_ACTION_TEXT = (
    "Подтверждение "
    "действия"
)
CONFIRM_GRANT_TEXT = (
    "Подтверждение "
    "ручной выдачи"
)
MESSAGE_SENT_TEXT = (
    "Сообщение "
    "отправлено."
)
TARIFF_FILTER_BUTTON = "По тарифу"


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


async def _seed_stage7_data(session: AsyncSession) -> dict[str, object]:
    now = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)

    channel = Channel(
        telegram_chat_id=-1001234567890,
        title="Основной канал",
        username="main_channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add(channel)
    await session.flush()

    tariff = Tariff(
        name="VIP 30",
        price_stars=250,
        duration_days=30,
        sort_order=10,
        is_active=True,
        channel_id=channel.id,
    )
    session.add(tariff)
    await session.flush()

    users = [
        User(
            telegram_id=1001,
            first_name="Active",
            role="user",
            is_admin=False,
            last_seen_at=now - timedelta(minutes=1),
        ),
        User(
            telegram_id=1002,
            first_name="Expired",
            role="user",
            is_admin=False,
            last_seen_at=now - timedelta(minutes=2),
        ),
        User(
            telegram_id=1003,
            first_name="Blocked",
            role="user",
            is_admin=False,
            is_blocked=True,
            last_seen_at=now - timedelta(minutes=3),
        ),
        User(
            telegram_id=1004,
            first_name="Never",
            role="user",
            is_admin=False,
            last_seen_at=now - timedelta(minutes=4),
        ),
        User(
            telegram_id=1005,
            first_name="Page",
            last_name="One",
            role="user",
            is_admin=False,
            last_seen_at=now - timedelta(minutes=5),
        ),
        User(
            telegram_id=1006,
            first_name="Page",
            last_name="Two",
            role="user",
            is_admin=False,
            last_seen_at=now - timedelta(minutes=6),
        ),
        User(
            telegram_id=1007,
            first_name="Page",
            last_name="Three",
            role="user",
            is_admin=False,
            last_seen_at=now - timedelta(minutes=7),
        ),
    ]
    session.add_all(users)
    await session.flush()

    session.add_all(
        [
            Subscription(
                user_id=users[0].id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                status="active",
                source="purchase",
                started_at=now - timedelta(days=5),
                expires_at=now + timedelta(days=10),
            ),
            Subscription(
                user_id=users[1].id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                status="expired",
                source="purchase",
                started_at=now - timedelta(days=40),
                expires_at=now - timedelta(days=1),
                revoked_at=now - timedelta(days=1),
            ),
        ]
    )

    session.add_all(
        [
            Payment(
                user_id=users[0].id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                amount=250,
                currency="XTR",
                provider="telegram_stars",
                telegram_payment_charge_id="charge-active",
                provider_payment_charge_id="provider-active",
                invoice_payload="stars:1",
                paid_at=now - timedelta(hours=2),
                status="paid",
            ),
            Payment(
                user_id=users[1].id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                amount=250,
                currency="XTR",
                provider="telegram_stars",
                telegram_payment_charge_id="charge-expired",
                provider_payment_charge_id="provider-expired",
                invoice_payload="stars:1",
                paid_at=now - timedelta(days=2),
                status="paid",
            ),
        ]
    )

    session.add_all(
        [
            AuditLog(action="user_start", target_user_id=users[0].id),
            AuditLog(action="user_start", target_user_id=users[1].id),
            AuditLog(action="invoice_created_stars", target_user_id=users[0].id),
            AuditLog(action="payment_paid_stars", target_user_id=users[0].id),
        ]
    )

    await session.commit()
    return {"channel": channel, "tariff": tariff, "users": users, "now": now}


async def test_analytics_dashboard_renders_snapshot(session: AsyncSession) -> None:
    await _seed_stage7_data(session)
    callback = DummyCallback("menu:admin:analytics")

    await analytics_dashboard(callback, session)

    text, markup = callback.message.edit_calls[0]
    assert ANALYTICS_TEXT in text
    assert "7" in text
    assert "1" in text
    assert _flatten_button_texts(markup) == [
        "👥 Пользователи",
        "🔄 Обновить",
        "Главное меню",
    ]


async def test_users_list_supports_filters_and_pagination(session: AsyncSession) -> None:
    await _seed_stage7_data(session)
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181]})

    callback_page = DummyCallback("menu:admin:users:list:all:2")
    await users_list(callback_page, session, settings)
    page_text, _ = callback_page.message.edit_calls[0]

    callback_active = DummyCallback("menu:admin:users:list:active:1")
    await users_list(callback_active, session, settings)
    active_text, _ = callback_active.message.edit_calls[0]

    assert PAGE_TWO_TEXT in page_text
    assert "Page Three" in page_text
    assert FILTER_ACTIVE_TEXT in active_text
    assert "Active" in active_text
    assert "Expired" not in active_text


async def test_pick_tariff_filter_opens_filter_picker(session: AsyncSession) -> None:
    await _seed_stage7_data(session)
    callback = DummyCallback("menu:admin:users:pick-filter:tariff")

    await pick_tariff_filter(callback, session)

    text, markup = callback.message.edit_calls[0]
    assert PICK_TARIFF_TEXT in text
    assert "VIP 30" in _flatten_button_texts(markup)


async def test_admin_filter_rejects_non_admin() -> None:
    event = type("Event", (), {"from_user": DummyUser(user_id=1)})()
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181]})

    result = await AdminFilter()(event, settings)

    assert result is False


async def test_block_flow_requires_confirmation(session: AsyncSession) -> None:
    seeded = await _seed_stage7_data(session)
    user = seeded["users"][0]
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181]})

    review_callback = DummyCallback(f"menu:admin:users:block:{user.id}:all:1")
    await review_block_toggle(review_callback, session, settings)

    unchanged = await session.get(User, user.id)
    assert unchanged is not None
    assert unchanged.is_blocked is False
    review_text, _ = review_callback.message.edit_calls[0]
    assert CONFIRM_ACTION_TEXT in review_text

    confirm_callback = DummyCallback(f"menu:admin:users:block-confirm:{user.id}:all:1")
    await confirm_block_toggle(confirm_callback, session, settings)

    refreshed = await session.get(User, user.id)
    assert refreshed is not None
    assert refreshed.is_blocked is True

    audit_rows = list(
        (
            await session.execute(
                select(AuditLog).where(AuditLog.target_user_id == user.id)
            )
        ).scalars()
    )
    assert any(row.action == "admin_user_blocked" for row in audit_rows)


async def test_manual_grant_requires_confirmation(session: AsyncSession) -> None:
    seeded = await _seed_stage7_data(session)
    user = seeded["users"][3]
    tariff = seeded["tariff"]
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181]})

    review_callback = DummyCallback(
        f"menu:admin:users:grant-review:{user.id}:{tariff.id}:all:1"
    )
    await review_manual_grant(review_callback, session, settings)

    subscriptions_before = list(
        (
            await session.execute(
                select(Subscription).where(Subscription.user_id == user.id)
            )
        ).scalars()
    )
    assert subscriptions_before == []
    review_text, _ = review_callback.message.edit_calls[0]
    assert CONFIRM_GRANT_TEXT in review_text

    confirm_callback = DummyCallback(
        f"menu:admin:users:grant-confirm:{user.id}:{tariff.id}:all:1"
    )
    await confirm_manual_grant(confirm_callback, session, settings)

    subscriptions_after = list(
        (
            await session.execute(
                select(Subscription).where(Subscription.user_id == user.id)
            )
        ).scalars()
    )
    assert len(subscriptions_after) == 1
    assert subscriptions_after[0].status == "active"

    audit_rows = list(
        (
            await session.execute(
                select(AuditLog).where(AuditLog.target_user_id == user.id)
            )
        ).scalars()
    )
    assert any(row.action == "admin_subscription_granted" for row in audit_rows)


async def test_admin_can_send_direct_message(session: AsyncSession) -> None:
    seeded = await _seed_stage7_data(session)
    user = seeded["users"][0]
    state = FakeState()
    bot = RecordingBot()
    settings = Settings.model_validate(
        {"bot_token": "123:token", "admin_ids": [755815181], "timezone": "Europe/Saratov"}
    )

    start_callback = DummyCallback(f"menu:admin:users:message:{user.id}:all:1")
    await start_direct_message(start_callback, session, state, settings)
    assert state.state_name is not None

    message = DummyMessage(text="Тестовое сообщение")
    await receive_direct_message(message, state, session, settings, bot)

    assert bot.messages == [
        (user.telegram_id, "Тестовое сообщение")
    ]
    assert message.answer_calls
    assert MESSAGE_SENT_TEXT in message.answer_calls[0][0]

    audit_rows = list(
        (
            await session.execute(
                select(AuditLog).where(AuditLog.action == "admin_direct_message")
            )
        ).scalars()
    )
    assert len(audit_rows) == 1


async def test_users_index_shows_directory(session: AsyncSession) -> None:
    await _seed_stage7_data(session)
    callback = DummyCallback("menu:admin:users")
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181]})

    await users_index(callback, session, settings)

    text, markup = callback.message.edit_calls[0]
    assert USERS_TEXT in text
    assert FILTER_ALL_TEXT in text
    assert TARIFF_FILTER_BUTTON in _flatten_button_texts(markup)

