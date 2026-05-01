from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.models import Channel, Tariff
from app.services.broadcasts import BroadcastCampaignSnapshot, BroadcastTemplateRecord

BASE_BROADCAST_FILTERS = (
    ("Все пользователи", "all"),
    ("Активная подписка", "active"),
    ("Истекла подписка", "expired"),
    ("Никогда не покупали", "never_paid"),
    ("Истекают скоро", "expires_soon"),
    ("Ожидают входа", "pending_join"),
)


def admin_broadcasts_keyboard(
    campaigns: Sequence[BroadcastCampaignSnapshot],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for snapshot in campaigns:
        status_icon = {
            "draft": "📝",
            "queued": "⏳",
            "sending": "🚀",
            "completed": "✅",
        }.get(snapshot.campaign.status, "•")
        builder.button(
            text=f"{status_icon} #{snapshot.campaign.id} • {snapshot.filter_label}",
            callback_data=f"menu:admin:broadcasts:view:{snapshot.campaign.id}",
        )
    builder.button(text="➕ Создать рассылку", callback_data="menu:admin:broadcasts:create")
    builder.button(text="Главное меню", callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_broadcast_filter_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, filter_name in BASE_BROADCAST_FILTERS:
        builder.button(text=label, callback_data=f"menu:admin:broadcasts:filter:{filter_name}")
    builder.button(text="По тарифу", callback_data="menu:admin:broadcasts:pick-filter:tariff")
    builder.button(text="По каналу", callback_data="menu:admin:broadcasts:pick-filter:channel")
    builder.button(text="Назад", callback_data="menu:admin:broadcasts")
    builder.button(text="Главное меню", callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_broadcast_item_filter_keyboard(
    items: Sequence[Tariff] | Sequence[Channel],
    *,
    kind: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        if kind == "tariff":
            callback_data = f"menu:admin:broadcasts:filter:tariff-{item.id}"
            label = getattr(item, "name", f"Тариф #{item.id}")
        else:
            callback_data = f"menu:admin:broadcasts:filter:channel-{item.id}"
            label = getattr(item, "title", f"Канал #{item.id}")
        builder.button(text=str(label), callback_data=callback_data)
    builder.button(text="Назад", callback_data="menu:admin:broadcasts:create")
    builder.button(text="Главное меню", callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_broadcast_content_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗂 Использовать шаблон", callback_data="menu:admin:broadcasts:templates")
    builder.button(text="Сменить фильтр", callback_data="menu:admin:broadcasts:create")
    builder.button(text="Главное меню", callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_broadcast_template_list_keyboard(
    templates: Sequence[BroadcastTemplateRecord],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for template in templates:
        title = template.title if len(template.title) <= 28 else f"{template.title[:25]}..."
        builder.button(
            text=f"🗂 {title}",
            callback_data=f"menu:admin:broadcasts:template:{template.key}",
        )
    builder.button(text="Назад", callback_data="menu:admin:broadcasts:content-entry")
    builder.button(text="Главное меню", callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_broadcast_preview_keyboard(*, allow_save_template: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Подтвердить отправку", callback_data="menu:admin:broadcasts:confirm")
    if allow_save_template:
        builder.button(
            text="💾 Сохранить шаблон",
            callback_data="menu:admin:broadcasts:save-template",
        )
    builder.button(text="Сменить фильтр", callback_data="menu:admin:broadcasts:create")
    builder.button(text="Главное меню", callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_broadcast_detail_keyboard(campaign_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Обновить", callback_data=f"menu:admin:broadcasts:view:{campaign_id}")
    builder.button(text="Назад", callback_data="menu:admin:broadcasts")
    builder.button(text="Главное меню", callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()

