# ruff: noqa: E501
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_finance_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, period in (
        ("CSV: \u0434\u0435\u043d\u044c", "day"),
        ("CSV: \u043d\u0435\u0434\u0435\u043b\u044f", "week"),
        ("CSV: \u043c\u0435\u0441\u044f\u0446", "month"),
        ("CSV: \u0432\u0441\u0451", "all"),
    ):
        builder.button(text=label, callback_data=f"menu:admin:finance:export:{period}")

    builder.button(text="\U0001fa99 Crypto \u0434\u0435\u0442\u0430\u043b\u0438", callback_data="menu:admin:payments:crypto")
    builder.button(text="\U0001f504 \u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c", callback_data="menu:admin:payments")
    builder.button(text="\u2b05\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="menu:admin:home")
    builder.button(text="\U0001f3e0 \u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c", callback_data="menu:admin:home")
    builder.adjust(2, 2, 1, 1, 1)
    return builder.as_markup()

