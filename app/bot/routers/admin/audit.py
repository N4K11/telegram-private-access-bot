# ruff: noqa: E501
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.assets import get_banner_path
from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin_audit import (
    admin_audit_detail_keyboard,
    admin_audit_overview_keyboard,
    admin_audit_prompt_keyboard,
)
from app.bot.rendering import render_section
from app.bot.states.admin import AdminAuditForm
from app.config import Settings
from app.services.admin_roles import PERMISSION_AUDIT
from app.services.audit import (
    AuditViewerError,
    AuditViewerFilters,
    build_audit_csv_report,
    build_audit_page,
    build_audit_report_filename,
    get_audit_event_detail,
    list_recent_audit_actions,
    normalize_audit_action_filter,
    normalize_audit_period,
    render_audit_event_detail,
    render_audit_overview,
    resolve_audit_user_reference,
)
from app.utils.datetime import utcnow

router = Router(name="admin_audit")
router.message.filter(AdminFilter(PERMISSION_AUDIT))
router.callback_query.filter(AdminFilter(PERMISSION_AUDIT))

AUDIT_FILTERS_KEY = "admin_audit_filters"
AUDIT_PAGE_KEY = "admin_audit_page"


@router.message(Command("admin_audit"))
async def admin_audit(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
) -> None:
    await _store_context(state, filters=AuditViewerFilters(), page=1, reset_state=True)
    await _render_overview(
        message,
        session,
        settings,
        state,
        use_banner=True,
    )


@router.callback_query(F.data == "menu:admin:audit")
async def admin_audit_home(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
) -> None:
    await _store_context(state, filters=AuditViewerFilters(), page=1, reset_state=True)
    await _render_overview(callback, session, settings, state, use_banner=True)


@router.callback_query(F.data == "menu:admin:audit:list")
async def admin_audit_list(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
) -> None:
    await _render_overview(callback, session, settings, state, use_banner=True)


@router.callback_query(F.data == "menu:admin:audit:reset")
async def admin_audit_reset(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
) -> None:
    await _store_context(state, filters=AuditViewerFilters(), page=1, reset_state=True)
    await _render_overview(callback, session, settings, state, use_banner=True)


@router.callback_query(F.data.startswith("menu:admin:audit:period:"))
async def admin_audit_set_period(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
) -> None:
    if callback.data is None:
        await callback.answer()
        return
    try:
        period = normalize_audit_period(callback.data.rsplit(":", maxsplit=1)[-1])
    except AuditViewerError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    filters, _ = await _load_context(state)
    updated_filters = AuditViewerFilters(
        target_user_id=filters.target_user_id,
        actor_user_id=filters.actor_user_id,
        action=filters.action,
        period=period,
    )
    await _store_context(state, filters=updated_filters, page=1)
    await _render_overview(callback, session, settings, state, use_banner=True)


@router.callback_query(F.data.startswith("menu:admin:audit:page:"))
async def admin_audit_page(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
) -> None:
    if callback.data is None:
        await callback.answer()
        return
    try:
        page = int(callback.data.rsplit(":", maxsplit=1)[-1])
    except ValueError:
        await callback.answer()
        return
    filters, _ = await _load_context(state)
    await _store_context(state, filters=filters, page=max(page, 1))
    await _render_overview(callback, session, settings, state, use_banner=True)


@router.callback_query(F.data.startswith("menu:admin:audit:view:"))
async def admin_audit_detail(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    audit_log_id = _parse_suffix_int(callback.data)
    if audit_log_id is None:
        await callback.answer()
        return
    try:
        detail = await get_audit_event_detail(session, audit_log_id=audit_log_id)
    except AuditViewerError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await render_section(
        callback,
        text=render_audit_event_detail(detail, timezone=settings.timezone),
        reply_markup=admin_audit_detail_keyboard(
            actor_user_id=detail.actor.user_id if detail.actor is not None else None,
            target_user_id=detail.target.user_id if detail.target is not None else None,
        ),
        banner_path=get_banner_path("admin"),
    )


@router.callback_query(F.data == "menu:admin:audit:export")
async def admin_audit_export(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    filters, _ = await _load_context(state)
    report = await build_audit_csv_report(
        session,
        filters=filters,
        timezone=settings.timezone,
    )
    document = BufferedInputFile(
        report.data,
        filename=build_audit_report_filename(generated_at=utcnow()),
    )
    caption = f"CSV аудита: {report.row_count} событий"
    if report.is_truncated:
        caption += f" из {report.total_count}"
    await callback.message.answer_document(document, caption=caption)
    await callback.answer("CSV отправлен.")


@router.callback_query(F.data == "menu:admin:audit:prompt:target")
async def admin_audit_prompt_target(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.set_state(AdminAuditForm.waiting_for_target_user)
    await state.update_data(admin_audit_prompt="target")
    if callback.message is not None:
        await callback.message.answer(
            "Введи внутренний user ID или Telegram ID цели.\n"
            "Можно использовать префикс id:123 или tg:755815181.\n"
            "Отправь `-`, чтобы снять фильтр.",
            reply_markup=admin_audit_prompt_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "menu:admin:audit:prompt:actor")
async def admin_audit_prompt_actor(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.set_state(AdminAuditForm.waiting_for_actor_user)
    await state.update_data(admin_audit_prompt="actor")
    if callback.message is not None:
        await callback.message.answer(
            "Введи внутренний user ID или Telegram ID актора.\n"
            "Можно использовать префикс id:123 или tg:755815181.\n"
            "Отправь `-`, чтобы снять фильтр.",
            reply_markup=admin_audit_prompt_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "menu:admin:audit:prompt:action")
async def admin_audit_prompt_action(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.set_state(AdminAuditForm.waiting_for_action)
    await state.update_data(admin_audit_prompt="action")
    examples = await list_recent_audit_actions(session, limit=6)
    text = (
        "Введи точное имя действия, например payment_paid_stars.\n"
        "Отправь `-`, чтобы снять фильтр."
    )
    if examples:
        text += "\n\nПримеры: " + ", ".join(examples)
    if callback.message is not None:
        await callback.message.answer(text, reply_markup=admin_audit_prompt_keyboard())
    await callback.answer()


@router.message(AdminAuditForm.waiting_for_target_user)
async def admin_audit_receive_target(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
) -> None:
    await _receive_user_filter_message(
        message,
        session,
        settings,
        state,
        kind="target",
    )


@router.message(AdminAuditForm.waiting_for_actor_user)
async def admin_audit_receive_actor(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
) -> None:
    await _receive_user_filter_message(
        message,
        session,
        settings,
        state,
        kind="actor",
    )


@router.message(AdminAuditForm.waiting_for_action)
async def admin_audit_receive_action(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
) -> None:
    raw_text = (message.text or "").strip()
    filters, _ = await _load_context(state)
    try:
        action = normalize_audit_action_filter(raw_text)
    except AuditViewerError as exc:
        await message.answer(str(exc), reply_markup=admin_audit_prompt_keyboard())
        return

    updated_filters = AuditViewerFilters(
        target_user_id=filters.target_user_id,
        actor_user_id=filters.actor_user_id,
        action=action,
        period=filters.period,
    )
    await _store_context(state, filters=updated_filters, page=1, reset_state=True)
    await _render_overview(message, session, settings, state, use_banner=False)


async def _receive_user_filter_message(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
    *,
    kind: str,
) -> None:
    raw_text = (message.text or "").strip()
    filters, _ = await _load_context(state)
    try:
        if raw_text in {"", "-", "*"} or raw_text.lower() == "all":
            reference = None
        else:
            reference = await resolve_audit_user_reference(session, raw_text)
    except AuditViewerError as exc:
        await message.answer(str(exc), reply_markup=admin_audit_prompt_keyboard())
        return

    updated_filters = AuditViewerFilters(
        target_user_id=(reference.user_id if kind == "target" and reference is not None else filters.target_user_id),
        actor_user_id=(reference.user_id if kind == "actor" and reference is not None else filters.actor_user_id),
        action=filters.action,
        period=filters.period,
    )
    if kind == "target" and reference is None:
        updated_filters = AuditViewerFilters(
            target_user_id=None,
            actor_user_id=filters.actor_user_id,
            action=filters.action,
            period=filters.period,
        )
    if kind == "actor" and reference is None:
        updated_filters = AuditViewerFilters(
            target_user_id=filters.target_user_id,
            actor_user_id=None,
            action=filters.action,
            period=filters.period,
        )

    await _store_context(state, filters=updated_filters, page=1, reset_state=True)
    await _render_overview(message, session, settings, state, use_banner=False)


async def _render_overview(
    target: Message | CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
    *,
    use_banner: bool,
) -> None:
    filters, page = await _load_context(state)
    page_data = await build_audit_page(session, filters=filters, page=page)
    await _store_context(state, filters=page_data.filters, page=page_data.page)
    text = render_audit_overview(page_data, timezone=settings.timezone)
    markup = admin_audit_overview_keyboard(page_data)

    if use_banner:
        await render_section(
            target,
            text=text,
            reply_markup=markup,
            banner_path=get_banner_path("admin"),
        )
        return

    await target.answer(text, reply_markup=markup)


async def _load_context(state: FSMContext) -> tuple[AuditViewerFilters, int]:
    data = await state.get_data()
    raw_filters = data.get(AUDIT_FILTERS_KEY)
    raw_page = data.get(AUDIT_PAGE_KEY, 1)
    if not isinstance(raw_filters, dict):
        return AuditViewerFilters(), 1

    filters = AuditViewerFilters(
        target_user_id=_optional_int(raw_filters.get("target_user_id")),
        actor_user_id=_optional_int(raw_filters.get("actor_user_id")),
        action=raw_filters.get("action") if isinstance(raw_filters.get("action"), str) else None,
        period=normalize_audit_period(raw_filters.get("period", "all")),
    )
    page = raw_page if isinstance(raw_page, int) and raw_page > 0 else 1
    return filters, page


async def _store_context(
    state: FSMContext,
    *,
    filters: AuditViewerFilters,
    page: int,
    reset_state: bool = False,
) -> None:
    if reset_state:
        await state.clear()
    await state.update_data(
        **{
            AUDIT_FILTERS_KEY: {
                "target_user_id": filters.target_user_id,
                "actor_user_id": filters.actor_user_id,
                "action": filters.action,
                "period": filters.period,
            },
            AUDIT_PAGE_KEY: max(page, 1),
        }
    )


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    return None


def _parse_suffix_int(data: str | None) -> int | None:
    if data is None:
        return None
    try:
        return int(data.rsplit(":", maxsplit=1)[-1])
    except ValueError:
        return None




