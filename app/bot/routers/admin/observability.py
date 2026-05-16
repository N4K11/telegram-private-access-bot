from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin import admin_observability_keyboard
from app.bot.routers.common import edit_or_answer
from app.config import Settings
from app.services.admin_read_model_text import render_admin_read_models_text
from app.services.admin_roles import PERMISSION_OBSERVABILITY, resolve_telegram_role
from app.services.observability import (
    build_admin_observability_report,
    render_admin_observability_report,
)
from app.services.web_admin_dashboard_read_model_sections import (
    READ_MODEL_VIEW_ACTIONS,
    READ_MODEL_VIEW_DRIFT,
    READ_MODEL_VIEW_OVERVIEW,
    READ_MODEL_VIEW_WATCHLIST,
    build_web_admin_read_models_payload,
)

router = Router(name="admin_observability")
router.message.filter(AdminFilter(PERMISSION_OBSERVABILITY))
router.callback_query.filter(AdminFilter(PERMISSION_OBSERVABILITY))


async def _resolve_viewer_role(
    session: AsyncSession | None,
    settings: Settings,
    telegram_user_id: int | None,
) -> str:
    if session is not None and telegram_user_id is not None:
        return await resolve_telegram_role(
            session,
            telegram_user_id=telegram_user_id,
            settings=settings,
        )
    if telegram_user_id is not None and telegram_user_id in settings.admin_ids_set:
        return "owner"
    return "owner"


async def _send_observability(
    target: Message | CallbackQuery,
    *,
    session: AsyncSession | None,
    settings: Settings,
) -> None:
    report = await build_admin_observability_report(
        session,
        settings=settings,
        critical_error_webhook_url=settings.critical_error_webhook_url,
    )
    text = render_admin_observability_report(report, timezone=settings.timezone)
    keyboard = admin_observability_keyboard()
    if isinstance(target, CallbackQuery):
        await edit_or_answer(target, text=text, reply_markup=keyboard)
        return
    await target.answer(text, reply_markup=keyboard)


async def _send_read_models(
    target: CallbackQuery,
    *,
    session: AsyncSession,
    settings: Settings,
    view: str,
    source: str,
) -> None:
    viewer_role = await _resolve_viewer_role(
        session,
        settings,
        target.from_user.id if target.from_user else None,
    )
    payload = await build_web_admin_read_models_payload(
        session,
        settings=settings,
        viewer_role=viewer_role,
        limit=8,
        source=source,
        view=view,
    )
    await edit_or_answer(
        target,
        text=render_admin_read_models_text(payload),
        reply_markup=admin_observability_keyboard(
            read_model_view=(
                "drift"
                if view == READ_MODEL_VIEW_DRIFT
                else (
                    "watchlist"
                    if view == READ_MODEL_VIEW_WATCHLIST
                    else (
                        "actions"
                        if view == READ_MODEL_VIEW_ACTIONS
                        else ("live" if source == "live" else "overview")
                    )
                )
            )
        ),
    )


@router.message(Command("admin_observability"))
async def admin_observability(
    message: Message,
    settings: Settings,
    session: AsyncSession | None = None,
) -> None:
    await _send_observability(
        message,
        session=session,
        settings=settings,
    )


@router.callback_query(F.data == "menu:admin:observability")
async def admin_observability_refresh(
    callback: CallbackQuery,
    settings: Settings,
    session: AsyncSession | None = None,
) -> None:
    await _send_observability(
        callback,
        session=session,
        settings=settings,
    )


@router.callback_query(F.data == "menu:admin:observability:read-models")
async def admin_observability_read_models(
    callback: CallbackQuery,
    settings: Settings,
    session: AsyncSession | None = None,
) -> None:
    if session is None:
        await callback.answer("Хранилище недоступно.", show_alert=True)
        return
    await _send_read_models(
        callback,
        session=session,
        settings=settings,
        view=READ_MODEL_VIEW_OVERVIEW,
        source="snapshot",
    )


@router.callback_query(F.data == "menu:admin:observability:read-models:live")
async def admin_observability_read_models_live(
    callback: CallbackQuery,
    settings: Settings,
    session: AsyncSession | None = None,
) -> None:
    if session is None:
        await callback.answer("Хранилище недоступно.", show_alert=True)
        return
    await _send_read_models(
        callback,
        session=session,
        settings=settings,
        view=READ_MODEL_VIEW_OVERVIEW,
        source="live",
    )


@router.callback_query(F.data == "menu:admin:observability:read-models:drift")
async def admin_observability_read_models_drift(
    callback: CallbackQuery,
    settings: Settings,
    session: AsyncSession | None = None,
) -> None:
    if session is None:
        await callback.answer("Хранилище недоступно.", show_alert=True)
        return
    await _send_read_models(
        callback,
        session=session,
        settings=settings,
        view=READ_MODEL_VIEW_DRIFT,
        source="live",
    )


@router.callback_query(F.data == "menu:admin:observability:read-models:watchlist")
async def admin_observability_read_models_watchlist(
    callback: CallbackQuery,
    settings: Settings,
    session: AsyncSession | None = None,
) -> None:
    if session is None:
        await callback.answer("Хранилище недоступно.", show_alert=True)
        return
    await _send_read_models(
        callback,
        session=session,
        settings=settings,
        view=READ_MODEL_VIEW_WATCHLIST,
        source="live",
    )


@router.callback_query(F.data == "menu:admin:observability:read-models:actions")
async def admin_observability_read_models_actions(
    callback: CallbackQuery,
    settings: Settings,
    session: AsyncSession | None = None,
) -> None:
    if session is None:
        await callback.answer("Хранилище недоступно.", show_alert=True)
        return
    await _send_read_models(
        callback,
        session=session,
        settings=settings,
        view=READ_MODEL_VIEW_ACTIONS,
        source="live",
    )
