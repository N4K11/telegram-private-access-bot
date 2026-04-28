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

ADMIN_SECTION_LABELS = {
    "analytics": "\u0410\u043d\u0430\u043b\u0438\u0442\u0438\u043a\u0430",
    "users": "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0438",
    "payments": "\u041f\u043b\u0430\u0442\u0435\u0436\u0438",
    "tariffs": "\u0422\u0430\u0440\u0438\u0444\u044b",
    "channels": "\u041a\u0430\u043d\u0430\u043b\u044b",
    "texts": "\u0422\u0435\u043a\u0441\u0442\u044b",
    "broadcasts": "\u0420\u0430\u0441\u0441\u044b\u043b\u043a\u0430",
    "backups": "\u0411\u044d\u043a\u0430\u043f\u044b",
    "settings": "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438",
    "diagnostics": "\u0414\u0438\u0430\u0433\u043d\u043e\u0441\u0442\u0438\u043a\u0430",
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

    label = ADMIN_SECTION_LABELS.get(section)
    if label is None:
        await callback.answer()
        return

    await edit_or_answer(
        callback,
        text=render_text("admin_section", section=label),
        reply_markup=admin_section_keyboard(),
    )