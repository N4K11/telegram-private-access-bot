from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin import admin_main_menu_keyboard, admin_section_keyboard
from app.bot.routers.common import edit_or_answer
from app.services.texts import render_text

router = Router(name="admin")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

ADMIN_SECTIONS = {
    "analytics",
    "users",
    "payments",
    "tariffs",
    "channels",
    "texts",
    "broadcasts",
    "backups",
    "settings",
    "diagnostics",
}


@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    await message.answer(render_text("admin_dashboard"), reply_markup=admin_main_menu_keyboard())


@router.callback_query(F.data == "menu:admin:home")
async def admin_home(callback: CallbackQuery) -> None:
    await edit_or_answer(
        callback,
        text=render_text("admin_dashboard"),
        reply_markup=admin_main_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("menu:admin:"))
async def admin_section(callback: CallbackQuery) -> None:
    if callback.data is None:
        await callback.answer()
        return

    section = callback.data.rsplit(":", 1)[-1]
    if section == "home":
        await admin_home(callback)
        return

    if section not in ADMIN_SECTIONS:
        await callback.answer()
        return

    await edit_or_answer(
        callback,
        text=render_text("admin_section", section=section.title()),
        reply_markup=admin_section_keyboard(),
    )