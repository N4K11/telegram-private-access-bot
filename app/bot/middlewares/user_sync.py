from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.repositories.users import UserRepository


class UserSyncMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session = data.get("session")
        settings = data.get("settings")
        user = self._extract_user(event)

        if (
            isinstance(session, AsyncSession)
            and isinstance(settings, Settings)
            and user is not None
        ):
            repository = UserRepository(session)
            await repository.upsert_from_telegram_user(user, admin_ids=settings.admin_ids_set)
            await session.commit()

        return await handler(event, data)

    @staticmethod
    def _extract_user(event: TelegramObject) -> User | None:
        return getattr(event, "from_user", None)
