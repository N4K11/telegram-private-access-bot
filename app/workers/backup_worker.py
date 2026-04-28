from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.repositories.backup_records import BackupRecordRepository
from app.services.audit import write_audit_log
from app.services.backups import (
    apply_backup_retention,
    create_backup_archive,
    mark_backup_delivery,
    send_backup_to_admins,
)
from app.utils.datetime import ensure_aware_utc, resolve_timezone, utcnow

logger = logging.getLogger(__name__)


async def run_scheduled_backup_cycle(
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
    *,
    now: datetime | None = None,
):
    if not settings.backup_enabled:
        return None

    current_time = ensure_aware_utc(now or utcnow())
    if not _is_backup_due(settings, current_time):
        return None

    latest = await BackupRecordRepository(session).get_latest_for_label("daily")
    if latest is not None:
        latest_local_date = ensure_aware_utc(latest.created_at).astimezone(
            resolve_timezone(settings.timezone)
        ).date()
        current_local_date = current_time.astimezone(resolve_timezone(settings.timezone)).date()
        if latest_local_date == current_local_date:
            return None

    artifact = await create_backup_archive(
        session,
        backup_root=settings.backup_directory,
        label="daily",
        now=current_time,
    )
    await write_audit_log(
        session,
        action="backup_created_scheduled",
        payload={
            "backup_record_id": artifact.record.id,
            "file_name": artifact.file_name,
            "size_bytes": artifact.size_bytes,
        },
    )
    await apply_backup_retention(
        session,
        backup_root=settings.backup_directory,
        retention_days=settings.backup_retention_days,
        now=current_time,
    )
    await session.commit()

    if settings.backup_send_to_admin and settings.admin_ids:
        delivered = await send_backup_to_admins(
            bot,
            admin_ids=settings.admin_ids,
            record=artifact.record,
        )
        try:
            await mark_backup_delivery(
                session,
                artifact.record,
                delivered=delivered,
                now=current_time,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception(
                "Failed to update backup delivery status for record %s",
                artifact.record.id,
            )

    return artifact


def _is_backup_due(settings: Settings, current_time: datetime) -> bool:
    timezone = resolve_timezone(settings.timezone)
    local_time = current_time.astimezone(timezone)
    hour, minute = _parse_backup_time(settings.backup_time)
    return local_time.hour > hour or (
        local_time.hour == hour and local_time.minute >= minute
    )


def _parse_backup_time(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.split(":", maxsplit=1)
        hour = max(0, min(23, int(hour_text)))
        minute = max(0, min(59, int(minute_text)))
        return hour, minute
    except Exception:
        return 3, 0