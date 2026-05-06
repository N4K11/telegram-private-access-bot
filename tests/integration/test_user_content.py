from __future__ import annotations

from app.bot.keyboards.user import (
    USER_BACK_TEXT,
    USER_BUTTON_BUY_TEXT,
    USER_BUTTON_LINK_TEXT,
    USER_HOME_TEXT,
)
from app.bot.routers.user.content import content_callback, faq_command
from app.services.content_service import all_content_entries, get_content_entry


class DummyUser:
    def __init__(self, user_id: int = 100, first_name: str = "Anna") -> None:
        self.id = user_id
        self.first_name = first_name


class DummyMessage:
    def __init__(self) -> None:
        self.from_user = DummyUser()
        self.answer_calls: list[tuple[str, object | None]] = []
        self.photo_calls: list[tuple[object, str | None, object | None]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))

    async def answer_photo(self, photo, caption: str | None = None, reply_markup=None) -> None:
        self.photo_calls.append((photo, caption, reply_markup))


class DummyCallbackMessage:
    def __init__(self) -> None:
        self.photo = [object()]
        self.media_calls: list[tuple[object, object | None]] = []
        self.answer_calls: list[tuple[str, object | None]] = []

    async def edit_media(self, media, reply_markup=None) -> None:
        self.media_calls.append((media, reply_markup))

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))


class DummyCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = DummyCallbackMessage()
        self.from_user = DummyUser()
        self.answer_count = 0

    async def answer(self, *args, **kwargs) -> None:
        self.answer_count += 1


def _flatten_button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def _expected_detail_buttons(current_slug: str) -> list[str]:
    buttons = [USER_BUTTON_BUY_TEXT, USER_BUTTON_LINK_TEXT]
    buttons.extend(
        entry.button_text
        for entry in all_content_entries()
        if entry.slug != current_slug
    )
    buttons.extend([USER_BACK_TEXT, USER_HOME_TEXT])
    return buttons


async def test_faq_command_renders_content_banner() -> None:
    message = DummyMessage()

    await faq_command(message)

    assert message.photo_calls
    _, caption, markup = message.photo_calls[0]
    assert "FAQ" in caption
    assert _flatten_button_texts(markup) == _expected_detail_buttons("faq")


async def test_content_callback_edits_existing_banner_message() -> None:
    callback = DummyCallback("menu:user:content:rules")

    await content_callback(callback)

    assert callback.message.media_calls
    media, markup = callback.message.media_calls[0]
    assert get_content_entry("rules") is not None
    assert get_content_entry("rules").title in media.caption
    assert _flatten_button_texts(markup) == _expected_detail_buttons("rules")
    assert callback.answer_count == 1
