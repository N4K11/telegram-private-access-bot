from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.assets import get_banner_path
from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin import admin_main_menu_keyboard, admin_section_keyboard
from app.bot.rendering import render_section
from app.services.admin_home import build_admin_home_snapshot
from app.bot.routers.common import edit_or_answer
from app.config import Settings
from app.services.admin_roles import (
    allowed_admin_menu_sections,
    get_admin_section_title,
    resolve_telegram_role,
)
from app.services.texts import render_text

router = Router(name="admin")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


async def _resolve_admin_role(
    session: AsyncSession | None,
    settings: Settings | None,
    telegram_user_id: int | None,
) -> str:
    if settings is None:
        return "owner"
    if session is not None and telegram_user_id is not None:
        return await resolve_telegram_role(
            session,
            telegram_user_id=telegram_user_id,
            settings=settings,
        )
    if telegram_user_id is not None and telegram_user_id in settings.admin_ids_set:
        return "owner"
    return "user"


async def _render_admin_home(
    target: Message | CallbackQuery,
    *,
    session: AsyncSession | None,
    settings: Settings | None,
    telegram_user_id: int | None,
) -> None:
    role = await _resolve_admin_role(session, settings, telegram_user_id)
    summary_text = render_text("admin_dashboard")
    section_badges: dict[str, int] | None = None
    if session is not None and settings is not None:
        home_snapshot = await build_admin_home_snapshot(
            session,
            role=role,
            settings=settings,
        )
        if home_snapshot.summary_block:
            summary_text = f"{summary_text}\n\n{home_snapshot.summary_block}"
        section_badges = home_snapshot.section_badges
    await render_section(
        target,
        text=summary_text,
        reply_markup=admin_main_menu_keyboard(role=role, section_badges=section_badges),
        banner_path=get_banner_path("admin"),
    )


@router.message(Command("admin"))
async def admin_panel(
    message: Message,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    await _render_admin_home(
        message,
        session=session,
        settings=settings,
        telegram_user_id=message.from_user.id if message.from_user else None,
    )


@router.callback_query(F.data == "menu:admin:home")
async def admin_home(
    callback: CallbackQuery,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    await _render_admin_home(
        callback,
        session=session,
        settings=settings,
        telegram_user_id=callback.from_user.id if callback.from_user else None,
    )


@router.callback_query(F.data.startswith("menu:admin:"))
async def admin_section(
    callback: CallbackQuery,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    if callback.data is None:
        await callback.answer()
        return

    section = callback.data.rsplit(":", 1)[-1]
    if section == "home":
        await admin_home(callback, session=session, settings=settings)
        return

    role = await _resolve_admin_role(
        session,
        settings,
        callback.from_user.id if callback.from_user else None,
    )
    allowed_keys = {item.key for item in allowed_admin_menu_sections(role)}
    if section not in allowed_keys:
        await callback.answer("Недостаточно прав для этого раздела.", show_alert=True)
        return

    label = get_admin_section_title(section)
    if label is None:
        await callback.answer()
        return

    await edit_or_answer(
        callback,
        text=render_text("admin_section", section=label),
        reply_markup=admin_section_keyboard(),
    )
