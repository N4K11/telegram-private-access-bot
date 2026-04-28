# ruff: noqa: E501
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

DOWNLOAD_NOW_TEXT = (
    "\U0001f4e5 "
    "\u0421\u043a\u0430\u0447\u0430\u0442\u044c backup \u0441\u0435\u0439\u0447\u0430\u0441"
)
RESTORE_GUIDE_TEXT = (
    "\U0001f4c3 "
    "\u0418\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u044f "
    "\u043f\u043e \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044e"
)
REFRESH_TEXT = "\U0001f504 \u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c"
BACK_TEXT = "\u041d\u0430\u0437\u0430\u0434"
HOME_TEXT = "\u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e"


def admin_backups_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=DOWNLOAD_NOW_TEXT,
        callback_data="menu:admin:backups:create",
    )
    builder.button(
        text=RESTORE_GUIDE_TEXT,
        callback_data="menu:admin:backups:restore",
    )
    builder.button(
        text=REFRESH_TEXT,
        callback_data="menu:admin:backups",
    )
    builder.button(text=BACK_TEXT, callback_data="menu:admin:home")
    builder.button(
        text=HOME_TEXT,
        callback_data="menu:admin:home",
    )
    builder.adjust(1)
    return builder.as_markup()