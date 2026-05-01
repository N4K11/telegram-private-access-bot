from __future__ import annotations

from app.bot.keyboards.admin import admin_main_menu_keyboard
from app.config import Settings
from app.db.models import User
from app.services.admin_roles import (
    PERMISSION_ANALYTICS,
    PERMISSION_BROADCASTS,
    PERMISSION_OBSERVABILITY,
    PERMISSION_PAYMENTS,
    PERMISSION_SETTINGS,
    ROLE_ANALYST,
    ROLE_SUPPORT,
    ROLE_USER,
    has_permission,
    resolve_role_from_user,
)


def _flatten_button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def test_admin_ids_owner_fallback_overrides_db_role() -> None:
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181]})
    user = User(telegram_id=755815181, role=ROLE_USER, is_admin=False)

    role = resolve_role_from_user(user, telegram_user_id=755815181, settings=settings)

    assert role == "owner"


def test_support_and_analyst_permissions_are_limited() -> None:
    assert has_permission(ROLE_SUPPORT, PERMISSION_SETTINGS) is False
    assert has_permission(ROLE_SUPPORT, PERMISSION_PAYMENTS) is False
    assert has_permission(ROLE_SUPPORT, PERMISSION_OBSERVABILITY) is True
    assert has_permission(ROLE_ANALYST, PERMISSION_ANALYTICS) is True
    assert has_permission(ROLE_ANALYST, PERMISSION_OBSERVABILITY) is True
    assert has_permission(ROLE_ANALYST, PERMISSION_BROADCASTS) is False


def test_admin_menu_for_support_hides_sensitive_sections() -> None:
    markup = admin_main_menu_keyboard(role=ROLE_SUPPORT)

    assert _flatten_button_texts(markup) == [
        "👥 Пользователи",
        "🎫 Поддержка",
        "📜 Аудит",
        "🧪 Диагностика",
        "⬅️ Назад в меню пользователя",
    ]


def test_admin_menu_for_analyst_shows_only_analytics_sections() -> None:
    markup = admin_main_menu_keyboard(role=ROLE_ANALYST)

    assert _flatten_button_texts(markup) == [
        "📊 Аналитика",
        "📜 Аудит",
        "🧪 Диагностика",
        "⬅️ Назад в меню пользователя",
    ]