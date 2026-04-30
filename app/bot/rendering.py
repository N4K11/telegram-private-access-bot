from __future__ import annotations

import logging
from pathlib import Path

from aiogram.types import FSInputFile, InlineKeyboardMarkup, InputMediaPhoto, Message

from app.bot.routers.common import edit_or_answer, is_not_modified_error

logger = logging.getLogger(__name__)


async def render_section(
    event: Message | object,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    banner_path: Path | None = None,
) -> None:
    callback_message = getattr(event, "message", None)
    callback_answer = getattr(event, "answer", None)

    if callback_message is not None and callable(callback_answer):
        if banner_path is not None and banner_path.is_file():
            edited = await _try_edit_callback_photo(
                callback_message,
                callback_answer=callback_answer,
                banner_path=banner_path,
                text=text,
                reply_markup=reply_markup,
            )
            if edited:
                return

        await edit_or_answer(event, text=text, reply_markup=reply_markup)
        return

    if banner_path is not None and banner_path.is_file():
        sent = await _try_send_photo(
            event,
            banner_path=banner_path,
            text=text,
            reply_markup=reply_markup,
        )
        if sent:
            return

    await edit_or_answer(event, text=text, reply_markup=reply_markup)


async def _try_edit_callback_photo(
    callback_message: object,
    *,
    callback_answer,
    banner_path: Path,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> bool:
    if not getattr(callback_message, "photo", None):
        return False

    edit_media = getattr(callback_message, "edit_media", None)
    if not callable(edit_media):
        return False

    photo = FSInputFile(banner_path)
    media = InputMediaPhoto(media=photo, caption=text)
    try:
        await edit_media(media=media, reply_markup=reply_markup)
        await callback_answer()
        return True
    except Exception as exc:
        if is_not_modified_error(exc):
            await callback_answer()
            return True
        logger.exception("Failed to edit section photo for callback event.")
        return False


async def _try_send_photo(
    event: object,
    *,
    banner_path: Path,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> bool:
    photo = FSInputFile(banner_path)
    answer_photo = getattr(event, "answer_photo", None)
    if callable(answer_photo):
        try:
            await answer_photo(photo, caption=text, reply_markup=reply_markup)
            return True
        except Exception:
            logger.exception("Failed to send section photo for message event.")
            return False

    return False
