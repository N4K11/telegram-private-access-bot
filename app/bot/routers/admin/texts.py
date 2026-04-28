# ruff: noqa: E501
from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin import admin_form_keyboard
from app.bot.keyboards.admin_texts import admin_text_detail_keyboard, admin_texts_keyboard
from app.bot.routers.common import edit_or_answer
from app.bot.states.admin import AdminTextEditor
from app.db.repositories.users import UserRepository
from app.services.texts import (
    TextTemplateValidationError,
    default_text_template,
    get_text_template_record,
    is_default_text_body,
    list_text_templates,
    reset_text_template_body,
    update_text_template_body,
)

router = Router(name="admin_texts")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())



def _callback_key(data: str | None, prefix: str) -> str | None:
    if data is None or not data.startswith(prefix):
        return None
    return data.removeprefix(prefix).strip() or None



def _render_texts_overview(templates) -> str:
    return (
        "\u0422\u0435\u043a\u0441\u0442\u044b\n\n"
        f"Templates: {len(templates)}"
    )



def _render_text_detail(template) -> str:
    default_template = default_text_template(template.key)
    state = "default" if is_default_text_body(template.key, template.body) else "edited"
    updated_by = template.updated_by_user_id if template.updated_by_user_id is not None else "-"
    body_preview = escape(template.body)

    lines = [
        template.title,
        "",
        f"Key: <code>{escape(template.key)}</code>",
        f"State: {state}",
        f"System: {'yes' if template.is_system else 'no'}",
        f"Updated by: {updated_by}",
    ]
    if default_template is not None and default_template.body != template.body:
        lines.append("Changed from default.")

    lines.extend(["", "Body:", "", body_preview])
    return "\n".join(lines)


async def _actor_user_id(
    session: AsyncSession,
    telegram_user_id: int | None,
) -> int | None:
    if telegram_user_id is None:
        return None
    user = await UserRepository(session).get_by_telegram_id(telegram_user_id)
    return user.id if user is not None else None


@router.callback_query(F.data == "menu:admin:texts")
async def texts_index(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext | None = None,
) -> None:
    if state is not None:
        await state.clear()

    templates = await list_text_templates(session)
    await session.commit()
    await edit_or_answer(
        callback,
        text=_render_texts_overview(templates),
        reply_markup=admin_texts_keyboard(templates),
    )


@router.callback_query(F.data.startswith("menu:admin:texts:view:"))
async def text_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    key = _callback_key(callback.data, "menu:admin:texts:view:")
    if key is None:
        await callback.answer()
        return

    template = await get_text_template_record(session, key)
    if template is None:
        await callback.answer("Template not found.", show_alert=True)
        return

    await session.commit()
    await edit_or_answer(
        callback,
        text=_render_text_detail(template),
        reply_markup=admin_text_detail_keyboard(template.key),
    )


@router.callback_query(F.data.startswith("menu:admin:texts:edit:"))
async def start_text_edit(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    key = _callback_key(callback.data, "menu:admin:texts:edit:")
    if key is None:
        await callback.answer()
        return

    template = await get_text_template_record(session, key)
    if template is None:
        await callback.answer("Template not found.", show_alert=True)
        return

    await session.commit()
    await state.clear()
    await state.set_state(AdminTextEditor.waiting_for_value)
    await state.update_data(text_template_key=template.key)
    await edit_or_answer(
        callback,
        text=(
            f"\u0420\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435: {escape(template.title)}\n\n"
            f"Key: <code>{escape(template.key)}</code>\n\n"
            "Send the new body in one message."
        ),
        reply_markup=admin_form_keyboard(back_callback=f"menu:admin:texts:view:{template.key}"),
    )


@router.callback_query(F.data.startswith("menu:admin:texts:reset:"))
async def reset_text(callback: CallbackQuery, session: AsyncSession) -> None:
    key = _callback_key(callback.data, "menu:admin:texts:reset:")
    if key is None:
        await callback.answer()
        return

    try:
        template = await reset_text_template_body(
            session,
            key=key,
            updated_by_user_id=await _actor_user_id(
                session,
                callback.from_user.id if callback.from_user is not None else None,
            ),
        )
        await session.commit()
    except TextTemplateValidationError as exc:
        await session.rollback()
        await callback.answer(str(exc), show_alert=True)
        return

    await edit_or_answer(
        callback,
        text=_render_text_detail(template),
        reply_markup=admin_text_detail_keyboard(template.key),
    )


@router.message(AdminTextEditor.waiting_for_value)
async def receive_text_value(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    body = message.text or ""
    data = await state.get_data()
    key = data.get("text_template_key")
    if not isinstance(key, str) or not key:
        await state.clear()
        await message.answer(
            "\u041a\u043e\u043d\u0442\u0435\u043a\u0441\u0442 \u0440\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f \u043f\u043e\u0442\u0435\u0440\u044f\u043d."
        )
        return

    try:
        template = await update_text_template_body(
            session,
            key=key,
            body=body,
            updated_by_user_id=await _actor_user_id(
                session,
                message.from_user.id if message.from_user is not None else None,
            ),
        )
        await session.commit()
    except TextTemplateValidationError as exc:
        await session.rollback()
        await message.answer(f"{exc}\n\nTry again.")
        return

    await state.clear()
    await message.answer(
        "\u0428\u0430\u0431\u043b\u043e\u043d \u043e\u0431\u043d\u043e\u0432\u043b\u0451\u043d.\n\n" + _render_text_detail(template),
        reply_markup=admin_text_detail_keyboard(template.key),
    )