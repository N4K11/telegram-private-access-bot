from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.assets import get_banner_path
from app.bot.keyboards.user import user_section_keyboard
from app.bot.rendering import render_section
from app.config import Settings
from app.db.repositories.users import UserRepository
from app.services.referral_service import (
    build_user_referral_dashboard,
    render_user_referral_dashboard,
)

router = Router(name="user_referrals")


@router.message(Command("my_referrals"))
async def my_referrals_command(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    bot: Bot,
) -> None:
    if message.from_user is None:
        return
    repository = UserRepository(session)
    user = await repository.get_by_telegram_id(message.from_user.id)
    if user is None:
        user = await repository.upsert_from_telegram_user(
            message.from_user,
            admin_ids=settings.admin_ids_set,
        )

    me = await bot.get_me()
    dashboard = await build_user_referral_dashboard(
        session,
        user_id=user.id,
        bot_username=me.username,
    )
    if dashboard is None:
        await message.answer("Не удалось загрузить реферальную статистику.")
        return

    await message.answer(render_user_referral_dashboard(dashboard))


@router.callback_query(F.data == "menu:user:referrals")
async def referrals_section(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    bot: Bot,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return

    repository = UserRepository(session)
    user = await repository.get_by_telegram_id(callback.from_user.id)
    if user is None:
        user = await repository.upsert_from_telegram_user(
            callback.from_user,
            admin_ids=settings.admin_ids_set,
        )

    me = await bot.get_me()
    dashboard = await build_user_referral_dashboard(
        session,
        user_id=user.id,
        bot_username=me.username,
    )
    if dashboard is None:
        await callback.answer("Статистика недоступна.", show_alert=True)
        return

    await render_section(
        callback,
        text=render_user_referral_dashboard(dashboard),
        reply_markup=user_section_keyboard(back_callback="menu:user:profile"),
        banner_path=get_banner_path("profile"),
    )
