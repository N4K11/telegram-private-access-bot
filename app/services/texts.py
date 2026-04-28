from __future__ import annotations

from html import escape


class _SafeDict(dict[str, object]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"

    def __getitem__(self, key: str) -> object:
        value = super().__getitem__(key)
        if isinstance(value, str):
            return escape(value)
        return value


DEFAULT_TEXTS: dict[str, str] = {
    "start": (
        "Здравствуйте, {first_name}.\n\n"
        "Этот бот управляет доступом в приватный канал, подписками и платежами."
    ),
    "user_subscription": (
        "Подписка\n\n"
        "Экран статуса подписки подключен. Полная логика подписок появится на следующих этапах."
    ),
    "user_tariffs": "Тарифы\n\nНиже показаны доступные тарифы.",
    "user_support": (
        "Поддержка\n\n"
        "Если возникли вопросы, свяжитесь с администратором, указанным в описании бота."
    ),
    "admin_dashboard": (
        "Панель администратора\n\n"
        "Управляйте тарифами, каналами и следующими этапами настройки прямо из Telegram."
    ),
    "admin_section": "Раздел администратора: {section}",
}


def render_text(key: str, **context: object) -> str:
    template = DEFAULT_TEXTS.get(key, key)
    return template.format_map(_SafeDict(context))