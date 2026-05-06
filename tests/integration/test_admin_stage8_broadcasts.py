from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.routers.admin.broadcasts import (
    confirm_broadcast_creation,
    receive_broadcast_content,
    select_broadcast_filter,
    start_broadcast_create,
)
from app.bot.states.admin import AdminBroadcastForm
from app.config import Settings
from app.db.base import Base
from app.db.models import (
    BroadcastCampaign,
    BroadcastDelivery,
    Channel,
    Payment,
    Subscription,
    Tariff,
    User,
)
from app.db.session import create_async_engine, create_session_factory
from app.services.broadcasts import queue_broadcast_campaign, select_broadcast_recipients
from app.workers.broadcast_sender import process_broadcast_campaigns


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


class BroadcastBot:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str):
        if chat_id == 1002:
            raise TelegramForbiddenError(object(), "bot was blocked by the user")
        if chat_id == 1003:
            raise RuntimeError("boom")
        self.sent_messages.append((chat_id, text))
        return True


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


async def _seed_broadcast_data(session: AsyncSession) -> dict[str, object]:
    now = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)

    admin_user = User(
        telegram_id=755815181,
        first_name="Admin",
        is_admin=True,
        role="owner",
        last_seen_at=now,
    )
    channel = Channel(
        telegram_chat_id=-1001234567890,
        title="Основной канал",
        username="main_channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add_all([admin_user, channel])
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

    active_user = User(
        telegram_id=1001,
        first_name="Active",
        last_seen_at=now - timedelta(minutes=1),
    )
    blocked_by_bot_user = User(
        telegram_id=1002,
        first_name="BlockedByBot",
        last_seen_at=now - timedelta(minutes=2),
    )
    failing_user = User(
        telegram_id=1003,
        first_name="Failing",
        last_seen_at=now - timedelta(minutes=3),
    )
    expired_user = User(
        telegram_id=1004,
        first_name="Expired",
        last_seen_at=now - timedelta(minutes=4),
    )
    blocked_user = User(
        telegram_id=1005,
        first_name="Blocked",
        is_blocked=True,
        last_seen_at=now - timedelta(minutes=5),
    )
    never_paid_user = User(
        telegram_id=1006,
        first_name="NeverPaid",
        last_seen_at=now - timedelta(minutes=6),
    )
    session.add_all(
        [
            active_user,
            blocked_by_bot_user,
            failing_user,
            expired_user,
            blocked_user,
            never_paid_user,
        ]
    )
    await session.flush()

    session.add_all(
        [
            Subscription(
                user_id=active_user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                status="active",
                source="purchase",
                started_at=now - timedelta(days=5),
                expires_at=now + timedelta(days=10),
            ),
            Subscription(
                user_id=blocked_by_bot_user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                status="active",
                source="purchase",
                started_at=now - timedelta(days=4),
                expires_at=now + timedelta(days=8),
            ),
            Subscription(
                user_id=failing_user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                status="active",
                source="purchase",
                started_at=now - timedelta(days=3),
                expires_at=now + timedelta(days=7),
            ),
            Subscription(
                user_id=expired_user.id,
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
                user_id=active_user.id,
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
                user_id=blocked_by_bot_user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                amount=250,
                currency="XTR",
                provider="telegram_stars",
                telegram_payment_charge_id="charge-blocked",
                provider_payment_charge_id="provider-blocked",
                invoice_payload="stars:1",
                paid_at=now - timedelta(hours=3),
                status="paid",
            ),
            Payment(
                user_id=failing_user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                amount=250,
                currency="XTR",
                provider="telegram_stars",
                telegram_payment_charge_id="charge-failing",
                provider_payment_charge_id="provider-failing",
                invoice_payload="stars:1",
                paid_at=now - timedelta(hours=4),
                status="paid",
            ),
            Payment(
                user_id=expired_user.id,
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

    await session.commit()
    return {
        "now": now,
        "admin": admin_user,
        "channel": channel,
        "tariff": tariff,
        "active_user": active_user,
        "blocked_by_bot_user": blocked_by_bot_user,
        "failing_user": failing_user,
        "expired_user": expired_user,
        "blocked_user": blocked_user,
        "never_paid_user": never_paid_user,
    }


async def test_select_broadcast_recipients_filters_and_excludes_blocked(
    session: AsyncSession,
) -> None:
    seeded = await _seed_broadcast_data(session)

    all_preview = await select_broadcast_recipients(
        session,
        filter_name="all",
        now=seeded["now"],
    )
    active_preview = await select_broadcast_recipients(
        session,
        filter_name="active",
        now=seeded["now"],
    )
    expired_preview = await select_broadcast_recipients(
        session,
        filter_name="expired",
        now=seeded["now"],
    )
    never_paid_preview = await select_broadcast_recipients(
        session,
        filter_name="never_paid",
        now=seeded["now"],
    )
    tariff_preview = await select_broadcast_recipients(
        session,
        filter_name=f"tariff-{seeded['tariff'].id}",
        now=seeded["now"],
    )
    channel_preview = await select_broadcast_recipients(
        session,
        filter_name=f"channel-{seeded['channel'].id}",
        now=seeded["now"],
    )

    assert seeded["blocked_user"].id not in all_preview.user_ids
    assert set(active_preview.user_ids) == {
        seeded["active_user"].id,
        seeded["blocked_by_bot_user"].id,
        seeded["failing_user"].id,
    }
    assert expired_preview.user_ids == [seeded["expired_user"].id]
    assert never_paid_preview.user_ids == [seeded["never_paid_user"].id]
    assert set(tariff_preview.user_ids) == {
        seeded["active_user"].id,
        seeded["blocked_by_bot_user"].id,
        seeded["failing_user"].id,
        seeded["expired_user"].id,
    }
    assert set(channel_preview.user_ids) == {
        seeded["active_user"].id,
        seeded["blocked_by_bot_user"].id,
        seeded["failing_user"].id,
        seeded["expired_user"].id,
    }


async def test_broadcast_creation_requires_confirmation(session: AsyncSession) -> None:
    seeded = await _seed_broadcast_data(session)
    state = FakeState()
    settings = Settings.model_validate(
        {"bot_token": "123:token", "admin_ids": [755815181], "timezone": "Europe/Saratov"}
    )

    start_callback = DummyCallback("menu:admin:broadcasts:create")
    await start_broadcast_create(start_callback, state)

    filter_callback = DummyCallback("menu:admin:broadcasts:filter:all")
    await select_broadcast_filter(filter_callback, state)
    assert state.state_name == AdminBroadcastForm.waiting_for_content

    message = DummyMessage(text="Тестовая рассылка")
    await receive_broadcast_content(message, state, session)

    campaigns_before = list((await session.execute(select(BroadcastCampaign))).scalars())
    assert campaigns_before == []
    assert "Получателей" in message.answer_calls[0][0]

    confirm_callback = DummyCallback("menu:admin:broadcasts:confirm")
    await confirm_broadcast_creation(confirm_callback, state, session, settings)

    campaigns_after = list((await session.execute(select(BroadcastCampaign))).scalars())
    deliveries = list((await session.execute(select(BroadcastDelivery))).scalars())

    assert len(campaigns_after) == 1
    assert campaigns_after[0].status == "queued"
    assert campaigns_after[0].total_targets == 5
    assert len(deliveries) == 5
    assert all(delivery.user_id != seeded["blocked_user"].id for delivery in deliveries)


async def test_broadcast_worker_handles_partial_failures(session: AsyncSession) -> None:
    seeded = await _seed_broadcast_data(session)
    campaign = await queue_broadcast_campaign(
        session,
        created_by_user_id=1,
        filter_name="active",
        now=seeded["now"],
        content="Рассылка для активных",
    )
    await session.commit()

    bot = BroadcastBot()
    result = await process_broadcast_campaigns(
        session,
        bot,
        rate_limit_per_second=1000,
        batch_size=20,
        sleep_func=lambda _seconds: _noop(),
    )

    refreshed_campaign = await session.get(BroadcastCampaign, campaign.id)
    deliveries = list(
        (
            await session.execute(
                select(BroadcastDelivery).where(BroadcastDelivery.campaign_id == campaign.id)
            )
        ).scalars()
    )
    statuses = {delivery.user_id: delivery.status for delivery in deliveries}

    assert result.processed_count == 3
    assert result.active_campaign is False
    assert refreshed_campaign is not None
    assert refreshed_campaign.status == "completed"
    assert refreshed_campaign.sent_count == 1
    assert refreshed_campaign.failed_count == 1
    assert len(bot.sent_messages) == 2
    assert any(text == "Рассылка для активных" for _, text in bot.sent_messages)
    assert "sent" in statuses.values()
    assert "blocked" in statuses.values()
    assert "failed" in statuses.values()


async def _noop() -> None:
    return None