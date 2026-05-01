from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin import admin_section_keyboard
from app.config import Settings
from app.services.admin_roles import PERMISSION_REFERRALS
from app.services.referral_service import (
    build_admin_referral_snapshot,
    render_admin_referral_snapshot,
)

router = Router(name="admin_referrals")
router.message.filter(AdminFilter(PERMISSION_REFERRALS))


@router.message(Command("admin_referrals"))
async def admin_referrals(message: Message, session: AsyncSession, settings: Settings) -> None:
    snapshot = await build_admin_referral_snapshot(session, limit=10)
    await message.answer(
        render_admin_referral_snapshot(snapshot, timezone=settings.timezone),
        reply_markup=admin_section_keyboard(),
    )



