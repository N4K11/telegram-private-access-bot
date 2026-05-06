from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.base import Base
from app.db.models import AuditLog, Channel, Subscription, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.services.subscriptions import activate_or_extend_subscription
from app.workers.subscription_expirer import (
    process_expired_subscriptions,
    remove_user_from_channel,
)


def _decode_payload(raw_payload):
    if raw_payload is None:
        return {}
    if isinstance(raw_payload, str):
        return json.loads(raw_payload or "{}")
    return raw_payload


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


class PartialFailureBot(RecordingBot):
    def __init__(
        self,
        *,
        fail_ban_for: int | None = None,
        fail_send_for: int | None = None,
    ) -> None:
        super().__init__()
        self.fail_ban_for = fail_ban_for
        self.fail_send_for = fail_send_for

    async def ban_chat_member(self, **kwargs):
        if self.fail_ban_for is not None and kwargs.get("user_id") == self.fail_ban_for:
            raise RuntimeError("ban failed")
        return await super().ban_chat_member(**kwargs)

    async def send_message(self, chat_id: int, text: str):
        if self.fail_send_for is not None and chat_id == self.fail_send_for:
            raise RuntimeError("send failed")
        return await super().send_message(chat_id, text)


async def _create_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    return session_factory(), engine


async def _close_session(session: AsyncSession, engine) -> None:
    await session.close()
    await engine.dispose()


async def _seed_subscription(
    session: AsyncSession,
    *,
    telegram_id: int = 42,
    channel_suffix: int = 0,
    started_at: datetime,
    expires_at: datetime,
    warning_3d_sent_at: datetime | None = None,
    warning_1d_sent_at: datetime | None = None,
    expired_notice_sent_at: datetime | None = None,
    grace_revoke_after: datetime | None = None,
) -> tuple[User, Tariff, Subscription]:
    user = User(
        telegram_id=telegram_id,
        first_name=f"User {telegram_id}",
        is_admin=False,
        role="user",
    )
    channel = Channel(
        telegram_chat_id=-1001234567890 - channel_suffix,
        title=f"Канал {telegram_id}",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add_all([user, channel])
    await session.flush()

    tariff = Tariff(
        name=f"VIP {telegram_id}",
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
        started_at=started_at,
        expires_at=expires_at,
        warning_3d_sent_at=warning_3d_sent_at,
        warning_1d_sent_at=warning_1d_sent_at,
        expired_notice_sent_at=expired_notice_sent_at,
        grace_revoke_after=grace_revoke_after,
    )
    session.add(subscription)
    await session.commit()
    return user, tariff, subscription


async def test_process_expired_subscriptions_sends_3d_warning_once() -> None:
    session, engine = await _create_session()
    try:
        now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        _, _, subscription = await _seed_subscription(
            session,
            started_at=now - timedelta(days=10),
            expires_at=now + timedelta(days=2, hours=12),
        )
        bot = RecordingBot()
        settings = Settings.model_validate(
            {
                "bot_token": "123:token",
                "admin_ids": [1],
                "bot_public_username": "privatair_bot",
            }
        )

        first = await process_expired_subscriptions(session, bot, now=now, settings=settings)
        second = await process_expired_subscriptions(session, bot, now=now + timedelta(hours=1))

        refreshed = await session.get(Subscription, subscription.id)

        assert first.warning_3d_count == 1
        assert second.warning_3d_count == 0
        assert refreshed is not None
        assert refreshed.warning_3d_sent_at == now
        assert [name for name, _ in bot.calls] == ["notify"]
        assert "VIP 42" in bot.calls[0][1]["text"]
        assert "start=buy_1" in bot.calls[0][1]["text"]
        audit_row = _decode_payload((
            await session.execute(
                select(AuditLog.payload).where(AuditLog.action == "subscription_warning_3d_sent")
            )
        ).scalar_one())
        assert audit_row["campaign_variant"] == "renewal_3d"
        assert audit_row["offer_mode"] == "renewal"
        assert audit_row["recommended_reason_code"] == "renewal"
        assert audit_row["campaign_rule_key"] == "renewal_wave"
        assert audit_row["campaign_family"] == "renewal"
    finally:
        await _close_session(session, engine)


async def test_process_expired_subscriptions_prefers_limited_renewal_offer() -> None:
    session, engine = await _create_session()
    try:
        now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        _user, tariff, subscription = await _seed_subscription(
            session,
            started_at=now - timedelta(days=10),
            expires_at=now + timedelta(days=2, hours=12),
        )
        tariff.is_default_offer = True
        tariff.offer_group = "Base"
        session.add(
            Tariff(
                name="VIP 90",
                price_stars=600,
                duration_days=90,
                sort_order=20,
                is_active=True,
                channel_id=tariff.channel_id,
                offer_group="Base",
                offer_expires_at=now + timedelta(days=2),
            )
        )
        await session.commit()

        bot = RecordingBot()
        settings = Settings.model_validate(
            {
                "bot_token": "123:token",
                "admin_ids": [1],
                "bot_public_username": "privatair_bot",
            }
        )

        result = await process_expired_subscriptions(session, bot, now=now, settings=settings)

        assert result.warning_3d_count == 1
        assert [name for name, _ in bot.calls] == ["notify"]
        assert "VIP 90" in bot.calls[0][1]["text"]
        assert "?????????? ??" in bot.calls[0][1]["text"]
        audit_row = _decode_payload((
            await session.execute(
                select(AuditLog.payload).where(AuditLog.action == "subscription_warning_3d_sent")
            )
        ).scalar_one())
        assert audit_row["campaign_variant"] == "renewal_3d"
        assert audit_row["offer_mode"] == "renewal"
        assert audit_row["offer_strategy"] == "renewal_limited"
        assert audit_row["recommended_reason_code"] == "limited_renew"
        assert audit_row["limited_primary"] is True
        assert audit_row["bundle_count"] == 0
        assert audit_row["campaign_rule_key"] == "renewal_wave"
        assert audit_row["campaign_family"] == "renewal"
        refreshed = await session.get(Subscription, subscription.id)
        assert refreshed is not None and refreshed.warning_3d_sent_at == now
    finally:
        await _close_session(session, engine)


async def test_process_expired_subscriptions_sends_1d_warning_once() -> None:
    session, engine = await _create_session()
    try:
        now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        _, _, subscription = await _seed_subscription(
            session,
            started_at=now - timedelta(days=10),
            expires_at=now + timedelta(hours=20),
        )
        bot = RecordingBot()
        settings = Settings.model_validate(
            {
                "bot_token": "123:token",
                "admin_ids": [1],
                "bot_public_username": "privatair_bot",
            }
        )

        first = await process_expired_subscriptions(session, bot, now=now, settings=settings)
        second = await process_expired_subscriptions(
            session,
            bot,
            now=now + timedelta(minutes=30),
        )

        refreshed = await session.get(Subscription, subscription.id)

        assert first.warning_1d_count == 1
        assert second.warning_1d_count == 0
        assert refreshed is not None
        assert refreshed.warning_1d_sent_at == now
        assert [name for name, _ in bot.calls] == ["notify"]
        assert "VIP 42" in bot.calls[0][1]["text"]
        assert "start=buy_1" in bot.calls[0][1]["text"]
        audit_row = _decode_payload((
            await session.execute(
                select(AuditLog.payload).where(AuditLog.action == "subscription_warning_1d_sent")
            )
        ).scalar_one())
        assert audit_row["campaign_variant"] == "renewal_1d"
        assert audit_row["offer_mode"] == "renewal"
        assert audit_row["recommended_reason_code"] == "renewal"
        assert audit_row["campaign_rule_key"] == "renewal_wave"
        assert audit_row["campaign_family"] == "renewal"
    finally:
        await _close_session(session, engine)


async def test_process_expired_subscriptions_sends_expired_notice_once_and_delays_revoke() -> None:
    session, engine = await _create_session()
    try:
        now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        _, _, subscription = await _seed_subscription(
            session,
            started_at=now - timedelta(days=30),
            expires_at=now - timedelta(minutes=5),
        )
        bot = RecordingBot()
        settings = Settings.model_validate(
            {
                "bot_token": "123:token",
                "admin_ids": [1],
                "bot_public_username": "privatair_bot",
            }
        )

        first = await process_expired_subscriptions(
            session,
            bot,
            now=now,
            grace_period_hours=6,
            settings=settings,
        )
        second = await process_expired_subscriptions(
            session,
            bot,
            now=now + timedelta(hours=1),
            grace_period_hours=6,
        )

        refreshed = await session.get(Subscription, subscription.id)

        assert first.expired_notice_count == 1
        assert first.revoked_count == 0
        assert second.expired_notice_count == 0
        assert second.revoked_count == 0
        assert refreshed is not None
        assert refreshed.status == "active"
        assert refreshed.revoked_at is None
        assert refreshed.expired_notice_sent_at == now
        assert refreshed.grace_revoke_after == now + timedelta(hours=6)
        assert [name for name, _ in bot.calls] == ["notify"]
        assert "VIP 42" in bot.calls[0][1]["text"]
        assert "start=buy_1" in bot.calls[0][1]["text"]
        audit_row = _decode_payload((
            await session.execute(
                select(AuditLog.payload).where(
                    AuditLog.action == "subscription_expired_notice_sent"
                )
            )
        ).scalar_one())
        assert audit_row["campaign_variant"] == "grace_recovery"
        assert audit_row["offer_mode"] == "expired_grace"
        assert audit_row["recommended_reason_code"] == "return_primary"
        assert audit_row["campaign_rule_key"] == "grace_recovery_wave"
        assert audit_row["campaign_family"] == "grace_recovery"
    finally:
        await _close_session(session, engine)


async def test_after_grace_revoke_happens() -> None:
    session, engine = await _create_session()
    try:
        now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        _, _, subscription = await _seed_subscription(
            session,
            started_at=now - timedelta(days=30),
            expires_at=now - timedelta(hours=1),
            expired_notice_sent_at=now - timedelta(minutes=30),
            grace_revoke_after=now,
        )
        bot = AbsentUserBot()
        settings = Settings.model_validate(
            {
                "bot_token": "123:token",
                "admin_ids": [1],
                "bot_public_username": "privatair_bot",
            }
        )

        result = await process_expired_subscriptions(
            session,
            bot,
            now=now,
            grace_period_hours=6,
            settings=settings,
        )

        refreshed = await session.get(Subscription, subscription.id)

        assert result.revoked_count == 1
        assert refreshed is not None
        assert refreshed.status == "expired"
        assert refreshed.revoked_at == now
        assert any(
            name == "notify" and "start=buy_1" in payload["text"]
            for name, payload in bot.calls
        )
        audit_row = _decode_payload((
            await session.execute(
                select(AuditLog.payload).where(AuditLog.action == "subscription_expired")
            )
        ).scalar_one())
        assert audit_row["campaign_variant"] == "final_win_back"
        assert audit_row["offer_mode"] == "expired_final"
        assert audit_row["recommended_reason_code"] == "return_primary"
        assert audit_row["campaign_rule_key"] == "final_reactivation_wave"
        assert audit_row["campaign_family"] == "final_reactivation"
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


async def test_user_can_buy_again_after_revocation_worker() -> None:
    session, engine = await _create_session()
    try:
        now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        user, tariff, subscription = await _seed_subscription(
            session,
            started_at=now - timedelta(days=30),
            expires_at=now - timedelta(hours=1),
            expired_notice_sent_at=now - timedelta(minutes=30),
            grace_revoke_after=now,
        )
        bot = RecordingBot()

        await process_expired_subscriptions(session, bot, now=now)

        change = await activate_or_extend_subscription(
            session,
            user_id=user.id,
            tariff=tariff,
            paid_at=now + timedelta(minutes=5),
        )

        assert change.is_extension is False
        assert change.subscription.id != subscription.id
        assert change.subscription.status == "active"
    finally:
        await _close_session(session, engine)


async def test_per_user_errors_are_isolated() -> None:
    session, engine = await _create_session()
    try:
        now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        _, _, failing = await _seed_subscription(
            session,
            telegram_id=42,
            channel_suffix=1,
            started_at=now - timedelta(days=30),
            expires_at=now - timedelta(hours=1),
            expired_notice_sent_at=now - timedelta(minutes=30),
            grace_revoke_after=now,
        )
        _, _, healthy = await _seed_subscription(
            session,
            telegram_id=77,
            channel_suffix=2,
            started_at=now - timedelta(days=30),
            expires_at=now - timedelta(hours=1),
            expired_notice_sent_at=now - timedelta(minutes=30),
            grace_revoke_after=now,
        )
        bot = PartialFailureBot(fail_ban_for=42)

        result = await process_expired_subscriptions(session, bot, now=now)

        failing_refreshed = await session.get(Subscription, failing.id)
        healthy_refreshed = await session.get(Subscription, healthy.id)

        assert result.revoked_count == 1
        assert failing_refreshed is not None
        assert healthy_refreshed is not None
        assert failing_refreshed.status == "active"
        assert failing_refreshed.revoked_at is None
        assert healthy_refreshed.status == "expired"
        assert healthy_refreshed.revoked_at == now
    finally:
        await _close_session(session, engine)
