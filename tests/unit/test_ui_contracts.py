from __future__ import annotations

from types import SimpleNamespace

from app.bot.keyboards.user import (
    user_main_menu_keyboard,
    user_product_picker_keyboard,
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
BACK = "\u2b05\ufe0f"

TXT_BUY_ACCESS = "\u041a\u0443\u043f\u0438\u0442\u044c \u0434\u043e\u0441\u0442\u0443\u043f"
TXT_TARIFFS = "\u0422\u0430\u0440\u0438\u0444\u044b"
TXT_PROFILE = "\u041c\u043e\u0439 \u043f\u0440\u043e\u0444\u0438\u043b\u044c"
TXT_LINK = "\u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0441\u0441\u044b\u043b\u043a\u0443"
TXT_HELP = "\u041f\u043e\u043c\u043e\u0449\u044c"
TXT_ADMIN = "\u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c"
TXT_BUY_PREFIX = "\u041a\u0443\u043f\u0438\u0442\u044c"
TXT_MAIN = "\u041e\u0441\u043d\u043e\u0432\u043d\u043e\u0439 \u043a\u0430\u043d\u0430\u043b"
TXT_VIP = "VIP-\u0447\u0430\u0442"
TXT_BACK = "\u041d\u0430\u0437\u0430\u0434"
TXT_ONE_TARIFF = "\u0442\u0430\u0440\u0438\u0444"


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
        (f"{DIAMOND} {TXT_BUY_PREFIX}: VIP 30 — 299\u2b50", "menu:user:buy:stars:7")
    ]

    assert _row_payload(markup)[0] == expected


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
        (f"{DIAMOND} VIP 90 — 90 \u0434\u043d. / 799\u2b50", "menu:user:tariff:9")
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
            price_range_label="\u043e\u0442 150\u2b50",
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
            price_range_label="700\u2b50",
            featured_tariff_id=None,
            default_tariff_id=None,
            bundle_names=(),
        ),
    ]

    buy_markup = user_product_picker_keyboard(products, mode="buy")
    browse_markup = user_product_picker_keyboard(products, mode="browse")
    expected_buy = [
        (f"{PRODUCT} {TXT_MAIN} — \u043e\u0442 150\u2b50", "menu:user:buy:product:10")
    ]
    expected_browse = [
        (f"{PRODUCT} {TXT_VIP} — 1 {TXT_ONE_TARIFF}", "menu:user:tariffs:product:20")
    ]

    assert _row_payload(buy_markup)[0] == expected_buy
    assert _row_payload(browse_markup)[1] == expected_browse


def test_tariff_detail_keyboard_preserves_custom_back_callback() -> None:
    markup = user_tariff_detail_keyboard(
        11,
        back_callback="menu:user:tariffs:product:5",
    )
    expected = [(f"{BACK} {TXT_BACK}", "menu:user:tariffs:product:5")]

    assert _row_payload(markup)[1] == expected