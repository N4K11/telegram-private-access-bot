from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup

from app.bot.keyboards.navigation import build_navigation_keyboard


def admin_main_menu_keyboard() -> InlineKeyboardMarkup:
    return build_navigation_keyboard(
        ("Analytics", "menu:admin:analytics"),
        ("Users", "menu:admin:users"),
        ("Payments", "menu:admin:payments"),
        ("Tariffs", "menu:admin:tariffs"),
        ("Channels", "menu:admin:channels"),
        ("Texts", "menu:admin:texts"),
        ("Broadcasts", "menu:admin:broadcasts"),
        ("Backups", "menu:admin:backups"),
        ("Settings", "menu:admin:settings"),
        ("Diagnostics", "menu:admin:diagnostics"),
        include_home=False,
    )


def admin_section_keyboard() -> InlineKeyboardMarkup:
    return build_navigation_keyboard(
        include_back=True,
        include_home=True,
        back_callback="menu:admin:home",
        home_callback="menu:admin:home",
    )