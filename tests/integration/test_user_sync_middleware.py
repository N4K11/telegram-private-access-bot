from __future__ import annotations

from aiogram.types import User as TelegramUser
from sqlalchemy import select

import app.db.models  # noqa: F401
from app.bot.middlewares.user_sync import UserSyncMiddleware
from app.config import Settings
from app.db.base import Base
from app.db.models import User
from app.db.session import create_async_engine, create_session_factory


async def test_user_sync_middleware_persists_user() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    middleware = UserSyncMiddleware()

    event = type("Event", (), {})()
    event.from_user = TelegramUser(
        id=42,
        is_bot=False,
        first_name="Anna",
        username="anna",
        language_code="en",
    )

    async def handler(_event, _data):
        return "ok"

    async with session_factory() as session:
        result = await middleware(
            handler,
            event,
            {
                "session": session,
                "settings": Settings.model_validate(
                    {"bot_token": "123:token", "admin_ids": [42]}
                ),
            },
        )

        row = await session.execute(select(User).where(User.telegram_id == 42))
        user = row.scalar_one()

    await engine.dispose()

    assert result == "ok"
    assert user.first_name == "Anna"
    assert user.is_admin is True
    assert user.role == "owner"