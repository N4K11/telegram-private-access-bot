from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.multi_channel_access_service import ProductAccessEntry
from app.services.offer_engine import build_offer_engine_snapshot
from app.services.product_service import build_product_catalog

MAIN_TITLE = "Private channel"
VIP_TITLE = "VIP chat"


def test_offer_engine_builds_hero_upgrade_bundle_and_inventory() -> None:
    catalog = build_product_catalog(
        [
            SimpleNamespace(
                id=1,
                channel_id=10,
                name="Main 30",
                price_stars=250,
                duration_days=30,
                sort_order=10,
                is_trial=False,
                is_lifetime=False,
                is_default_offer=True,
                is_featured=False,
                offer_copy="Base access",
                offer_group="Base",
                offer_expires_at=None,
                channel=SimpleNamespace(title=MAIN_TITLE, username="main"),
            ),
            SimpleNamespace(
                id=2,
                channel_id=10,
                name="Main 90",
                price_stars=600,
                duration_days=90,
                sort_order=20,
                is_trial=False,
                is_lifetime=False,
                is_default_offer=False,
                is_featured=False,
                offer_copy="Longer access",
                offer_group="Base",
                offer_expires_at=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
                channel=SimpleNamespace(title=MAIN_TITLE, username="main"),
            ),
            SimpleNamespace(
                id=3,
                channel_id=20,
                name="VIP Club",
                price_stars=900,
                duration_days=90,
                sort_order=30,
                is_trial=False,
                is_lifetime=False,
                is_default_offer=False,
                is_featured=True,
                offer_copy="Premium access",
                offer_group="VIP",
                offer_expires_at=datetime(2026, 5, 10, 12, 0, tzinfo=UTC),
                channel=SimpleNamespace(title=VIP_TITLE, username="vip"),
            ),
        ]
    )
    active_products = [
        ProductAccessEntry(
            channel_id=10,
            channel_title=MAIN_TITLE,
            latest_expires_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
            subscription_count=1,
            tariff_names=("Main 30",),
            tariff_ids=(1,),
            primary_tariff_id=1,
            subscription_ids=(101,),
        )
    ]

    snapshot = build_offer_engine_snapshot(
        catalog,
        active_products=active_products,
        primary_channel_id=10,
    )

    assert snapshot.hero_offer is not None
    assert snapshot.hero_offer.channel_id == 10
    assert snapshot.renewal_offer is not None
    assert snapshot.upgrade_offers
    assert snapshot.upgrade_offers[0].tariff_id == 2
    assert snapshot.upgrade_offers[0].reason_code == "upgrade"
    assert snapshot.cross_sell_offers
    assert snapshot.cross_sell_offers[0].channel_id == 20
    assert snapshot.bundle_offers
    assert snapshot.bundle_offers[0].offer_group == "Base"
    assert snapshot.limited_offers
    assert {item.tariff_id for item in snapshot.limited_offers} == {2, 3}
    assert snapshot.product_lanes[0].limited_offer is not None
    assert snapshot.product_lanes[0].limited_offer.tariff_id == 2
    assert snapshot.inventory.total_products == 2
    assert snapshot.inventory.bundle_group_count == 2
    assert snapshot.inventory.limited_offer_count == 2
    assert snapshot.inventory.upgrade_ready_products == 1
