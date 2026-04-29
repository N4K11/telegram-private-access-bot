from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def build_navigation_keyboard(
    *buttons: tuple[str, str],
    include_back: bool = False,
    back_callback: str = "menu:user:home",
    back_text: str = "⬅️ Назад",
    include_home: bool = True,
    home_callback: str = "menu:user:home",
    home_text: str = "🏠 Главное меню",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for text, callback_data in buttons:
        builder.button(text=text, callback_data=callback_data)
    if include_back:
        builder.button(text=back_text, callback_data=back_callback)
    if include_home:
        builder.button(text=home_text, callback_data=home_callback)
    builder.adjust(1)
    return builder.as_markup()