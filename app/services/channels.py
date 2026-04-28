from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import Message


class ChannelValidationError(ValueError):
    """Raised when the admin input cannot be converted into a channel reference."""


@dataclass(slots=True)
class ChannelSnapshot:
    telegram_chat_id: int
    title: str
    username: str | None
    is_admin: bool
    invite_users_permission: bool
    ban_users_permission: bool


def parse_channel_reference(raw_value: str) -> str | int:
    value = raw_value.strip()
    if not value:
        raise ChannelValidationError(
            "Укажите @username, chat_id или перешлите сообщение из канала."
        )
    if value.startswith("@"):
        return value

    try:
        return int(value)
    except ValueError as exc:
        raise ChannelValidationError(
            "Канал нужно указать как @username или числовой chat_id."
        ) from exc


def extract_channel_reference(message: Message) -> str | int:
    if message.text:
        return parse_channel_reference(message.text)

    sender_chat = getattr(message, "sender_chat", None)
    if sender_chat is not None and getattr(sender_chat, "id", None) is not None:
        return sender_chat.id

    forward_from_chat = getattr(message, "forward_from_chat", None)
    if forward_from_chat is not None and getattr(forward_from_chat, "id", None) is not None:
        return forward_from_chat.id

    raise ChannelValidationError(
        "Не удалось определить канал. Отправьте @username, chat_id или "
        "перешлите сообщение канала."
    )


async def inspect_channel_access(bot: Bot, reference: str | int) -> ChannelSnapshot:
    chat = await bot.get_chat(reference)
    me = await bot.get_me()
    member = await bot.get_chat_member(chat.id, me.id)

    status = str(getattr(member, "status", ""))
    is_admin = status in {"administrator", "creator"}
    can_invite = is_admin and (
        status == "creator" or bool(getattr(member, "can_invite_users", False))
    )
    can_restrict = is_admin and (
        status == "creator"
        or bool(getattr(member, "can_restrict_members", False))
        or bool(getattr(member, "can_manage_chat", False))
    )

    title = getattr(chat, "title", None) or getattr(chat, "full_name", None) or str(chat.id)
    username = getattr(chat, "username", None)

    return ChannelSnapshot(
        telegram_chat_id=chat.id,
        title=title,
        username=username,
        is_admin=is_admin,
        invite_users_permission=can_invite,
        ban_users_permission=can_restrict,
    )