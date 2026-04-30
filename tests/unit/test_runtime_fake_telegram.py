from __future__ import annotations

from pathlib import Path

from app.bot.rendering import render_section


class DummyMessage:
    def __init__(self) -> None:
        self.answer_calls: list[tuple[str, object | None]] = []
        self.photo_calls: list[tuple[object, str | None, object | None]] = []
        self.edit_calls: list[tuple[str, object | None]] = []
        self.from_user = None

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))

    async def answer_photo(self, photo, caption: str | None = None, reply_markup=None) -> None:
        self.photo_calls.append((photo, caption, reply_markup))

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edit_calls.append((text, reply_markup))


class DummyCallback:
    def __init__(self) -> None:
        self.message = DummyMessage()
        self.answer_count = 0

    async def answer(self, *args, **kwargs) -> None:
        self.answer_count += 1


async def test_render_section_falls_back_to_text_for_message_when_banner_missing() -> None:
    message = DummyMessage()

    await render_section(message, text="Fallback text", banner_path=Path("missing-banner.png"))

    assert message.photo_calls == []
    assert message.answer_calls == [("Fallback text", None)]


async def test_render_section_falls_back_to_edit_for_callback_when_banner_missing() -> None:
    callback = DummyCallback()

    await render_section(callback, text="Fallback text", banner_path=Path("missing-banner.png"))

    assert callback.message.photo_calls == []
    assert callback.message.edit_calls == [("Fallback text", None)]
    assert callback.answer_count == 1
