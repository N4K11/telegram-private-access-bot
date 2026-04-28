from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin import (
    admin_channel_detail_keyboard,
    admin_channels_keyboard,
    admin_form_keyboard,
)
from app.bot.routers.common import edit_or_answer
from app.bot.states.admin import AdminChannelForm
from app.db.models import Channel
from app.db.repositories.channels import ChannelRepository
from app.services.channels import (
    ChannelSnapshot,
    ChannelValidationError,
    extract_channel_reference,
    inspect_channel_access,
)

logger = logging.getLogger(__name__)

router = Router(name="admin_channels")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


def _callback_entity_id(data: str | None) -> int | None:
    if data is None:
        return None
    try:
        return int(data.rsplit(":", 1)[-1])
    except ValueError:
        return None


def _channel_reference(channel: Channel) -> str | int:
    if channel.username:
        username = channel.username if channel.username.startswith("@") else f"@{channel.username}"
        return username
    return channel.telegram_chat_id


def _permission_status(value: bool) -> str:
    return "есть" if value else "нет"


def _render_channels_overview(channels: list[Channel]) -> str:
    lines = [
        "Каналы",
        "",
        "Здесь вы подключаете каналы и проверяете права бота.",
        "",
    ]
    if not channels:
        lines.append(
            "Пока нет ни одного канала. Добавьте @username, числовой chat_id "
            "или перешлите сообщение из канала."
        )
        return "\n".join(lines)

    lines.append(f"Всего каналов: {len(channels)}")
    lines.append("")
    for channel in channels:
        status = "активен" if channel.is_active else "выключен"
        lines.append(f"{'✅' if channel.is_active else '⏸'} {escape(channel.title)}")
        lines.append(f"Статус: {status}")
        lines.append(
            f"Права: invite {_permission_status(channel.invite_users_permission)}, "
            f"ban {_permission_status(channel.ban_users_permission)}"
        )
        lines.append("")
    return "\n".join(lines).rstrip()


def _render_channel_detail(channel: Channel) -> str:
    username = f"@{escape(channel.username.lstrip('@'))}" if channel.username else "не указан"
    status = "активен" if channel.is_active else "выключен"
    warning = ""
    if not channel.invite_users_permission or not channel.ban_users_permission:
        warning = (
            "\n\n⚠️ У бота не хватает прав для полноценной выдачи и отзыва доступа. "
            "Такой канал нельзя безопасно использовать в активных тарифах."
        )

    return (
        f"Канал #{channel.id}\n\n"
        f"Название: {escape(channel.title)}\n"
        f"Username: {username}\n"
        f"Chat ID: <code>{channel.telegram_chat_id}</code>\n"
        f"Статус: {status}\n"
        f"Право приглашать: {_permission_status(channel.invite_users_permission)}\n"
        f"Право удалять: {_permission_status(channel.ban_users_permission)}"
        f"{warning}"
    )


def _render_snapshot_prompt(snapshot: ChannelSnapshot) -> str:
    username = f"@{escape(snapshot.username.lstrip('@'))}" if snapshot.username else "не указан"
    return (
        "Проверка канала прошла.\n\n"
        f"Telegram title: {escape(snapshot.title)}\n"
        f"Username: {username}\n"
        f"Chat ID: <code>{snapshot.telegram_chat_id}</code>\n"
        f"Бот администратор: {'да' if snapshot.is_admin else 'нет'}\n"
        f"Право приглашать: {_permission_status(snapshot.invite_users_permission)}\n"
        f"Право удалять: {_permission_status(snapshot.ban_users_permission)}\n\n"
        "Отправьте название для админки или `-`, чтобы оставить текущее."
    )


def _parse_channel_title(raw_value: str | None, *, fallback: str | None = None) -> str:
    value = (raw_value or "").strip()
    if value == "-" and fallback is not None:
        return fallback
    if not value:
        raise ChannelValidationError("Название канала не должно быть пустым.")
    return value


@router.callback_query(F.data == "menu:admin:channels")
async def channels_index(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext | None = None,
) -> None:
    if state is not None:
        await state.clear()

    channels = await ChannelRepository(session).list_all()
    await edit_or_answer(
        callback,
        text=_render_channels_overview(channels),
        reply_markup=admin_channels_keyboard(channels),
    )


@router.callback_query(F.data == "menu:admin:channels:create")
async def start_channel_create(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AdminChannelForm.waiting_for_reference)
    await state.update_data(channel_action="create")
    await edit_or_answer(
        callback,
        text=(
            "Добавление канала\n\n"
            "Отправьте @username, числовой chat_id или перешлите сообщение из нужного канала."
        ),
        reply_markup=admin_form_keyboard(back_callback="menu:admin:channels"),
    )


@router.callback_query(F.data.startswith("menu:admin:channels:view:"))
async def channel_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    channel_id = _callback_entity_id(callback.data)
    if channel_id is None:
        await callback.answer()
        return

    channel = await ChannelRepository(session).get_by_id(channel_id)
    if channel is None:
        await callback.answer("Канал не найден.")
        return

    await edit_or_answer(
        callback,
        text=_render_channel_detail(channel),
        reply_markup=admin_channel_detail_keyboard(channel.id, is_active=channel.is_active),
    )


@router.callback_query(F.data.startswith("menu:admin:channels:rename:"))
async def start_channel_rename(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    channel_id = _callback_entity_id(callback.data)
    if channel_id is None:
        await callback.answer()
        return

    channel = await ChannelRepository(session).get_by_id(channel_id)
    if channel is None:
        await callback.answer("Канал не найден.")
        return

    await state.clear()
    await state.set_state(AdminChannelForm.waiting_for_title)
    await state.update_data(channel_action="rename", channel_id=channel.id)
    await edit_or_answer(
        callback,
        text=(
            f"Переименование канала #{channel.id}\n\n"
            f"Текущее название: {escape(channel.title)}\n\n"
            "Отправьте новое название."
        ),
        reply_markup=admin_form_keyboard(back_callback=f"menu:admin:channels:view:{channel.id}"),
    )


@router.callback_query(F.data.startswith("menu:admin:channels:toggle:"))
async def toggle_channel(callback: CallbackQuery, session: AsyncSession) -> None:
    channel_id = _callback_entity_id(callback.data)
    if channel_id is None:
        await callback.answer()
        return

    repository = ChannelRepository(session)
    channel = await repository.get_by_id(channel_id)
    if channel is None:
        await callback.answer("Канал не найден.")
        return

    await repository.set_active(channel, is_active=not channel.is_active)
    await session.commit()
    await edit_or_answer(
        callback,
        text=_render_channel_detail(channel),
        reply_markup=admin_channel_detail_keyboard(channel.id, is_active=channel.is_active),
    )


@router.callback_query(F.data.startswith("menu:admin:channels:refresh:"))
async def refresh_channel(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
) -> None:
    channel_id = _callback_entity_id(callback.data)
    if channel_id is None:
        await callback.answer()
        return

    repository = ChannelRepository(session)
    channel = await repository.get_by_id(channel_id)
    if channel is None:
        await callback.answer("Канал не найден.")
        return

    try:
        snapshot = await inspect_channel_access(bot, _channel_reference(channel))
    except Exception:
        logger.exception("Failed to refresh channel %s", channel_id)
        await callback.answer("Не удалось обновить данные канала.")
        return

    snapshot.title = channel.title
    await repository.upsert_snapshot(snapshot)
    await session.commit()
    await edit_or_answer(
        callback,
        text=_render_channel_detail(channel),
        reply_markup=admin_channel_detail_keyboard(channel.id, is_active=channel.is_active),
    )


@router.message(AdminChannelForm.waiting_for_reference)
async def receive_channel_reference(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    try:
        reference = extract_channel_reference(message)
        snapshot = await inspect_channel_access(bot, reference)
    except ChannelValidationError as exc:
        await message.answer(f"{exc}\n\nПопробуйте ещё раз.")
        return
    except Exception:
        logger.exception("Failed to inspect channel during admin flow")
        await message.answer(
            "Не удалось получить данные канала. Проверьте, что бот добавлен "
            "в канал и имеет права администратора."
        )
        return

    if not snapshot.is_admin:
        await message.answer(
            "Бот видит канал, но не является его администратором. "
            "Выдайте права администратора и повторите попытку."
        )
        return

    await state.update_data(
        channel_action="create",
        channel_snapshot={
            "telegram_chat_id": snapshot.telegram_chat_id,
            "title": snapshot.title,
            "username": snapshot.username,
            "is_admin": snapshot.is_admin,
            "invite_users_permission": snapshot.invite_users_permission,
            "ban_users_permission": snapshot.ban_users_permission,
        },
    )
    await state.set_state(AdminChannelForm.waiting_for_title)
    await message.answer(_render_snapshot_prompt(snapshot))


@router.message(AdminChannelForm.waiting_for_title)
async def receive_channel_title(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    action = data.get("channel_action")
    repository = ChannelRepository(session)

    try:
        if action == "create":
            snapshot_data = data.get("channel_snapshot")
            if not isinstance(snapshot_data, dict):
                raise ChannelValidationError(
                    "Форма добавления канала устарела. Запустите её заново."
                )
            snapshot = ChannelSnapshot(**snapshot_data)
            snapshot.title = _parse_channel_title(message.text, fallback=snapshot.title)
            channel = await repository.upsert_snapshot(snapshot)
            await session.commit()
            await state.clear()
            await message.answer(
                "Канал сохранён.\n\n" + _render_channel_detail(channel),
                reply_markup=admin_channel_detail_keyboard(channel.id, is_active=channel.is_active),
            )
            return

        if action == "rename":
            channel_id = data.get("channel_id")
            if not isinstance(channel_id, int):
                raise ChannelValidationError("Не удалось определить канал для переименования.")
            channel = await repository.get_by_id(channel_id)
            if channel is None:
                raise ChannelValidationError("Канал не найден.")
            await repository.rename(channel, _parse_channel_title(message.text))
            await session.commit()
            await state.clear()
            await message.answer(
                "Название канала обновлено.\n\n" + _render_channel_detail(channel),
                reply_markup=admin_channel_detail_keyboard(channel.id, is_active=channel.is_active),
            )
            return
    except ChannelValidationError as exc:
        await message.answer(f"{exc}\n\nПопробуйте ещё раз.")
        return

    await state.clear()
    await message.answer("Состояние формы не распознано. Откройте раздел каналов заново.")