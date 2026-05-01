from __future__ import annotations

import inspect
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.assets import get_banner_path
from app.bot.keyboards.user_support import (
    user_support_category_keyboard,
    user_support_compose_keyboard,
    user_support_overview_keyboard,
    user_support_ticket_keyboard,
    user_support_ticket_list_keyboard,
)
from app.bot.rendering import render_section
from app.bot.states.user import UserSupportForm
from app.config import Settings
from app.db.repositories.users import UserRepository
from app.services.support import (
    SUPPORT_STATUS_OPEN,
    SupportTicketError,
    add_user_ticket_message,
    build_user_support_dashboard,
    create_support_ticket,
    get_user_ticket_thread,
    support_category_label,
    support_status_label,
)
from app.services.texts import render_text
from app.utils.datetime import format_datetime

router = Router(name="user_support")
logger = logging.getLogger(__name__)
THREAD_RENDER_LIMIT = 6


async def _text(
    session: AsyncSession | None,
    key: str,
    **context: object,
) -> str:
    rendered = (
        render_text(session, key, **context) if session is not None else render_text(key, **context)
    )
    if inspect.isawaitable(rendered):
        return await rendered
    return rendered


async def render_support_home(
    target: Message | CallbackQuery,
    *,
    session: AsyncSession | None,
    settings: Settings | None = None,
) -> None:
    if session is None or getattr(target, "from_user", None) is None:
        await render_section(
            target,
            text="❓ Поддержка\n\nОткрой /start, чтобы бот загрузил твой профиль и обращения.",
            reply_markup=user_support_overview_keyboard(open_ticket_id=None),
            banner_path=get_banner_path("help"),
        )
        return

    user = await UserRepository(session).get_by_telegram_id(target.from_user.id)
    if user is None:
        await render_section(
            target,
            text="❓ Поддержка\n\nОткрой /start, чтобы бот зарегистрировал тебя в системе.",
            reply_markup=user_support_overview_keyboard(open_ticket_id=None),
            banner_path=get_banner_path("help"),
        )
        return

    dashboard = await build_user_support_dashboard(session, user_id=user.id)
    text = await _render_dashboard_text(session, dashboard=dashboard, timezone=_timezone(settings))
    await render_section(
        target,
        text=text,
        reply_markup=user_support_overview_keyboard(
            open_ticket_id=dashboard.open_ticket.id if dashboard.open_ticket is not None else None
        ),
        banner_path=get_banner_path("help"),
    )


@router.message(Command("support"))
async def support_command(
    message: Message,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    await render_support_home(message, session=session, settings=settings)


@router.callback_query(F.data == "menu:user:support:create")
async def create_support_request(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()
    user = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.answer("Сначала открой /start.", show_alert=True)
        return

    dashboard = await build_user_support_dashboard(session, user_id=user.id)
    if dashboard.open_ticket is not None:
        await show_user_ticket(callback, session, ticket_id=dashboard.open_ticket.id)
        return

    await render_section(
        callback,
        text=(
            "🎫 Новое обращение\n\n"
            "Выбери категорию. После этого бот попросит текст обращения."
        ),
        reply_markup=user_support_category_keyboard(),
        banner_path=get_banner_path("help"),
    )


@router.callback_query(F.data == "menu:user:support:list")
async def list_user_tickets(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings | None = None,
) -> None:
    user = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.answer("Сначала открой /start.", show_alert=True)
        return

    dashboard = await build_user_support_dashboard(session, user_id=user.id)
    if not dashboard.recent_tickets:
        text = "📨 Мои обращения\n\nУ тебя пока нет сохранённых обращений."
    else:
        text = _render_ticket_list(dashboard.recent_tickets, timezone=_timezone(settings))
    await render_section(
        callback,
        text=text,
        reply_markup=user_support_ticket_list_keyboard(dashboard.recent_tickets),
        banner_path=get_banner_path("help"),
    )


@router.callback_query(F.data.startswith("menu:user:support:view:"))
async def show_user_ticket(
    callback: CallbackQuery,
    session: AsyncSession,
    ticket_id: int | None = None,
    settings: Settings | None = None,
) -> None:
    resolved_ticket_id = ticket_id or _parse_ticket_id(
        callback.data,
        prefix="menu:user:support:view:",
    )
    if resolved_ticket_id is None:
        await callback.answer()
        return

    user = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.answer("Сначала открой /start.", show_alert=True)
        return

    try:
        thread = await get_user_ticket_thread(
            session,
            ticket_id=resolved_ticket_id,
            user_id=user.id,
        )
    except SupportTicketError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await render_section(
        callback,
        text=_render_ticket_thread(thread, timezone=_timezone(settings), viewer="user"),
        reply_markup=user_support_ticket_keyboard(thread.ticket),
        banner_path=get_banner_path("help"),
    )


@router.callback_query(F.data.startswith("menu:user:support:add:"))
async def add_to_open_ticket(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    ticket_id = _parse_ticket_id(callback.data, prefix="menu:user:support:add:")
    if ticket_id is None:
        await callback.answer()
        return

    user = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.answer("Сначала открой /start.", show_alert=True)
        return

    try:
        thread = await get_user_ticket_thread(session, ticket_id=ticket_id, user_id=user.id)
    except SupportTicketError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    if thread.ticket.status != SUPPORT_STATUS_OPEN:
        await callback.answer("Обращение уже закрыто.", show_alert=True)
        return

    await state.set_state(UserSupportForm.waiting_for_message)
    await state.update_data(support_mode="reply", support_ticket_id=ticket_id)
    await callback.message.answer(
        "✍️ Напиши сообщение для поддержки одним сообщением.",
        reply_markup=user_support_compose_keyboard(
            back_callback=f"menu:user:support:view:{ticket_id}"
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("menu:user:support:category:"))
async def choose_support_category(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    category = callback.data.rsplit(":", 1)[-1] if callback.data else ""
    await state.set_state(UserSupportForm.waiting_for_message)
    await state.update_data(support_mode="create", support_category=category)
    await callback.message.answer(
        f"✍️ Напиши текст обращения в категории «{support_category_label(category)}».",
        reply_markup=user_support_compose_keyboard(back_callback="menu:user:support:create"),
    )
    await callback.answer()


@router.message(UserSupportForm.waiting_for_message)
async def receive_support_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
) -> None:
    data = await state.get_data()
    user = await UserRepository(session).get_by_telegram_id(message.from_user.id)
    if user is None:
        await state.clear()
        await message.answer("Сначала открой /start.")
        return

    try:
        mode = data.get("support_mode")
        if mode == "create":
            thread = await create_support_ticket(
                session,
                user_id=user.id,
                category=str(data.get("support_category") or ""),
                body=message.text or "",
                now=message.date,
            )
            await session.commit()
            await _notify_admins_about_user_ticket(bot, settings, thread, is_new=True)
            await state.clear()
            await message.answer(
                "✅ Обращение создано. Поддержка увидит его в админке и ответит сюда.\n\n"
                + _render_ticket_thread(thread, timezone=settings.timezone, viewer="user"),
                reply_markup=user_support_ticket_keyboard(thread.ticket),
            )
            return
        if mode == "reply":
            thread = await add_user_ticket_message(
                session,
                ticket_id=int(data.get("support_ticket_id")),
                user_id=user.id,
                body=message.text or "",
                now=message.date,
            )
            await session.commit()
            await _notify_admins_about_user_ticket(bot, settings, thread, is_new=False)
            await state.clear()
            await message.answer(
                "✅ Сообщение добавлено в обращение.\n\n"
                + _render_ticket_thread(thread, timezone=settings.timezone, viewer="user"),
                reply_markup=user_support_ticket_keyboard(thread.ticket),
            )
            return
        await state.clear()
        await message.answer("Контекст обращения потерян. Открой помощь заново.")
    except SupportTicketError as exc:
        await session.rollback()
        await message.answer(str(exc))
    except Exception:
        await session.rollback()
        logger.exception("Failed to process support message for user %s", user.id)
        await message.answer("Не удалось обработать обращение. Попробуй позже.")


def _render_ticket_list(tickets, *, timezone: str) -> str:
    lines = ["📨 Мои обращения", ""]
    for ticket in tickets:
        lines.append(
            f"#{ticket.id} • {support_category_label(ticket.category)} • "
            f"{support_status_label(ticket.status)}"
        )
        lines.append(
            f"Создано: {format_datetime(ticket.created_at, timezone)} • "
            f"Обновлено: {format_datetime(ticket.updated_at, timezone)}"
        )
        if ticket.messages:
            lines.append(f"Последнее: {_shorten(ticket.messages[-1].body, limit=90)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _render_ticket_thread(thread, *, timezone: str, viewer: str) -> str:
    ticket = thread.ticket
    lines = [
        f"🎫 Обращение #{ticket.id}",
        "",
        f"Категория: {support_category_label(ticket.category)}",
        f"Статус: {support_status_label(ticket.status)}",
        f"Создано: {format_datetime(ticket.created_at, timezone)}",
        f"Обновлено: {format_datetime(ticket.updated_at, timezone)}",
        "",
        "Последние сообщения:",
    ]
    for item in thread.messages[-THREAD_RENDER_LIMIT:]:
        sender_label = (
            "Поддержка"
            if item.is_admin
            else ("Ты" if viewer == "user" else "Пользователь")
        )
        lines.append(f"• {sender_label} • {format_datetime(item.created_at, timezone)}")
        lines.append(escape(_shorten(item.body, limit=350)))
    return "\n".join(lines)


async def _render_dashboard_text(session: AsyncSession, *, dashboard, timezone: str) -> str:
    lines = [await _text(session, "user_support"), "", "Для обращения используй кнопки ниже."]
    if dashboard.open_ticket is not None:
        lines.extend(
            [
                "",
                (
                    f"Открытое обращение: #{dashboard.open_ticket.id} • "
                    f"{support_category_label(dashboard.open_ticket.category)} • "
                    f"{support_status_label(dashboard.open_ticket.status)}"
                ),
                f"Обновлено: {format_datetime(dashboard.open_ticket.updated_at, timezone)}",
            ]
        )
    lines.extend(["", f"Всего сохранённых обращений: {len(dashboard.recent_tickets)}"])
    return "\n".join(lines)


async def _notify_admins_about_user_ticket(
    bot: Bot,
    settings: Settings,
    thread,
    *,
    is_new: bool,
) -> None:
    ticket = thread.ticket
    user = ticket.user
    if user is None:
        return
    action = "Новое обращение" if is_new else "Обновление обращения"
    text = "\n".join(
        [
            f"🎫 {action} #{ticket.id}",
            "",
            f"Категория: {support_category_label(ticket.category)}",
            f"Пользователь: {escape(user.first_name or user.username or str(user.telegram_id))}",
            f"Telegram ID: <code>{user.telegram_id}</code>",
            "",
            f"Сообщение: {escape(_shorten(thread.messages[-1].body, limit=500))}",
            "",
            "Открой /admin и раздел поддержки, чтобы ответить.",
        ]
    )
    for admin_id in settings.admin_ids_set:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            logger.warning(
                "Failed to notify admin %s about support ticket %s",
                admin_id,
                ticket.id,
            )


def _parse_ticket_id(data: str | None, *, prefix: str) -> int | None:
    if data is None or not data.startswith(prefix):
        return None
    raw = data.removeprefix(prefix)
    try:
        return int(raw)
    except ValueError:
        return None


def _timezone(settings: Settings | None) -> str:
    return settings.timezone if settings is not None else "UTC"


def _shorten(text: str, *, limit: int) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 3]}..."
