from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.navigation import build_navigation_keyboard
from app.db.models import Channel, Tariff


def admin_main_menu_keyboard() -> InlineKeyboardMarkup:
    return build_navigation_keyboard(
        ("📊 Аналитика", "menu:admin:analytics"),
        ("👥 Пользователи", "menu:admin:users"),
        ("💳 Платежи", "menu:admin:payments"),
        ("🧾 Тарифы", "menu:admin:tariffs"),
        ("📣 Каналы", "menu:admin:channels"),
        ("✍️ Тексты", "menu:admin:texts"),
        ("📢 Рассылка", "menu:admin:broadcasts"),
        ("💾 Бэкапы", "menu:admin:backups"),
        ("⚙️ Настройки", "menu:admin:settings"),
        ("🧪 Диагностика", "menu:admin:diagnostics"),
        include_home=False,
    )


def admin_section_keyboard() -> InlineKeyboardMarkup:
    return build_navigation_keyboard(
        include_back=True,
        include_home=True,
        back_callback="menu:admin:home",
        home_callback="menu:admin:home",
    )


def admin_form_keyboard(*, back_callback: str) -> InlineKeyboardMarkup:
    return build_navigation_keyboard(
        include_back=True,
        include_home=True,
        back_callback=back_callback,
        home_callback="menu:admin:home",
    )


def admin_channels_keyboard(channels: Sequence[Channel]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for channel in channels:
        status = "✅" if channel.is_active else "⏸"
        builder.button(
            text=f"{status} {channel.title}",
            callback_data=f"menu:admin:channels:view:{channel.id}",
        )
    builder.button(text="➕ Добавить канал", callback_data="menu:admin:channels:create")
    builder.button(text="Главное меню", callback_data="menu:admin:home")
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
    builder.button(text="Назад", callback_data="menu:admin:channels")
    builder.button(text="Главное меню", callback_data="menu:admin:home")
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
        builder.button(
            text=f"{status} {tariff.name}",
            callback_data=f"menu:admin:tariffs:view:{tariff.id}",
        )
    builder.button(text="➕ Создать тариф", callback_data="menu:admin:tariffs:create")
    builder.button(text="Главное меню", callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_tariff_detail_keyboard(
    tariff_id: int,
    *,
    is_active: bool,
    is_archived: bool,
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
            text="⏸ Выключить" if is_active else "▶️ Включить",
            callback_data=f"menu:admin:tariffs:toggle:{tariff_id}",
        )
        builder.button(
            text="🗄 Архивировать",
            callback_data=f"menu:admin:tariffs:archive:{tariff_id}",
        )
    builder.button(text="Назад", callback_data="menu:admin:tariffs")
    builder.button(text="Главное меню", callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_channel_picker_keyboard(
    channels: Sequence[Channel],
    *,
    back_callback: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for channel in channels:
        builder.button(
            text=f"📣 {channel.title}",
            callback_data=f"menu:admin:tariffs:pick-channel:{channel.id}",
        )
    builder.button(text="Назад", callback_data=back_callback)
    builder.button(text="Главное меню", callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()