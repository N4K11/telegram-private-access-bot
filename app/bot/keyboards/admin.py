from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.navigation import build_navigation_keyboard
from app.db.models import Channel, Tariff
from app.services.admin_roles import allowed_admin_menu_sections
from app.utils.encoding import safe_ui_text

ADMIN_HOME_TEXT = "🏠 Админ-панель"
ADMIN_USER_MENU_TEXT = "⬅️ Назад в меню пользователя"


def admin_main_menu_keyboard(*, role: str | None = "owner") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for section in allowed_admin_menu_sections(role):
        builder.button(
            text=section.button_text,
            callback_data=f"menu:admin:{section.key}",
        )
    builder.button(text=ADMIN_USER_MENU_TEXT, callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_section_keyboard() -> InlineKeyboardMarkup:
    return build_navigation_keyboard(
        include_back=True,
        include_home=True,
        back_callback="menu:admin:home",
        home_callback="menu:admin:home",
        back_text="⬅️ Назад",
        home_text=ADMIN_HOME_TEXT,
    )


def admin_form_keyboard(*, back_callback: str) -> InlineKeyboardMarkup:
    return build_navigation_keyboard(
        include_back=True,
        include_home=True,
        back_callback=back_callback,
        home_callback="menu:admin:home",
        back_text="⬅️ Назад",
        home_text=ADMIN_HOME_TEXT,
    )


def admin_channels_keyboard(channels: Sequence[Channel]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for channel in channels:
        status = "✅" if channel.is_active else "⏸"
        title = safe_ui_text(channel.title, f"Канал #{channel.id}")
        builder.button(
            text=f"{status} {title}",
            callback_data=f"menu:admin:channels:view:{channel.id}",
        )
    builder.button(text="➕ Добавить канал", callback_data="menu:admin:channels:create")
    builder.button(text=ADMIN_HOME_TEXT, callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_channel_detail_keyboard(channel_id: int, *, is_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✏️ Переименовать",
        callback_data=f"menu:admin:channels:rename:{channel_id}",
    )
    builder.button(
        text="⏸ Выключить" if is_active else "▶️ Включить",
        callback_data=f"menu:admin:channels:toggle:{channel_id}",
    )
    builder.button(
        text="🔄 Обновить проверку",
        callback_data=f"menu:admin:channels:refresh:{channel_id}",
    )
    builder.button(text="⬅️ Назад", callback_data="menu:admin:channels")
    builder.button(text=ADMIN_HOME_TEXT, callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_tariffs_keyboard(tariffs: Sequence[Tariff]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for tariff in tariffs:
        if tariff.archived_at is not None:
            status = "📦"
        elif tariff.is_active:
            status = "✅"
        else:
            status = "⏸"
        title = safe_ui_text(tariff.name, f"Тариф #{tariff.id}")
        builder.button(
            text=f"{status} {title}",
            callback_data=f"menu:admin:tariffs:view:{tariff.id}",
        )
    builder.button(text="➕ Создать тариф", callback_data="menu:admin:tariffs:create")
    builder.button(text=ADMIN_HOME_TEXT, callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_tariff_detail_keyboard(
    tariff_id: int,
    *,
    is_active: bool,
    is_archived: bool,
    is_trial: bool = False,
    is_lifetime: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not is_archived:
        builder.button(
            text="✏️ Изменить название",
            callback_data=f"menu:admin:tariffs:rename:{tariff_id}",
        )
        builder.button(
            text="💳 Изменить цену",
            callback_data=f"menu:admin:tariffs:price:{tariff_id}",
        )
        builder.button(
            text="📅 Изменить длительность",
            callback_data=f"menu:admin:tariffs:days:{tariff_id}",
        )
        builder.button(
            text="📣 Сменить канал",
            callback_data=f"menu:admin:tariffs:channel:{tariff_id}",
        )
        builder.button(
            text="↕️ Изменить сортировку",
            callback_data=f"menu:admin:tariffs:sort:{tariff_id}",
        )
        builder.button(
            text="🏷 Изменить бейдж",
            callback_data=f"menu:admin:tariffs:badge:{tariff_id}",
        )
        builder.button(
            text="🧪 Trial: ВКЛ" if is_trial else "🧪 Trial: ВЫКЛ",
            callback_data=f"menu:admin:tariffs:trial:{tariff_id}",
        )
        builder.button(
            text="♾ Lifetime: ВКЛ" if is_lifetime else "♾ Lifetime: ВЫКЛ",
            callback_data=f"menu:admin:tariffs:lifetime:{tariff_id}",
        )
        builder.button(
            text="⏸ Выключить" if is_active else "▶️ Включить",
            callback_data=f"menu:admin:tariffs:toggle:{tariff_id}",
        )
        builder.button(
            text="👁 Превью как пользователь",
            callback_data=f"menu:admin:tariffs:preview:{tariff_id}",
        )
        builder.button(
            text="🗄 Архивировать",
            callback_data=f"menu:admin:tariffs:archive:{tariff_id}",
        )
    else:
        builder.button(
            text="📤 Разархивировать",
            callback_data=f"menu:admin:tariffs:unarchive:{tariff_id}",
        )
    builder.button(text="⬅️ Назад", callback_data="menu:admin:tariffs")
    builder.button(text=ADMIN_HOME_TEXT, callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_channel_picker_keyboard(
    channels: Sequence[Channel],
    *,
    back_callback: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for channel in channels:
        title = safe_ui_text(channel.title, f"Канал #{channel.id}")
        builder.button(
            text=f"📣 {title}",
            callback_data=f"menu:admin:tariffs:pick-channel:{channel.id}",
        )
    builder.button(text="⬅️ Назад", callback_data=back_callback)
    builder.button(text=ADMIN_HOME_TEXT, callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()

