from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from app.config import Settings

router = Router(name="user_cabinet")


def _cabinet_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🪟 Открыть кабинет",
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )


@router.message(Command("cabinet"))
async def cabinet_command(message: Message, settings: Settings) -> None:
    if not settings.use_webhook or not settings.public_webhook_url:
        await message.answer(
            "Мини-приложение пока недоступно. "
            "Используй основные разделы бота или включи webhook mode "
            "для web cabinet."
        )
        return
    await message.answer(
        "Открой кабинет в Telegram Mini App.",
        reply_markup=_cabinet_keyboard(settings.mini_app_url),
    )
