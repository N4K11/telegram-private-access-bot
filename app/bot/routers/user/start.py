from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.user import user_main_menu_keyboard, user_section_keyboard
from app.bot.routers.common import edit_or_answer
from app.db.repositories.tariffs import TariffRepository
from app.services.texts import render_text

router = Router(name="user")

USER_SECTION_KEYS = {
    "subscription": "user_subscription",
    "support": "user_support",
}


def _render_tariffs_text(items: list[object]) -> str:
    if not items:
        return render_text("user_tariffs") + "\n\nСейчас активных тарифов нет."

    lines = [render_text("user_tariffs"), ""]
    for tariff in items:
        lines.append(
            f"• {escape(tariff.name)} — {tariff.price_stars} Stars на {tariff.duration_days} дн."
        )
    lines.append("")
    lines.append("Оплата и покупка будут подключены на следующем этапе.")
    return "\n".join(lines)


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    first_name = message.from_user.first_name if message.from_user else "друг"
    await message.answer(
        render_text("start", first_name=first_name),
        reply_markup=user_main_menu_keyboard(),
    )


@router.callback_query(F.data == "menu:user:home")
async def user_home(callback: CallbackQuery) -> None:
    first_name = callback.from_user.first_name if callback.from_user else "друг"
    await edit_or_answer(
        callback,
        text=render_text("start", first_name=first_name),
        reply_markup=user_main_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("menu:user:"))
async def user_section(callback: CallbackQuery, session: AsyncSession | None = None) -> None:
    if callback.data is None:
        await callback.answer()
        return

    section = callback.data.rsplit(":", 1)[-1]
    if section == "home":
        await user_home(callback)
        return

    if section == "tariffs":
        tariffs = []
        if session is not None:
            tariffs = await TariffRepository(session).list_active()
        await edit_or_answer(
            callback,
            text=_render_tariffs_text(tariffs),
            reply_markup=user_section_keyboard(),
        )
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