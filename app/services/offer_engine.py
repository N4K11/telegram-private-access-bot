from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.db.models import Tariff
from app.services.multi_channel_access_service import ProductAccessEntry
from app.services.product_service import (
    ProductCatalogEntry,
    RecommendedTariffOffer,
    build_catalog_recommendations,
    build_offer_details,
    normalize_offer_group,
    pick_default_tariff,
    recommended_tariff_for_entry,
)
from app.services.tariffs import is_limited_offer_active
from app.utils.encoding import safe_ui_text

TXT_PRODUCT = "Продукт"
TXT_TARIFF = "Тариф"


@dataclass(slots=True)
class ProductOfferLane:
    channel_id: int
    channel_title: str
    has_active_access: bool
    hero_offer: RecommendedTariffOffer | None
    limited_offer: RecommendedTariffOffer | None
    upgrade_offer: RecommendedTariffOffer | None
    bundle_offer: RecommendedTariffOffer | None


@dataclass(slots=True)
class OfferInventorySnapshot:
    total_products: int
    featured_products: int
    default_products: int
    bundle_group_count: int
    upgrade_ready_products: int
    cross_sell_product_count: int
    limited_offer_count: int
    hero_offers: tuple[RecommendedTariffOffer, ...]


@dataclass(slots=True)
class OfferEngineSnapshot:
    hero_offer: RecommendedTariffOffer | None
    renewal_offer: RecommendedTariffOffer | None
    upgrade_offers: tuple[RecommendedTariffOffer, ...]
    cross_sell_offers: tuple[RecommendedTariffOffer, ...]
    bundle_offers: tuple[RecommendedTariffOffer, ...]
    limited_offers: tuple[RecommendedTariffOffer, ...]
    product_lanes: tuple[ProductOfferLane, ...]
    inventory: OfferInventorySnapshot


def build_offer_engine_snapshot(
    catalog: Sequence[ProductCatalogEntry],
    *,
    active_products: Sequence[ProductAccessEntry] = (),
    primary_channel_id: int | None = None,
    cross_sell_limit: int = 3,
    upgrade_limit: int = 3,
    bundle_limit: int = 3,
    hero_limit: int = 3,
    limited_limit: int = 3,
    now: datetime | None = None,
) -> OfferEngineSnapshot:
    recommendations = build_catalog_recommendations(
        catalog,
        active_channel_ids=[item.channel_id for item in active_products],
        primary_channel_id=primary_channel_id,
        cross_sell_limit=cross_sell_limit,
    )
    active_map = {int(item.channel_id): item for item in active_products}

    lanes: list[ProductOfferLane] = []
    upgrade_offers: list[RecommendedTariffOffer] = []
    bundle_offers: list[RecommendedTariffOffer] = []
    limited_offers: list[RecommendedTariffOffer] = []

    for product in catalog:
        active_product = active_map.get(product.channel_id)
        hero_offer = _build_product_hero_offer(
            product,
            is_active=active_product is not None,
            is_primary=primary_channel_id == product.channel_id,
        )
        limited_offer = _build_product_limited_offer(product, access=active_product, now=now)
        upgrade_offer = _build_product_upgrade_offer(product, active_product)
        bundle_offer = _build_product_bundle_offer(product)
        lanes.append(
            ProductOfferLane(
                channel_id=product.channel_id,
                channel_title=product.channel_title,
                has_active_access=active_product is not None,
                hero_offer=hero_offer,
                limited_offer=limited_offer,
                upgrade_offer=upgrade_offer,
                bundle_offer=bundle_offer,
            )
        )
        if limited_offer is not None:
            limited_offers.append(limited_offer)
        if upgrade_offer is not None:
            upgrade_offers.append(upgrade_offer)
        if bundle_offer is not None:
            bundle_offers.append(bundle_offer)

    deduped_bundle_offers = _dedupe_offers_by_group(bundle_offers)
    deduped_limited_offers = _dedupe_offers_by_tariff(limited_offers)
    inventory = OfferInventorySnapshot(
        total_products=len(catalog),
        featured_products=sum(1 for item in catalog if item.featured_tariff_id is not None),
        default_products=sum(1 for item in catalog if item.default_tariff_id is not None),
        bundle_group_count=len({name for item in catalog for name in item.bundle_names}),
        upgrade_ready_products=len(upgrade_offers),
        cross_sell_product_count=len(recommendations.cross_sell_offers),
        limited_offer_count=len(deduped_limited_offers),
        hero_offers=tuple(
            lane.hero_offer for lane in lanes if lane.hero_offer is not None
        )[: max(int(hero_limit), 0)],
    )
    return OfferEngineSnapshot(
        hero_offer=recommendations.primary_offer,
        renewal_offer=recommendations.renewal_offer,
        upgrade_offers=tuple(upgrade_offers[: max(int(upgrade_limit), 0)]),
        cross_sell_offers=recommendations.cross_sell_offers,
        bundle_offers=tuple(deduped_bundle_offers[: max(int(bundle_limit), 0)]),
        limited_offers=tuple(deduped_limited_offers[: max(int(limited_limit), 0)]),
        product_lanes=tuple(lanes),
        inventory=inventory,
    )


def get_product_offer_lane(
    snapshot: OfferEngineSnapshot | None,
    channel_id: int,
) -> ProductOfferLane | None:
    if snapshot is None:
        return None
    for lane in snapshot.product_lanes:
        if lane.channel_id == channel_id:
            return lane
    return None


def _build_product_hero_offer(
    product: ProductCatalogEntry,
    *,
    is_active: bool,
    is_primary: bool,
) -> RecommendedTariffOffer | None:
    tariff = recommended_tariff_for_entry(product)
    if tariff is None:
        return None
    if is_active:
        reason_code = "hero_renew"
        reason_label = "Лучший тариф для продления"
    elif is_primary:
        reason_code = "hero_return"
        reason_label = "Вернуться к основному продукту"
    else:
        reason_code = "hero_product"
        reason_label = "Лучший тариф продукта"
    baseline_tariff = pick_default_tariff(product.tariffs) or tariff
    return _offer_from_tariff(
        product,
        tariff,
        baseline_tariff=baseline_tariff,
        reason_code=reason_code,
        reason_label=reason_label,
    )


def _build_product_limited_offer(
    product: ProductCatalogEntry,
    *,
    access: ProductAccessEntry | None,
    now: datetime | None = None,
) -> RecommendedTariffOffer | None:
    candidates = [
        tariff for tariff in product.tariffs if is_limited_offer_active(tariff, now=now)
    ]
    if not candidates:
        return None
    selected = max(candidates, key=lambda item: _limited_offer_score(item, now=now))
    baseline_tariff = pick_default_tariff(product.tariffs) or selected
    if access is not None:
        reason_code = "limited_renew"
        reason_label = "Ограниченный оффер для продления"
    else:
        reason_code = "limited_product"
        reason_label = "Ограниченное предложение"
    return _offer_from_tariff(
        product,
        selected,
        baseline_tariff=baseline_tariff,
        reason_code=reason_code,
        reason_label=reason_label,
        now=now,
    )


def _build_product_upgrade_offer(
    product: ProductCatalogEntry,
    access: ProductAccessEntry | None,
) -> RecommendedTariffOffer | None:
    if access is None:
        return None
    current_tariff = next(
        (tariff for tariff in product.tariffs if tariff.id == access.primary_tariff_id),
        None,
    )
    if current_tariff is None:
        return None
    candidates = [
        tariff
        for tariff in product.tariffs
        if int(tariff.id) not in access.tariff_ids
        and _is_upgrade_candidate(tariff, current_tariff)
    ]
    if not candidates:
        return None
    selected = max(candidates, key=lambda item: _upgrade_score(item, current_tariff))
    return _offer_from_tariff(
        product,
        selected,
        baseline_tariff=current_tariff,
        reason_code="upgrade",
        reason_label="Перейти на расширенный тариф",
    )


def _build_product_bundle_offer(product: ProductCatalogEntry) -> RecommendedTariffOffer | None:
    if not product.bundle_names:
        return None
    preferred_group = None
    recommended_tariff = recommended_tariff_for_entry(product)
    if recommended_tariff is not None:
        preferred_group = normalize_offer_group(getattr(recommended_tariff, "offer_group", None))
    bundle_group = preferred_group or product.bundle_names[0]
    bundle_tariffs = [
        tariff
        for tariff in product.tariffs
        if normalize_offer_group(getattr(tariff, "offer_group", None)) == bundle_group
    ]
    if not bundle_tariffs:
        return None
    selected = max(bundle_tariffs, key=_bundle_score)
    baseline_tariff = pick_default_tariff(product.tariffs) or selected
    return _offer_from_tariff(
        product,
        selected,
        baseline_tariff=baseline_tariff,
        reason_code="bundle",
        reason_label=f"Пакет {bundle_group}",
    )


def _offer_from_tariff(
    product: ProductCatalogEntry,
    tariff: Tariff,
    *,
    baseline_tariff: Tariff,
    reason_code: str,
    reason_label: str,
    now: datetime | None = None,
) -> RecommendedTariffOffer:
    details = build_offer_details(tariff, baseline_tariff=baseline_tariff, now=now)
    return RecommendedTariffOffer(
        channel_id=product.channel_id,
        channel_title=product.channel_title,
        tariff_id=int(tariff.id),
        tariff_name=safe_ui_text(
            getattr(tariff, "name", None),
            f"{TXT_TARIFF} #{getattr(tariff, 'id', '?')}",
        ),
        price_stars=int(getattr(tariff, "price_stars", 0) or 0),
        price_per_day_label=details.price_per_day_label,
        savings_label=details.savings_label,
        offer_copy=details.offer_copy,
        offer_group=details.offer_group,
        is_featured=details.is_featured,
        is_default_offer=details.is_default_offer,
        is_limited_time=details.is_limited_time,
        offer_expires_at=details.offer_expires_at,
        reason_code=reason_code,
        reason_label=reason_label,
    )


def _is_upgrade_candidate(candidate: Tariff, current: Tariff) -> bool:
    if bool(getattr(candidate, "is_trial", False)):
        return False
    if bool(getattr(current, "is_lifetime", False)):
        return False
    if bool(getattr(candidate, "is_lifetime", False)) and not bool(
        getattr(current, "is_lifetime", False)
    ):
        return True
    if int(getattr(candidate, "price_stars", 0) or 0) > int(
        getattr(current, "price_stars", 0) or 0
    ):
        return True
    if int(getattr(candidate, "duration_days", 0) or 0) > int(
        getattr(current, "duration_days", 0) or 0
    ):
        return True
    candidate_details = build_offer_details(candidate, baseline_tariff=current)
    return candidate_details.savings_label is not None


def _upgrade_score(candidate: Tariff, current: Tariff) -> tuple[int, int, int, int, int, int]:
    details = build_offer_details(candidate, baseline_tariff=current)
    return (
        int(bool(getattr(candidate, "is_featured", False))),
        int(bool(getattr(candidate, "is_lifetime", False))),
        (
            int(getattr(candidate, "duration_days", 0) or 0)
            - int(getattr(current, "duration_days", 0) or 0)
        ),
        (
            int(getattr(candidate, "price_stars", 0) or 0)
            - int(getattr(current, "price_stars", 0) or 0)
        ),
        int(details.savings_label is not None),
        -int(getattr(candidate, "sort_order", 100) or 100),
    )


def _limited_offer_score(
    tariff: Tariff,
    *,
    now: datetime | None = None,
) -> tuple[int, int, int, int, int, int]:
    offer_expires_at = getattr(tariff, "offer_expires_at", None)
    expires_rank = 0
    if offer_expires_at is not None and hasattr(offer_expires_at, "timestamp"):
        expires_rank = -int(offer_expires_at.timestamp())
    details = build_offer_details(tariff, baseline_tariff=tariff, now=now)
    return (
        int(bool(getattr(tariff, "is_featured", False))),
        int(bool(getattr(tariff, "is_default_offer", False))),
        int(details.savings_label is not None),
        expires_rank,
        int(getattr(tariff, "duration_days", 0) or 0),
        -int(getattr(tariff, "sort_order", 100) or 100),
    )


def _bundle_score(tariff: Tariff) -> tuple[int, int, int, int]:
    return (
        int(bool(getattr(tariff, "is_featured", False))),
        int(bool(getattr(tariff, "is_default_offer", False))),
        int(getattr(tariff, "duration_days", 0) or 0),
        int(getattr(tariff, "price_stars", 0) or 0),
    )


def _dedupe_offers_by_group(
    offers: Sequence[RecommendedTariffOffer],
) -> list[RecommendedTariffOffer]:
    grouped: OrderedDict[str, RecommendedTariffOffer] = OrderedDict()
    fallback: list[RecommendedTariffOffer] = []
    for offer in offers:
        group_name = normalize_offer_group(offer.offer_group)
        if group_name is None:
            fallback.append(offer)
            continue
        grouped.setdefault(group_name, offer)
    return list(grouped.values()) + fallback


def _dedupe_offers_by_tariff(
    offers: Sequence[RecommendedTariffOffer],
) -> list[RecommendedTariffOffer]:
    grouped: OrderedDict[int, RecommendedTariffOffer] = OrderedDict()
    for offer in offers:
        grouped.setdefault(int(offer.tariff_id), offer)
    return list(grouped.values())
