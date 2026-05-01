from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.navigation import build_navigation_keyboard
from app.db.models import SupportTicket
from app.services.legal_texts import all_legal_text_entries
from app.services.support import support_category_label, support_status_label

USER_HOME_TEXT = "🏠 Главное меню"
USER_BACK_TEXT = "⬅️ Назад"


def user_support_overview_keyboard(*, open_ticket_id: int | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if open_ticket_id is None:
        builder.button(text="🎫 Создать обращение", callback_data="menu:user:support:create")
    else:
        builder.button(
            text=f"💬 Открытый тикет #{open_ticket_id}",
            callback_data=f"menu:user:support:view:{open_ticket_id}",
        )
    builder.button(text="📨 Мои обращения", callback_data="menu:user:support:list")
    for entry in all_legal_text_entries():
        builder.button(
            text=entry.button_text,
            callback_data=f"menu:user:legal:{entry.slug}",
        )
    builder.button(text=USER_BACK_TEXT, callback_data="menu:user:home")
    builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()


def user_support_category_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in (
        ("payment", "💳 Оплата"),
        ("access", "🔐 Доступ"),
        ("technical", "🛠 Технический вопрос"),
        ("other", "💬 Другое"),
    ):
        builder.button(text=label, callback_data=f"menu:user:support:category:{key}")
    builder.button(text=USER_BACK_TEXT, callback_data="menu:user:help")
    builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()


def user_support_ticket_list_keyboard(tickets: Sequence[SupportTicket]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ticket in tickets:
        builder.button(
            text=(
                f"#{ticket.id} • {support_category_label(ticket.category)} • "
                f"{support_status_label(ticket.status)}"
            ),
            callback_data=f"menu:user:support:view:{ticket.id}",
        )
    builder.button(text=USER_BACK_TEXT, callback_data="menu:user:help")
    builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()


def user_support_ticket_keyboard(ticket: SupportTicket) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if ticket.status == "open":
        builder.button(
            text="✍️ Добавить сообщение",
            callback_data=f"menu:user:support:add:{ticket.id}",
        )
    builder.button(text="📨 К списку обращений", callback_data="menu:user:support:list")
    builder.button(text=USER_BACK_TEXT, callback_data="menu:user:help")
    builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()


def user_support_compose_keyboard(*, back_callback: str) -> InlineKeyboardMarkup:
    return build_navigation_keyboard(
        include_back=True,
        include_home=True,
        back_callback=back_callback,
        home_callback="menu:user:home",
        back_text=USER_BACK_TEXT,
        home_text=USER_HOME_TEXT,
    )
