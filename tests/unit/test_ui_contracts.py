from __future__ import annotations

from types import SimpleNamespace

from app.bot.keyboards.user import (
    user_main_menu_keyboard,
    user_product_picker_keyboard,
    user_profile_keyboard,
    user_tariff_detail_keyboard,
    user_tariffs_keyboard,
)

DIAMOND = "\U0001f48e"
BOX = "\U0001f4e6"
PROFILE = "\U0001f464"
LINK = "\U0001f517"
HELP = "\u2753"
ADMIN = "\U0001f6e0"
PRODUCT = "\U0001f4c1"
FIRE = "\U0001f525"
BACK = "\u2b05\ufe0f"

TXT_BUY_ACCESS = "Купить доступ"
TXT_TARIFFS = "Тарифы"
TXT_PROFILE = "Мой профиль"
TXT_LINK = "Получить ссылку"
TXT_HELP = "Помощь"
TXT_ADMIN = "Админ-панель"
TXT_BUY_PREFIX = "Купить"
TXT_MAIN = "Основной канал"
TXT_VIP = "VIP-чат"
TXT_BACK = "Назад"
TXT_ONE_TARIFF = "тариф"
TXT_QUICK_START = "Быстрый старт"
TXT_EXTEND = "Продлить доступ"


def _row_payload(markup) -> list[list[tuple[str, str | None]]]:
    rows: list[list[tuple[str, str | None]]] = []
    for row in markup.inline_keyboard:
        rows.append([(button.text, button.callback_data) for button in row])
    return rows


def test_user_main_menu_contract_for_regular_user() -> None:
    expected = [
        [
            (f"{DIAMOND} {TXT_BUY_ACCESS}", "menu:user:buy"),
            (f"{BOX} {TXT_TARIFFS}", "menu:user:tariffs"),
        ],
        [
            (f"{PROFILE} {TXT_PROFILE}", "menu:user:profile"),
            (f"{LINK} {TXT_LINK}", "menu:user:link"),
        ],
        [(f"{HELP} {TXT_HELP}", "menu:user:help")],
    ]

    assert _row_payload(user_main_menu_keyboard()) == expected


def test_user_main_menu_contract_for_admin() -> None:
    expected = [
        [
            (f"{DIAMOND} {TXT_BUY_ACCESS}", "menu:user:buy"),
            (f"{BOX} {TXT_TARIFFS}", "menu:user:tariffs"),
        ],
        [
            (f"{PROFILE} {TXT_PROFILE}", "menu:user:profile"),
            (f"{LINK} {TXT_LINK}", "menu:user:link"),
        ],
        [(f"{HELP} {TXT_HELP}", "menu:user:help")],
        [(f"{ADMIN} {TXT_ADMIN}", "menu:admin:home")],
    ]

    assert _row_payload(user_main_menu_keyboard(is_admin=True)) == expected


def test_buy_keyboard_preserves_direct_purchase_callbacks() -> None:
    tariff = SimpleNamespace(
        id=7,
        name="VIP 30",
        duration_days=30,
        price_stars=299,
        is_lifetime=False,
        is_trial=False,
        badge=None,
        is_featured=False,
        is_default_offer=False,
        offer_copy=None,
        offer_group=None,
    )
    markup = user_tariffs_keyboard([tariff], mode="buy")
    expected = [
        (f"{DIAMOND} {TXT_BUY_PREFIX}: VIP 30 — 299⭐", "menu:user:buy:stars:7")
    ]

    assert _row_payload(markup)[0] == expected


def test_buy_keyboard_promotes_featured_quick_start_before_other_tariffs() -> None:
    featured = SimpleNamespace(
        id=9,
        name="VIP 90",
        duration_days=90,
        price_stars=799,
        is_lifetime=False,
        is_trial=False,
        badge="HIT",
        is_featured=True,
        is_default_offer=False,
        offer_copy=None,
        offer_group="VIP",
    )
    standard = SimpleNamespace(
        id=8,
        name="VIP 30",
        duration_days=30,
        price_stars=299,
        is_lifetime=False,
        is_trial=False,
        badge=None,
        is_featured=False,
        is_default_offer=True,
        offer_copy=None,
        offer_group="Base",
    )

    markup = user_tariffs_keyboard([standard, featured], mode="buy")
    rows = _row_payload(markup)

    assert rows[0] == [
        (f"{FIRE} {TXT_QUICK_START}: [HIT] VIP 90 — 799⭐", "menu:user:buy:stars:9")
    ]
    assert rows[1] == [
        (f"{DIAMOND} 🎯 {TXT_BUY_PREFIX}: VIP 30 — 299⭐", "menu:user:buy:stars:8")
    ]


def test_browse_keyboard_uses_tariff_detail_callback() -> None:
    tariff = SimpleNamespace(
        id=9,
        name="VIP 90",
        duration_days=90,
        price_stars=799,
        is_lifetime=False,
        is_trial=False,
        badge=None,
        is_featured=False,
        is_default_offer=False,
        offer_copy=None,
        offer_group=None,
    )
    markup = user_tariffs_keyboard([tariff], mode="browse")
    expected = [
        (f"{DIAMOND} VIP 90 — 90 дн. / 799⭐", "menu:user:tariff:9")
    ]

    assert _row_payload(markup)[0] == expected


def test_product_picker_keyboard_uses_product_callbacks() -> None:
    products = [
        SimpleNamespace(
            channel_id=10,
            channel_title=TXT_MAIN,
            tariff_count=2,
            price_from_stars=150,
            price_to_stars=250,
            price_range_label="от 150⭐",
            featured_tariff_id=None,
            default_tariff_id=None,
            bundle_names=(),
        ),
        SimpleNamespace(
            channel_id=20,
            channel_title=TXT_VIP,
            tariff_count=1,
            price_from_stars=700,
            price_to_stars=700,
            price_range_label="700⭐",
            featured_tariff_id=None,
            default_tariff_id=None,
            bundle_names=(),
        ),
    ]

    buy_markup = user_product_picker_keyboard(products, mode="buy")
    browse_markup = user_product_picker_keyboard(products, mode="browse")
    expected_buy = [
        (f"{PRODUCT} {TXT_MAIN} — от 150⭐", "menu:user:buy:product:10")
    ]
    expected_browse = [
        (f"{PRODUCT} {TXT_VIP} — 1 {TXT_ONE_TARIFF}", "menu:user:tariffs:product:20")
    ]

    assert _row_payload(buy_markup)[0] == expected_buy
    assert _row_payload(browse_markup)[1] == expected_browse


def test_user_profile_keyboard_uses_custom_buy_callback() -> None:
    inactive_markup = user_profile_keyboard(
        has_active_subscription=False,
        buy_callback="menu:user:buy:product:12",
    )
    active_markup = user_profile_keyboard(
        has_active_subscription=True,
        buy_callback="menu:user:buy:product:12",
    )

    assert _row_payload(inactive_markup)[0][0] == (
        f"{DIAMOND} {TXT_BUY_ACCESS}",
        "menu:user:buy:product:12",
    )
    assert _row_payload(active_markup)[0][1] == (
        f"{DIAMOND} {TXT_EXTEND}",
        "menu:user:buy:product:12",
    )


def test_tariff_detail_keyboard_preserves_custom_back_callback() -> None:
    markup = user_tariff_detail_keyboard(
        11,
        back_callback="menu:user:tariffs:product:5",
    )
    expected = [(f"{BACK} {TXT_BACK}", "menu:user:tariffs:product:5")]

    assert _row_payload(markup)[1] == expected