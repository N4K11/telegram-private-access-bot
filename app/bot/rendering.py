from __future__ import annotations

import logging
from pathlib import Path

from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message

from app.bot.routers.common import edit_or_answer

logger = logging.getLogger(__name__)


async def render_section(
    event: Message | object,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    banner_path: Path | None = None,
) -> None:
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


async def _try_send_photo(
    event: object,
    *,
    banner_path: Path,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> bool:
    photo = FSInputFile(banner_path)
    callback_message = getattr(event, "message", None)
    callback_answer = getattr(event, "answer", None)

    if callback_message is not None and callable(callback_answer):
        answer_photo = getattr(callback_message, "answer_photo", None)
        if callable(answer_photo):
            try:
                await answer_photo(photo, caption=text, reply_markup=reply_markup)
                await callback_answer()
                return True
            except Exception:
                logger.exception("Failed to send section photo for callback event.")
                return False

    answer_photo = getattr(event, "answer_photo", None)
    if callable(answer_photo):
        try:
            await answer_photo(photo, caption=text, reply_markup=reply_markup)
            return True
        except Exception:
            logger.exception("Failed to send section photo for message event.")
            return False

    return False
