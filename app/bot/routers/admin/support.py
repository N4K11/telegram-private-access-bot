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
    SUPPORT_SLA_BUCKET_LABELS,
    SUPPORT_STATUS_CLOSED,
    SUPPORT_STATUS_OPEN,
    SupportAdminInbox,
    SupportTicketError,
    add_admin_ticket_reply,
    build_admin_support_inbox,
    build_support_canned_replies,
    close_support_ticket,
    get_admin_ticket_thread,
    reopen_support_ticket,
    support_action_lane_label,
    support_canned_reply_pack_label,
    support_category_label,
    support_close_reason_label,
    support_escalation_lane,
    support_escalation_lane_label,
    support_priority_label,
    support_sla_bucket,
    support_sla_hotspot_label,
    support_status_label,
    support_waiting_state_label,
)
from app.utils.datetime import format_datetime

router = Router(name="admin_support")
router.message.filter(AdminFilter(PERMISSION_SUPPORT))
router.callback_query.filter(AdminFilter(PERMISSION_SUPPORT))
logger = logging.getLogger(__name__)
THREAD_RENDER_LIMIT = 8

REPLY_PROMPT_TEXT = (
    "\u2709\ufe0f "
    "\u041d\u0430\u043f\u0438\u0448\u0438 "
    "\u043e\u0442\u0432\u0435\u0442 "
    "\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044e "
    "\u043e\u0434\u043d\u0438\u043c "
    "\u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435\u043c."
)
REPLY_SENT_TEXT = (
    "\u2705 "
    "\u041e\u0442\u0432\u0435\u0442 "
    "\u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d "
    "\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044e."
)
REPLY_FAILED_TEXT = (
    "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c "
    "\u043e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c "
    "\u043e\u0442\u0432\u0435\u0442. "
    "\u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439 "
    "\u043f\u043e\u0437\u0436\u0435."
)
CLOSE_TEXT = (
    "\u2705 "
    "\u041e\u0431\u0440\u0430\u0449\u0435\u043d\u0438\u0435 "
    "\u0437\u0430\u043a\u0440\u044b\u0442\u043e."
)
REOPEN_TEXT = (
    "\u267b\ufe0f "
    "\u041e\u0431\u0440\u0430\u0449\u0435\u043d\u0438\u0435 "
    "\u043f\u0435\u0440\u0435\u043e\u0442\u043a\u0440\u044b\u0442\u043e."
)
SUPPORT_TITLE = "\U0001f3ab \u041f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430"
TICKET_TITLE = "\U0001f3ab \u041e\u0431\u0440\u0430\u0449\u0435\u043d\u0438\u0435"
WAITING_CLOSED = "\u0437\u0430\u043a\u0440\u044b\u0442"
WAITING_ADMIN = "\u0436\u0434\u0451\u0442 \u0430\u0434\u043c\u0438\u043d\u0430"
WAITING_USER = (
    "\u0436\u0434\u0451\u0442 "
    "\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f"
)
WAITING_NEW = "\u043d\u043e\u0432\u044b\u0439"


@router.message(Command("admin_support"))
async def admin_support(message: Message, session: AsyncSession, settings: Settings) -> None:
    inbox = await build_admin_support_inbox(session, status=SUPPORT_STATUS_OPEN)
    await render_section(
        message,
        text=_render_inbox(inbox, timezone=settings.timezone),
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
        text=_render_inbox(inbox, timezone=settings.timezone),
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
        text=_render_inbox(inbox, timezone=settings.timezone),
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
            user_id=thread.ticket.user_id,
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
        await callback.answer(
            "\u0421\u043d\u0430\u0447\u0430\u043b\u0430 "
            "\u043f\u0435\u0440\u0435\u043e\u0442\u043a\u0440\u043e\u0439 "
            "\u043e\u0431\u0440\u0430\u0449\u0435\u043d\u0438\u0435.",
            show_alert=True,
        )
        return

    await state.set_state(AdminSupportForm.waiting_for_reply)
    await state.update_data(admin_support_ticket_id=ticket_id, admin_support_status=status)
    await callback.message.answer(REPLY_PROMPT_TEXT)
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
            REPLY_SENT_TEXT + "\n\n" + _render_thread(thread, timezone=settings.timezone),
            reply_markup=admin_support_ticket_keyboard(
                thread.ticket.id,
                user_id=thread.ticket.user_id,
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
        await message.answer(REPLY_FAILED_TEXT)


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
            text=CLOSE_TEXT + "\n\n" + _render_thread(thread, timezone=settings.timezone),
            reply_markup=admin_support_ticket_keyboard(
                thread.ticket.id,
                user_id=thread.ticket.user_id,
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
            text=REOPEN_TEXT + "\n\n" + _render_thread(thread, timezone=settings.timezone),
            reply_markup=admin_support_ticket_keyboard(
                thread.ticket.id,
                user_id=thread.ticket.user_id,
                status=status,
                is_open=True,
            ),
            banner_path=get_banner_path("admin"),
        )
    except SupportTicketError as exc:
        await session.rollback()
        await callback.answer(str(exc), show_alert=True)


def _render_inbox(inbox: SupportAdminInbox, *, timezone: str) -> str:
    lines = [
        f"{SUPPORT_TITLE} • {support_status_label(inbox.status)}",
        "",
        "Сводка:",
        f"• Открыто: {inbox.open_count}",
        f"• Закрыто: {inbox.closed_count}",
        f"• Ждут ответа админа: {inbox.awaiting_admin_count}",
        f"• Ждут пользователя: {inbox.awaiting_user_count}",
        f"• Высокий приоритет: {inbox.high_priority_open_count}",
        f"• Скоро SLA: {inbox.sla_warning_count}",
        f"• SLA нарушен: {inbox.sla_breach_count}",
        f"• Просрочено >24ч: {inbox.stale_open_count}",
    ]
    if inbox.close_reason_counts:
        close_reasons = ", ".join(
            f"{support_close_reason_label(reason)} — {count}"
            for reason, count in sorted(inbox.close_reason_counts.items())
        )
        lines.append(
            "• Причины закрытия: "
            + close_reasons
        )

    insight_lines = _render_insights(inbox)
    if insight_lines:
        lines.append("")
        lines.extend(insight_lines)

    lines.append("")
    if not inbox.tickets:
        lines.append(
            "Список обращений пуст."
        )
        return "\n".join(lines)

    for ticket in inbox.tickets:
        user_name = ticket.user.first_name or ticket.user.username or f"User {ticket.user_id}"
        state_label = _ticket_waiting_label(ticket)
        sla_label = SUPPORT_SLA_BUCKET_LABELS.get(support_sla_bucket(ticket), "—")
        updated_label = format_datetime(ticket.updated_at, timezone)
        lines.append(
            f"#{ticket.id} • {support_category_label(ticket.category)} • {escape(user_name)}"
        )
        lines.append(
            f"?????????: {support_priority_label(ticket.priority)} "
            f"? SLA: {sla_label} ? {state_label}"
        )
        lines.append(
            f"Эскалация: {support_escalation_lane_label(support_escalation_lane(ticket))}"
        )
        lines.append(
            f"Обновлено: {updated_label} • Сообщений: {len(ticket.messages)}"
        )
        if ticket.close_reason:
            lines.append(
                f"Закрытие: {support_close_reason_label(ticket.close_reason)}"
            )
        if ticket.messages:
            lines.append(
                f"Последнее: {escape(_shorten(ticket.messages[-1].body, limit=100))}"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def _render_insights(inbox: SupportAdminInbox) -> list[str]:
    priority_preview = _format_insight_counts(
        inbox.insights.priority_counts,
        label_resolver=support_priority_label,
        limit=4,
    )
    waiting_preview = _format_insight_counts(
        inbox.insights.waiting_state_counts,
        label_resolver=support_waiting_state_label,
        limit=3,
    )
    category_preview = _format_insight_counts(
        inbox.insights.category_counts,
        label_resolver=support_category_label,
        limit=3,
    )
    pack_preview = _format_insight_counts(
        inbox.insights.canned_reply_pack_counts,
        label_resolver=support_canned_reply_pack_label,
        limit=3,
    )
    recent_close_preview = _format_insight_counts(
        inbox.insights.recent_close_reason_counts,
        label_resolver=support_close_reason_label,
        limit=3,
        total=inbox.insights.recent_close_total,
        with_share=True,
    )
    hotspot_preview = _format_hotspot_preview(inbox, limit=3)
    sla_action_preview = _format_sla_action_preview(inbox, limit=3)
    pack_outcome_preview = _format_pack_outcome_preview(inbox, limit=2)
    trend_preview = _format_close_trend_preview(inbox, limit=3)
    action_lane_preview = _format_action_lane_preview(inbox, limit=3)
    escalation_preview = _format_escalation_preview(inbox, limit=3)
    escalation_action_preview = _format_escalation_action_preview(inbox, limit=3)
    priority_focus_preview = _format_priority_focus_preview(inbox, limit=3)
    escalation_watch_preview = _format_escalation_watch_preview(inbox, limit=3)
    escalation_trend_preview = _format_escalation_trend_preview(inbox, limit=3)
    operator_action_trend_preview = _format_operator_action_trend_preview(inbox, limit=2)

    lines = ["???????:"]
    if priority_preview:
        lines.append(f"? ??????????: {priority_preview}")
    if waiting_preview:
        lines.append(f"? ???????: {waiting_preview}")
    if category_preview:
        lines.append(f"? ?????????: {category_preview}")
    if pack_preview:
        lines.append(f"? Reply-????: {pack_preview}")
    if hotspot_preview:
        lines.append(f"? SLA hotspots: {hotspot_preview}")
    if sla_action_preview:
        lines.append(f"? SLA ????????: {sla_action_preview}")
    if pack_outcome_preview:
        lines.append(f"? ????????????? ?????: {pack_outcome_preview}")
    if recent_close_preview:
        lines.append(f"? ???????? ?? {inbox.insights.recent_close_days}?: {recent_close_preview}")
    if trend_preview:
        lines.append(f"? ?????? ????????: {trend_preview}")
    if action_lane_preview:
        lines.append(f"? Action lanes: {action_lane_preview}")
    if escalation_preview:
        lines.append(f"? ?????????: {escalation_preview}")
    if escalation_action_preview:
        lines.append(f"? ????????? ? ???: {escalation_action_preview}")
    if priority_focus_preview:
        lines.append(f"? ?????????-?????: {priority_focus_preview}")
    if escalation_watch_preview:
        lines.append(f"? ?????????-watchlist: {escalation_watch_preview}")
    if escalation_trend_preview:
        lines.append(f"? ?????? ?????????: {escalation_trend_preview}")
    if operator_action_trend_preview:
        lines.append(f"• Operator action trends: {operator_action_trend_preview}")
    return lines if len(lines) > 1 else []

def _format_insight_counts(
    counts: dict[str, int],
    *,
    label_resolver,
    limit: int,
    total: int | None = None,
    with_share: bool = False,
) -> str:
    if not counts:
        return ""
    base_total = total if total is not None else sum(counts.values())
    parts: list[str] = []
    for key, count in sorted(
        counts.items(),
        key=lambda item: (-item[1], label_resolver(item[0])),
    )[:limit]:
        suffix = ""
        if with_share and base_total:
            suffix = f" ({round((count / base_total) * 100, 1)}%)"
        parts.append(f"{label_resolver(key)} — {count}{suffix}")
    return ", ".join(parts)


def _format_hotspot_preview(inbox: SupportAdminInbox, *, limit: int) -> str:
    if not inbox.insights.sla_hotspots:
        return ""
    parts = []
    for item in inbox.insights.sla_hotspots[:limit]:
        parts.append(
            f"{support_sla_hotspot_label(item.kind)} / "
            f"{support_category_label(item.category)} / "
            f"{support_priority_label(item.priority)} ? {item.count}"
        )
    return ", ".join(parts)


def _format_sla_action_preview(inbox: SupportAdminInbox, *, limit: int) -> str:
    if not inbox.insights.sla_actions:
        return ""
    parts = []
    for item in inbox.insights.sla_actions[:limit]:
        parts.append(
            f"{support_sla_hotspot_label(item.kind)} -> "
            f"{support_action_lane_label(item.action_key)} "
            f"({support_escalation_lane_label(item.escalation_key)})"
        )
    return ", ".join(parts)


def _format_pack_outcome_preview(inbox: SupportAdminInbox, *, limit: int) -> str:
    if not inbox.insights.canned_reply_pack_outcomes:
        return ""
    parts = []
    for item in inbox.insights.canned_reply_pack_outcomes[:limit]:
        parts.append(
            f"{support_canned_reply_pack_label(item.pack_key)} ? "
            f"{item.resolved_rate_percent}% ??????, "
            f"{item.no_response_rate_percent}% ??? ??????"
        )
    return ", ".join(parts)


def _format_close_trend_preview(inbox: SupportAdminInbox, *, limit: int) -> str:
    if not inbox.insights.close_reason_trends:
        return ""
    parts = []
    for item in inbox.insights.close_reason_trends[:limit]:
        delta = f"+{item.delta}" if item.delta > 0 else str(item.delta)
        parts.append(
            f"{support_close_reason_label(item.reason)} ? "
            f"{item.current_count}/{item.previous_count} ({delta})"
        )
    return ", ".join(parts)


def _format_action_lane_preview(inbox: SupportAdminInbox, *, limit: int) -> str:
    if not inbox.insights.action_lanes:
        return ""
    parts = []
    for item in inbox.insights.action_lanes[:limit]:
        parts.append(f"{support_action_lane_label(item.key)} ? {item.count}")
    return ", ".join(parts)


def _format_escalation_preview(inbox: SupportAdminInbox, *, limit: int) -> str:
    if not inbox.insights.escalation_lanes:
        return ""
    parts = []
    for item in inbox.insights.escalation_lanes[:limit]:
        parts.append(f"{support_escalation_lane_label(item.key)} ? {item.count}")
    return ", ".join(parts)


def _format_escalation_action_preview(inbox: SupportAdminInbox, *, limit: int) -> str:
    if not inbox.insights.escalation_actions:
        return ""
    parts = []
    for item in inbox.insights.escalation_actions[:limit]:
        parts.append(
            f"{support_escalation_lane_label(item.escalation_key)} -> "
            f"{support_action_lane_label(item.action_key)} ? {item.count}"
        )
    return ", ".join(parts)


def _format_priority_focus_preview(inbox: SupportAdminInbox, *, limit: int) -> str:
    if not inbox.insights.priority_focus:
        return ""
    parts = []
    for item in inbox.insights.priority_focus[:limit]:
        action_label = (
            support_action_lane_label(item.top_action_lane)
            if item.top_action_lane
            else "?"
        )
        escalation_label = (
            support_escalation_lane_label(item.top_escalation_lane)
            if item.top_escalation_lane
            else "?"
        )
        parts.append(
            f"{support_priority_label(item.key)} ? {item.count} "
            f"(breach {item.sla_breach_count}, {action_label}, {escalation_label})"
        )
    return ", ".join(parts)


def _format_escalation_watch_preview(inbox: SupportAdminInbox, *, limit: int) -> str:
    if not inbox.insights.escalation_watchlist:
        return ""
    parts = []
    for item in inbox.insights.escalation_watchlist[:limit]:
        action_label = (
            support_action_lane_label(item.top_action_lane)
            if item.top_action_lane
            else "?"
        )
        parts.append(
            f"{support_escalation_lane_label(item.key)} ? score {item.watch_score} "
            f"({action_label})"
        )
    return ", ".join(parts)


def _format_escalation_trend_preview(inbox: SupportAdminInbox, *, limit: int) -> str:
    if not inbox.insights.escalation_trends:
        return ""
    parts = []
    for item in inbox.insights.escalation_trends[:limit]:
        delta = f"+{item.delta}" if item.delta > 0 else str(item.delta)
        parts.append(
            f"{support_escalation_lane_label(item.key)} ? "
            f"{item.current_count}/{item.previous_count} ({delta})"
        )
    return ", ".join(parts)


def _format_operator_action_trend_preview(inbox: SupportAdminInbox, *, limit: int) -> str:
    if not inbox.insights.operator_action_trends:
        return ""
    parts = []
    for item in inbox.insights.operator_action_trends[:limit]:
        delta = f"+{item.delta}" if item.delta > 0 else str(item.delta)
        parts.append(
            f"{support_canned_reply_pack_label(item.pack_key)} -> "
            f"{support_action_lane_label(item.action_key)} / "
            f"{support_close_reason_label(item.close_reason)} • "
            f"{item.current_count}/{item.previous_count} ({delta})"
        )
    return ", ".join(parts)


def _render_thread(thread, *, timezone: str) -> str:
    ticket = thread.ticket
    user = ticket.user
    user_name = user.first_name or user.username or str(user.telegram_id)
    user_label = "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c"
    category_label = "\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f"
    status_label = "\u0421\u0442\u0430\u0442\u0443\u0441"
    priority_label = "\u041f\u0440\u0438\u043e\u0440\u0438\u0442\u0435\u0442"
    state_label = "\u0421\u043e\u0441\u0442\u043e\u044f\u043d\u0438\u0435"
    close_label = (
        "\u041f\u0440\u0438\u0447\u0438\u043d\u0430 "
        "\u0437\u0430\u043a\u0440\u044b\u0442\u0438\u044f"
    )
    created_label = "\u0421\u043e\u0437\u0434\u0430\u043d\u043e"
    updated_label = "\u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u043e"
    messages_label = (
        "\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 "
        "\u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f"
    )
    close_reason_label = (
        support_close_reason_label(ticket.close_reason)
        if ticket.status == SUPPORT_STATUS_CLOSED
        else "\u2014"
    )
    sla_label = SUPPORT_SLA_BUCKET_LABELS.get(support_sla_bucket(ticket), "\u2014")
    escalation_label = support_escalation_lane_label(support_escalation_lane(ticket))
    lines = [
        f"{TICKET_TITLE} #{ticket.id}",
        "",
        f"{user_label}: {escape(user_name)}",
        f"Telegram ID: <code>{user.telegram_id}</code>",
        f"{category_label}: {support_category_label(ticket.category)}",
        f"{status_label}: {support_status_label(ticket.status)}",
        f"{priority_label}: {support_priority_label(ticket.priority)}",
        f"SLA: {sla_label}",
        f"{state_label}: {_ticket_waiting_label(ticket)}",
        f"Эскалация: {escape(escalation_label)}",
        f"{close_label}: {close_reason_label}",
        f"{created_label}: {format_datetime(ticket.created_at, timezone)}",
        f"{updated_label}: {format_datetime(ticket.updated_at, timezone)}",
        "",
        f"{messages_label}:",
    ]
    for item in thread.messages[-THREAD_RENDER_LIMIT:]:
        sender_label = (
            "\u0410\u0434\u043c\u0438\u043d"
            if item.is_admin
            else "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c"
        )
        item_time = format_datetime(item.created_at, timezone)
        lines.append(f"\u2022 {sender_label} \u2022 {item_time}")
        lines.append(escape(_shorten(item.body, limit=450)))

    suggested_replies = build_support_canned_replies(ticket)
    if suggested_replies:
        lines.append("")
        lines.append(
            "\u0411\u044b\u0441\u0442\u0440\u044b\u0435 "
            "\u043e\u0442\u0432\u0435\u0442\u044b:"
        )
        for reply in suggested_replies:
            lines.append(f"\u2022 {reply.title}")
            lines.append(escape(_shorten(reply.body, limit=220)))
    return "\n".join(lines)


async def _notify_user_about_admin_reply(bot: Bot, thread, *, timezone: str) -> None:
    latest_message = thread.messages[-1]
    category_label = support_category_label(thread.ticket.category)
    status_label = support_status_label(thread.ticket.status)
    created_label = format_datetime(latest_message.created_at, timezone)
    text = "\n".join(
        [
            (
                "\u2709\ufe0f \u041e\u0442\u0432\u0435\u0442 "
                "\u043f\u043e \u043e\u0431\u0440\u0430\u0449\u0435\u043d\u0438\u044e "
                f"#{thread.ticket.id}"
            ),
            "",
            f"\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f: {category_label}",
            f"\u0421\u0442\u0430\u0442\u0443\u0441: {status_label}",
            f"\u0412\u0440\u0435\u043c\u044f: {created_label}",
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


def _ticket_waiting_label(ticket) -> str:
    if ticket.status != SUPPORT_STATUS_OPEN:
        return WAITING_CLOSED
    if ticket.last_user_message_at and (
        ticket.last_admin_message_at is None
        or ticket.last_user_message_at > ticket.last_admin_message_at
    ):
        return WAITING_ADMIN
    if ticket.last_admin_message_at:
        return WAITING_USER
    return WAITING_NEW


def _shorten(text: str, *, limit: int) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 3]}..."
