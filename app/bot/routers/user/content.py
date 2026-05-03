from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.assets import get_banner_path
from app.bot.keyboards.user import user_section_keyboard
from app.bot.keyboards.user_content import user_content_detail_keyboard
from app.bot.rendering import render_section
from app.services.content_service import get_content_entry, render_content_text

router = Router(name='user_content')


async def _render_content_entry(
    target: Message | CallbackQuery,
    *,
    slug: str,
    session: AsyncSession | None,
) -> None:
    entry = get_content_entry(slug)
    await render_section(
        target,
        text=await render_content_text(session, slug),
        reply_markup=(
            user_content_detail_keyboard(current_slug=entry.slug)
            if entry is not None
            else user_section_keyboard(back_callback='menu:user:help')
        ),
        banner_path=get_banner_path('help'),
    )


@router.message(Command('faq'))
async def faq_command(message: Message, session: AsyncSession | None = None) -> None:
    await _render_content_entry(message, slug='faq', session=session)


@router.message(Command('rules'))
async def rules_command(message: Message, session: AsyncSession | None = None) -> None:
    await _render_content_entry(message, slug='rules', session=session)


@router.message(Command('afterpay'))
async def afterpay_command(message: Message, session: AsyncSession | None = None) -> None:
    await _render_content_entry(message, slug='after-payment', session=session)


@router.message(Command('cryptopay'))
async def cryptopay_command(message: Message, session: AsyncSession | None = None) -> None:
    await _render_content_entry(message, slug='crypto-payment', session=session)


@router.message(Command('offer'))
async def offer_command(message: Message, session: AsyncSession | None = None) -> None:
    await _render_content_entry(message, slug='offer', session=session)


@router.callback_query(F.data.startswith('menu:user:content:'))
async def content_callback(
    callback: CallbackQuery,
    session: AsyncSession | None = None,
) -> None:
    slug = callback.data.removeprefix('menu:user:content:') if callback.data else ''
    await _render_content_entry(callback, slug=slug, session=session)
