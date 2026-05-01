from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.admin import ADMIN_HOME_TEXT
from app.db.models import User
from app.services.admin_roles import ASSIGNABLE_ROLES, role_button_label


def _user_label(user: User) -> str:
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}".strip()
    if user.first_name:
        return user.first_name
    if user.username:
        return f"@{user.username}"
    return f"User #{user.id}"


def admin_roles_home_keyboard(users: Sequence[User]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for user in users:
        builder.button(
            text=f"{role_button_label(user.role)} • {_user_label(user)}",
            callback_data=f"menu:admin:roles:view:{user.id}",
        )
    builder.button(text="➕ Назначить или изменить роль", callback_data="menu:admin:roles:prompt")
    builder.button(text="🔄 Обновить", callback_data="menu:admin:settings")
    builder.button(text="⬅️ Назад", callback_data="menu:admin:home")
    builder.button(text=ADMIN_HOME_TEXT, callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_role_detail_keyboard(
    user_id: int,
    *,
    current_role: str,
    can_edit: bool,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if can_edit:
        for role in ASSIGNABLE_ROLES:
            prefix = "✅" if role == current_role else "▫️"
            builder.button(
                text=f"{prefix} {role_button_label(role)}",
                callback_data=f"menu:admin:roles:set:{user_id}:{role}",
            )
    builder.button(text="⬅️ К списку ролей", callback_data="menu:admin:settings")
    builder.button(text=ADMIN_HOME_TEXT, callback_data="menu:admin:home")
    builder.adjust(1 if not can_edit else 2)
    return builder.as_markup()


def admin_role_prompt_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ К ролям", callback_data="menu:admin:settings")
    builder.button(text=ADMIN_HOME_TEXT, callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()
