from __future__ import annotations

from pathlib import Path

from app.bot.rendering import render_section

BANNER_PATH = Path(__file__).resolve().parents[2] / "assets" / "banners" / "main.png"


class DummyMessage:
    def __init__(
        self,
        *,
        has_photo: bool = False,
        fail_edit: bool = False,
        fail_media: bool = False,
    ) -> None:
        self.answer_calls: list[tuple[str, object | None]] = []
        self.photo_calls: list[tuple[object, str | None, object | None]] = []
        self.edit_calls: list[tuple[str, object | None]] = []
        self.media_calls: list[tuple[object, object | None]] = []
        self.photo = [object()] if has_photo else None
        self.from_user = None
        self._fail_edit = fail_edit
        self._fail_media = fail_media

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))

    async def answer_photo(self, photo, caption: str | None = None, reply_markup=None) -> None:
        self.photo_calls.append((photo, caption, reply_markup))

    async def edit_text(self, text: str, reply_markup=None) -> None:
        if self._fail_edit:
            raise RuntimeError("edit failed")
        self.edit_calls.append((text, reply_markup))

    async def edit_media(self, media, reply_markup=None) -> None:
        if self._fail_media:
            raise RuntimeError("media edit failed")
        self.media_calls.append((media, reply_markup))


class DummyCallback:
    def __init__(
        self,
        *,
        has_photo: bool = False,
        fail_edit: bool = False,
        fail_media: bool = False,
    ) -> None:
        self.message = DummyMessage(
            has_photo=has_photo,
            fail_edit=fail_edit,
            fail_media=fail_media,
        )
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


async def test_render_section_edits_existing_callback_photo_when_banner_exists() -> None:
    callback = DummyCallback(has_photo=True)

    await render_section(callback, text="Banner text", banner_path=BANNER_PATH)

    assert callback.message.photo_calls == []
    assert callback.message.edit_calls == []
    assert len(callback.message.media_calls) == 1
    media, markup = callback.message.media_calls[0]
    assert media.caption == "Banner text"
    assert markup is None
    assert callback.answer_count == 1


async def test_render_section_keeps_text_edit_for_text_callback_when_banner_exists() -> None:
    callback = DummyCallback(has_photo=False)

    await render_section(callback, text="Banner text", banner_path=BANNER_PATH)

    assert callback.message.photo_calls == []
    assert callback.message.media_calls == []
    assert callback.message.edit_calls == [("Banner text", None)]
    assert callback.answer_count == 1
