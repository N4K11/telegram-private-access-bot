# ruff: noqa: E501
from __future__ import annotations

from app.bot.keyboards.admin import admin_main_menu_keyboard
from app.bot.keyboards.user import user_main_menu_keyboard, user_section_keyboard
from app.bot.routers.admin.dashboard import admin_section
from app.bot.routers.common import edit_or_answer
from app.bot.routers.user.start import help_section, start_handler


class DummyUser:
    def __init__(self, user_id: int = 100, first_name: str = "Anna") -> None:
        self.id = user_id
        self.first_name = first_name


class DummyMessage:
    def __init__(self, *, fail_edit: bool = False) -> None:
        self.from_user = DummyUser()
        self.answer_calls: list[tuple[str, object | None]] = []
        self.edit_calls: list[tuple[str, object | None]] = []
        self._fail_edit = fail_edit

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))

    async def edit_text(self, text: str, reply_markup=None) -> None:
        if self._fail_edit:
            raise RuntimeError("edit failed")
        self.edit_calls.append((text, reply_markup))


class DummyCallback:
    def __init__(self, data: str, *, fail_edit: bool = False) -> None:
        self.data = data
        self.message = DummyMessage(fail_edit=fail_edit)
        self.from_user = DummyUser(user_id=1)
        self.answer_count = 0
        self.answer_payloads: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args, **kwargs) -> None:
        self.answer_count += 1
        self.answer_payloads.append((args, kwargs))


def _flatten_button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


async def test_start_handler_sends_new_message() -> None:
    message = DummyMessage()

    await start_handler(message)

    assert len(message.answer_calls) == 1
    assert message.edit_calls == []
    assert "\u041f\u0440\u0438\u0432\u0435\u0442, Anna!" in message.answer_calls[0][0]


async def test_edit_or_answer_edits_existing_callback_message() -> None:
    callback = DummyCallback("menu:user:profile")

    await edit_or_answer(callback, text="Updated")

    assert callback.message.edit_calls == [("Updated", None)]
    assert callback.message.answer_calls == []
    assert callback.answer_count == 1


async def test_edit_or_answer_falls_back_to_new_message() -> None:
    callback = DummyCallback("menu:user:profile", fail_edit=True)

    await edit_or_answer(callback, text="Fallback")

    assert callback.message.edit_calls == []
    assert callback.message.answer_calls == [("Fallback", None)]
    assert callback.answer_count == 1


async def test_help_section_navigation_renders_back_and_home() -> None:
    callback = DummyCallback("menu:user:help")

    await help_section(callback)

    assert callback.message.edit_calls
    _, markup = callback.message.edit_calls[0]
    assert _flatten_button_texts(markup) == ["\u2b05\ufe0f \u041d\u0430\u0437\u0430\u0434", "\U0001f3e0 \u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e"]


async def test_admin_section_navigation_renders_back_and_home() -> None:
    callback = DummyCallback("menu:admin:analytics")

    await admin_section(callback)

    assert callback.message.edit_calls
    text, markup = callback.message.edit_calls[0]
    assert "\u0420\u0430\u0437\u0434\u0435\u043b \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u0430: \u0410\u043d\u0430\u043b\u0438\u0442\u0438\u043a\u0430" in text
    assert _flatten_button_texts(markup) == ["\u2b05\ufe0f \u041d\u0430\u0437\u0430\u0434", "\U0001f3e0 \u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c"]


def test_user_main_menu_keyboard_has_expected_buttons() -> None:
    assert _flatten_button_texts(user_main_menu_keyboard()) == [
        "\U0001f48e \u041a\u0443\u043f\u0438\u0442\u044c \u0434\u043e\u0441\u0442\u0443\u043f",
        "\U0001f4e6 \u0422\u0430\u0440\u0438\u0444\u044b",
        "\U0001f464 \u041c\u043e\u0439 \u043f\u0440\u043e\u0444\u0438\u043b\u044c",
        "\U0001f517 \u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0441\u0441\u044b\u043b\u043a\u0443",
        "\u2753 \u041f\u043e\u043c\u043e\u0449\u044c",
    ]


def test_user_main_menu_keyboard_adds_admin_button_when_requested() -> None:
    assert _flatten_button_texts(user_main_menu_keyboard(is_admin=True))[-1] == "\U0001f6e0 \u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c"


def test_user_section_keyboard_has_back_and_home() -> None:
    assert _flatten_button_texts(user_section_keyboard()) == ["\u2b05\ufe0f \u041d\u0430\u0437\u0430\u0434", "\U0001f3e0 \u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e"]


def test_admin_main_menu_keyboard_has_expected_buttons() -> None:
    assert _flatten_button_texts(admin_main_menu_keyboard()) == [
        "\U0001f4ca \u0410\u043d\u0430\u043b\u0438\u0442\u0438\u043a\u0430",
        "\U0001f465 \u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0438",
        "\U0001f4b3 \u041f\u043b\u0430\u0442\u0435\u0436\u0438",
        "\U0001f9fe \u0422\u0430\u0440\u0438\u0444\u044b",
        "\U0001f4e3 \u041a\u0430\u043d\u0430\u043b\u044b",
        "\u270d\ufe0f \u0422\u0435\u043a\u0441\u0442\u044b",
        "\U0001f4e2 \u0420\u0430\u0441\u0441\u044b\u043b\u043a\u0438",
        "\U0001f4be \u0411\u044d\u043a\u0430\u043f\u044b",
        "\u2699\ufe0f \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438",
        "\U0001f9ea \u0414\u0438\u0430\u0433\u043d\u043e\u0441\u0442\u0438\u043a\u0430",
        "\u2b05\ufe0f \u041d\u0430\u0437\u0430\u0434 \u0432 \u043c\u0435\u043d\u044e \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f",
    ]
