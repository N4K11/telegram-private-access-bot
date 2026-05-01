from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin import admin_section_keyboard
from app.bot.routers.common import edit_or_answer
from app.config import Settings
from app.services.admin_roles import PERMISSION_PAYMENTS
from app.services.crypto_admin import (
    CryptoAdminDiagnosticError,
    build_crypto_diagnostic_report,
    build_crypto_reconciliation_summary,
    render_crypto_diagnostic_report,
    render_crypto_reconciliation_summary,
)

router = Router(name="admin_crypto")
router.message.filter(AdminFilter(PERMISSION_PAYMENTS))
router.callback_query.filter(AdminFilter(PERMISSION_PAYMENTS))


@router.message(Command("admin_crypto_invoices"))
async def admin_crypto_invoices(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    summary = await build_crypto_reconciliation_summary(session, settings)
    await message.answer(
        render_crypto_reconciliation_summary(summary, timezone=settings.timezone),
        reply_markup=admin_section_keyboard(),
    )


@router.message(Command("admin_crypto_diag"))
async def admin_crypto_diag(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    parts = _extract_args(message.text)
    if len(parts) != 1:
        usage = (
            "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: "
            "/admin_crypto_diag <user_id|invoice_id>"
        )
        await message.answer(usage)
        return

    try:
        report = await build_crypto_diagnostic_report(session, reference=parts[0])
    except CryptoAdminDiagnosticError as exc:
        await message.answer(str(exc))
        return

    await message.answer(
        render_crypto_diagnostic_report(report, timezone=settings.timezone),
        reply_markup=admin_section_keyboard(),
    )


@router.callback_query(F.data == "menu:admin:payments:crypto")
async def admin_crypto_dashboard(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    summary = await build_crypto_reconciliation_summary(session, settings)
    await edit_or_answer(
        callback,
        text=render_crypto_reconciliation_summary(summary, timezone=settings.timezone),
        reply_markup=admin_section_keyboard(),
    )


def _extract_args(text: str | None) -> list[str]:
    if not text:
        return []
    parts = text.split()
    return parts[1:]


