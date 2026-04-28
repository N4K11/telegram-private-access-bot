from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup

from app.bot.keyboards.navigation import build_navigation_keyboard


def user_main_menu_keyboard() -> InlineKeyboardMarkup:
    return build_navigation_keyboard(
        ("My subscription", "menu:user:subscription"),
        ("Tariffs", "menu:user:tariffs"),
        ("Support", "menu:user:support"),
        include_home=False,
    )


def user_section_keyboard() -> InlineKeyboardMarkup:
    return build_navigation_keyboard(
        include_back=True,
        include_home=True,
        back_callback="menu:user:home",
        home_callback="menu:user:home",
    )