from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.user import user_main_menu_keyboard, user_section_keyboard
from app.bot.routers.common import edit_or_answer
from app.services.texts import render_text

router = Router(name="user")

USER_SECTION_KEYS = {
    "subscription": "user_subscription",
    "tariffs": "user_tariffs",
    "support": "user_support",
}


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    first_name = message.from_user.first_name if message.from_user else "friend"
    await message.answer(
        render_text("start", first_name=first_name),
        reply_markup=user_main_menu_keyboard(),
    )


@router.callback_query(F.data == "menu:user:home")
async def user_home(callback: CallbackQuery) -> None:
    first_name = callback.from_user.first_name if callback.from_user else "friend"
    await edit_or_answer(
        callback,
        text=render_text("start", first_name=first_name),
        reply_markup=user_main_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("menu:user:"))
async def user_section(callback: CallbackQuery) -> None:
    if callback.data is None:
        await callback.answer()
        return

    section = callback.data.rsplit(":", 1)[-1]
    if section == "home":
        await user_home(callback)
        return

    text_key = USER_SECTION_KEYS.get(section)
    if text_key is None:
        await callback.answer()
        return

    await edit_or_answer(
        callback,
        text=render_text(text_key),
        reply_markup=user_section_keyboard(),
    )