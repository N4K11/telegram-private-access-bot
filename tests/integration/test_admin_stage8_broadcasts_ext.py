from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from aiogram.exceptions import TelegramRetryAfter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.routers.admin.broadcasts import (
    choose_broadcast_template,
    receive_broadcast_content,
    receive_broadcast_template_name,
)
from app.db.base import Base
from app.db.models import (
    BroadcastCampaign,
    BroadcastDelivery,
    Channel,
    InviteLink,
    Payment,
    Subscription,
    Tariff,
    User,
)
from app.db.session import create_async_engine, create_session_factory
from app.services.broadcasts import (
    get_broadcast_campaign_snapshot,
    queue_broadcast_campaign,
    save_broadcast_template,
    select_broadcast_recipients,
)
from app.workers.broadcast_sender import process_broadcast_campaigns


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
        self.edit_calls: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edit_calls.append((text, reply_markup))


class DummyCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = DummyMessage()
        self.message.photo = None
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


class RateLimitedBot:
    def __init__(self, rate_limited_chat_id: int) -> None:
        self.rate_limited_chat_id = rate_limited_chat_id
        self.sent_messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str):
        if chat_id == self.rate_limited_chat_id:
            raise TelegramRetryAfter(object(), "retry", 0)
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


async def _seed_stage8_data(session: AsyncSession) -> dict[str, object]:
    now = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)

    admin_user = User(
        telegram_id=755815181,
        first_name="Admin",
        is_admin=True,
        role="owner",
        last_seen_at=now,
    )
    channel = Channel(
        telegram_chat_id=-100888000111,
        title="Broadcast channel",
        username="broadcast_channel",
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

    soon_user = User(telegram_id=2101, first_name="Soon", last_seen_at=now - timedelta(minutes=1))
    active_user = User(
        telegram_id=2102,
        first_name="Active",
        last_seen_at=now - timedelta(minutes=2),
    )
    rate_limited_user = User(
        telegram_id=2103,
        first_name="Retry",
        last_seen_at=now - timedelta(minutes=3),
    )
    never_paid_user = User(
        telegram_id=2104,
        first_name="NeverPaid",
        last_seen_at=now - timedelta(minutes=4),
    )
    session.add_all([soon_user, active_user, rate_limited_user, never_paid_user])
    await session.flush()

    session.add_all(
        [
            Subscription(
                user_id=soon_user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                status="active",
                source="purchase",
                started_at=now - timedelta(days=1),
                expires_at=now + timedelta(days=2),
            ),
            Subscription(
                user_id=active_user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                status="active",
                source="purchase",
                started_at=now - timedelta(days=2),
                expires_at=now + timedelta(days=10),
            ),
            Subscription(
                user_id=rate_limited_user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                status="active",
                source="purchase",
                started_at=now - timedelta(days=2),
                expires_at=now + timedelta(days=5),
            ),
        ]
    )
    session.add(
        InviteLink(
            user_id=soon_user.id,
            channel_id=channel.id,
            subscription_id=1,
            invite_link="https://t.me/+pending-join",
            expire_at=now + timedelta(hours=12),
            member_limit=1,
            is_revoked=False,
        )
    )
    session.add_all(
        [
            Payment(
                user_id=soon_user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                amount=250,
                currency="XTR",
                provider="telegram_stars",
                telegram_payment_charge_id="stage8-soon",
                provider_payment_charge_id="stage8-soon-p",
                invoice_payload="stars:1",
                paid_at=now - timedelta(hours=1),
                status="paid",
            ),
            Payment(
                user_id=active_user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                amount=250,
                currency="XTR",
                provider="telegram_stars",
                telegram_payment_charge_id="stage8-active",
                provider_payment_charge_id="stage8-active-p",
                invoice_payload="stars:1",
                paid_at=now - timedelta(hours=2),
                status="paid",
            ),
            Payment(
                user_id=rate_limited_user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                amount=250,
                currency="XTR",
                provider="telegram_stars",
                telegram_payment_charge_id="stage8-retry",
                provider_payment_charge_id="stage8-retry-p",
                invoice_payload="stars:1",
                paid_at=now - timedelta(hours=3),
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
        "soon_user": soon_user,
        "active_user": active_user,
        "rate_limited_user": rate_limited_user,
        "never_paid_user": never_paid_user,
    }


async def test_stage8_new_segments_preview_and_templates(session: AsyncSession) -> None:
    seeded = await _seed_stage8_data(session)

    expires_soon = await select_broadcast_recipients(
        session,
        filter_name="expires_soon",
        now=seeded["now"],
    )
    pending_join = await select_broadcast_recipients(
        session,
        filter_name="pending_join",
        now=seeded["now"],
    )

    template = await save_broadcast_template(
        session,
        title="Winback",
        content="Вернитесь в канал",
        updated_by_user_id=seeded["admin"].id,
    )
    await session.commit()

    state = FakeState()
    await state.update_data(broadcast_filter="all")
    callback = DummyCallback(f"menu:admin:broadcasts:template:{template.key}")
    await choose_broadcast_template(callback, state, session)

    campaigns = list((await session.execute(select(BroadcastCampaign))).scalars())

    assert expires_soon.user_ids == [seeded["soon_user"].id]
    assert pending_join.user_ids == [seeded["soon_user"].id]
    assert expires_soon.samples
    assert campaigns == []
    assert state.data["broadcast_content"] == "Вернитесь в канал"
    assert callback.message.edit_calls
    preview_text = callback.message.edit_calls[0][0]
    assert "Шаблон: Winback" in preview_text
    assert "Первые получатели:" in preview_text
    assert callback.answer_count == 1


async def test_plain_text_without_filter_does_not_queue_campaign(session: AsyncSession) -> None:
    await _seed_stage8_data(session)
    state = FakeState()
    message = DummyMessage("Loose text")

    await receive_broadcast_content(message, state, session)

    campaigns = list((await session.execute(select(BroadcastCampaign))).scalars())

    assert campaigns == []
    assert message.answer_calls
    assert "Контекст создания рассылки потерян" in message.answer_calls[0][0]


async def test_save_template_from_preview_flow(session: AsyncSession) -> None:
    seeded = await _seed_stage8_data(session)
    state = FakeState()
    await state.update_data(
        broadcast_content="Скидка для вас",
        broadcast_filter_label="Все",
        broadcast_total_targets=3,
        broadcast_sample_labels=["Soon (Telegram 2101)", "Active (Telegram 2102)"],
    )
    message = DummyMessage("Promo Template")

    await receive_broadcast_template_name(message, state, session)

    templates = await select_broadcast_recipients(session, filter_name="all", now=seeded["now"])
    campaigns = list((await session.execute(select(BroadcastCampaign))).scalars())
    saved_template = await save_broadcast_template(
        session,
        title="Promo Template",
        content="Скидка для вас",
        updated_by_user_id=seeded["admin"].id,
    )
    await session.rollback()

    assert campaigns == []
    assert templates.total_targets == 4
    assert message.answer_calls
    assert "Шаблон сохранён" in message.answer_calls[0][0]
    assert saved_template.title == "Promo Template"


async def test_broadcast_worker_marks_rate_limited_delivery(session: AsyncSession) -> None:
    seeded = await _seed_stage8_data(session)
    campaign = await queue_broadcast_campaign(
        session,
        created_by_user_id=seeded["admin"].id,
        filter_name="active",
        content="Привет, активные",
        now=seeded["now"],
    )
    await session.commit()

    bot = RateLimitedBot(seeded["rate_limited_user"].telegram_id)
    result = await process_broadcast_campaigns(
        session,
        bot,
        rate_limit_per_second=1000,
        batch_size=20,
        sleep_func=lambda _seconds: _noop(),
        now=seeded["now"],
    )

    snapshot = await get_broadcast_campaign_snapshot(session, campaign.id)
    deliveries = list(
        (
            await session.execute(
                select(BroadcastDelivery).where(BroadcastDelivery.campaign_id == campaign.id)
            )
        ).scalars()
    )
    statuses = {delivery.user_id: delivery.status for delivery in deliveries}

    assert snapshot is not None
    assert result.processed_count == 3
    assert result.active_campaign is False
    assert snapshot.rate_limited_count == 1
    assert snapshot.campaign.failed_count == 1
    assert snapshot.campaign.sent_count == 2
    assert statuses[seeded["rate_limited_user"].id] == "rate_limited"
    assert any("Рассылка завершена." in text for _, text in bot.sent_messages)


async def _noop() -> None:
    return None

