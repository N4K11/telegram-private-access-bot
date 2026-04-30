from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Subscription
from app.db.repositories.subscriptions import SubscriptionRepository
from app.services.audit import write_audit_log
from app.services.texts import render_text
from app.utils.datetime import ensure_aware_utc, format_datetime, utcnow

logger = logging.getLogger(__name__)

MAX_REMOVE_RETRIES = 3
ABSENT_MEMBER_FRAGMENTS = (
    "user not participant",
    "participant_id_invalid",
    "user not found",
    "chat not found",
    "member not found",
)


@dataclass(slots=True)
class SubscriptionExpirationProcessingResult:
    warning_3d_count: int = 0
    warning_1d_count: int = 0
    expired_notice_count: int = 0
    revoked_count: int = 0

    @property
    def processed_count(self) -> int:
        return (
            self.warning_3d_count
            + self.warning_1d_count
            + self.expired_notice_count
            + self.revoked_count
        )

    @property
    def has_work(self) -> bool:
        return self.processed_count > 0


async def remove_user_from_channel(
    bot: Bot | Any,
    *,
    channel_chat_id: int,
    telegram_user_id: int,
    now: datetime | None = None,
    sleep_func: Callable[[float], Awaitable[None]] = asyncio.sleep,
    max_attempts: int = MAX_REMOVE_RETRIES,
) -> None:
    ban_until = ensure_aware_utc(now or utcnow())

    for attempt in range(1, max_attempts + 1):
        try:
            await bot.ban_chat_member(
                chat_id=channel_chat_id,
                user_id=telegram_user_id,
                until_date=ban_until,
            )
            await bot.unban_chat_member(
                chat_id=channel_chat_id,
                user_id=telegram_user_id,
                only_if_banned=True,
            )
            return
        except TelegramRetryAfter as exc:
            if attempt >= max_attempts:
                raise
            retry_after = float(getattr(exc, "retry_after", 0) or 0)
            await sleep_func(retry_after)
        except TelegramBadRequest as exc:
            if _is_absent_member_error(exc):
                return
            raise


async def process_expired_subscriptions(
    session: AsyncSession,
    bot: Bot | Any,
    *,
    now: datetime | None = None,
    batch_limit: int = 100,
    grace_period_hours: int = 6,
    warning_3d_enabled: bool = True,
    warning_1d_enabled: bool = True,
    timezone: str = "UTC",
) -> SubscriptionExpirationProcessingResult:
    processed_at = ensure_aware_utc(now or utcnow())
    repository = SubscriptionRepository(session)
    result = SubscriptionExpirationProcessingResult()
    has_mutations = False

    if warning_3d_enabled:
        subscriptions = await repository.list_due_for_warning_3d(
            at_time=processed_at,
            limit=batch_limit,
        )
        for subscription in subscriptions:
            sent = await _send_subscription_message(
                session,
                bot,
                subscription=subscription,
                text_key="subscription_warning_3d",
                timezone=timezone,
            )
            if not sent:
                continue
            subscription.warning_3d_sent_at = processed_at
            result.warning_3d_count += 1
            has_mutations = True
            await write_audit_log(
                session,
                action="subscription_warning_3d_sent",
                target_user_id=subscription.user_id,
                payload={
                    "subscription_id": subscription.id,
                    "tariff_id": subscription.tariff_id,
                    "channel_id": subscription.channel_id,
                    "expires_at": subscription.expires_at.isoformat(),
                },
            )

    if warning_1d_enabled:
        subscriptions = await repository.list_due_for_warning_1d(
            at_time=processed_at,
            limit=batch_limit,
        )
        for subscription in subscriptions:
            sent = await _send_subscription_message(
                session,
                bot,
                subscription=subscription,
                text_key="subscription_warning_1d",
                timezone=timezone,
            )
            if not sent:
                continue
            subscription.warning_1d_sent_at = processed_at
            result.warning_1d_count += 1
            has_mutations = True
            await write_audit_log(
                session,
                action="subscription_warning_1d_sent",
                target_user_id=subscription.user_id,
                payload={
                    "subscription_id": subscription.id,
                    "tariff_id": subscription.tariff_id,
                    "channel_id": subscription.channel_id,
                    "expires_at": subscription.expires_at.isoformat(),
                },
            )

    expired_subscriptions = await repository.list_due_for_expired_notice(
        at_time=processed_at,
        limit=batch_limit,
    )
    for subscription in expired_subscriptions:
        if subscription.grace_revoke_after is None:
            subscription.grace_revoke_after = processed_at + timedelta(hours=grace_period_hours)
            has_mutations = True

        sent = await _send_subscription_message(
            session,
            bot,
            subscription=subscription,
            text_key="subscription_expired_grace",
            timezone=timezone,
            grace_period_hours=grace_period_hours,
        )
        if not sent:
            continue
        subscription.expired_notice_sent_at = processed_at
        result.expired_notice_count += 1
        has_mutations = True
        await write_audit_log(
            session,
            action="subscription_expired_notice_sent",
            target_user_id=subscription.user_id,
            payload={
                "subscription_id": subscription.id,
                "tariff_id": subscription.tariff_id,
                "channel_id": subscription.channel_id,
                "expired_at": subscription.expires_at.isoformat(),
                "grace_revoke_after": subscription.grace_revoke_after.isoformat()
                if subscription.grace_revoke_after is not None
                else None,
            },
        )

    revoke_subscriptions = await repository.list_due_for_grace_revoke(
        at_time=processed_at,
        limit=batch_limit,
    )
    for subscription in revoke_subscriptions:
        channel = subscription.channel
        user = subscription.user
        if channel is None or user is None:
            logger.warning(
                "Skipping revoke for subscription %s because relations are missing.",
                subscription.id,
            )
            continue

        try:
            await remove_user_from_channel(
                bot,
                channel_chat_id=channel.telegram_chat_id,
                telegram_user_id=user.telegram_id,
                now=processed_at,
            )
        except Exception:
            logger.exception(
                "Failed to revoke access for subscription %s (user %s, channel %s)",
                subscription.id,
                subscription.user_id,
                subscription.channel_id,
            )
            continue

        subscription.status = "expired"
        subscription.revoked_at = processed_at
        result.revoked_count += 1
        has_mutations = True

        await write_audit_log(
            session,
            action="subscription_expired",
            target_user_id=subscription.user_id,
            payload={
                "subscription_id": subscription.id,
                "tariff_id": subscription.tariff_id,
                "channel_id": subscription.channel_id,
                "expired_at": subscription.expires_at.isoformat(),
                "grace_revoke_after": subscription.grace_revoke_after.isoformat()
                if subscription.grace_revoke_after is not None
                else None,
                "revoked_at": processed_at.isoformat(),
            },
        )

        try:
            notification_text = await render_text(
                session,
                "subscription_expired",
                channel_name=channel.title,
            )
            await bot.send_message(user.telegram_id, notification_text)
        except Exception:
            logger.exception(
                "Failed to notify user %s about revoked subscription %s",
                user.telegram_id,
                subscription.id,
            )

    if has_mutations:
        await session.commit()

    return result


async def _send_subscription_message(
    session: AsyncSession,
    bot: Bot | Any,
    *,
    subscription: Subscription,
    text_key: str,
    timezone: str,
    grace_period_hours: int | None = None,
) -> bool:
    channel = subscription.channel
    user = subscription.user
    if channel is None or user is None:
        logger.warning(
            "Skipping %s for subscription %s because relations are missing.",
            text_key,
            subscription.id,
        )
        return False

    try:
        text = await render_text(
            session,
            text_key,
            channel_name=channel.title,
            expires_at=format_datetime(subscription.expires_at, timezone),
            expired_at=format_datetime(subscription.expires_at, timezone),
            grace_period_hours=grace_period_hours or 0,
        )
        await bot.send_message(user.telegram_id, text)
        return True
    except Exception:
        logger.exception(
            "Failed to send %s to user %s for subscription %s",
            text_key,
            user.telegram_id,
            subscription.id,
        )
        return False



def _is_absent_member_error(exc: TelegramBadRequest) -> bool:
    message = str(exc).lower()
    return any(fragment in message for fragment in ABSENT_MEMBER_FRAGMENTS)
