from __future__ import annotations

from types import SimpleNamespace

from app.bot.keyboards.user import user_main_menu_keyboard, user_tariffs_keyboard


def _row_payload(markup) -> list[list[tuple[str, str | None]]]:
    rows: list[list[tuple[str, str | None]]] = []
    for row in markup.inline_keyboard:
        rows.append([(button.text, button.callback_data) for button in row])
    return rows


def test_user_main_menu_contract_for_regular_user() -> None:
    assert _row_payload(user_main_menu_keyboard()) == [
        [("💎 Купить доступ", "menu:user:buy"), ("📦 Тарифы", "menu:user:tariffs")],
        [("👤 Мой профиль", "menu:user:profile"), ("🔗 Получить ссылку", "menu:user:link")],
        [("❓ Помощь", "menu:user:help")],
    ]


def test_user_main_menu_contract_for_admin() -> None:
    assert _row_payload(user_main_menu_keyboard(is_admin=True)) == [
        [("💎 Купить доступ", "menu:user:buy"), ("📦 Тарифы", "menu:user:tariffs")],
        [("👤 Мой профиль", "menu:user:profile"), ("🔗 Получить ссылку", "menu:user:link")],
        [("❓ Помощь", "menu:user:help")],
        [("🛠 Админ-панель", "menu:admin:home")],
    ]


def test_buy_keyboard_preserves_direct_purchase_callbacks() -> None:
    tariff = SimpleNamespace(id=7, name="VIP 30", duration_days=30, price_stars=299)
    markup = user_tariffs_keyboard([tariff], mode="buy")

    assert _row_payload(markup)[0] == [("💎 Купить: VIP 30 — 299⭐", "menu:user:buy:stars:7")]


def test_browse_keyboard_uses_tariff_detail_callback() -> None:
    tariff = SimpleNamespace(id=9, name="VIP 90", duration_days=90, price_stars=799)
    markup = user_tariffs_keyboard([tariff], mode="browse")

    assert _row_payload(markup)[0] == [("💎 VIP 90 — 90 дн. / 799⭐", "menu:user:tariff:9")]
