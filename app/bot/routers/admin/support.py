from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.assets import get_banner_path
from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin_support import (
    admin_support_inbox_keyboard,
    admin_support_ticket_keyboard,
)
from app.bot.rendering import render_section
from app.bot.states.admin import AdminSupportForm
from app.config import Settings
from app.db.repositories.users import UserRepository
from app.services.admin_roles import PERMISSION_SUPPORT
from app.services.support import (
    SUPPORT_STATUS_CLOSED,
    SUPPORT_STATUS_OPEN,
    SupportTicketError,
    add_admin_ticket_reply,
    build_admin_support_inbox,
    close_support_ticket,
    get_admin_ticket_thread,
    reopen_support_ticket,
    support_category_label,
    support_status_label,
)
from app.utils.datetime import format_datetime

router = Router(name="admin_support")
router.message.filter(AdminFilter(PERMISSION_SUPPORT))
router.callback_query.filter(AdminFilter(PERMISSION_SUPPORT))
logger = logging.getLogger(__name__)
THREAD_RENDER_LIMIT = 8


@router.message(Command("admin_support"))
async def admin_support(message: Message, session: AsyncSession, settings: Settings) -> None:
    inbox = await build_admin_support_inbox(session, status=SUPPORT_STATUS_OPEN)
    await render_section(
        message,
        text=_render_inbox(inbox.status, inbox.tickets, timezone=settings.timezone),
        reply_markup=admin_support_inbox_keyboard(inbox.tickets, status=inbox.status),
        banner_path=get_banner_path("admin"),
    )


@router.callback_query(F.data == "menu:admin:support")
async def admin_support_home(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    inbox = await build_admin_support_inbox(session, status=SUPPORT_STATUS_OPEN)
    await render_section(
        callback,
        text=_render_inbox(inbox.status, inbox.tickets, timezone=settings.timezone),
        reply_markup=admin_support_inbox_keyboard(inbox.tickets, status=inbox.status),
        banner_path=get_banner_path("admin"),
    )


@router.callback_query(F.data.startswith("menu:admin:support:list:"))
async def admin_support_list(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    status = callback.data.rsplit(":", 1)[-1] if callback.data else SUPPORT_STATUS_OPEN
    if status not in {SUPPORT_STATUS_OPEN, SUPPORT_STATUS_CLOSED}:
        await callback.answer()
        return
    inbox = await build_admin_support_inbox(session, status=status)
    await render_section(
        callback,
        text=_render_inbox(inbox.status, inbox.tickets, timezone=settings.timezone),
        reply_markup=admin_support_inbox_keyboard(inbox.tickets, status=inbox.status),
        banner_path=get_banner_path("admin"),
    )


@router.callback_query(F.data.startswith("menu:admin:support:view:"))
async def admin_support_view(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    context = _parse_admin_ticket_context(callback.data, action="view")
    if context is None:
        await callback.answer()
        return
    ticket_id, status = context
    try:
        thread = await get_admin_ticket_thread(session, ticket_id=ticket_id)
    except SupportTicketError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await render_section(
        callback,
        text=_render_thread(thread, timezone=settings.timezone),
        reply_markup=admin_support_ticket_keyboard(
            thread.ticket.id,
            status=status,
            is_open=thread.ticket.status == SUPPORT_STATUS_OPEN,
        ),
        banner_path=get_banner_path("admin"),
    )


@router.callback_query(F.data.startswith("menu:admin:support:reply:"))
async def admin_support_reply_prompt(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    context = _parse_admin_ticket_context(callback.data, action="reply")
    if context is None:
        await callback.answer()
        return
    ticket_id, status = context
    try:
        thread = await get_admin_ticket_thread(session, ticket_id=ticket_id)
    except SupportTicketError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    if thread.ticket.status != SUPPORT_STATUS_OPEN:
        await callback.answer("Сначала переоткрой обращение.", show_alert=True)
        return

    await state.set_state(AdminSupportForm.waiting_for_reply)
    await state.update_data(admin_support_ticket_id=ticket_id, admin_support_status=status)
    await callback.message.answer("✉️ Напиши ответ пользователю одним сообщением.")
    await callback.answer()


@router.message(AdminSupportForm.waiting_for_reply)
async def admin_support_receive_reply(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    bot: Bot,
) -> None:
    data = await state.get_data()
    ticket_id = int(data.get("admin_support_ticket_id"))
    list_status = str(data.get("admin_support_status") or SUPPORT_STATUS_OPEN)
    admin_user = await UserRepository(session).get_by_telegram_id(message.from_user.id)
    try:
        thread = await add_admin_ticket_reply(
            session,
            ticket_id=ticket_id,
            admin_user_id=admin_user.id if admin_user is not None else None,
            body=message.text or "",
            now=message.date,
        )
        await session.commit()
        await _notify_user_about_admin_reply(bot, thread, timezone=settings.timezone)
        await state.clear()
        await message.answer(
            "✅ Ответ отправлен пользователю.\n\n"
            + _render_thread(thread, timezone=settings.timezone),
            reply_markup=admin_support_ticket_keyboard(
                thread.ticket.id,
                status=list_status,
                is_open=True,
            ),
        )
    except SupportTicketError as exc:
        await session.rollback()
        await message.answer(str(exc))
    except Exception:
        await session.rollback()
        logger.exception("Failed to send admin support reply for ticket %s", ticket_id)
        await message.answer("Не удалось отправить ответ. Попробуй позже.")


@router.callback_query(F.data.startswith("menu:admin:support:close:"))
async def admin_support_close(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    context = _parse_admin_ticket_context(callback.data, action="close")
    if context is None:
        await callback.answer()
        return
    ticket_id, status = context
    admin_user = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
    try:
        thread = await close_support_ticket(
            session,
            ticket_id=ticket_id,
            actor_user_id=admin_user.id if admin_user is not None else None,
        )
        await session.commit()
        await render_section(
            callback,
            text="✅ Обращение закрыто.\n\n" + _render_thread(thread, timezone=settings.timezone),
            reply_markup=admin_support_ticket_keyboard(
                thread.ticket.id,
                status=status,
                is_open=False,
            ),
            banner_path=get_banner_path("admin"),
        )
    except SupportTicketError as exc:
        await session.rollback()
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data.startswith("menu:admin:support:reopen:"))
async def admin_support_reopen(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    context = _parse_admin_ticket_context(callback.data, action="reopen")
    if context is None:
        await callback.answer()
        return
    ticket_id, status = context
    admin_user = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
    try:
        thread = await reopen_support_ticket(
            session,
            ticket_id=ticket_id,
            actor_user_id=admin_user.id if admin_user is not None else None,
        )
        await session.commit()
        await render_section(
            callback,
            text=(
                "♻️ Обращение переоткрыто.\n\n"
                + _render_thread(thread, timezone=settings.timezone)
            ),
            reply_markup=admin_support_ticket_keyboard(
                thread.ticket.id,
                status=status,
                is_open=True,
            ),
            banner_path=get_banner_path("admin"),
        )
    except SupportTicketError as exc:
        await session.rollback()
        await callback.answer(str(exc), show_alert=True)


def _render_inbox(status: str, tickets, *, timezone: str) -> str:
    lines = [
        f"🎫 Поддержка • {support_status_label(status)}",
        "",
    ]
    if not tickets:
        lines.append("Список обращений пуст.")
        return "\n".join(lines)
    for ticket in tickets:
        user_name = ticket.user.first_name or ticket.user.username or f"User {ticket.user_id}"
        lines.append(
            f"#{ticket.id} • {support_category_label(ticket.category)} • {escape(user_name)}"
        )
        lines.append(
            f"Обновлено: {format_datetime(ticket.updated_at, timezone)} • "
            f"Сообщений: {len(ticket.messages)}"
        )
        if ticket.messages:
            lines.append(f"Последнее: {escape(_shorten(ticket.messages[-1].body, limit=100))}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _render_thread(thread, *, timezone: str) -> str:
    ticket = thread.ticket
    user = ticket.user
    user_name = user.first_name or user.username or str(user.telegram_id)
    lines = [
        f"🎫 Обращение #{ticket.id}",
        "",
        f"Пользователь: {escape(user_name)}",
        f"Telegram ID: <code>{user.telegram_id}</code>",
        f"Категория: {support_category_label(ticket.category)}",
        f"Статус: {support_status_label(ticket.status)}",
        f"Создано: {format_datetime(ticket.created_at, timezone)}",
        f"Обновлено: {format_datetime(ticket.updated_at, timezone)}",
        "",
        "Последние сообщения:",
    ]
    for item in thread.messages[-THREAD_RENDER_LIMIT:]:
        sender_label = "Админ" if item.is_admin else "Пользователь"
        lines.append(f"• {sender_label} • {format_datetime(item.created_at, timezone)}")
        lines.append(escape(_shorten(item.body, limit=450)))
    return "\n".join(lines)


async def _notify_user_about_admin_reply(bot: Bot, thread, *, timezone: str) -> None:
    latest_message = thread.messages[-1]
    text = "\n".join(
        [
            f"✉️ Ответ по обращению #{thread.ticket.id}",
            "",
            f"Категория: {support_category_label(thread.ticket.category)}",
            f"Статус: {support_status_label(thread.ticket.status)}",
            f"Время: {format_datetime(latest_message.created_at, timezone)}",
            "",
            escape(latest_message.body),
        ]
    )
    await bot.send_message(thread.ticket.user.telegram_id, text)


def _parse_admin_ticket_context(data: str | None, *, action: str) -> tuple[int, str] | None:
    if data is None:
        return None
    parts = data.split(":")
    if len(parts) != 6 or parts[:4] != ["menu", "admin", "support", action]:
        return None
    try:
        return int(parts[4]), parts[5]
    except ValueError:
        return None


def _shorten(text: str, *, limit: int) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 3]}..."


