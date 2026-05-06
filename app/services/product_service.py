from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from app.db.models import Tariff
from app.services.tariffs import is_limited_offer_active
from app.utils.encoding import safe_ui_text

TXT_PRODUCT = "Продукт"
TXT_FROM = "от"
EMOJI_STARS = "⭐"
DAY_QUANT = Decimal("0.1")


@dataclass(slots=True)
class TariffOfferDetails:
    tariff_id: int
    price_per_day_label: str
    savings_label: str | None
    offer_copy: str | None
    offer_group: str | None
    is_featured: bool
    is_default_offer: bool
    is_limited_time: bool
    offer_expires_at: datetime | None


@dataclass(slots=True)
class ProductCatalogEntry:
    channel_id: int
    channel_title: str
    channel_username: str | None
    tariffs: list[Tariff]
    tariff_count: int
    price_from_stars: int
    price_to_stars: int
    featured_tariff_id: int | None
    default_tariff_id: int | None
    recommended_tariff_id: int | None
    bundle_names: tuple[str, ...]

    @property
    def price_range_label(self) -> str:
        if self.price_from_stars == self.price_to_stars:
            return f"{self.price_from_stars}{EMOJI_STARS}"
        return f"{TXT_FROM} {self.price_from_stars}{EMOJI_STARS}"


@dataclass(slots=True)
class RecommendedTariffOffer:
    channel_id: int
    channel_title: str
    tariff_id: int
    tariff_name: str
    price_stars: int
    price_per_day_label: str
    savings_label: str | None
    offer_copy: str | None
    offer_group: str | None
    is_featured: bool
    is_default_offer: bool
    is_limited_time: bool
    offer_expires_at: datetime | None
    reason_code: str
    reason_label: str


@dataclass(slots=True)
class CatalogRecommendations:
    primary_offer: RecommendedTariffOffer | None
    renewal_offer: RecommendedTariffOffer | None
    cross_sell_offers: tuple[RecommendedTariffOffer, ...]


def build_product_catalog(tariffs: Sequence[Tariff]) -> list[ProductCatalogEntry]:
    grouped: OrderedDict[int, list[Tariff]] = OrderedDict()
    for tariff in tariffs:
        grouped.setdefault(int(tariff.channel_id), []).append(tariff)

    catalog: list[ProductCatalogEntry] = []
    for channel_id, channel_tariffs in grouped.items():
        ordered_tariffs = sorted(
            channel_tariffs,
            key=lambda item: (
                int(getattr(item, "sort_order", 100)),
                int(getattr(item, "id", 0)),
            ),
        )
        first_tariff = ordered_tariffs[0]
        channel = getattr(first_tariff, "channel", None)
        channel_title = safe_ui_text(
            getattr(channel, "title", None),
            f"{TXT_PRODUCT} #{channel_id}",
        )
        channel_username = getattr(channel, "username", None)
        prices = [int(tariff.price_stars) for tariff in ordered_tariffs]
        featured_tariff = pick_featured_tariff(ordered_tariffs)
        default_tariff = pick_default_tariff(ordered_tariffs)
        recommended_tariff = recommended_tariff_for_product(ordered_tariffs)
        bundle_names = tuple(
            dict.fromkeys(
                group_name
                for group_name in (
                    normalize_offer_group(getattr(tariff, "offer_group", None))
                    for tariff in ordered_tariffs
                )
                if group_name is not None
            )
        )
        catalog.append(
            ProductCatalogEntry(
                channel_id=channel_id,
                channel_title=channel_title,
                channel_username=channel_username,
                tariffs=list(ordered_tariffs),
                tariff_count=len(ordered_tariffs),
                price_from_stars=min(prices),
                price_to_stars=max(prices),
                featured_tariff_id=(
                    featured_tariff.id if featured_tariff is not None else None
                ),
                default_tariff_id=(
                    default_tariff.id if default_tariff is not None else None
                ),
                recommended_tariff_id=(
                    recommended_tariff.id if recommended_tariff is not None else None
                ),
                bundle_names=bundle_names,
            )
        )
    return catalog


def get_product_entry(
    catalog: Sequence[ProductCatalogEntry],
    channel_id: int,
) -> ProductCatalogEntry | None:
    for entry in catalog:
        if entry.channel_id == channel_id:
            return entry
    return None


def is_multi_product_catalog(catalog: Sequence[ProductCatalogEntry]) -> bool:
    return len(catalog) > 1


def pick_featured_tariff(tariffs: Sequence[Tariff]) -> Tariff | None:
    for tariff in tariffs:
        if bool(getattr(tariff, "is_featured", False)):
            return tariff
    for tariff in tariffs:
        if bool(getattr(tariff, "is_default_offer", False)):
            return tariff
    return tariffs[0] if tariffs else None


def pick_default_tariff(tariffs: Sequence[Tariff]) -> Tariff | None:
    for tariff in tariffs:
        if bool(getattr(tariff, "is_default_offer", False)):
            return tariff
    non_trial = [tariff for tariff in tariffs if not bool(getattr(tariff, "is_trial", False))]
    pool = non_trial or list(tariffs)
    if not pool:
        return None
    return min(
        pool,
        key=lambda item: (
            int(getattr(item, "price_stars", 0)),
            int(getattr(item, "duration_days", 0)),
        ),
    )


def recommended_tariff_for_product(tariffs: Sequence[Tariff]) -> Tariff | None:
    featured = pick_featured_tariff(tariffs)
    if featured is not None:
        return featured
    return pick_default_tariff(tariffs)


def recommended_tariff_for_entry(product: ProductCatalogEntry) -> Tariff | None:
    if not product.tariffs:
        return None
    return recommended_tariff_for_product(product.tariffs)


def build_offer_details(
    tariff: Tariff,
    *,
    baseline_tariff: Tariff | None,
    now: datetime | None = None,
) -> TariffOfferDetails:
    baseline = baseline_tariff if baseline_tariff is not None else tariff
    is_limited_time = is_limited_offer_active(tariff, now=now)
    return TariffOfferDetails(
        tariff_id=int(tariff.id),
        price_per_day_label=price_per_day_label(tariff),
        savings_label=savings_vs_baseline_label(tariff, baseline),
        offer_copy=normalize_offer_copy(getattr(tariff, "offer_copy", None)),
        offer_group=normalize_offer_group(getattr(tariff, "offer_group", None)),
        is_featured=bool(getattr(tariff, "is_featured", False)),
        is_default_offer=bool(getattr(tariff, "is_default_offer", False)),
        is_limited_time=is_limited_offer_active(tariff, now=now),
        offer_expires_at=(getattr(tariff, "offer_expires_at", None) if is_limited_time else None),
    )


def build_catalog_recommendations(
    catalog: Sequence[ProductCatalogEntry],
    *,
    active_channel_ids: Sequence[int] = (),
    primary_channel_id: int | None = None,
    cross_sell_limit: int = 3,
) -> CatalogRecommendations:
    if not catalog:
        return CatalogRecommendations(
            primary_offer=None,
            renewal_offer=None,
            cross_sell_offers=(),
        )

    active_set = {int(channel_id) for channel_id in active_channel_ids}
    by_channel = {entry.channel_id: entry for entry in catalog}

    primary_entry = (
        by_channel.get(primary_channel_id) if primary_channel_id is not None else None
    )
    if primary_entry is None and active_set:
        primary_entry = next(
            (entry for entry in catalog if entry.channel_id in active_set),
            None,
        )
    if primary_entry is None:
        primary_entry = next(
            (entry for entry in catalog if entry.channel_id not in active_set),
            catalog[0],
        )

    primary_offer = None
    if primary_entry is not None:
        if primary_entry.channel_id in active_set:
            primary_offer = build_recommended_offer(
                primary_entry,
                reason_code="renew_current",
                reason_label="Продлить текущий доступ",
            )
        elif primary_channel_id is not None:
            primary_offer = build_recommended_offer(
                primary_entry,
                reason_code="return_primary",
                reason_label="Вернуться в основной продукт",
            )
        elif active_set:
            primary_offer = build_recommended_offer(
                primary_entry,
                reason_code="expand_catalog",
                reason_label="Докупить ещё продукт",
            )
        else:
            primary_offer = build_recommended_offer(
                primary_entry,
                reason_code="start_here",
                reason_label="Рекомендуем начать с этого оффера",
            )

    renewal_entry = None
    if primary_channel_id is not None and primary_channel_id in active_set:
        renewal_entry = by_channel.get(primary_channel_id)
    if renewal_entry is None:
        renewal_entry = next(
            (entry for entry in catalog if entry.channel_id in active_set),
            None,
        )
    renewal_offer = (
        build_recommended_offer(
            renewal_entry,
            reason_code="renewal",
            reason_label="Лучший оффер для продления",
        )
        if renewal_entry is not None
        else None
    )

    cross_sell_offers: list[RecommendedTariffOffer] = []
    for entry in catalog:
        if entry.channel_id in active_set:
            continue
        if primary_offer is not None and entry.channel_id == primary_offer.channel_id:
            continue
        offer = build_recommended_offer(
            entry,
            reason_code="cross_sell",
            reason_label="Можно докупить как следующий продукт",
        )
        if offer is None:
            continue
        cross_sell_offers.append(offer)
        if len(cross_sell_offers) >= max(int(cross_sell_limit), 0):
            break

    return CatalogRecommendations(
        primary_offer=primary_offer,
        renewal_offer=renewal_offer,
        cross_sell_offers=tuple(cross_sell_offers),
    )


def build_recommended_offer(
    product: ProductCatalogEntry | None,
    *,
    reason_code: str,
    reason_label: str,
) -> RecommendedTariffOffer | None:
    if product is None:
        return None
    recommended_tariff = recommended_tariff_for_entry(product)
    if recommended_tariff is None:
        return None
    baseline_tariff = pick_default_tariff(product.tariffs) or recommended_tariff
    details = build_offer_details(recommended_tariff, baseline_tariff=baseline_tariff)
    return RecommendedTariffOffer(
        channel_id=product.channel_id,
        channel_title=product.channel_title,
        tariff_id=int(recommended_tariff.id),
        tariff_name=safe_ui_text(
            getattr(recommended_tariff, "name", None),
            f"Тариф #{getattr(recommended_tariff, 'id', '?')}",
        ),
        price_stars=int(getattr(recommended_tariff, "price_stars", 0) or 0),
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


def price_per_day_label(tariff: Tariff) -> str:
    if bool(getattr(tariff, "is_lifetime", False)):
        return "без лимита по сроку"
    duration_days = max(int(getattr(tariff, "duration_days", 1) or 1), 1)
    price_stars = Decimal(int(getattr(tariff, "price_stars", 0) or 0))
    per_day = (price_stars / Decimal(duration_days)).quantize(
        DAY_QUANT,
        rounding=ROUND_HALF_UP,
    )
    normalized = format(per_day.normalize(), "f")
    return f"{normalized}{EMOJI_STARS}/день"


def savings_vs_baseline_label(tariff: Tariff, baseline_tariff: Tariff) -> str | None:
    if bool(getattr(tariff, "is_lifetime", False)):
        return None
    baseline_daily = _daily_rate(baseline_tariff)
    current_daily = _daily_rate(tariff)
    if baseline_daily is None or current_daily is None or baseline_daily <= current_daily:
        return None
    savings = ((baseline_daily - current_daily) / baseline_daily * Decimal(100)).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )
    if savings <= 0:
        return None
    return f"выгода {int(savings)}% к дневному тарифу"


def normalize_offer_copy(value: str | None) -> str | None:
    return _normalize_optional_text(value)


def normalize_offer_group(value: str | None) -> str | None:
    return _normalize_optional_text(value)


def _daily_rate(tariff: Tariff) -> Decimal | None:
    if bool(getattr(tariff, "is_lifetime", False)):
        return None
    duration_days = max(int(getattr(tariff, "duration_days", 0) or 0), 0)
    if duration_days <= 0:
        return None
    return Decimal(int(getattr(tariff, "price_stars", 0) or 0)) / Decimal(duration_days)


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
