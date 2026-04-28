from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.subscriptions import SubscriptionRepository
from app.services.audit import write_audit_log
from app.services.texts import render_text
from app.utils.datetime import ensure_aware_utc, utcnow

logger = logging.getLogger(__name__)

MAX_REMOVE_RETRIES = 3
ABSENT_MEMBER_FRAGMENTS = (
    "user not participant",
    "participant_id_invalid",
    "user not found",
    "chat not found",
    "member not found",
)


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
) -> int:
    processed_at = ensure_aware_utc(now or utcnow())
    repository = SubscriptionRepository(session)
    subscriptions = await repository.list_expired_for_processing(
        at_time=processed_at,
        limit=batch_limit,
    )

    processed = 0
    for subscription in subscriptions:
        channel = subscription.channel
        user = subscription.user
        if channel is None or user is None:
            logger.warning(
                "Skipping expired subscription %s because relations are missing.",
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
        processed += 1

        await write_audit_log(
            session,
            action="subscription_expired",
            target_user_id=subscription.user_id,
            payload={
                "subscription_id": subscription.id,
                "tariff_id": subscription.tariff_id,
                "channel_id": subscription.channel_id,
                "expired_at": processed_at.isoformat(),
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
                "Failed to notify user %s about expired subscription %s",
                user.telegram_id,
                subscription.id,
            )

    if processed:
        await session.commit()

    return processed


def _is_absent_member_error(exc: TelegramBadRequest) -> bool:
    message = str(exc).lower()
    return any(fragment in message for fragment in ABSENT_MEMBER_FRAGMENTS)