from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.models import Channel, Tariff
from app.services.users import USER_FILTER_LABELS, UserDirectoryPage

BASE_USER_FILTERS = (
    "all",
    "active",
    "expired",
    "never_paid",
    "blocked",
    "stars",
    "crypto",
)



def _active_label(label: str, *, is_active: bool) -> str:
    return f"• {label}" if is_active else label



def _profile_callback(user_id: int, filter_key: str, page: int) -> str:
    return f"menu:admin:users:view:{user_id}:{filter_key}:{page}"



def admin_analytics_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Пользователи", callback_data="menu:admin:users")
    builder.button(text="🔄 Обновить", callback_data="menu:admin:analytics")
    builder.button(text="Главное меню", callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()



def admin_users_directory_keyboard(page_data: UserDirectoryPage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for filter_key in BASE_USER_FILTERS:
        builder.button(
            text=_active_label(
                USER_FILTER_LABELS[filter_key],
                is_active=page_data.filter_key == filter_key,
            ),
            callback_data=f"menu:admin:users:list:{filter_key}:1",
        )

    builder.button(text="По тарифу", callback_data="menu:admin:users:pick-filter:tariff")
    builder.button(text="По каналу", callback_data="menu:admin:users:pick-filter:channel")

    for entry in page_data.items:
        username = (
            f"@{entry.user.username}"
            if entry.user.username
            else f"id {entry.user.telegram_id}"
        )
        builder.button(
            text=f"{username} • {entry.status}",
            callback_data=_profile_callback(
                entry.user.id,
                page_data.filter_key,
                page_data.page,
            ),
        )

    nav_buttons: list[tuple[str, str]] = []
    if page_data.page > 1:
        nav_buttons.append(
            (
                "◀️ Назад",
                f"menu:admin:users:list:{page_data.filter_key}:{page_data.page - 1}",
            )
        )
    if page_data.page < page_data.total_pages:
        nav_buttons.append(
            (
                "Вперёд ▶️",
                f"menu:admin:users:list:{page_data.filter_key}:{page_data.page + 1}",
            )
        )
    for text, callback_data in nav_buttons:
        builder.button(text=text, callback_data=callback_data)

    builder.button(text="Главное меню", callback_data="menu:admin:home")

    if page_data.items:
        builder.adjust(
            2,
            2,
            2,
            1,
            2,
            *([1] * len(page_data.items)),
            len(nav_buttons) or 1,
            1,
        )
    else:
        builder.adjust(2, 2, 2, 1, 2, len(nav_buttons) or 1, 1)

    return builder.as_markup()



def admin_user_filter_picker_keyboard(
    items: Sequence[Tariff] | Sequence[Channel],
    *,
    kind: str,
    back_filter: str,
    back_page: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        if kind == "tariff":
            callback_data = f"menu:admin:users:list:tariff-{item.id}:1"
            label = getattr(item, "name", f"Тариф #{item.id}")
        else:
            callback_data = f"menu:admin:users:list:channel-{item.id}:1"
            label = getattr(item, "title", f"Канал #{item.id}")
        builder.button(text=str(label), callback_data=callback_data)

    builder.button(
        text="Назад",
        callback_data=f"menu:admin:users:list:{back_filter}:{back_page}",
    )
    builder.button(text="Главное меню", callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()



def admin_user_profile_keyboard(
    *,
    user_id: int,
    filter_key: str,
    page: int,
    is_blocked: bool,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="💬 Написать",
        callback_data=f"menu:admin:users:message:{user_id}:{filter_key}:{page}",
    )
    builder.button(
        text="🎁 Выдать тариф",
        callback_data=f"menu:admin:users:grant:{user_id}:{filter_key}:{page}",
    )
    builder.button(
        text="🔓 Разблокировать" if is_blocked else "🔒 Заблокировать",
        callback_data=f"menu:admin:users:block:{user_id}:{filter_key}:{page}",
    )
    builder.button(
        text="💳 Платежи",
        callback_data=f"menu:admin:users:payments:{user_id}:{filter_key}:{page}",
    )
    builder.button(
        text="📚 Подписки",
        callback_data=f"menu:admin:users:subscriptions:{user_id}:{filter_key}:{page}",
    )
    builder.button(
        text="🧾 Аудит",
        callback_data=f"menu:admin:users:audit:{user_id}:{filter_key}:{page}",
    )
    builder.button(text="Назад", callback_data=f"menu:admin:users:list:{filter_key}:{page}")
    builder.button(text="Главное меню", callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()



def admin_user_history_keyboard(
    *,
    user_id: int,
    filter_key: str,
    page: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Назад к профилю",
        callback_data=_profile_callback(user_id, filter_key, page),
    )
    builder.button(text="Главное меню", callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()



def admin_user_grant_tariff_keyboard(
    tariffs: Sequence[Tariff],
    *,
    user_id: int,
    filter_key: str,
    page: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for tariff in tariffs:
        builder.button(
            text=f"{tariff.name} • {tariff.price_stars} Stars • {tariff.duration_days} дн.",
            callback_data=(
                f"menu:admin:users:grant-review:{user_id}:{tariff.id}:{filter_key}:{page}"
            ),
        )
    builder.button(text="Назад", callback_data=_profile_callback(user_id, filter_key, page))
    builder.button(text="Главное меню", callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()



def admin_confirm_keyboard(*, confirm_callback: str, cancel_callback: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Подтвердить", callback_data=confirm_callback)
    builder.button(text="Отмена", callback_data=cancel_callback)
    builder.adjust(1)
    return builder.as_markup()