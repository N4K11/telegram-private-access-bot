from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin import admin_section_keyboard
from app.config import Settings
from app.services.admin_roles import PERMISSION_OBSERVABILITY
from app.services.observability import (
    build_admin_observability_report,
    render_admin_observability_report,
)

router = Router(name="admin_observability")
router.message.filter(AdminFilter(PERMISSION_OBSERVABILITY))


@router.message(Command("admin_observability"))
async def admin_observability(message: Message, settings: Settings) -> None:
    report = build_admin_observability_report(
        critical_error_webhook_url=settings.critical_error_webhook_url,
    )
    await message.answer(
        render_admin_observability_report(report, timezone=settings.timezone),
        reply_markup=admin_section_keyboard(),
    )