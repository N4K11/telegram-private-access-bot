from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.admin import ADMIN_HOME_TEXT
from app.db.models import TextTemplate
from app.services.content_service import ContentEntry
from app.services.texts import is_default_text_body


def admin_content_keyboard(
    items: Sequence[tuple[ContentEntry, TextTemplate]],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for entry, template in items:
        status = '🟢' if is_default_text_body(template.key, template.body) else '📝'
        builder.button(
            text=f'{status} {entry.title}',
            callback_data=f'menu:admin:content:view:{entry.slug}',
        )
    builder.button(text='⬅️ Назад', callback_data='menu:admin:texts')
    builder.button(text=ADMIN_HOME_TEXT, callback_data='menu:admin:home')
    builder.adjust(1)
    return builder.as_markup()


def admin_content_detail_keyboard(slug: str, template_key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text='✏️ Редактировать материал',
        callback_data=f'menu:admin:content:edit:{slug}',
    )
    builder.button(
        text='🧾 Открыть шаблон',
        callback_data=f'menu:admin:texts:view:{template_key}',
    )
    builder.button(text='⬅️ Назад', callback_data='menu:admin:content')
    builder.button(text=ADMIN_HOME_TEXT, callback_data='menu:admin:home')
    builder.adjust(1)
    return builder.as_markup()
