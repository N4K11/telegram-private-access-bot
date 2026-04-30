from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.runtime_state import record_maintenance_run
from app.services.payments.crypto_pay import reconcile_active_crypto_invoices
from app.workers.backup_worker import run_scheduled_backup_cycle
from app.workers.broadcast_sender import process_broadcast_campaigns
from app.workers.subscription_expirer import process_expired_subscriptions

logger = logging.getLogger(__name__)

DEFAULT_WORKER_INTERVAL_SECONDS = 60
ACTIVE_WORKER_INTERVAL_SECONDS = 1
DEFAULT_BROADCAST_RATE_LIMIT_PER_SECOND = 20


async def run_background_workers(
    *,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    stop_event: asyncio.Event,
    interval_seconds: int = DEFAULT_WORKER_INTERVAL_SECONDS,
    broadcast_rate_limit_per_second: int = DEFAULT_BROADCAST_RATE_LIMIT_PER_SECOND,
) -> None:
    while not stop_event.is_set():
        has_active_work = False
        try:
            async with session_factory() as session:
                expiration_result = await process_expired_subscriptions(
                    session,
                    bot,
                    grace_period_hours=settings.grace_period_hours,
                    warning_3d_enabled=settings.warning_3d_enabled,
                    warning_1d_enabled=settings.warning_1d_enabled,
                    timezone=settings.timezone,
                )
                if expiration_result.has_work:
                    logger.info(
                        (
                            "Subscription expiration cycle: warn3d=%s warn1d=%s "
                            "expired_notice=%s revoked=%s."
                        ),
                        expiration_result.warning_3d_count,
                        expiration_result.warning_1d_count,
                        expiration_result.expired_notice_count,
                        expiration_result.revoked_count,
                    )
                    has_active_work = True
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Subscription expiration worker cycle failed")

        try:
            async with session_factory() as session:
                broadcast_result = await process_broadcast_campaigns(
                    session,
                    bot,
                    rate_limit_per_second=broadcast_rate_limit_per_second,
                )
                if broadcast_result.processed_count:
                    logger.info(
                        "Processed %s broadcast deliveries.",
                        broadcast_result.processed_count,
                    )
                has_active_work = has_active_work or broadcast_result.active_campaign
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Broadcast worker cycle failed")

        try:
            async with session_factory() as session:
                backup_artifact = await run_scheduled_backup_cycle(session, bot, settings)
                if backup_artifact is not None:
                    logger.info("Created scheduled backup %s.", backup_artifact.file_name)
                    has_active_work = True
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Backup worker cycle failed")

        try:
            async with session_factory() as session:
                crypto_result = await reconcile_active_crypto_invoices(session, settings)
                if crypto_result.processed_count:
                    logger.info(
                        "Reconciled %s crypto invoices (paid=%s, expired=%s).",
                        crypto_result.processed_count,
                        crypto_result.paid_count,
                        crypto_result.expired_count,
                    )
                has_active_work = has_active_work or bool(
                    crypto_result.paid_count or crypto_result.expired_count
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Crypto reconciliation worker cycle failed")

        record_maintenance_run(label="background_workers")
        wait_timeout = ACTIVE_WORKER_INTERVAL_SECONDS if has_active_work else interval_seconds
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=wait_timeout)
        except TimeoutError:
            continue


@asynccontextmanager
async def background_workers(
    *,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    interval_seconds: int = DEFAULT_WORKER_INTERVAL_SECONDS,
    broadcast_rate_limit_per_second: int = DEFAULT_BROADCAST_RATE_LIMIT_PER_SECOND,
) -> AsyncIterator[None]:
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        run_background_workers(
            bot=bot,
            session_factory=session_factory,
            settings=settings,
            stop_event=stop_event,
            interval_seconds=interval_seconds,
            broadcast_rate_limit_per_second=broadcast_rate_limit_per_second,
        )
    )
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

