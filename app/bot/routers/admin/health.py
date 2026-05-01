from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin import admin_section_keyboard
from app.config import Settings
from app.services.admin_roles import PERMISSION_HEALTH
from app.services.health_service import build_admin_health_report, render_admin_health_report

router = Router(name="admin_health")
router.message.filter(AdminFilter(PERMISSION_HEALTH))


@router.message(Command("admin_health"))
async def admin_health(message: Message, session: AsyncSession, settings: Settings, bot) -> None:
    report = await build_admin_health_report(session, bot, settings)
    await message.answer(
        render_admin_health_report(report),
        reply_markup=admin_section_keyboard(),
    )


