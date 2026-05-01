from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.services.admin_roles import has_permission, is_admin_role, resolve_telegram_role


class AdminFilter(BaseFilter):
    def __init__(self, *permissions: str) -> None:
        self._permissions = tuple(permission for permission in permissions if permission)

    async def __call__(
        self,
        event: TelegramObject,
        settings: Settings,
        session: AsyncSession | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> bool:
        user_id = self._extract_user_id(event)
        if user_id is None:
            return False

        role = await self._resolve_role(
            telegram_user_id=user_id,
            settings=settings,
            session=session,
            session_factory=session_factory,
        )
        if not is_admin_role(role):
            return False
        if not self._permissions:
            return True
        return all(has_permission(role, permission) for permission in self._permissions)

    async def _resolve_role(
        self,
        *,
        telegram_user_id: int,
        settings: Settings,
        session: AsyncSession | None,
        session_factory: async_sessionmaker[AsyncSession] | None,
    ) -> str:
        if session is not None:
            return await resolve_telegram_role(
                session,
                telegram_user_id=telegram_user_id,
                settings=settings,
            )
        if session_factory is not None:
            async with session_factory() as owned_session:
                return await resolve_telegram_role(
                    owned_session,
                    telegram_user_id=telegram_user_id,
                    settings=settings,
                )
        if telegram_user_id in settings.admin_ids_set:
            return "owner"
        return "user"

    @staticmethod
    def _extract_user_id(event: TelegramObject) -> int | None:
        if isinstance(event, Message):
            return event.from_user.id if event.from_user else None
        if isinstance(event, CallbackQuery):
            return event.from_user.id if event.from_user else None
        return getattr(getattr(event, "from_user", None), "id", None)
