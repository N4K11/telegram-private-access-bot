from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin import admin_section_keyboard
from app.bot.routers.common import edit_or_answer
from app.db.repositories.channels import ChannelRepository
from app.services.admin_roles import PERMISSION_DIAGNOSTICS
from app.services.channel_diagnostics import (
    build_channel_diagnostics_report,
    render_channel_diagnostics_report,
)

router = Router(name="admin_diagnostics")
router.message.filter(AdminFilter(PERMISSION_DIAGNOSTICS))
router.callback_query.filter(AdminFilter(PERMISSION_DIAGNOSTICS))


@router.message(Command("admin_channel_check"))
async def admin_channel_check(message: Message, session: AsyncSession, bot) -> None:
    channels = await ChannelRepository(session).list_all()
    report = await build_channel_diagnostics_report(bot, channels)
    await message.answer(
        render_channel_diagnostics_report(report),
        reply_markup=admin_section_keyboard(),
    )


@router.callback_query(F.data == "menu:admin:diagnostics")
async def diagnostics_dashboard(callback: CallbackQuery, session: AsyncSession, bot) -> None:
    channels = await ChannelRepository(session).list_all()
    report = await build_channel_diagnostics_report(bot, channels)
    await edit_or_answer(
        callback,
        text=render_channel_diagnostics_report(report),
        reply_markup=admin_section_keyboard(),
    )


