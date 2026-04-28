from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import text

from app.config import Settings, get_settings
from app.db.session import create_async_engine


async def run_healthcheck(settings: Settings | None = None) -> None:
    resolved_settings = settings or get_settings()
    engine = create_async_engine(resolved_settings.database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        Path(resolved_settings.backup_directory).mkdir(parents=True, exist_ok=True)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(run_healthcheck())


if __name__ == "__main__":
    main()