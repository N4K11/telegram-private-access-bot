from __future__ import annotations

import inspect

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.assets import get_banner_path
from app.bot.keyboards.user_legal import user_legal_detail_keyboard
from app.bot.rendering import render_section
from app.services.legal_texts import get_legal_text_entry
from app.services.texts import render_text

router = Router(name="user_legal")


async def _text(
    session: AsyncSession | None,
    key: str,
    **context: object,
) -> str:
    rendered = (
        render_text(session, key, **context) if session is not None else render_text(key, **context)
    )
    if inspect.isawaitable(rendered):
        return await rendered
    return rendered


async def _render_legal_entry(
    target: Message | CallbackQuery,
    *,
    slug: str,
    session: AsyncSession | None,
) -> None:
    entry = get_legal_text_entry(slug)
    if entry is None:
        if isinstance(target, CallbackQuery):
            await target.answer()
        return
    await render_section(
        target,
        text=await _text(session, entry.template_key),
        reply_markup=user_legal_detail_keyboard(current_slug=entry.slug),
        banner_path=get_banner_path("help"),
    )


@router.message(Command("terms"))
async def terms_command(message: Message, session: AsyncSession | None = None) -> None:
    await _render_legal_entry(message, slug="terms", session=session)


@router.message(Command("privacy"))
async def privacy_command(message: Message, session: AsyncSession | None = None) -> None:
    await _render_legal_entry(message, slug="privacy", session=session)


@router.message(Command("refunds"))
async def refunds_command(message: Message, session: AsyncSession | None = None) -> None:
    await _render_legal_entry(message, slug="refunds", session=session)


@router.callback_query(F.data.startswith("menu:user:legal:"))
async def legal_callback(callback: CallbackQuery, session: AsyncSession | None = None) -> None:
    slug = callback.data.removeprefix("menu:user:legal:") if callback.data else ""
    await _render_legal_entry(callback, slug=slug, session=session)
