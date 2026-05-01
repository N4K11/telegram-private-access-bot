from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.user import USER_BACK_TEXT, USER_HOME_TEXT
from app.services.legal_texts import all_legal_text_entries


def user_legal_detail_keyboard(*, current_slug: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for entry in all_legal_text_entries():
        if entry.slug == current_slug:
            continue
        builder.button(
            text=entry.button_text,
            callback_data=f"menu:user:legal:{entry.slug}",
        )
    builder.button(text=USER_BACK_TEXT, callback_data="menu:user:help")
    builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()