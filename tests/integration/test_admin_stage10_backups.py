from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.routers.admin.backups import backups_restore_help, create_backup_now
from app.config import Settings
from app.db.base import Base
from app.db.models import BackupRecord, User
from app.db.session import create_async_engine, create_session_factory


class DummyUser:
    def __init__(self, user_id: int = 755815181) -> None:
        self.id = user_id
        self.first_name = "Admin"
        self.username = "admin"
        self.last_name = None
        self.language_code = "ru"


class DummyMessage:
    def __init__(self) -> None:
        self.answer_calls: list[tuple[str, object | None]] = []
        self.edit_calls: list[tuple[str, object | None]] = []
        self.answer_document_calls: list[dict[str, object]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edit_calls.append((text, reply_markup))

    async def answer_document(self, document, caption=None) -> None:
        self.answer_document_calls.append({"document": document, "caption": caption})


class DummyCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = DummyMessage()
        self.from_user = DummyUser()
        self.answer_count = 0
        self.answer_payloads: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args, **kwargs) -> None:
        self.answer_count += 1
        self.answer_payloads.append((args, kwargs))


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        db_session.add(User(telegram_id=755815181, first_name="Admin", is_admin=True, role="owner"))
        await db_session.commit()
        yield db_session

    await engine.dispose()


def _workspace_tmp(name: str) -> Path:
    path = Path("D:/botproj/.testdata") / f"{name}-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def test_manual_backup_route_creates_record_and_sends_document(
    session: AsyncSession,
) -> None:
    callback = DummyCallback("menu:admin:backups:create")
    root = _workspace_tmp("backup-route")
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "backup_directory": str(root / "backups"),
            "backup_retention_days": 14,
        }
    )

    await create_backup_now(callback, session, settings)

    records = list((await session.execute(select(BackupRecord))).scalars())
    assert len(records) == 1
    assert records[0].status == "sent"
    assert len(callback.message.answer_document_calls) == 1
    assert callback.answer_count == 1


async def test_backup_restore_help_renders_instruction() -> None:
    callback = DummyCallback("menu:admin:backups:restore")

    await backups_restore_help(callback)

    assert callback.answer_count == 1
    rendered_text = callback.message.edit_calls[0][0]
    assert "Restore instructions" in rendered_text