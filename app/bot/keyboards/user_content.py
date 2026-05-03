from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.user import (
    USER_BACK_TEXT,
    USER_BUTTON_BUY_TEXT,
    USER_BUTTON_LINK_TEXT,
    USER_HOME_TEXT,
)
from app.services.content_service import all_content_entries


def user_content_detail_keyboard(*, current_slug: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=USER_BUTTON_BUY_TEXT, callback_data="menu:user:buy")
    builder.button(text=USER_BUTTON_LINK_TEXT, callback_data="menu:user:link")
    for entry in all_content_entries():
        if entry.slug == current_slug:
            continue
        builder.button(
            text=entry.button_text,
            callback_data=f"menu:user:content:{entry.slug}",
        )
    builder.button(text=USER_BACK_TEXT, callback_data="menu:user:help")
    builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()