# ruff: noqa: E501
from __future__ import annotations

import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from html import escape

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TextTemplate
from app.db.repositories.text_templates import TextTemplateRepository
from app.utils.encoding import is_mojibake

logger = logging.getLogger(__name__)


class TextTemplateValidationError(ValueError):
    """Raised when a managed text template is invalid."""


class _SafeDict(dict[str, object]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"

    def __getitem__(self, key: str) -> object:
        value = super().__getitem__(key)
        if isinstance(value, str):
            return escape(value)
        return value


@dataclass(frozen=True, slots=True)
class TextTemplateSeed:
    key: str
    title: str
    body: str
    is_system: bool = False


DEFAULT_TEXT_TEMPLATES: dict[str, TextTemplateSeed] = {
    "start": TextTemplateSeed(
        key="start",
        title="Главное меню пользователя",
        body=(
            "👋 Привет, {first_name}!\n\n"
            "Это бот для управления доступом в приватный канал.\n\n"
            "{subscription_status_block}\n\n"
            "Выбери действие ниже 👇"
        ),
    ),
    "user_subscription_inactive": TextTemplateSeed(
        key="user_subscription_inactive",
        title="Блок статуса без подписки",
        body=(
            "🔒 Подписка: не активна\n\n"
            "Оформи доступ и получи персональную ссылку для входа."
        ),
    ),
    "user_subscription_active": TextTemplateSeed(
        key="user_subscription_active",
        title="Блок статуса активной подписки",
        body=(
            "✅ Подписка активна до: {expires_at}\n\n"
            "Ты можешь повторно получить ссылку для входа, если потерял её."
        ),
    ),
    "user_subscription": TextTemplateSeed(
        key="user_subscription",
        title="Активные подписки",
        body=(
            "🔗 Активные подписки\n\n"
            "Выбери канал, для которого нужна персональная ссылка доступа."
        ),
    ),
    "user_tariffs": TextTemplateSeed(
        key="user_tariffs",
        title="Покупка доступа",
        body=(
            "💎 Купить доступ\n\n"
            "Выбери подходящий тариф для оплаты и мгновенного получения доступа."
        ),
    ),
    "profile": TextTemplateSeed(
        key="profile",
        title="Профиль пользователя",
        body=(
            "👤 Мой профиль\n\n"
            "Telegram ID: {telegram_id}\n"
            "Username: {username}\n"
            "Подписка: {subscription_status}\n"
            "Доступ до: {expires_at}\n"
            "Покупок: {purchase_count}\n"
            "Оплачено Stars: {total_paid}\n\n"
            "Активные каналы:\n{active_channels_block}"
        ),
    ),
    "tariffs": TextTemplateSeed(
        key="tariffs",
        title="Список тарифов",
        body="📦 Доступные тарифы\n\n{tariffs_block}\n\nВыбери тариф для оплаты 👇",
    ),
    "tariffs_empty": TextTemplateSeed(
        key="tariffs_empty",
        title="Нет активных тарифов",
        body=(
            "📦 Тарифы\n\n"
            "Сейчас активных тарифов нет.\n"
            "Администратор скоро добавит доступные варианты подписки."
        ),
    ),
    "tariff_detail": TextTemplateSeed(
        key="tariff_detail",
        title="Карточка тарифа",
        body=(
            "💎 {tariff_name}\n\n"
            "⏳ Срок: {duration_days} дней\n"
            "⭐ Цена: {price_stars} Stars\n"
            "📣 Канал: {channel_name}{crypto_block}"
        ),
    ),
    "payment_success": TextTemplateSeed(
        key="payment_success",
        title="Успешная оплата",
        body=(
            "✅ Оплата прошла успешно.\n\n"
            "{action}\n"
            "Тариф: {tariff_name}\n"
            "Канал: {channel_name}\n"
            "Доступ активен до: {expires_at}{invite_block}"
        ),
    ),
    "payment_failed": TextTemplateSeed(
        key="payment_failed",
        title="Ошибка обработки оплаты",
        body=(
            "⚠️ Оплата получена, но не удалось завершить обработку: {reason}\n\n"
            "Напиши в /paysupport, если доступ не активировался автоматически."
        ),
    ),
    "subscription_warning_3d": TextTemplateSeed(
        key="subscription_warning_3d",
        title="Напоминание за 3 дня до окончания подписки",
        body=(
            "⏳ До окончания доступа к каналу «{channel_name}» осталось около 3 дней.\n\n"
            "Подписка действует до: {expires_at}.\n"
            "Продли доступ заранее, чтобы не потерять вход."
        ),
    ),
    "subscription_warning_1d": TextTemplateSeed(
        key="subscription_warning_1d",
        title="Напоминание за 1 день до окончания подписки",
        body=(
            "⚠️ До окончания доступа к каналу «{channel_name}» остался примерно 1 день.\n\n"
            "Подписка действует до: {expires_at}.\n"
            "Продли доступ заранее, чтобы бот не отозвал доступ."
        ),
    ),
    "subscription_expired_grace": TextTemplateSeed(
        key="subscription_expired_grace",
        title="Подписка истекла, действует grace period",
        body=(
            "⌛ Подписка на канал «{channel_name}» уже истекла.\n\n"
            "Истекла: {expired_at}.\n"
            "Если не продлить доступ, бот отзовёт его через {grace_period_hours} ч."
        ),
    ),    "subscription_expired": TextTemplateSeed(
        key="subscription_expired",
        title="Подписка истекла",
        body=(
            "⛔ Доступ к каналу «{channel_name}» завершён.\n\n"
            "Подписка истекла. Оформи новый тариф, чтобы вернуться в канал."
        ),
    ),
    "invite_link": TextTemplateSeed(
        key="invite_link",
        title="Ссылка доступа",
        body=(
            "{action}\n\n"
            "Канал: {channel_name}\n"
            "Ссылка: {invite_link}{invite_expires_block}"
        ),
    ),
    "support": TextTemplateSeed(
        key="support",
        title="Помощь",
        body=(
            "❓ Помощь\n\n"
            "1. Выбери тариф и оплати его Stars.\n"
            "2. После оплаты бот выдаст персональную ссылку.\n"
            "3. Если ссылка потерялась, открой раздел «🔗 Получить ссылку».\n"
            "4. Если что-то пошло не так, используй /paysupport."
        ),
    ),
    "user_support": TextTemplateSeed(
        key="user_support",
        title="Помощь пользователю",
        body=(
            "❓ Помощь\n\n"
            "После оплаты доступ активируется автоматически.\n"
            "Если ссылка потерялась, открой «🔗 Получить ссылку».\n"
            "Если платёж прошёл, а доступа нет, используй /paysupport."
        ),
    ),
    "payment_support": TextTemplateSeed(
        key="payment_support",
        title="\u041f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430 \u043e\u043f\u043b\u0430\u0442\u044b",
        body=(
            "\U0001f4b3 \u041f\u043e\u043c\u043e\u0449\u044c \u0441 \u043e\u043f\u043b\u0430\u0442\u043e\u0439\n\n"
            "\u0415\u0441\u043b\u0438 \u043f\u043b\u0430\u0442\u0451\u0436 \u043f\u0440\u043e\u0448\u0451\u043b, \u0430 \u0434\u043e\u0441\u0442\u0443\u043f \u043d\u0435 \u0430\u043a\u0442\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u043b\u0441\u044f, \u043e\u0442\u043f\u0440\u0430\u0432\u044c \u0432 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0443 \u043d\u043e\u043c\u0435\u0440 \u0447\u0435\u043a\u0430 \u0438\u043b\u0438 \u0438\u043d\u0432\u043e\u0439\u0441\u0430, \u0434\u0430\u0442\u0443 \u043e\u043f\u043b\u0430\u0442\u044b, \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u0442\u0430\u0440\u0438\u0444\u0430 \u0438 \u0441\u0432\u043e\u0439 Telegram ID.\n\n"
            "\u041f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430 \u043f\u0440\u043e\u0432\u0435\u0440\u0438\u0442 \u043f\u043b\u0430\u0442\u0451\u0436 \u0438 \u043e\u0442\u0432\u0435\u0442\u0438\u0442 \u0432 \u044d\u0442\u043e\u043c \u0431\u043e\u0442\u0435."
        ),
    ),
    "terms": TextTemplateSeed(
        key="terms",
        title="\u0423\u0441\u043b\u043e\u0432\u0438\u044f \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u044f",
        body=(
            "\U0001f4c4 \u0423\u0441\u043b\u043e\u0432\u0438\u044f \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u044f\n\n"
            "1. \u0422\u044b \u043f\u043e\u043a\u0443\u043f\u0430\u0435\u0448\u044c \u0441\u0440\u043e\u043a \u0434\u043e\u0441\u0442\u0443\u043f\u0430 \u043a \u043f\u0440\u0438\u0432\u0430\u0442\u043d\u043e\u043c\u0443 \u043a\u0430\u043d\u0430\u043b\u0443, \u0443\u043a\u0430\u0437\u0430\u043d\u043d\u044b\u0439 \u0432 \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u043e\u043c \u0442\u0430\u0440\u0438\u0444\u0435.\n"
            "2. \u0414\u043e\u0441\u0442\u0443\u043f \u0434\u0435\u0439\u0441\u0442\u0432\u0443\u0435\u0442 \u0442\u043e\u043b\u044c\u043a\u043e \u0434\u043b\u044f \u0442\u0432\u043e\u0435\u0433\u043e Telegram-\u0430\u043a\u043a\u0430\u0443\u043d\u0442\u0430 \u0438 \u043d\u0435 \u043f\u0440\u0435\u0434\u043d\u0430\u0437\u043d\u0430\u0447\u0435\u043d \u0434\u043b\u044f \u043f\u0435\u0440\u0435\u0434\u0430\u0447\u0438 \u0434\u0440\u0443\u0433\u0438\u043c \u043b\u044e\u0434\u044f\u043c.\n"
            "3. \u0421\u0440\u043e\u043a, \u0446\u0435\u043d\u0430 \u0438 \u043a\u0430\u043d\u0430\u043b \u0432\u0441\u0435\u0433\u0434\u0430 \u043f\u043e\u043a\u0430\u0437\u044b\u0432\u0430\u044e\u0442\u0441\u044f \u043f\u0435\u0440\u0435\u0434 \u043e\u043f\u043b\u0430\u0442\u043e\u0439.\n"
            "4. \u041f\u0440\u0438 \u043d\u0430\u0440\u0443\u0448\u0435\u043d\u0438\u0438 \u043f\u0440\u0430\u0432\u0438\u043b \u043a\u0430\u043d\u0430\u043b\u0430 \u0438\u043b\u0438 \u043f\u043e\u043f\u044b\u0442\u043a\u0430\u0445 \u043e\u0431\u0445\u043e\u0434\u0430 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u0439 \u0434\u043e\u0441\u0442\u0443\u043f \u043c\u043e\u0436\u0435\u0442 \u0431\u044b\u0442\u044c \u043e\u0442\u043e\u0437\u0432\u0430\u043d \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u043e\u043c."
        ),
    ),
    "privacy": TextTemplateSeed(
        key="privacy",
        title="\u041f\u043e\u043b\u0438\u0442\u0438\u043a\u0430 \u043a\u043e\u043d\u0444\u0438\u0434\u0435\u043d\u0446\u0438\u0430\u043b\u044c\u043d\u043e\u0441\u0442\u0438",
        body=(
            "\U0001f512 \u041f\u043e\u043b\u0438\u0442\u0438\u043a\u0430 \u043a\u043e\u043d\u0444\u0438\u0434\u0435\u043d\u0446\u0438\u0430\u043b\u044c\u043d\u043e\u0441\u0442\u0438\n\n"
            "\u0411\u043e\u0442 \u0445\u0440\u0430\u043d\u0438\u0442 \u0442\u043e\u043b\u044c\u043a\u043e \u0434\u0430\u043d\u043d\u044b\u0435, \u043d\u0435\u043e\u0431\u0445\u043e\u0434\u0438\u043c\u044b\u0435 \u0434\u043b\u044f \u0440\u0430\u0431\u043e\u0442\u044b \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0438: Telegram ID, username, \u0438\u0441\u0442\u043e\u0440\u0438\u044e \u043f\u043b\u0430\u0442\u0435\u0436\u0435\u0439, \u0441\u0442\u0430\u0442\u0443\u0441 \u0434\u043e\u0441\u0442\u0443\u043f\u0430, \u0432\u044b\u0434\u0430\u043d\u043d\u044b\u0435 invite-\u0441\u0441\u044b\u043b\u043a\u0438 \u0438 \u043e\u0431\u0440\u0430\u0449\u0435\u043d\u0438\u044f \u0432 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0443.\n\n"
            "\u042d\u0442\u0438 \u0434\u0430\u043d\u043d\u044b\u0435 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u044e\u0442\u0441\u044f \u0442\u043e\u043b\u044c\u043a\u043e \u0434\u043b\u044f \u0432\u044b\u0434\u0430\u0447\u0438 \u0434\u043e\u0441\u0442\u0443\u043f\u0430, \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0438 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439, \u0434\u0438\u0430\u0433\u043d\u043e\u0441\u0442\u0438\u043a\u0438 \u0438 \u0444\u0438\u043d\u0430\u043d\u0441\u043e\u0432\u043e\u0433\u043e \u0443\u0447\u0451\u0442\u0430 \u0432\u043d\u0443\u0442\u0440\u0438 \u0431\u043e\u0442\u0430."
        ),
    ),
    "refund_policy": TextTemplateSeed(
        key="refund_policy",
        title="\u041f\u043e\u043b\u0438\u0442\u0438\u043a\u0430 \u0432\u043e\u0437\u0432\u0440\u0430\u0442\u043e\u0432",
        body=(
            "\u21a9\ufe0f \u041f\u043e\u043b\u0438\u0442\u0438\u043a\u0430 \u0432\u043e\u0437\u0432\u0440\u0430\u0442\u043e\u0432\n\n"
            "\u0415\u0441\u043b\u0438 \u043f\u043b\u0430\u0442\u0451\u0436 \u043f\u0440\u043e\u0448\u0451\u043b \u043e\u0448\u0438\u0431\u043e\u0447\u043d\u043e \u0438\u043b\u0438 \u0431\u043e\u0442 \u043d\u0435 \u0432\u044b\u0434\u0430\u043b \u0434\u043e\u0441\u0442\u0443\u043f \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438, \u043e\u0442\u043a\u0440\u043e\u0439 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0443 \u0441\u0440\u0430\u0437\u0443 \u043f\u043e\u0441\u043b\u0435 \u043e\u043f\u043b\u0430\u0442\u044b.\n\n"
            "\u041a\u0430\u0436\u0434\u044b\u0439 \u0437\u0430\u043f\u0440\u043e\u0441 \u043d\u0430 \u0432\u043e\u0437\u0432\u0440\u0430\u0442 \u0438\u043b\u0438 \u0440\u0443\u0447\u043d\u043e\u0435 \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435 \u0434\u043e\u0441\u0442\u0443\u043f\u0430 \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440 \u0440\u0430\u0441\u0441\u043c\u0430\u0442\u0440\u0438\u0432\u0430\u0435\u0442 \u043e\u0442\u0434\u0435\u043b\u044c\u043d\u043e \u043f\u043e \u0434\u0430\u043d\u043d\u044b\u043c \u043f\u043b\u0430\u0442\u0435\u0436\u0430 \u0438 \u0444\u0430\u043a\u0442\u0438\u0447\u0435\u0441\u043a\u043e\u043c\u0443 \u0441\u0442\u0430\u0442\u0443\u0441\u0443 \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0438."
        ),
    ),
    "user_invite_picker": TextTemplateSeed(
        key="user_invite_picker",
        title="Выбор ссылки доступа",
        body=(
            "🔗 Получить ссылку\n\n"
            "Выбери канал, для которого нужна ссылка доступа:\n\n{subscriptions_block}"
        ),
    ),
    "user_invite_missing": TextTemplateSeed(
        key="user_invite_missing",
        title="Нет активной подписки для ссылки",
        body=(
            "🔗 Получить ссылку\n\n"
            "У тебя нет активной подписки.\n\n"
            "Выбери тариф и оформи доступ, чтобы получить персональную ссылку."
        ),
    ),
    "admin_dashboard": TextTemplateSeed(
        key="admin_dashboard",
        title="Главное меню администратора",
        body=(
            "🛠 Админ-панель\n\n"
            "Управляй тарифами, каналами, текстами, пользователями и резервными копиями из одного меню."
        ),
    ),
    "admin_section": TextTemplateSeed(
        key="admin_section",
        title="Раздел админки",
        body="🛠 Раздел администратора: {section}",
    ),
    "admin_menu_analytics": TextTemplateSeed(key="admin_menu_analytics", title="Кнопка аналитики", body="📊 Аналитика", is_system=True),
    "admin_menu_users": TextTemplateSeed(key="admin_menu_users", title="Кнопка пользователей", body="👥 Пользователи", is_system=True),
    "admin_menu_payments": TextTemplateSeed(key="admin_menu_payments", title="Кнопка платежей", body="💳 Платежи", is_system=True),
    "admin_menu_tariffs": TextTemplateSeed(key="admin_menu_tariffs", title="Кнопка тарифов", body="🧾 Тарифы", is_system=True),
    "admin_menu_channels": TextTemplateSeed(key="admin_menu_channels", title="Кнопка каналов", body="📣 Каналы", is_system=True),
    "admin_menu_texts": TextTemplateSeed(key="admin_menu_texts", title="Кнопка текстов", body="✍️ Тексты", is_system=True),
    "admin_menu_broadcasts": TextTemplateSeed(key="admin_menu_broadcasts", title="Кнопка рассылок", body="📢 Рассылки", is_system=True),
    "admin_menu_backups": TextTemplateSeed(key="admin_menu_backups", title="Кнопка бэкапов", body="💾 Бэкапы", is_system=True),
    "admin_menu_settings": TextTemplateSeed(key="admin_menu_settings", title="Кнопка настроек", body="⚙️ Настройки", is_system=True),
    "admin_menu_diagnostics": TextTemplateSeed(key="admin_menu_diagnostics", title="Кнопка диагностики", body="🧪 Диагностика", is_system=True),
    "admin_button_back": TextTemplateSeed(key="admin_button_back", title="Кнопка назад", body="⬅️ Назад", is_system=True),
    "admin_button_home": TextTemplateSeed(key="admin_button_home", title="Кнопка домой", body="🏠 Админ-панель", is_system=True),
}

LEGACY_DEFAULT_TEXT_BODIES: dict[str, str] = {
    "start": "Здравствуйте, {first_name}.\n\nPrivate access bot.",
    "user_subscription": "Моя подписка\n\nАктивных подписок сейчас нет.",
    "user_tariffs": "Тарифы\n\nВыберите подходящий тариф.",
    "profile": "Моя подписка\n\n{subscriptions_block}{payments_block}",
    "tariffs": "Тарифы\n\n{tariffs_block}",
    "payment_success": "Оплата прошла успешно.\n\n{action}\nTariff: {tariff_name}\nChannel: {channel_name}\nExpires: {expires_at}{invite_block}",
    "payment_failed": "Оплата получена, но обработка не завершилась: {reason}\n\nUse /paysupport.",
    "support": "Поддержка\n\nUse /paysupport or contact the admin.",
    "user_support": "Поддержка\n\nUse /paysupport or contact the admin.",
    "paysupport": "Поддержка оплаты\n\nSend the payment screenshot and tariff details to the admin.",
    "admin_dashboard": "Панель администратора\n\nManage tariffs, channels, texts and broadcasts.",
    "admin_section": "Раздел администратора: {section}",
}


def default_text_template(key: str) -> TextTemplateSeed | None:
    return DEFAULT_TEXT_TEMPLATES.get(key)


def default_text_body(key: str) -> str:
    template = default_text_template(key)
    return template.body if template is not None else key


def has_mojibake(value: str) -> bool:
    return is_mojibake(value)


def iter_default_template_texts() -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for key, template in DEFAULT_TEXT_TEMPLATES.items():
        values.append((f"{key}.title", template.title))
        values.append((f"{key}.body", template.body))
    return values


def is_default_text_body(key: str, body: str) -> bool:
    template = default_text_template(key)
    return template is not None and template.body == body


def should_repair_managed_template(template: TextTemplate) -> bool:
    seed = default_text_template(template.key)
    if seed is None or template.updated_by_user_id is not None:
        return False
    if template.body == seed.body and template.title == seed.title:
        return False
    if LEGACY_DEFAULT_TEXT_BODIES.get(template.key) == template.body:
        return True
    return has_mojibake(template.body) or has_mojibake(template.title)


def repair_managed_template(template: TextTemplate) -> bool:
    seed = default_text_template(template.key)
    if seed is None or not should_repair_managed_template(template):
        return False
    template.title = seed.title
    template.body = seed.body
    return True


def validate_text_body(body: str) -> str:
    normalized = body.strip()
    if not normalized:
        raise TextTemplateValidationError("Текст шаблона не должен быть пустым.")
    if has_mojibake(normalized):
        raise TextTemplateValidationError("Похоже, в тексте есть кракозябры.")

    try:
        _render_body(normalized)
    except (IndexError, ValueError) as exc:
        raise TextTemplateValidationError("Некорректные placeholders или фигурные скобки.") from exc

    return normalized


async def ensure_default_text_templates(session: AsyncSession) -> int:
    repository = TextTemplateRepository(session)
    existing = await repository.get_by_keys(tuple(DEFAULT_TEXT_TEMPLATES))
    created = 0
    repaired = 0
    for key, seed in DEFAULT_TEXT_TEMPLATES.items():
        template = existing.get(key)
        if template is None:
            await repository.create(key=seed.key, title=seed.title, body=seed.body, is_system=seed.is_system)
            created += 1
            continue
        if repair_managed_template(template):
            repaired += 1
    if repaired:
        logger.warning("Repaired %s legacy or broken text templates during startup.", repaired)
    return created


async def list_text_templates(session: AsyncSession) -> list[TextTemplate]:
    await ensure_default_text_templates(session)
    return await TextTemplateRepository(session).list_all()


async def get_text_template_record(session: AsyncSession, key: str) -> TextTemplate | None:
    repository = TextTemplateRepository(session)
    template = await repository.get_by_key(key)
    if template is not None:
        return template

    seed = default_text_template(key)
    if seed is None:
        return None

    return await repository.create(key=seed.key, title=seed.title, body=seed.body, is_system=seed.is_system)


async def update_text_template_body(session: AsyncSession, *, key: str, body: str, updated_by_user_id: int | None) -> TextTemplate:
    template = await get_text_template_record(session, key)
    if template is None:
        raise TextTemplateValidationError(f"Unknown template key: {key}")

    template.body = validate_text_body(body)
    template.updated_by_user_id = updated_by_user_id
    await session.flush()
    return template


async def reset_text_template_body(session: AsyncSession, *, key: str, updated_by_user_id: int | None) -> TextTemplate:
    template = await get_text_template_record(session, key)
    default_template = default_text_template(key)
    if template is None or default_template is None:
        raise TextTemplateValidationError(f"Unknown template key: {key}")

    template.title = default_template.title
    template.body = default_template.body
    template.updated_by_user_id = updated_by_user_id
    await session.flush()
    return template


async def get_text_bodies(session: AsyncSession | None, keys: tuple[str, ...]) -> dict[str, str]:
    if session is None:
        return {key: default_text_body(key) for key in keys}

    templates = await TextTemplateRepository(session).get_by_keys(keys)
    return {key: templates[key].body if key in templates else default_text_body(key) for key in keys}


def render_text(session_or_key: AsyncSession | str | None, key: str | None = None, **context: object) -> str | Awaitable[str]:
    if isinstance(session_or_key, AsyncSession) or key is not None:
        session = session_or_key if isinstance(session_or_key, AsyncSession) else None
        managed_key = key if key is not None else str(session_or_key)
        return _render_managed_text(session, managed_key, **context)

    fallback_key = str(session_or_key)
    fallback_body = default_text_body(fallback_key)
    return _render_with_fallback(fallback_body, fallback_body, **context)


async def _render_managed_text(session: AsyncSession | None, key: str, **context: object) -> str:
    template_body = (await get_text_bodies(session, (key,))).get(key, key)
    fallback_body = default_text_body(key)
    return _render_with_fallback(template_body, fallback_body, **context)


def _render_with_fallback(template_body: str, fallback_body: str, **context: object) -> str:
    try:
        return _render_body(template_body, **context)
    except (IndexError, ValueError):
        if template_body != fallback_body:
            logger.warning("Managed text template fallback activated.")
            try:
                return _render_body(fallback_body, **context)
            except (IndexError, ValueError):
                return fallback_body
        return fallback_body


def _render_body(body: str, **context: object) -> str:
    return body.format_map(_SafeDict(context))