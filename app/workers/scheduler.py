from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.runtime_state import (
    record_backup_result,
    record_crypto_reconcile_error,
    record_crypto_reconcile_run,
    record_maintenance_run,
    record_worker_status,
)
from app.services.channel_guard_service import run_channel_guard_cycle
from app.services.observability import EVENT_WORKER_CYCLE_FAILED
from app.services.payments.crypto_pay import reconcile_active_crypto_invoices
from app.services.report_service import dispatch_scheduled_admin_reports
from app.services.retention_automation import process_retention_messages
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
                    settings=settings,
                )
                details = (
                    f"warn3d={expiration_result.warning_3d_count}, "
                    f"warn1d={expiration_result.warning_1d_count}, "
                    f"expired_notice={expiration_result.expired_notice_count}, "
                    f"revoked={expiration_result.revoked_count}"
                )
                record_worker_status("subscription_expirer", "ok", details=details)
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
        except Exception as exc:
            details = f"{exc.__class__.__name__}: {exc}"
            record_worker_status("subscription_expirer", "fail", details=details)
            logger.exception(
                "Subscription expiration worker cycle failed",
                extra={
                    "event_name": EVENT_WORKER_CYCLE_FAILED,
                    "worker_name": "subscription_expirer",
                },
            )

        try:
            async with session_factory() as session:
                broadcast_result = await process_broadcast_campaigns(
                    session,
                    bot,
                    rate_limit_per_second=broadcast_rate_limit_per_second,
                )
                record_worker_status(
                    "broadcast_sender",
                    "ok",
                    details=(
                        f"processed={broadcast_result.processed_count}, "
                        f"active_campaign={broadcast_result.active_campaign}"
                    ),
                )
                if broadcast_result.processed_count:
                    logger.info(
                        "Processed %s broadcast deliveries.",
                        broadcast_result.processed_count,
                    )
                has_active_work = has_active_work or broadcast_result.active_campaign
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            details = f"{exc.__class__.__name__}: {exc}"
            record_worker_status("broadcast_sender", "fail", details=details)
            logger.exception(
                "Broadcast worker cycle failed",
                extra={"event_name": EVENT_WORKER_CYCLE_FAILED, "worker_name": "broadcast_sender"},
            )

        try:
            async with session_factory() as session:
                backup_artifact = await run_scheduled_backup_cycle(session, bot, settings)
                if backup_artifact is not None:
                    logger.info("Created scheduled backup %s.", backup_artifact.file_name)
                    record_backup_result("ok", backup_artifact.file_name)
                    record_worker_status(
                        "backup_worker",
                        "ok",
                        details=f"created={backup_artifact.file_name}",
                    )
                    has_active_work = True
                else:
                    record_worker_status("backup_worker", "ok", details="no scheduled backup")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            details = f"{exc.__class__.__name__}: {exc}"
            record_backup_result("fail", details)
            record_worker_status("backup_worker", "fail", details=details)
            logger.exception(
                "Backup worker cycle failed",
                extra={"event_name": EVENT_WORKER_CYCLE_FAILED, "worker_name": "backup_worker"},
            )

        try:
            async with session_factory() as session:
                crypto_result = await reconcile_active_crypto_invoices(session, settings)
                record_crypto_reconcile_run(
                    processed_count=crypto_result.processed_count,
                    paid_count=crypto_result.paid_count,
                    expired_count=crypto_result.expired_count,
                    active_invoice_count=crypto_result.active_invoice_count,
                )
                record_worker_status(
                    "crypto_reconciler",
                    "ok",
                    details=(
                        f"processed={crypto_result.processed_count}, "
                        f"paid={crypto_result.paid_count}, "
                        f"expired={crypto_result.expired_count}, "
                        f"active={crypto_result.active_invoice_count}"
                    ),
                )
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
        except Exception as exc:
            details = f"{exc.__class__.__name__}: {exc}"
            record_crypto_reconcile_error(details)
            record_worker_status("crypto_reconciler", "fail", details=details)
            logger.exception(
                "Crypto reconciliation worker cycle failed",
                extra={"event_name": EVENT_WORKER_CYCLE_FAILED, "worker_name": "crypto_reconciler"},
            )

        try:
            async with session_factory() as session:
                channel_guard_result = await run_channel_guard_cycle(
                    session=session,
                    bot=bot,
                    admin_ids=settings.admin_ids_set,
                )
                if channel_guard_result.has_issues:
                    details = (
                        f"issues={len(channel_guard_result.issues)}, "
                        f"sent={len(channel_guard_result.notified_admin_ids)}"
                    )
                    if channel_guard_result.suppressed:
                        details += ', suppressed=yes'
                    record_worker_status("channel_guard", "warn", details=details)
                    has_active_work = has_active_work or channel_guard_result.alert_sent
                elif channel_guard_result.get_me_error:
                    record_worker_status(
                        "channel_guard",
                        "fail",
                        details=f"getMe unavailable: {channel_guard_result.get_me_error}",
                    )
                else:
                    record_worker_status(
                        "channel_guard",
                        "ok",
                        details=f"checked={channel_guard_result.checked_channel_count}",
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            details = f"{exc.__class__.__name__}: {exc}"
            record_worker_status("channel_guard", "fail", details=details)
            logger.exception(
                "Channel guard worker cycle failed",
                extra={"event_name": EVENT_WORKER_CYCLE_FAILED, "worker_name": "channel_guard"},
            )

        try:
            async with session_factory() as session:
                report_result = await dispatch_scheduled_admin_reports(
                    session,
                    bot,
                    settings,
                )
                if report_result.not_due:
                    record_worker_status("admin_reports", "ok", details="not due")
                elif report_result.sent_periods:
                    details = "sent=" + ",".join(report_result.sent_periods)
                    if report_result.skipped_periods:
                        details += "; skipped=" + ",".join(report_result.skipped_periods)
                    record_worker_status("admin_reports", "ok", details=details)
                    has_active_work = True
                else:
                    details = "skipped=" + ",".join(report_result.skipped_periods or ("none",))
                    record_worker_status("admin_reports", "ok", details=details)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            details = f"{exc.__class__.__name__}: {exc}"
            record_worker_status("admin_reports", "fail", details=details)
            logger.exception(
                "Admin report worker cycle failed",
                extra={"event_name": EVENT_WORKER_CYCLE_FAILED, "worker_name": "admin_reports"},
            )

        try:
            async with session_factory() as session:
                retention_result = await process_retention_messages(session, bot, settings)
                details = (
                    f"sent={retention_result.sent_count}, "
                    f"failed={retention_result.failed_count}, "
                    f"candidates={sum(retention_result.segment_candidate_counts.values())}"
                )
                record_worker_status("retention_automation", "ok", details=details)
                if retention_result.processed_count:
                    logger.info(
                        "Retention cycle: sent=%s failed=%s skipped=%s candidates=%s.",
                        retention_result.sent_count,
                        retention_result.failed_count,
                        retention_result.skipped_count,
                        sum(retention_result.segment_candidate_counts.values()),
                    )
                has_active_work = has_active_work or retention_result.has_work
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            details = f"{exc.__class__.__name__}: {exc}"
            record_worker_status("retention_automation", "fail", details=details)
            logger.exception(
                "Retention automation worker cycle failed",
                extra={
                    "event_name": EVENT_WORKER_CYCLE_FAILED,
                    "worker_name": "retention_automation",
                },
            )
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



