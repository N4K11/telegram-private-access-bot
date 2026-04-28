# ruff: noqa: E501
from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.models import TextTemplate
from app.services.texts import default_text_body, is_default_text_body


def admin_texts_keyboard(templates: Sequence[TextTemplate]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for template in templates:
        status = "[default]" if is_default_text_body(template.key, template.body) else "[edited]"
        builder.button(
            text=f"{status} {template.title}",
            callback_data=f"menu:admin:texts:view:{template.key}",
        )
    builder.button(text=default_text_body("admin_button_home"), callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_text_detail_keyboard(key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="\u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0442\u0435\u043a\u0441\u0442",
        callback_data=f"menu:admin:texts:edit:{key}",
    )
    builder.button(
        text="\u0421\u0431\u0440\u043e\u0441\u0438\u0442\u044c \u043a \u0441\u0442\u0430\u043d\u0434\u0430\u0440\u0442\u0443",
        callback_data=f"menu:admin:texts:reset:{key}",
    )
    builder.button(text=default_text_body("admin_button_back"), callback_data="menu:admin:texts")
    builder.button(text=default_text_body("admin_button_home"), callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()