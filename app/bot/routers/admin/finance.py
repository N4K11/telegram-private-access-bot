# ruff: noqa: E501
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin_finance import admin_finance_keyboard
from app.bot.routers.common import edit_or_answer
from app.config import Settings
from app.services.admin_roles import PERMISSION_PAYMENTS
from app.services.finance import (
    build_finance_report_csv,
    build_finance_report_filename,
    build_finance_snapshot,
    normalize_finance_period,
    render_finance_dashboard,
)

router = Router(name="admin_finance")
router.message.filter(AdminFilter(PERMISSION_PAYMENTS))
router.callback_query.filter(AdminFilter(PERMISSION_PAYMENTS))


@router.message(Command("admin_finance"))
async def admin_finance(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    snapshot = await build_finance_snapshot(session)
    await message.answer(
        render_finance_dashboard(snapshot, timezone=settings.timezone),
        reply_markup=admin_finance_keyboard(),
    )


@router.callback_query(F.data == "menu:admin:finance")
@router.callback_query(F.data == "menu:admin:payments")
async def finance_dashboard(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    snapshot = await build_finance_snapshot(session)
    await edit_or_answer(
        callback,
        text=render_finance_dashboard(snapshot, timezone=settings.timezone),
        reply_markup=admin_finance_keyboard(),
    )


@router.callback_query(F.data.startswith("menu:admin:finance:export:"))
async def export_finance_report(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if callback.data is None or callback.message is None:
        await callback.answer()
        return

    period = callback.data.rsplit(":", maxsplit=1)[-1]
    try:
        normalized_period = normalize_finance_period(period)
    except ValueError:
        await callback.answer("\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439 \u043f\u0435\u0440\u0438\u043e\u0434.", show_alert=True)
        return

    snapshot = await build_finance_snapshot(session)
    report = build_finance_report_csv(
        snapshot,
        period=normalized_period,
        timezone=settings.timezone,
    )
    filename = build_finance_report_filename(
        period=normalized_period,
        generated_at=snapshot.generated_at,
    )
    document = BufferedInputFile(report, filename=filename)
    await callback.message.answer_document(
        document,
        caption=f"\u0424\u0438\u043d\u0430\u043d\u0441\u043e\u0432\u044b\u0439 \u043e\u0442\u0447\u0451\u0442 CSV: {normalized_period}",
    )
    await callback.answer("CSV \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d.")



