# ruff: noqa: E501
from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.navigation import build_navigation_keyboard
from app.db.models import Subscription, Tariff

USER_MENU_SUBSCRIPTION_TEXT = "\u041c\u043e\u044f \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0430"
USER_MENU_TARIFFS_TEXT = "\u0422\u0430\u0440\u0438\u0444\u044b"
USER_MENU_SUPPORT_TEXT = "\u041f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430"


def user_main_menu_keyboard() -> InlineKeyboardMarkup:
    return build_navigation_keyboard(
        (USER_MENU_SUBSCRIPTION_TEXT, "menu:user:subscription"),
        (USER_MENU_TARIFFS_TEXT, "menu:user:tariffs"),
        (USER_MENU_SUPPORT_TEXT, "menu:user:support"),
        include_home=False,
    )


def user_section_keyboard() -> InlineKeyboardMarkup:
    return build_navigation_keyboard(
        include_back=True,
        include_home=True,
        back_callback="menu:user:home",
        home_callback="menu:user:home",
    )


def user_subscription_keyboard(subscriptions: Sequence[Subscription]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for subscription in subscriptions:
        title = subscription.channel.title.strip() or f"РљР°РЅР°Р» #{subscription.channel_id}"
        short_title = title if len(title) <= 28 else f"{title[:25]}..."
        builder.button(
            text=f"РЎСЃС‹Р»РєР°: {short_title}",
            callback_data=f"menu:user:invite:{subscription.id}",
        )
    builder.button(text="РќР°Р·Р°Рґ", callback_data="menu:user:home")
    builder.button(text="Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ", callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()


def user_tariffs_keyboard(tariffs: Sequence[Tariff]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for tariff in tariffs:
        builder.button(
            text=f"рџ§ѕ {tariff.name} вЂў {tariff.price_stars} Stars",
            callback_data=f"menu:user:tariff:{tariff.id}",
        )
    builder.button(text="РќР°Р·Р°Рґ", callback_data="menu:user:home")
    builder.button(text="Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ", callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()


def user_tariff_detail_keyboard(
    tariff_id: int,
    *,
    include_crypto: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="в­ђ РћРїР»Р°С‚РёС‚СЊ Stars",
        callback_data=f"menu:user:buy:stars:{tariff_id}",
    )
    if include_crypto:
        builder.button(
            text="в‚ї Crypto Pay",
            callback_data=f"menu:user:buy:crypto:{tariff_id}",
        )
    builder.button(text="РќР°Р·Р°Рґ", callback_data="menu:user:tariffs")
    builder.button(text="Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ", callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()


def user_crypto_invoice_keyboard(invoice_url: str | None) -> InlineKeyboardMarkup | None:
    if not invoice_url:
        return None
    builder = InlineKeyboardBuilder()
    builder.button(text="Open Crypto Pay", url=invoice_url)
    builder.button(text="РќР°Р·Р°Рґ", callback_data="menu:user:tariffs")
    builder.button(text="Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ", callback_data="menu:user:home")
    builder.adjust(1)
    return builder.as_markup()