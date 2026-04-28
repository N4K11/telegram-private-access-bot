# ruff: noqa: E501
from __future__ import annotations

import json
import logging
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.types import FSInputFile, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AuditLog,
    BackupRecord,
    BroadcastCampaign,
    BroadcastDelivery,
    Channel,
    CryptoInvoice,
    InviteLink,
    Payment,
    Subscription,
    Tariff,
    TextTemplate,
    User,
)
from app.db.repositories.backup_records import BackupRecordRepository
from app.utils.datetime import ensure_aware_utc, utcnow

logger = logging.getLogger(__name__)

BACKUP_FILE_PREFIX = "backup"
BACKUP_STATUS_CREATED = "created"
BACKUP_STATUS_SENT = "sent"
BACKUP_STATUS_SEND_FAILED = "send_failed"
BACKUP_STATUS_PRUNED = "pruned"

RESTORE_INSTRUCTIONS = """\
Restore instructions
====================

1. Stop the bot before touching the database.
2. Extract this archive into a safe directory.
3. Review database/export.json and metadata.json.
4. Run database migrations on the target environment before importing data.
5. This backup intentionally excludes .env and other runtime secrets. Restore secrets separately.
6. After import, verify active subscriptions, tariffs, channels and payment history.
""".strip()

MODELS_TO_BACKUP = (
    User,
    Channel,
    Tariff,
    Subscription,
    Payment,
    InviteLink,
    AuditLog,
    TextTemplate,
    BroadcastCampaign,
    BroadcastDelivery,
    BackupRecord,
    CryptoInvoice,
)


@dataclass(frozen=True, slots=True)
class BackupArtifact:
    record: BackupRecord
    file_path: Path
    file_name: str
    size_bytes: int
    created_at: datetime
    label: str


async def create_backup_archive(
    session: AsyncSession,
    *,
    backup_root: str | Path,
    label: str = "manual",
    now: datetime | None = None,
) -> BackupArtifact:
    created_at = ensure_aware_utc(now or utcnow())
    backup_dir = Path(backup_root)
    backup_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"{label}-{BACKUP_FILE_PREFIX}-{created_at:%Y%m%d-%H%M%S}.zip"
    file_path = backup_dir / file_name

    payload = await _build_database_payload(session)
    metadata = {
        "created_at": created_at.isoformat(),
        "label": label,
        "format": "json-export-v1",
        "tables": {table_name: len(rows) for table_name, rows in payload.items()},
        "secret_files_excluded": True,
    }

    with zipfile.ZipFile(file_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "metadata.json",
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True),
        )
        archive.writestr(
            "database/export.json",
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        )
        archive.writestr("restore/RESTORE.txt", RESTORE_INSTRUCTIONS)

    size_bytes = file_path.stat().st_size
    record = await BackupRecordRepository(session).create(
        file_name=file_name,
        file_path=str(file_path.resolve()),
        storage_kind="local",
        size_bytes=size_bytes,
        status=BACKUP_STATUS_CREATED,
        created_at=created_at,
    )
    return BackupArtifact(
        record=record,
        file_path=file_path,
        file_name=file_name,
        size_bytes=size_bytes,
        created_at=created_at,
        label=label,
    )


async def list_backup_records(session: AsyncSession, *, limit: int = 10) -> list[BackupRecord]:
    return await BackupRecordRepository(session).list_recent(limit=limit)


async def apply_backup_retention(
    session: AsyncSession,
    *,
    backup_root: str | Path,
    retention_days: int,
    now: datetime | None = None,
) -> list[BackupRecord]:
    if retention_days < 0:
        return []

    cutoff = ensure_aware_utc(now or utcnow()) - timedelta(days=retention_days)
    repository = BackupRecordRepository(session)
    records = await repository.list_older_than(cutoff)
    pruned: list[BackupRecord] = []

    for record in records:
        record_path = Path(record.file_path)
        if record_path.exists():
            record_path.unlink()
        record.status = BACKUP_STATUS_PRUNED
        pruned.append(record)

    backup_dir = Path(backup_root)
    if backup_dir.exists():
        for orphan in backup_dir.glob("*.zip"):
            if datetime.fromtimestamp(orphan.stat().st_mtime, tz=created_at_tz(now)) < cutoff:
                orphan.unlink()

    await session.flush()
    return pruned


async def mark_backup_delivery(
    session: AsyncSession,
    record: BackupRecord,
    *,
    delivered: bool,
    now: datetime | None = None,
) -> BackupRecord:
    record.status = BACKUP_STATUS_SENT if delivered else BACKUP_STATUS_SEND_FAILED
    if delivered:
        record.sent_to_admin_at = ensure_aware_utc(now or utcnow())
    await session.flush()
    return record


async def send_backup_to_message(
    message: Message,
    record: BackupRecord,
    *,
    caption: str | None = None,
) -> None:
    document = FSInputFile(record.file_path, filename=record.file_name)
    await message.answer_document(document=document, caption=caption or _default_backup_caption(record))


async def send_backup_to_admins(
    bot: Bot | Any,
    *,
    admin_ids: list[int],
    record: BackupRecord,
    caption: str | None = None,
) -> bool:
    delivered = True
    for admin_id in admin_ids:
        try:
            document = FSInputFile(record.file_path, filename=record.file_name)
            await bot.send_document(
                chat_id=admin_id,
                document=document,
                caption=caption or _default_backup_caption(record),
            )
        except Exception:
            delivered = False
            logger.exception("Failed to send backup %s to admin %s", record.id, admin_id)
    return delivered


async def _build_database_payload(session: AsyncSession) -> dict[str, list[dict[str, Any]]]:
    payload: dict[str, list[dict[str, Any]]] = {}
    for model in MODELS_TO_BACKUP:
        payload[model.__tablename__] = await _serialize_model_rows(session, model)
    return payload


async def _serialize_model_rows(session: AsyncSession, model) -> list[dict[str, Any]]:
    primary_keys = list(model.__table__.primary_key.columns)
    statement = select(model)
    for column in primary_keys:
        statement = statement.order_by(column.asc())

    result = await session.execute(statement)
    return [_serialize_model_row(row) for row in result.scalars()]


def _serialize_model_row(instance: Any) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for column in instance.__table__.columns:
        row[column.name] = _serialize_value(getattr(instance, column.name))
    return row


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return ensure_aware_utc(value).isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _default_backup_caption(record: BackupRecord) -> str:
    return f"Backup: {record.file_name}\nStatus: {record.status}\nRestore notes inside archive."


def created_at_tz(now: datetime | None) -> Any:
    reference = ensure_aware_utc(now or utcnow())
    return reference.tzinfo