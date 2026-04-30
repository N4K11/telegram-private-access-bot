from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.assets import get_banner_path
from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin import admin_main_menu_keyboard, admin_section_keyboard
from app.bot.rendering import render_section
from app.bot.routers.common import edit_or_answer
from app.services.texts import render_text

router = Router(name="admin")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

ADMIN_SECTION_LABELS = {
    "analytics": "Аналитика",
    "users": "Пользователи",
    "payments": "Платежи",
    "tariffs": "Тарифы",
    "channels": "Каналы",
    "texts": "Тексты",
    "broadcasts": "Рассылка",
    "backups": "Бэкапы",
    "settings": "Настройки",
    "diagnostics": "Диагностика",
}


@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    await render_section(
        message,
        text=render_text("admin_dashboard"),
        reply_markup=admin_main_menu_keyboard(),
        banner_path=get_banner_path("admin"),
    )


@router.callback_query(F.data == "menu:admin:home")
async def admin_home(callback: CallbackQuery) -> None:
    await render_section(
        callback,
        text=render_text("admin_dashboard"),
        reply_markup=admin_main_menu_keyboard(),
        banner_path=get_banner_path("admin"),
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
