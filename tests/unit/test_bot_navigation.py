from __future__ import annotations

from app.bot.keyboards.admin import admin_main_menu_keyboard
from app.bot.keyboards.user import user_main_menu_keyboard, user_section_keyboard
from app.bot.routers.admin.dashboard import admin_section
from app.bot.routers.common import edit_or_answer
from app.bot.routers.user.start import start_handler, user_section


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
    assert "Здравствуйте, Anna." in message.answer_calls[0][0]


async def test_edit_or_answer_edits_existing_callback_message() -> None:
    callback = DummyCallback("menu:user:subscription")

    await edit_or_answer(callback, text="Updated")

    assert callback.message.edit_calls == [("Updated", None)]
    assert callback.message.answer_calls == []
    assert callback.answer_count == 1


async def test_edit_or_answer_falls_back_to_new_message() -> None:
    callback = DummyCallback("menu:user:subscription", fail_edit=True)

    await edit_or_answer(callback, text="Fallback")

    assert callback.message.edit_calls == []
    assert callback.message.answer_calls == [("Fallback", None)]
    assert callback.answer_count == 1


async def test_user_section_navigation_renders_back_and_home() -> None:
    callback = DummyCallback("menu:user:subscription")

    await user_section(callback)

    assert callback.message.edit_calls
    _, markup = callback.message.edit_calls[0]
    assert _flatten_button_texts(markup) == ["Назад", "Главное меню"]


async def test_admin_section_navigation_renders_back_and_home() -> None:
    callback = DummyCallback("menu:admin:analytics")

    await admin_section(callback)

    assert callback.message.edit_calls
    text, markup = callback.message.edit_calls[0]
    assert "Раздел администратора: Аналитика" in text
    assert _flatten_button_texts(markup) == ["Назад", "Главное меню"]



def test_user_main_menu_keyboard_has_expected_buttons() -> None:
    assert _flatten_button_texts(user_main_menu_keyboard()) == [
        "Моя подписка",
        "Тарифы",
        "Поддержка",
    ]



def test_user_section_keyboard_has_back_and_home() -> None:
    assert _flatten_button_texts(user_section_keyboard()) == ["Назад", "Главное меню"]



def test_admin_main_menu_keyboard_has_expected_buttons() -> None:
    assert _flatten_button_texts(admin_main_menu_keyboard()) == [
        "📊 Аналитика",
        "👥 Пользователи",
        "💳 Платежи",
        "🧾 Тарифы",
        "📣 Каналы",
        "✍️ Тексты",
        "📢 Рассылка",
        "💾 Бэкапы",
        "⚙️ Настройки",
        "🧪 Диагностика",
    ]