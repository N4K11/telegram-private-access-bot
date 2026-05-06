from __future__ import annotations

from types import SimpleNamespace

from app.services.product_service import (
    build_catalog_recommendations,
    build_offer_details,
    build_product_catalog,
    get_product_entry,
    is_multi_product_catalog,
    pick_default_tariff,
    pick_featured_tariff,
    recommended_tariff_for_entry,
    recommended_tariff_for_product,
)

MAIN_TITLE = "Основной канал"
VIP_TITLE = "VIP-чат"
FALLBACK_TITLE = "Продукт #77"


def test_build_product_catalog_groups_tariffs_by_channel() -> None:
    tariffs = [
        SimpleNamespace(
            id=1,
            channel_id=10,
            price_stars=150,
            channel=SimpleNamespace(title=MAIN_TITLE, username="main"),
        ),
        SimpleNamespace(
            id=2,
            channel_id=10,
            price_stars=250,
            channel=SimpleNamespace(title=MAIN_TITLE, username="main"),
        ),
        SimpleNamespace(
            id=3,
            channel_id=20,
            price_stars=500,
            channel=SimpleNamespace(title=VIP_TITLE, username="vip"),
        ),
    ]

    catalog = build_product_catalog(tariffs)

    assert len(catalog) == 2
    assert is_multi_product_catalog(catalog) is True
    assert catalog[0].channel_id == 10
    assert catalog[0].channel_title == MAIN_TITLE
    assert catalog[0].tariff_count == 2
    assert catalog[0].price_from_stars == 150
    assert catalog[0].price_to_stars == 250
    assert catalog[0].price_range_label == "от 150⭐"
    assert [tariff.id for tariff in catalog[0].tariffs] == [1, 2]

    vip = get_product_entry(catalog, 20)
    assert vip is not None
    assert vip.channel_title == VIP_TITLE
    assert vip.price_range_label == "500⭐"


def test_build_product_catalog_uses_safe_fallback_title() -> None:
    tariffs = [
        SimpleNamespace(
            id=7,
            channel_id=77,
            price_stars=99,
            channel=SimpleNamespace(title=None, username=None),
        )
    ]

    catalog = build_product_catalog(tariffs)

    assert len(catalog) == 1
    assert catalog[0].channel_title == FALLBACK_TITLE
    assert is_multi_product_catalog(catalog) is False


def test_featured_and_default_tariffs_are_detected() -> None:
    tariffs = [
        SimpleNamespace(
            id=1,
            channel_id=10,
            name="1 month",
            price_stars=100,
            duration_days=30,
            is_trial=False,
            is_lifetime=False,
            is_default_offer=True,
            is_featured=False,
            offer_copy="Стартовый оффер",
            offer_group="Base",
            channel=SimpleNamespace(title=MAIN_TITLE, username="main"),
        ),
        SimpleNamespace(
            id=2,
            channel_id=10,
            name="3 months",
            price_stars=240,
            duration_days=90,
            is_trial=False,
            is_lifetime=False,
            is_default_offer=False,
            is_featured=True,
            offer_copy="Самая выгодная цена",
            offer_group="Base",
            channel=SimpleNamespace(title=MAIN_TITLE, username="main"),
        ),
    ]

    featured = pick_featured_tariff(tariffs)
    default = pick_default_tariff(tariffs)
    offer = build_offer_details(tariffs[1], baseline_tariff=default)

    assert featured is tariffs[1]
    assert default is tariffs[0]
    assert offer.offer_copy == "Самая выгодная цена"
    assert offer.offer_group == "Base"
    assert offer.is_featured is True
    assert offer.is_default_offer is False
    assert offer.price_per_day_label.endswith("/день")
    assert offer.savings_label is not None


def test_build_product_catalog_exposes_offer_flags() -> None:
    tariffs = [
        SimpleNamespace(
            id=11,
            channel_id=10,
            price_stars=150,
            duration_days=30,
            sort_order=10,
            is_trial=False,
            is_featured=False,
            is_default_offer=True,
            offer_group="Base",
            channel=SimpleNamespace(title=MAIN_TITLE, username="main"),
        ),
        SimpleNamespace(
            id=12,
            channel_id=10,
            price_stars=390,
            duration_days=90,
            sort_order=20,
            is_trial=False,
            is_featured=True,
            is_default_offer=False,
            offer_group="Base",
            channel=SimpleNamespace(title=MAIN_TITLE, username="main"),
        ),
    ]

    catalog = build_product_catalog(tariffs)

    assert catalog[0].default_tariff_id == 11
    assert catalog[0].featured_tariff_id == 12
    assert catalog[0].recommended_tariff_id == 12
    assert catalog[0].bundle_names == ("Base",)


def test_recommended_tariff_prefers_featured_then_default() -> None:
    default = SimpleNamespace(
        id=21,
        channel_id=10,
        price_stars=199,
        duration_days=30,
        is_trial=False,
        is_default_offer=True,
        is_featured=False,
    )
    featured = SimpleNamespace(
        id=22,
        channel_id=10,
        price_stars=499,
        duration_days=90,
        is_trial=False,
        is_default_offer=False,
        is_featured=True,
    )
    entry = build_product_catalog(
        [
            SimpleNamespace(
                **default.__dict__,
                channel=SimpleNamespace(title=MAIN_TITLE, username="main"),
            ),
            SimpleNamespace(
                **featured.__dict__,
                channel=SimpleNamespace(title=MAIN_TITLE, username="main"),
            ),
        ]
    )[0]

    assert recommended_tariff_for_product([default, featured]) is featured
    assert recommended_tariff_for_entry(entry).id == 22


def test_build_catalog_recommendations_prefers_primary_renewal_and_cross_sell() -> None:
    tariffs = [
        SimpleNamespace(
            id=31,
            channel_id=10,
            name="Main 30",
            price_stars=250,
            duration_days=30,
            sort_order=10,
            is_trial=False,
            is_default_offer=True,
            is_featured=False,
            offer_copy="Базовый доступ",
            offer_group="Base",
            channel=SimpleNamespace(title=MAIN_TITLE, username="main"),
        ),
        SimpleNamespace(
            id=32,
            channel_id=20,
            name="VIP 90",
            price_stars=700,
            duration_days=90,
            sort_order=20,
            is_trial=False,
            is_default_offer=False,
            is_featured=True,
            offer_copy="Премиум доступ",
            offer_group="VIP",
            channel=SimpleNamespace(title=VIP_TITLE, username="vip"),
        ),
    ]

    catalog = build_product_catalog(tariffs)
    recommendations = build_catalog_recommendations(
        catalog,
        active_channel_ids=[10],
        primary_channel_id=10,
    )

    assert recommendations.primary_offer is not None
    assert recommendations.primary_offer.channel_id == 10
    assert recommendations.primary_offer.reason_code == "renew_current"
    assert recommendations.renewal_offer is not None
    assert recommendations.renewal_offer.channel_id == 10
    assert recommendations.cross_sell_offers
    assert recommendations.cross_sell_offers[0].channel_id == 20
    assert recommendations.cross_sell_offers[0].reason_code == "cross_sell"
