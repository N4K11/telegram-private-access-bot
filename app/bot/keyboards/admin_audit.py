# ruff: noqa: E501
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.audit import PERIOD_LABELS, AuditPage, AuditUserReference

MAX_FILTER_LABEL_LENGTH = 18
MAX_EVENT_LABEL_LENGTH = 20


def admin_audit_overview_keyboard(page: AuditPage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for period in ("day", "week", "month", "all"):
        label = PERIOD_LABELS[period]
        if page.filters.period == period:
            label = f"• {label}"
        builder.button(text=label, callback_data=f"menu:admin:audit:period:{period}")

    builder.button(
        text=_filter_button_label("🎯 Цель", page.filter_target),
        callback_data="menu:admin:audit:prompt:target",
    )
    builder.button(
        text=_filter_button_label("🛡 Актор", page.filter_actor),
        callback_data="menu:admin:audit:prompt:actor",
    )
    builder.button(
        text=_action_button_label(page.filters.action),
        callback_data="menu:admin:audit:prompt:action",
    )
    builder.button(text="🧹 Сбросить", callback_data="menu:admin:audit:reset")

    for item in page.items:
        builder.button(
            text=_event_button_label(item.id, item.action),
            callback_data=f"menu:admin:audit:view:{item.id}",
        )

    if page.page > 1:
        builder.button(
            text="◀️ Назад",
            callback_data=f"menu:admin:audit:page:{page.page - 1}",
        )
    if page.page < page.total_pages:
        builder.button(
            text="Вперёд ▶️",
            callback_data=f"menu:admin:audit:page:{page.page + 1}",
        )

    builder.button(text="📤 CSV", callback_data="menu:admin:audit:export")
    builder.button(text="🔄 Обновить", callback_data="menu:admin:audit:list")
    builder.button(text="⬅️ Назад", callback_data="menu:admin:home")
    builder.button(text="🏠 Админ-панель", callback_data="menu:admin:home")

    adjust_spec = [2, 2, 2]
    adjust_spec.extend([1] * len(page.items))
    nav_size = 0
    if page.page > 1:
        nav_size += 1
    if page.page < page.total_pages:
        nav_size += 1
    if nav_size:
        adjust_spec.append(nav_size)
    adjust_spec.extend([2, 2])
    builder.adjust(*adjust_spec)
    return builder.as_markup()


def admin_audit_detail_keyboard(
    *,
    actor_user_id: int | None,
    target_user_id: int | None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    added_targets: set[int] = set()
    if target_user_id is not None:
        added_targets.add(target_user_id)
        builder.button(
            text="👤 Профиль цели",
            callback_data=f"menu:admin:users:view:{target_user_id}:all:1",
        )
    if actor_user_id is not None and actor_user_id not in added_targets:
        builder.button(
            text="🛡 Профиль актора",
            callback_data=f"menu:admin:users:view:{actor_user_id}:all:1",
        )
    builder.button(text="⬅️ К списку", callback_data="menu:admin:audit:list")
    builder.button(text="🔄 Обновить", callback_data="menu:admin:audit:list")
    builder.button(text="🏠 Админ-панель", callback_data="menu:admin:home")

    first_row_size = 0
    if target_user_id is not None:
        first_row_size += 1
    if actor_user_id is not None and actor_user_id not in added_targets:
        first_row_size += 1
    adjust_spec: list[int] = []
    if first_row_size:
        adjust_spec.append(first_row_size)
    adjust_spec.extend([2, 1])
    builder.adjust(*adjust_spec)
    return builder.as_markup()


def admin_audit_prompt_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ К списку", callback_data="menu:admin:audit:list")
    builder.button(text="🏠 Админ-панель", callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()


def _filter_button_label(prefix: str, reference: AuditUserReference | None) -> str:
    if reference is None:
        return prefix
    return _truncate(
        f"{prefix}: {reference.display_name}",
        MAX_FILTER_LABEL_LENGTH + len(prefix) + 2,
    )


def _action_button_label(action: str | None) -> str:
    if not action:
        return "🏷 Действие"
    return _truncate(f"🏷 {action}", MAX_FILTER_LABEL_LENGTH + 2)


def _event_button_label(event_id: int, action: str) -> str:
    return _truncate(f"#{event_id} {action}", MAX_EVENT_LABEL_LENGTH)


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."
