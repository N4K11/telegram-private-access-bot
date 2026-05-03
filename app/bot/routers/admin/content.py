# ruff: noqa: E501
from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin import admin_form_keyboard
from app.bot.keyboards.admin_content import admin_content_detail_keyboard, admin_content_keyboard
from app.bot.routers.common import edit_or_answer
from app.bot.states.admin import AdminTextEditor
from app.services.admin_roles import PERMISSION_TEXTS
from app.services.content_service import all_content_entries, get_content_entry, render_content_text
from app.services.texts import get_text_template_record, is_default_text_body

router = Router(name='admin_content')
router.message.filter(AdminFilter(PERMISSION_TEXTS))
router.callback_query.filter(AdminFilter(PERMISSION_TEXTS))


async def _load_content_items(session: AsyncSession):
    items = []
    for entry in all_content_entries():
        template = await get_text_template_record(session, entry.template_key)
        if template is None:
            continue
        items.append((entry, template))
    return items


def _render_overview(items) -> str:
    lines = [
        '📚 Content / FAQ CMS',
        '',
        'Редактируемые пользовательские материалы поверх managed TextTemplate.',
        '',
        f'Разделов: {len(items)}',
    ]
    for entry, template in items:
        state = 'standard' if is_default_text_body(template.key, template.body) else 'edited'
        lines.append(f'• {entry.title} — {entry.summary} [{state}]')
    return '\n'.join(lines)


async def _render_detail_text(session: AsyncSession, slug: str) -> str:
    entry = get_content_entry(slug)
    if entry is None:
        return '📚 Материал не найден.'

    template = await get_text_template_record(session, entry.template_key)
    if template is None:
        return '📚 Материал не найден.'

    state = 'standard' if is_default_text_body(template.key, template.body) else 'edited'
    updated_by = template.updated_by_user_id if template.updated_by_user_id is not None else '-'
    preview = await render_content_text(session, slug)
    lines = [
        f'📚 {entry.title}',
        '',
        f'Key: <code>{escape(entry.template_key)}</code>',
        f'Slug: <code>{escape(entry.slug)}</code>',
        f'State: {state}',
        f'Updated by: {updated_by}',
        '',
        'Preview:',
        '',
        preview,
    ]
    return '\n'.join(lines)


@router.message(Command('admin_content'))
async def admin_content(message: Message, session: AsyncSession) -> None:
    items = await _load_content_items(session)
    await session.commit()
    await message.answer(_render_overview(items), reply_markup=admin_content_keyboard(items))


@router.callback_query(F.data == 'menu:admin:content')
async def content_index(callback: CallbackQuery, session: AsyncSession) -> None:
    items = await _load_content_items(session)
    await session.commit()
    await edit_or_answer(
        callback,
        text=_render_overview(items),
        reply_markup=admin_content_keyboard(items),
    )


@router.callback_query(F.data.startswith('menu:admin:content:view:'))
async def content_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    slug = callback.data.removeprefix('menu:admin:content:view:') if callback.data else ''
    entry = get_content_entry(slug)
    if entry is None:
        await callback.answer('Материал не найден.', show_alert=True)
        return

    await session.commit()
    await edit_or_answer(
        callback,
        text=await _render_detail_text(session, slug),
        reply_markup=admin_content_detail_keyboard(entry.slug, entry.template_key),
    )


@router.callback_query(F.data.startswith('menu:admin:content:edit:'))
async def start_content_edit(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    slug = callback.data.removeprefix('menu:admin:content:edit:') if callback.data else ''
    entry = get_content_entry(slug)
    if entry is None:
        await callback.answer('Материал не найден.', show_alert=True)
        return

    template = await get_text_template_record(session, entry.template_key)
    if template is None:
        await callback.answer('Шаблон не найден.', show_alert=True)
        return

    await session.commit()
    await state.clear()
    await state.set_state(AdminTextEditor.waiting_for_value)
    await state.update_data(
        text_template_key=template.key,
        text_template_origin_slug=entry.slug,
        text_template_return_callback=f'menu:admin:content:view:{entry.slug}',
    )
    await edit_or_answer(
        callback,
        text=(
            f'Редактирование материала: {escape(entry.title)}\n\n'
            f'Key: <code>{escape(template.key)}</code>\n\n'
            'Отправь новый текст одним сообщением.'
        ),
        reply_markup=admin_form_keyboard(back_callback=f'menu:admin:content:view:{entry.slug}'),
    )
