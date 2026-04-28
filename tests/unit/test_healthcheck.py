from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.config import Settings
from app.healthcheck import run_healthcheck


async def test_healthcheck_validates_database_and_creates_backup_directory() -> None:
    backup_dir = Path("D:/botproj/.testdata") / f"health-{uuid4().hex}" / "backups"
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [1],
            "database_url": "sqlite+aiosqlite:///:memory:",
            "backup_directory": str(backup_dir),
        }
    )

    await run_healthcheck(settings)

    assert backup_dir.exists() is True