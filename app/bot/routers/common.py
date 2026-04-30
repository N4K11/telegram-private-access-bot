from __future__ import annotations

from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message


def is_not_modified_error(exc: Exception) -> bool:
    return "message is not modified" in str(exc).lower()


async def edit_or_answer(
    event: Message | CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    callback_message = getattr(event, "message", None)
    callback_answer = getattr(event, "answer", None)

    if callback_message is not None and callable(callback_answer):
        try:
            await callback_message.edit_text(text, reply_markup=reply_markup)
            await callback_answer()
            return
        except Exception as exc:
            if is_not_modified_error(exc):
                await callback_answer()
                return

        await callback_message.answer(text, reply_markup=reply_markup)
        await callback_answer()
        return

    await event.answer(text, reply_markup=reply_markup)
