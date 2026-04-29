from __future__ import annotations

import logging
from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.navigation import build_navigation_keyboard
from app.db.models import Subscription, Tariff
from app.utils.encoding import safe_ui_text

logger = logging.getLogger(__name__)

USER_BUTTON_BUY_TEXT = "💎 Купить доступ"
USER_BUTTON_TARIFFS_TEXT = "📦 Тарифы"
USER_BUTTON_PROFILE_TEXT = "👤 Мой профиль"
USER_BUTTON_LINK_TEXT = "🔗 Получить ссылку"
USER_BUTTON_HELP_TEXT = "❓ Помощь"
USER_BUTTON_ADMIN_TEXT = "🛠 Админ-панель"
USER_BUTTON_REFRESH_TEXT = "🔄 Обновить"
USER_BUTTON_STARS_TEXT = "⭐ Оплатить Stars"
USER_BUTTON_CRYPTO_TEXT = "₿ Оплатить Crypto Pay"
USER_BUTTON_OPEN_CRYPTO_TEXT = "💸 Открыть Crypto Pay"
USER_BACK_TEXT = "⬅️ Назад"
USER_HOME_TEXT = "🏠 Главное меню"

TARIFF_ICONS = ("💎", "🚀", "⭐", "🔥", "🎯")


def _safe_button_text(text: str | None, fallback: str) -> str:
    sanitized = safe_ui_text(text, fallback)
    if sanitized != (text or "").strip():
        logger.warning("Detected broken UI text. Using fallback label instead.")
    return sanitized


def _safe_tariff_name(tariff: Tariff) -> str:
    return _safe_button_text(tariff.name, f"Тариф #{tariff.id}")


def _safe_channel_title(subscription: Subscription) -> str:
    return _safe_button_text(subscription.channel.title, f"Канал #{subscription.channel_id}")


def _safe_tariff_icon(index: int) -> str:
    return TARIFF_ICONS[index % len(TARIFF_ICONS)]


def user_main_menu_keyboard(*, is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for text, callback_data in (
        (USER_BUTTON_BUY_TEXT, "menu:user:buy"),
        (USER_BUTTON_TARIFFS_TEXT, "menu:user:tariffs"),
        (USER_BUTTON_PROFILE_TEXT, "menu:user:profile"),
        (USER_BUTTON_LINK_TEXT, "menu:user:link"),
        (USER_BUTTON_HELP_TEXT, "menu:user:help"),
    ):
        builder.button(text=text, callback_data=callback_data)
    if is_admin:
        builder.button(text=USER_BUTTON_ADMIN_TEXT, callback_data="menu:admin:home")
    builder.adjust(1)
    return builder.as_markup()


def user_section_keyboard(
    *,
    back_callback: str = "menu:user:home",
    include_back: bool = True,
    include_home: bool = True,
) -> InlineKeyboardMarkup:
    return build_navigation_keyboard(
        include_back=include_back,
        include_home=include_home,
        back_callback=back_callback,
        home_callback="menu:user:home",
        back_text=USER_BACK_TEXT,
        home_text=USER_HOME_TEXT,
    )


def user_purchase_prompt_keyboard() -> InlineKeyboardMarkup:
    return build_navigation_keyboard(
        (USER_BUTTON_BUY_TEXT, "menu:user:buy"),
        include_home=True,
        home_callback="menu:user:home",
        home_text=USER_HOME_TEXT,
    )


def user_profile_keyboard(*, has_active_subscription: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_active_subscription:
        builder.button(text=USER_BUTTON_LINK_TEXT, callback_data="menu:user:link")
        builder.button(text="💎 Продлить доступ", callback_data="menu:user:buy")
    else:
        builder.button(text=USER_BUTTON_BUY_TEXT, callback_data="menu:user:buy")
    builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()


def user_subscription_keyboard(subscriptions: Sequence[Subscription]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for subscription in subscriptions:
        title = _safe_channel_title(subscription)
        short_title = title if len(title) <= 28 else f"{title[:25]}..."
        builder.button(
            text=f"🔗 {short_title}",
            callback_data=f"menu:user:invite:{subscription.id}",
        )
    builder.button(text=USER_BACK_TEXT, callback_data="menu:user:profile")
    builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()


def user_tariffs_keyboard(tariffs: Sequence[Tariff]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not tariffs:
        builder.button(text=USER_BUTTON_REFRESH_TEXT, callback_data="menu:user:tariffs")
        builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
        builder.adjust(1)
        return builder.as_markup()

    for index, tariff in enumerate(tariffs):
        title = _safe_tariff_name(tariff)
        icon = _safe_tariff_icon(index)
        builder.button(
            text=f"{icon} Купить: {title} — {tariff.price_stars}⭐",
            callback_data=f"menu:user:buy:stars:{tariff.id}",
        )
    builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()


def user_tariff_detail_keyboard(
    tariff_id: int,
    *,
    include_crypto: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=USER_BUTTON_STARS_TEXT,
        callback_data=f"menu:user:buy:stars:{tariff_id}",
    )
    if include_crypto:
        builder.button(
            text=USER_BUTTON_CRYPTO_TEXT,
            callback_data=f"menu:user:buy:crypto:{tariff_id}",
        )
    builder.button(text=USER_BACK_TEXT, callback_data="menu:user:tariffs")
    builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()


def user_crypto_invoice_keyboard(invoice_url: str | None) -> InlineKeyboardMarkup | None:
    if not invoice_url:
        return None
    builder = InlineKeyboardBuilder()
    builder.button(text=USER_BUTTON_OPEN_CRYPTO_TEXT, url=invoice_url)
    builder.button(text=USER_BACK_TEXT, callback_data="menu:user:tariffs")
    builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()