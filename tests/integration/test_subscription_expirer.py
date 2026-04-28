from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import Channel, Subscription, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.services.subscriptions import activate_or_extend_subscription
from app.workers.subscription_expirer import process_expired_subscriptions, remove_user_from_channel


class RecordingBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def ban_chat_member(self, **kwargs):
        self.calls.append(("ban", kwargs))
        return True

    async def unban_chat_member(self, **kwargs):
        self.calls.append(("unban", kwargs))
        return True

    async def send_message(self, chat_id: int, text: str):
        self.calls.append(("notify", {"chat_id": chat_id, "text": text}))
        return True


class AbsentUserBot(RecordingBot):
    async def ban_chat_member(self, **kwargs):
        raise TelegramBadRequest(object(), "user not participant")


class RetryBot(RecordingBot):
    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    async def ban_chat_member(self, **kwargs):
        self.attempts += 1
        if self.attempts == 1:
            raise TelegramRetryAfter(object(), "retry", 0)
        return await super().ban_chat_member(**kwargs)


async def _create_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    return session_factory(), engine


async def _close_session(session: AsyncSession, engine) -> None:
    await session.close()
    await engine.dispose()


async def _seed_expired_subscription(session: AsyncSession) -> tuple[User, Tariff, Subscription]:
    user = User(telegram_id=42, first_name="Anna", is_admin=False, role="user")
    channel = Channel(
        telegram_chat_id=-1001234567890,
        title="Основной канал",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add_all([user, channel])
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

    subscription = Subscription(
        user_id=user.id,
        tariff_id=tariff.id,
        channel_id=channel.id,
        status="active",
        source="purchase",
        started_at=datetime(2026, 3, 28, 12, 0, tzinfo=UTC),
        expires_at=datetime(2026, 4, 27, 12, 0, tzinfo=UTC),
    )
    session.add(subscription)
    await session.commit()
    return user, tariff, subscription


async def test_process_expired_subscriptions_marks_expired_and_notifies() -> None:
    session, engine = await _create_session()
    try:
        _, _, subscription = await _seed_expired_subscription(session)
        bot = RecordingBot()

        processed = await process_expired_subscriptions(
            session,
            bot,
            now=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
        )

        refreshed = await session.get(Subscription, subscription.id)

        assert processed == 1
        assert refreshed is not None
        assert refreshed.status == "expired"
        assert refreshed.revoked_at == datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
        assert [name for name, _ in bot.calls] == ["ban", "unban", "notify"]
    finally:
        await _close_session(session, engine)


async def test_process_expired_subscriptions_handles_absent_member() -> None:
    session, engine = await _create_session()
    try:
        _, _, subscription = await _seed_expired_subscription(session)
        bot = AbsentUserBot()

        processed = await process_expired_subscriptions(
            session,
            bot,
            now=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
        )

        refreshed = await session.get(Subscription, subscription.id)

        assert processed == 1
        assert refreshed is not None
        assert refreshed.status == "expired"
    finally:
        await _close_session(session, engine)


async def test_remove_user_from_channel_retries_after_rate_limit() -> None:
    bot = RetryBot()
    sleep_calls: list[float] = []

    async def sleep_recorder(seconds: float) -> None:
        sleep_calls.append(seconds)

    await remove_user_from_channel(
        bot,
        channel_chat_id=-1001234567890,
        telegram_user_id=42,
        now=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
        sleep_func=sleep_recorder,
    )

    assert bot.attempts == 2
    assert sleep_calls == [0.0]
    assert [name for name, _ in bot.calls] == ["ban", "unban"]


async def test_user_can_buy_again_after_expiration_worker() -> None:
    session, engine = await _create_session()
    try:
        user, tariff, subscription = await _seed_expired_subscription(session)
        bot = RecordingBot()
        expired_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)

        await process_expired_subscriptions(session, bot, now=expired_at)

        change = await activate_or_extend_subscription(
            session,
            user_id=user.id,
            tariff=tariff,
            paid_at=expired_at + timedelta(minutes=5),
        )

        assert change.is_extension is False
        assert change.subscription.id != subscription.id
        assert change.subscription.status == "active"
    finally:
        await _close_session(session, engine)