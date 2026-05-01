from __future__ import annotations

from app.bot.routers.user.legal import legal_callback, privacy_command, terms_command
from app.bot.routers.user.payments import paysupport_command


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


async def test_terms_command_renders_legal_template() -> None:
    message = DummyMessage()

    await terms_command(message)

    assert message.photo_calls
    _, caption, markup = message.photo_calls[0]
    assert "Условия" in caption
    assert _flatten_button_texts(markup) == [
        "💳 Помощь с оплатой",
        "🔒 Конфиденциальность",
        "↩️ Возвраты",
        "⬅️ Назад",
        "🏠 Главное меню",
    ]


async def test_privacy_command_renders_legal_template() -> None:
    message = DummyMessage()

    await privacy_command(message)

    assert message.photo_calls
    _, caption, _ = message.photo_calls[0]
    assert "конфиденциальности" in caption.lower()


async def test_legal_callback_edits_existing_banner_message() -> None:
    callback = DummyCallback("menu:user:legal:refunds")

    await legal_callback(callback)

    assert callback.message.media_calls
    media, markup = callback.message.media_calls[0]
    assert "возврат" in media.caption.lower()
    assert _flatten_button_texts(markup) == [
        "💳 Помощь с оплатой",
        "📄 Условия",
        "🔒 Конфиденциальность",
        "⬅️ Назад",
        "🏠 Главное меню",
    ]
    assert callback.answer_count == 1


async def test_paysupport_command_uses_payment_support_template() -> None:
    message = DummyMessage()

    await paysupport_command(message)

    assert message.answer_calls
    assert "Помощь с оплатой" in message.answer_calls[0][0]

