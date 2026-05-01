from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.models import SupportTicket
from app.services.support import support_category_label

ADMIN_HOME_TEXT = "🏠 Админ-панель"


def admin_support_inbox_keyboard(
    tickets: Sequence[SupportTicket],
    *,
    status: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📬 Открытые", callback_data="menu:admin:support:list:open")
    builder.button(text="🗂 Закрытые", callback_data="menu:admin:support:list:closed")
    for ticket in tickets:
        user_label = ticket.user.first_name or ticket.user.username or f"User {ticket.user_id}"
        builder.button(
            text=(
                f"#{ticket.id} • {support_category_label(ticket.category)} • "
                f"{user_label}"
            ),
            callback_data=f"menu:admin:support:view:{ticket.id}:{status}",
        )
    builder.button(text="⬅️ Назад", callback_data="menu:admin:home")
    builder.button(text=ADMIN_HOME_TEXT, callback_data="menu:admin:home")
    builder.adjust(2, *([1] * len(tickets)), 1, 1)
    return builder.as_markup()


def admin_support_ticket_keyboard(
    ticket_id: int,
    *,
    status: str,
    is_open: bool,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_open:
        builder.button(
            text="✉️ Ответить",
            callback_data=f"menu:admin:support:reply:{ticket_id}:{status}",
        )
        builder.button(
            text="✅ Закрыть",
            callback_data=f"menu:admin:support:close:{ticket_id}:{status}",
        )
    else:
        builder.button(
            text="♻️ Переоткрыть",
            callback_data=f"menu:admin:support:reopen:{ticket_id}:{status}",
        )
    builder.button(text="📬 К списку", callback_data=f"menu:admin:support:list:{status}")
    builder.button(text="⬅️ Назад", callback_data="menu:admin:home")
    builder.button(text=ADMIN_HOME_TEXT, callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()
