from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.repositories.broadcast_campaigns import BroadcastCampaignRepository
from app.db.repositories.broadcast_deliveries import BroadcastDeliveryRepository
from app.services.audit import write_audit_log
from app.services.broadcasts import get_broadcast_campaign_snapshot, get_next_broadcast_campaign
from app.utils.datetime import ensure_aware_utc, utcnow

logger = logging.getLogger(__name__)

SleepFunc = Callable[[float], Awaitable[None]]


@dataclass(slots=True)
class BroadcastWorkerResult:
    processed_count: int
    active_campaign: bool


async def _send_broadcast_message(
    bot: Bot,
    *,
    telegram_id: int,
    text: str,
    sleep_func: SleepFunc,
    max_attempts: int = 3,
) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            await bot.send_message(telegram_id, text)
            return
        except TelegramRetryAfter as exc:
            if attempt >= max_attempts:
                raise
            await sleep_func(max(float(exc.retry_after), 0.0))
        except TelegramForbiddenError:
            raise
        except TelegramAPIError:
            if attempt >= max_attempts:
                raise
            await sleep_func(float(attempt))


async def process_broadcast_campaigns(
    session: AsyncSession,
    bot: Bot,
    *,
    rate_limit_per_second: int,
    batch_size: int = 50,
    sleep_func: SleepFunc = asyncio.sleep,
    now: datetime | None = None,
) -> BroadcastWorkerResult:
    current_time = ensure_aware_utc(now or utcnow())
    campaign = await get_next_broadcast_campaign(session)
    if campaign is None:
        return BroadcastWorkerResult(processed_count=0, active_campaign=False)

    campaign_repository = BroadcastCampaignRepository(session)
    delivery_repository = BroadcastDeliveryRepository(session)
    if campaign.status == "queued":
        await campaign_repository.mark_sending(campaign, started_at=current_time)
        await session.commit()

    deliveries = await delivery_repository.list_pending_batch(campaign.id, limit=batch_size)
    if not deliveries:
        await campaign_repository.mark_completed(campaign, finished_at=current_time)
        await session.commit()
        await _notify_campaign_completed(session, bot, campaign.id)
        return BroadcastWorkerResult(processed_count=0, active_campaign=False)

    interval_seconds = 1 / max(rate_limit_per_second, 1)
    sent_delta = 0
    failed_delta = 0
    blocked_delta = 0

    for item in deliveries:
        try:
            await _send_broadcast_message(
                bot,
                telegram_id=item.telegram_id,
                text=campaign.content,
                sleep_func=sleep_func,
            )
        except TelegramForbiddenError as exc:
            blocked_delta += 1
            await delivery_repository.mark_blocked(item.delivery, error_message=str(exc))
        except Exception as exc:
            failed_delta += 1
            logger.exception(
                "Broadcast delivery %s failed for telegram user %s",
                item.delivery.id,
                item.telegram_id,
            )
            await delivery_repository.mark_failed(item.delivery, error_message=str(exc))
        else:
            sent_delta += 1
            await delivery_repository.mark_sent(item.delivery, sent_at=ensure_aware_utc(utcnow()))
        await sleep_func(interval_seconds)

    campaign.sent_count += sent_delta
    campaign.failed_count += failed_delta
    await session.commit()

    pending_count = await delivery_repository.count_pending(campaign.id)
    if pending_count == 0:
        await campaign_repository.mark_completed(campaign, finished_at=ensure_aware_utc(utcnow()))
        await session.commit()
        await _notify_campaign_completed(session, bot, campaign.id)
        active_campaign = False
    else:
        active_campaign = True

    if sent_delta or failed_delta or blocked_delta:
        await write_audit_log(
            session,
            action="broadcast_batch_processed",
            target_user_id=campaign.created_by_user_id,
            payload={
                "campaign_id": campaign.id,
                "sent": sent_delta,
                "failed": failed_delta,
                "blocked": blocked_delta,
                "remaining": pending_count,
            },
        )
        await session.commit()

    return BroadcastWorkerResult(
        processed_count=sent_delta + failed_delta + blocked_delta,
        active_campaign=active_campaign,
    )


async def _notify_campaign_completed(session: AsyncSession, bot: Bot, campaign_id: int) -> None:
    snapshot = await get_broadcast_campaign_snapshot(session, campaign_id)
    if snapshot is None:
        return

    if snapshot.campaign.created_by_user_id is None:
        return

    creator = await session.scalar(
        select(User).where(User.id == snapshot.campaign.created_by_user_id)
    )
    if creator is None:
        return

    remaining = snapshot.remaining_count
    text = "\n".join(
        [
            "Рассылка завершена.",
            "",
            f"Кампания: #{snapshot.campaign.id}",
            f"Фильтр: {snapshot.filter_label}",
            f"Отправлено: {snapshot.campaign.sent_count}",
            f"Ошибок: {snapshot.campaign.failed_count}",
            f"Заблокировали бота: {snapshot.blocked_count}",
            f"Осталось: {remaining}",
        ]
    )
    try:
        await bot.send_message(creator.telegram_id, text)
    except Exception:
        logger.exception(
            "Failed to notify broadcast creator %s about campaign %s",
            creator.telegram_id,
            campaign_id,
        )