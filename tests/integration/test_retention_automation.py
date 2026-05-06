from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.base import Base
from app.db.models import AuditLog, Channel, InviteLink, Payment, Subscription, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.services.retention_automation import (
    SEGMENT_EXPIRED_RECENTLY,
    SEGMENT_FIRST_PAYMENT_FOLLOW_UP,
    SEGMENT_INACTIVE_PAID,
    SEGMENT_LOST_AFTER_TRIAL,
    SEGMENT_PENDING_JOIN,
    process_retention_messages,
)


def _decode_payload(raw_payload):
    if raw_payload is None:
        return {}
    if isinstance(raw_payload, str):
        return json.loads(raw_payload or "{}")
    return raw_payload


class RecordingBot:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> bool:
        self.sent_messages.append((chat_id, text))
        return True


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


async def _seed_retention_data(session: AsyncSession, *, now: datetime) -> None:
    main_channel = Channel(
        telegram_chat_id=-1001234567890,
        title="Private channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    trial_channel = Channel(
        telegram_chat_id=-1001234567891,
        title="Trial channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add_all([main_channel, trial_channel])
    await session.flush()

    regular_tariff = Tariff(
        name="Base 30",
        price_stars=250,
        duration_days=30,
        sort_order=10,
        is_active=True,
        is_default_offer=True,
        channel_id=main_channel.id,
        offer_group="Base",
    )
    limited_tariff = Tariff(
        name="Base 90",
        price_stars=600,
        duration_days=90,
        sort_order=20,
        is_active=True,
        channel_id=main_channel.id,
        offer_group="Base",
        offer_expires_at=now + timedelta(days=2),
    )
    trial_tariff = Tariff(
        name="Trial 3",
        price_stars=1,
        duration_days=3,
        sort_order=5,
        is_active=True,
        channel_id=trial_channel.id,
        is_trial=True,
    )
    session.add_all([regular_tariff, limited_tariff, trial_tariff])
    await session.flush()

    users = [
        User(telegram_id=1001, first_name="First follow-up", role="user"),
        User(telegram_id=1002, first_name="Pending join", role="user"),
        User(telegram_id=1003, first_name="Win back", role="user"),
        User(telegram_id=1004, first_name="Inactive paid", role="user"),
        User(telegram_id=1005, first_name="Lost after trial", role="user"),
        User(telegram_id=1006, first_name="Blocked", role="user", is_blocked=True),
    ]
    session.add_all(users)
    await session.flush()

    first_user, pending_user, win_back_user, inactive_user, trial_user, blocked_user = users

    session.add_all(
        [
            Payment(
                user_id=first_user.id,
                tariff_id=regular_tariff.id,
                channel_id=main_channel.id,
                amount=250,
                currency="XTR",
                provider="telegram_stars",
                telegram_payment_charge_id="retention-first-1",
                provider_payment_charge_id="provider-first-1",
                invoice_payload="subscription:1001",
                paid_at=now - timedelta(hours=2),
                status="paid",
            ),
            Payment(
                user_id=pending_user.id,
                tariff_id=regular_tariff.id,
                channel_id=main_channel.id,
                amount=250,
                currency="XTR",
                provider="telegram_stars",
                telegram_payment_charge_id="retention-pending-1",
                provider_payment_charge_id="provider-pending-1",
                invoice_payload="subscription:1002",
                paid_at=now - timedelta(hours=36),
                status="paid",
            ),
            Payment(
                user_id=win_back_user.id,
                tariff_id=regular_tariff.id,
                channel_id=main_channel.id,
                amount=250,
                currency="XTR",
                provider="telegram_stars",
                telegram_payment_charge_id="retention-winback-1",
                provider_payment_charge_id="provider-winback-1",
                invoice_payload="subscription:1003",
                paid_at=now - timedelta(days=5),
                status="paid",
            ),
            Payment(
                user_id=inactive_user.id,
                tariff_id=regular_tariff.id,
                channel_id=main_channel.id,
                amount=250,
                currency="XTR",
                provider="telegram_stars",
                telegram_payment_charge_id="retention-inactive-1",
                provider_payment_charge_id="provider-inactive-1",
                invoice_payload="subscription:1004",
                paid_at=now - timedelta(days=20),
                status="paid",
            ),
            Payment(
                user_id=trial_user.id,
                tariff_id=trial_tariff.id,
                channel_id=trial_channel.id,
                amount=1,
                currency="XTR",
                provider="telegram_stars",
                telegram_payment_charge_id="retention-trial-1",
                provider_payment_charge_id="provider-trial-1",
                invoice_payload="subscription:1005",
                paid_at=now - timedelta(days=4),
                status="paid",
            ),
            Payment(
                user_id=blocked_user.id,
                tariff_id=regular_tariff.id,
                channel_id=main_channel.id,
                amount=250,
                currency="XTR",
                provider="telegram_stars",
                telegram_payment_charge_id="retention-blocked-1",
                provider_payment_charge_id="provider-blocked-1",
                invoice_payload="subscription:1006",
                paid_at=now - timedelta(hours=1),
                status="paid",
            ),
        ]
    )
    await session.flush()

    subscriptions = [
        Subscription(
            user_id=first_user.id,
            tariff_id=regular_tariff.id,
            channel_id=main_channel.id,
            status="active",
            source="purchase",
            started_at=now - timedelta(hours=2),
            expires_at=now + timedelta(days=30),
        ),
        Subscription(
            user_id=pending_user.id,
            tariff_id=regular_tariff.id,
            channel_id=main_channel.id,
            status="active",
            source="purchase",
            started_at=now - timedelta(hours=36),
            expires_at=now + timedelta(days=30),
        ),
        Subscription(
            user_id=win_back_user.id,
            tariff_id=regular_tariff.id,
            channel_id=main_channel.id,
            status="active",
            source="purchase",
            started_at=now - timedelta(days=35),
            expires_at=now - timedelta(days=2),
        ),
        Subscription(
            user_id=inactive_user.id,
            tariff_id=regular_tariff.id,
            channel_id=main_channel.id,
            status="active",
            source="purchase",
            started_at=now - timedelta(days=50),
            expires_at=now - timedelta(days=15),
        ),
        Subscription(
            user_id=trial_user.id,
            tariff_id=trial_tariff.id,
            channel_id=trial_channel.id,
            status="active",
            source="purchase",
            started_at=now - timedelta(days=6),
            expires_at=now - timedelta(days=2),
        ),
        Subscription(
            user_id=blocked_user.id,
            tariff_id=regular_tariff.id,
            channel_id=main_channel.id,
            status="active",
            source="purchase",
            started_at=now - timedelta(hours=1),
            expires_at=now + timedelta(days=30),
        ),
    ]
    session.add_all(subscriptions)
    await session.flush()

    session.add(
        InviteLink(
            user_id=pending_user.id,
            channel_id=main_channel.id,
            subscription_id=subscriptions[1].id,
            invite_link="https://t.me/+pending-join",
            expire_at=now + timedelta(hours=10),
            member_limit=1,
            is_revoked=False,
        )
    )
    await session.commit()


async def test_process_retention_messages_sends_segmented_lifecycle_touches(
    session: AsyncSession,
) -> None:
    now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    await _seed_retention_data(session, now=now)
    bot = RecordingBot()
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [1],
            "bot_public_username": "privatair_bot",
            "timezone": "UTC",
        }
    )

    first_result = await process_retention_messages(session, bot, settings, now=now)
    second_result = await process_retention_messages(session, bot, settings, now=now)

    assert first_result.sent_count == 5
    assert first_result.failed_count == 0
    assert first_result.segment_candidate_counts == {
        SEGMENT_FIRST_PAYMENT_FOLLOW_UP: 1,
        SEGMENT_PENDING_JOIN: 1,
        SEGMENT_EXPIRED_RECENTLY: 1,
        SEGMENT_INACTIVE_PAID: 1,
        SEGMENT_LOST_AFTER_TRIAL: 1,
    }
    assert first_result.segment_sent_counts == {
        SEGMENT_FIRST_PAYMENT_FOLLOW_UP: 1,
        SEGMENT_PENDING_JOIN: 1,
        SEGMENT_EXPIRED_RECENTLY: 1,
        SEGMENT_INACTIVE_PAID: 1,
        SEGMENT_LOST_AFTER_TRIAL: 1,
    }
    assert len(bot.sent_messages) == 5
    assert any("start=buy_1" in text for _, text in bot.sent_messages)
    assert any("start=link" in text for _, text in bot.sent_messages)
    by_user = {chat_id: text for chat_id, text in bot.sent_messages}
    assert "Base 90" in by_user[1003]
    assert "Base 90" in by_user[1004]
    assert "Base 90" in by_user[1005]
    assert "?????????? ??" in by_user[1003]
    assert "?????????? ??" in by_user[1004]
    assert "?????????? ??" in by_user[1005]
    assert "start=buy_1" in by_user[1003]
    assert "start=buy_1" in by_user[1004]
    assert "start=buy_1" in by_user[1005]

    audit_rows = list(
        (
            await session.execute(
                select(AuditLog.action, AuditLog.payload)
                .where(AuditLog.action.like("retention_%_sent"))
                .order_by(AuditLog.action.asc())
            )
        ).all()
    )
    actions = [action for action, _payload in audit_rows]
    assert actions == [
        "retention_first_payment_follow_up_sent",
        "retention_inactive_paid_sent",
        "retention_lost_after_trial_sent",
        "retention_pending_join_sent",
        "retention_win_back_sent",
    ]
    payload_by_action = {action: _decode_payload(payload) for action, payload in audit_rows}
    assert (
        payload_by_action["retention_lost_after_trial_sent"]["campaign_variant"]
        == "trial_to_paid"
    )
    assert (
        payload_by_action["retention_lost_after_trial_sent"]["offer_strategy"]
        == "trial_to_limited"
    )
    assert (
        payload_by_action["retention_lost_after_trial_sent"]["recommended_reason_code"]
        == "limited_product"
    )
    assert payload_by_action["retention_lost_after_trial_sent"]["limited_primary"] is True
    assert payload_by_action["retention_lost_after_trial_sent"]["bundle_count"] == 1
    assert payload_by_action["retention_lost_after_trial_sent"]["cross_sell_count"] == 0
    assert (
        payload_by_action["retention_lost_after_trial_sent"]["campaign_rule_key"]
        == "trial_recovery_wave"
    )
    assert (
        payload_by_action["retention_lost_after_trial_sent"]["campaign_family"]
        == "trial_recovery"
    )
    assert payload_by_action["retention_win_back_sent"]["campaign_variant"] == "win_back_recent"
    assert payload_by_action["retention_win_back_sent"]["offer_strategy"] == "win_back_limited"
    assert payload_by_action["retention_win_back_sent"]["limited_primary"] is True
    assert payload_by_action["retention_win_back_sent"]["campaign_rule_key"] == "win_back_wave"
    assert payload_by_action["retention_win_back_sent"]["campaign_family"] == "win_back"
    assert payload_by_action["retention_inactive_paid_sent"]["campaign_variant"] == "reactivation"
    assert (
        payload_by_action["retention_inactive_paid_sent"]["offer_strategy"]
        == "reactivation_limited"
    )
    assert (
        payload_by_action["retention_inactive_paid_sent"]["campaign_rule_key"]
        == "reactivation_wave"
    )
    assert payload_by_action["retention_inactive_paid_sent"]["campaign_family"] == "reactivation"

    assert second_result.sent_count == 0
    assert second_result.failed_count == 0

