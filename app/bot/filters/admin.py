from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import Settings


class AdminFilter(BaseFilter):
    async def __call__(self, event: TelegramObject, settings: Settings) -> bool:
        user_id = self._extract_user_id(event)
        return user_id in settings.admin_ids_set

    @staticmethod
    def _extract_user_id(event: TelegramObject) -> int | None:
        if isinstance(event, Message):
            return event.from_user.id if event.from_user else None
        if isinstance(event, CallbackQuery):
            return event.from_user.id if event.from_user else None
        return getattr(getattr(event, "from_user", None), "id", None)
