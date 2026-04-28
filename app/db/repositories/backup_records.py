from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BackupRecord


class BackupRecordRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        file_name: str,
        file_path: str,
        storage_kind: str = "local",
        size_bytes: int | None = None,
        status: str = "created",
        created_at: datetime | None = None,
        sent_to_admin_at: datetime | None = None,
    ) -> BackupRecord:
        record = BackupRecord(
            file_name=file_name,
            file_path=file_path,
            storage_kind=storage_kind,
            size_bytes=size_bytes,
            status=status,
            created_at=created_at,
            sent_to_admin_at=sent_to_admin_at,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def list_recent(self, *, limit: int = 10) -> list[BackupRecord]:
        result = await self._session.execute(
            select(BackupRecord)
            .order_by(BackupRecord.created_at.desc(), BackupRecord.id.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def list_older_than(self, cutoff: datetime) -> list[BackupRecord]:
        result = await self._session.execute(
            select(BackupRecord)
            .where(BackupRecord.created_at < cutoff)
            .where(BackupRecord.status != "pruned")
            .order_by(BackupRecord.created_at.asc(), BackupRecord.id.asc())
        )
        return list(result.scalars())

    async def get_latest_for_label(self, label: str) -> BackupRecord | None:
        result = await self._session.execute(
            select(BackupRecord)
            .where(BackupRecord.file_name.like(f"{label}-backup-%"))
            .order_by(BackupRecord.created_at.desc(), BackupRecord.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()