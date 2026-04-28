from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.base import Base
from app.db.models import User
from app.db.repositories.backup_records import BackupRecordRepository
from app.db.session import create_async_engine, create_session_factory
from app.services.backups import (
    apply_backup_retention,
    create_backup_archive,
    send_backup_to_admins,
)
from app.workers.backup_worker import run_scheduled_backup_cycle


class RecordingBot:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def send_document(self, **kwargs):
        self.calls.append(kwargs)
        return True


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        db_session.add(User(telegram_id=42, first_name="Admin", is_admin=True, role="owner"))
        await db_session.commit()
        yield db_session

    await engine.dispose()


def _workspace_tmp(name: str) -> Path:
    path = Path("D:/botproj/.testdata") / f"{name}-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def test_create_backup_archive_writes_zip_and_excludes_env(
    session: AsyncSession,
) -> None:
    root = _workspace_tmp("backup-service")
    backup_root = root / "backups"
    (root / ".env").write_text("BOT_TOKEN=secret-token", encoding="utf-8")

    artifact = await create_backup_archive(
        session,
        backup_root=backup_root,
        label="manual",
        now=datetime(2026, 4, 28, 10, 0, tzinfo=UTC),
    )
    await session.commit()

    assert artifact.file_path.exists()
    assert artifact.record.file_name.startswith("manual-backup-")

    with ZipFile(artifact.file_path) as archive:
        names = set(archive.namelist())
        export_payload = archive.read("database/export.json").decode("utf-8")

    assert {"metadata.json", "database/export.json", "restore/RESTORE.txt"}.issubset(names)
    assert all(not name.endswith(".env") for name in names)
    assert "secret-token" not in export_payload
    assert '"users"' in export_payload


async def test_apply_backup_retention_prunes_old_backups(
    session: AsyncSession,
) -> None:
    backup_root = _workspace_tmp("backup-retention") / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)

    old_path = backup_root / "daily-backup-20260401-010000.zip"
    new_path = backup_root / "daily-backup-20260428-010000.zip"
    old_path.write_text("old", encoding="utf-8")
    new_path.write_text("new", encoding="utf-8")

    repository = BackupRecordRepository(session)
    old_record = await repository.create(
        file_name=old_path.name,
        file_path=str(old_path),
        size_bytes=old_path.stat().st_size,
        status="created",
        created_at=datetime(2026, 4, 1, 1, 0, tzinfo=UTC),
    )
    new_record = await repository.create(
        file_name=new_path.name,
        file_path=str(new_path),
        size_bytes=new_path.stat().st_size,
        status="created",
        created_at=datetime(2026, 4, 28, 1, 0, tzinfo=UTC),
    )
    await session.commit()

    pruned = await apply_backup_retention(
        session,
        backup_root=backup_root,
        retention_days=7,
        now=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
    )
    await session.commit()

    assert [record.id for record in pruned] == [old_record.id]
    assert old_record.status == "pruned"
    assert new_record.status == "created"
    assert old_path.exists() is False
    assert new_path.exists() is True


async def test_send_backup_to_admins_and_daily_worker_are_idempotent(
    session: AsyncSession,
) -> None:
    root = _workspace_tmp("backup-worker")
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [42],
            "backup_directory": str(root / "backups"),
            "backup_enabled": True,
            "backup_send_to_admin": True,
            "backup_time": "03:00",
            "timezone": "UTC",
        }
    )
    bot = RecordingBot()

    artifact = await run_scheduled_backup_cycle(
        session,
        bot,
        settings,
        now=datetime(2026, 4, 28, 3, 5, tzinfo=UTC),
    )
    assert artifact is not None
    assert len(bot.calls) == 1
    assert artifact.record.status == "sent"

    delivered = await send_backup_to_admins(bot, admin_ids=[42], record=artifact.record)
    assert delivered is True
    assert len(bot.calls) == 2

    second = await run_scheduled_backup_cycle(
        session,
        bot,
        settings,
        now=datetime(2026, 4, 28, 3, 25, tzinfo=UTC),
    )
    assert second is None

    records = await BackupRecordRepository(session).list_recent(limit=10)
    assert len(records) == 1