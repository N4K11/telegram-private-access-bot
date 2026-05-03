from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Literal

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.navigation import build_navigation_keyboard
from app.db.models import Subscription, Tariff
from app.services.product_service import (
    ProductCatalogEntry,
    build_offer_details,
    pick_default_tariff,
)
from app.utils.encoding import safe_ui_text

logger = logging.getLogger(__name__)

EMOJI_BUY = "\U0001f48e"
EMOJI_TARIFFS = "\U0001f4e6"
EMOJI_PROFILE = "\U0001f464"
EMOJI_HISTORY = "\U0001f4dc"
EMOJI_REFERRALS = "\U0001f381"
EMOJI_LINK = "\U0001f517"
EMOJI_HELP = "\u2753"
EMOJI_ADMIN = "\U0001f6e0"
EMOJI_REFRESH = "\U0001f504"
EMOJI_STARS = "\u2b50"
EMOJI_CRYPTO = "\u20bf"
EMOJI_CRYPTO_OPEN = "\U0001f4b8"
EMOJI_NEXT = "\u27a1\ufe0f"
EMOJI_SKIP = "\u23ed"
EMOJI_FINISH = "\u2705"
EMOJI_BACK = "\u2b05\ufe0f"
EMOJI_HOME = "\U0001f3e0"
EMOJI_PRODUCT = "\U0001f4c1"
EMOJI_ROCKET = "\U0001f680"
EMOJI_FIRE = "\U0001f525"
EMOJI_TARGET = "\U0001f3af"

TXT_BUY_ACCESS = "\u041a\u0443\u043f\u0438\u0442\u044c \u0434\u043e\u0441\u0442\u0443\u043f"
TXT_TARIFFS = "\u0422\u0430\u0440\u0438\u0444\u044b"
TXT_PROFILE = "\u041c\u043e\u0439 \u043f\u0440\u043e\u0444\u0438\u043b\u044c"
TXT_HISTORY = (
    "\u0418\u0441\u0442\u043e\u0440\u0438\u044f "
    "\u043f\u043b\u0430\u0442\u0435\u0436\u0435\u0439"
)
TXT_REFERRALS = "\u0420\u0435\u0444\u0435\u0440\u0430\u043b\u044b"
TXT_GET_LINK = (
    "\u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c "
    "\u0441\u0441\u044b\u043b\u043a\u0443"
)
TXT_HELP = "\u041f\u043e\u043c\u043e\u0449\u044c"
TXT_ADMIN_PANEL = "\u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c"
TXT_REFRESH = "\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c"
TXT_PAY_STARS = "\u041e\u043f\u043b\u0430\u0442\u0438\u0442\u044c Stars"
TXT_PAY_CRYPTO = "\u041e\u043f\u043b\u0430\u0442\u0438\u0442\u044c Crypto Pay"
TXT_OPEN_CRYPTO = "\u041e\u0442\u043a\u0440\u044b\u0442\u044c Crypto Pay"
TXT_NEXT = "\u0414\u0430\u043b\u044c\u0448\u0435"
TXT_SKIP = "\u041f\u0440\u043e\u043f\u0443\u0441\u0442\u0438\u0442\u044c"
TXT_OPEN_MENU = "\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043c\u0435\u043d\u044e"
TXT_BACK = "\u041d\u0430\u0437\u0430\u0434"
TXT_HOME = "\u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e"
TXT_EXTEND_ACCESS = (
    "\u041f\u0440\u043e\u0434\u043b\u0438\u0442\u044c "
    "\u0434\u043e\u0441\u0442\u0443\u043f"
)
TXT_FOREVER = "\u041d\u0430\u0432\u0441\u0435\u0433\u0434\u0430"
TXT_DAYS = "\u0434\u043d."
TXT_TRIAL = "trial"
TXT_PRODUCT = "\u041f\u0440\u043e\u0434\u0443\u043a\u0442"
TXT_TARIFF = "\u0422\u0430\u0440\u0438\u0444"
TXT_CHANNEL = "\u041a\u0430\u043d\u0430\u043b"
TXT_BUY_PREFIX = "\u041a\u0443\u043f\u0438\u0442\u044c"
TXT_RATE = "\u0442\u0430\u0440\u0438\u0444"
TXT_RATES_2_4 = "\u0442\u0430\u0440\u0438\u0444\u0430"
TXT_RATES_5 = "\u0442\u0430\u0440\u0438\u0444\u043e\u0432"

USER_BUTTON_BUY_TEXT = f"{EMOJI_BUY} {TXT_BUY_ACCESS}"
USER_BUTTON_TARIFFS_TEXT = f"{EMOJI_TARIFFS} {TXT_TARIFFS}"
USER_BUTTON_PROFILE_TEXT = f"{EMOJI_PROFILE} {TXT_PROFILE}"
USER_BUTTON_HISTORY_TEXT = f"{EMOJI_HISTORY} {TXT_HISTORY}"
USER_BUTTON_REFERRALS_TEXT = f"{EMOJI_REFERRALS} {TXT_REFERRALS}"
USER_BUTTON_LINK_TEXT = f"{EMOJI_LINK} {TXT_GET_LINK}"
USER_BUTTON_HELP_TEXT = f"{EMOJI_HELP} {TXT_HELP}"
USER_BUTTON_ADMIN_TEXT = f"{EMOJI_ADMIN} {TXT_ADMIN_PANEL}"
USER_BUTTON_REFRESH_TEXT = f"{EMOJI_REFRESH} {TXT_REFRESH}"
USER_BUTTON_STARS_TEXT = f"{EMOJI_STARS} {TXT_PAY_STARS}"
USER_BUTTON_CRYPTO_TEXT = f"{EMOJI_CRYPTO} {TXT_PAY_CRYPTO}"
USER_BUTTON_OPEN_CRYPTO_TEXT = f"{EMOJI_CRYPTO_OPEN} {TXT_OPEN_CRYPTO}"
USER_BUTTON_ONBOARDING_NEXT_TEXT = f"{EMOJI_NEXT} {TXT_NEXT}"
USER_BUTTON_ONBOARDING_SKIP_TEXT = f"{EMOJI_SKIP} {TXT_SKIP}"
USER_BUTTON_ONBOARDING_FINISH_TEXT = f"{EMOJI_FINISH} {TXT_OPEN_MENU}"
USER_BACK_TEXT = f"{EMOJI_BACK} {TXT_BACK}"
USER_HOME_TEXT = f"{EMOJI_HOME} {TXT_HOME}"
PRODUCT_BUTTON_ICON = EMOJI_PRODUCT

TARIFF_ICONS = (EMOJI_BUY, EMOJI_ROCKET, EMOJI_STARS, EMOJI_FIRE, EMOJI_TARGET)


def _safe_button_text(text: str | None, fallback: str) -> str:
    sanitized = safe_ui_text(text, fallback)
    if sanitized != (text or "").strip():
        logger.warning("Detected broken UI text. Using fallback label instead.")
    return sanitized


def _safe_tariff_name(tariff: Tariff) -> str:
    return _safe_button_text(tariff.name, f"{TXT_TARIFF} #{tariff.id}")


def _safe_channel_title(subscription: Subscription) -> str:
    return _safe_button_text(
        subscription.channel.title,
        f"{TXT_CHANNEL} #{subscription.channel_id}",
    )


def _safe_tariff_badge(tariff: Tariff) -> str | None:
    badge = (getattr(tariff, "badge", None) or "").strip()
    if not badge:
        return None
    return _safe_button_text(badge, "") or None


def _safe_tariff_icon(index: int) -> str:
    return TARIFF_ICONS[index % len(TARIFF_ICONS)]


def _product_button_label(product: ProductCatalogEntry, *, mode: Literal["buy", "browse"]) -> str:
    title = _safe_button_text(
        product.channel_title,
        f"{TXT_PRODUCT} #{product.channel_id}",
    )
    featured_tariff_id = getattr(product, "featured_tariff_id", None)
    default_tariff_id = getattr(product, "default_tariff_id", None)
    bundle_names = tuple(getattr(product, "bundle_names", ()) or ())
    markers: list[str] = []
    if featured_tariff_id is not None:
        markers.append(EMOJI_FIRE)
    if default_tariff_id is not None:
        markers.append(EMOJI_TARGET)
    if bundle_names:
        markers.append(EMOJI_TARIFFS)
    marker_suffix = f" {' '.join(markers)}" if markers else ""
    if mode == "buy":
        return f"{PRODUCT_BUTTON_ICON} {title}{marker_suffix} \u2014 {product.price_range_label}"
    tariff_label = TXT_RATE if product.tariff_count == 1 else TXT_RATES_2_4
    if product.tariff_count >= 5:
        tariff_label = TXT_RATES_5
    return f"{PRODUCT_BUTTON_ICON} {title}{marker_suffix} \u2014 {product.tariff_count} {tariff_label}"


def _tariff_button_text(
    tariff: Tariff,
    *,
    mode: Literal["buy", "browse"],
    index: int,
    baseline_tariff: Tariff,
) -> str:
    title = _safe_tariff_name(tariff)
    badge = _safe_tariff_badge(tariff)
    prefix = f"[{badge}] " if badge else ""
    if getattr(tariff, "is_lifetime", False):
        duration_label = TXT_FOREVER
    else:
        duration_label = f"{tariff.duration_days} {TXT_DAYS}"
    if getattr(tariff, "is_trial", False) and duration_label != TXT_FOREVER:
        duration_label += f" {TXT_TRIAL}"
    icon = _safe_tariff_icon(index)
    details = build_offer_details(tariff, baseline_tariff=baseline_tariff)
    markers: list[str] = []
    if details.is_featured:
        markers.append(EMOJI_FIRE)
    if details.is_default_offer:
        markers.append(EMOJI_TARGET)
    marker_prefix = f"{' '.join(markers)} " if markers else ""
    if mode == "browse":
        return (
            f"{icon} {marker_prefix}{prefix}{title} \u2014 {duration_label} / "
            f"{tariff.price_stars}{EMOJI_STARS}"
        )
    return (
        f"{icon} {marker_prefix}{TXT_BUY_PREFIX}: {prefix}{title} \u2014 "
        f"{tariff.price_stars}{EMOJI_STARS}"
    )


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
        builder.adjust(2, 2, 1, 1)
    else:
        builder.adjust(2, 2, 1)
    return builder.as_markup()


def user_onboarding_keyboard(*, is_last: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_last:
        builder.button(text=USER_BUTTON_BUY_TEXT, callback_data="menu:user:buy")
        builder.button(
            text=USER_BUTTON_ONBOARDING_FINISH_TEXT,
            callback_data="menu:user:onboarding:finish",
        )
        builder.button(
            text=USER_BUTTON_ONBOARDING_SKIP_TEXT,
            callback_data="menu:user:onboarding:skip",
        )
        builder.adjust(1, 2)
    else:
        builder.button(
            text=USER_BUTTON_ONBOARDING_NEXT_TEXT,
            callback_data="menu:user:onboarding:next",
        )
        builder.button(
            text=USER_BUTTON_ONBOARDING_SKIP_TEXT,
            callback_data="menu:user:onboarding:skip",
        )
        builder.adjust(2)
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
        builder.button(
            text=f"{EMOJI_BUY} {TXT_EXTEND_ACCESS}",
            callback_data="menu:user:buy",
        )
        builder.button(text=USER_BUTTON_HISTORY_TEXT, callback_data="menu:user:payment-history")
        builder.button(text=USER_BUTTON_REFERRALS_TEXT, callback_data="menu:user:referrals")
        builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
        builder.adjust(2, 2, 1)
    else:
        builder.button(text=USER_BUTTON_BUY_TEXT, callback_data="menu:user:buy")
        builder.button(text=USER_BUTTON_HISTORY_TEXT, callback_data="menu:user:payment-history")
        builder.button(text=USER_BUTTON_REFERRALS_TEXT, callback_data="menu:user:referrals")
        builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
        builder.adjust(2, 1, 1)
    return builder.as_markup()


def user_payment_history_keyboard() -> InlineKeyboardMarkup:
    return build_navigation_keyboard(
        include_back=True,
        include_home=True,
        back_callback="menu:user:profile",
        home_callback="menu:user:home",
        back_text=USER_BACK_TEXT,
        home_text=USER_HOME_TEXT,
    )


def user_subscription_keyboard(subscriptions: Sequence[Subscription]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for subscription in subscriptions:
        title = _safe_channel_title(subscription)
        short_title = title if len(title) <= 28 else f"{title[:25]}..."
        builder.button(
            text=f"{EMOJI_LINK} {short_title}",
            callback_data=f"menu:user:invite:{subscription.id}",
        )
    builder.button(text=USER_BACK_TEXT, callback_data="menu:user:profile")
    builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()


def user_product_picker_keyboard(
    products: Sequence[ProductCatalogEntry],
    *,
    mode: Literal["buy", "browse"] = "buy",
    back_callback: str | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in products:
        callback_prefix = (
            "menu:user:buy:product"
            if mode == "buy"
            else "menu:user:tariffs:product"
        )
        builder.button(
            text=_product_button_label(product, mode=mode),
            callback_data=f"{callback_prefix}:{product.channel_id}",
        )
    if back_callback is not None:
        builder.button(text=USER_BACK_TEXT, callback_data=back_callback)
    builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()


def user_tariffs_keyboard(
    tariffs: Sequence[Tariff],
    *,
    mode: Literal["buy", "browse"] = "buy",
    back_callback: str | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not tariffs:
        refresh_callback = "menu:user:buy" if mode == "buy" else "menu:user:tariffs"
        builder.button(text=USER_BUTTON_REFRESH_TEXT, callback_data=refresh_callback)
        if back_callback is not None:
            builder.button(text=USER_BACK_TEXT, callback_data=back_callback)
        builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
        builder.adjust(1)
        return builder.as_markup()

    baseline_tariff = pick_default_tariff(tariffs) or tariffs[0]
    for index, tariff in enumerate(tariffs):
        text = _tariff_button_text(
            tariff,
            mode=mode,
            index=index,
            baseline_tariff=baseline_tariff,
        )
        callback_data = (
            f"menu:user:tariff:{tariff.id}"
            if mode == "browse"
            else f"menu:user:buy:stars:{tariff.id}"
        )
        builder.button(text=text, callback_data=callback_data)
    if back_callback is not None:
        builder.button(text=USER_BACK_TEXT, callback_data=back_callback)
    builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()

def user_tariff_detail_keyboard(
    tariff_id: int,
    *,
    include_crypto: bool = False,
    back_callback: str = "menu:user:tariffs",
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
    builder.button(text=USER_BACK_TEXT, callback_data=back_callback)
    builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()


def user_crypto_invoice_keyboard(
    invoice_url: str | None,
    *,
    back_callback: str = "menu:user:tariffs",
) -> InlineKeyboardMarkup | None:
    if not invoice_url:
        return None
    builder = InlineKeyboardBuilder()
    builder.button(text=USER_BUTTON_OPEN_CRYPTO_TEXT, url=invoice_url)
    builder.button(text=USER_BACK_TEXT, callback_data=back_callback)
    builder.button(text=USER_HOME_TEXT, callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()