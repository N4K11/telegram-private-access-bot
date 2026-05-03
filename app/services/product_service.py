from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.db.models import Tariff
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
    bundle_names: tuple[str, ...]

    @property
    def price_range_label(self) -> str:
        if self.price_from_stars == self.price_to_stars:
            return f"{self.price_from_stars}{EMOJI_STARS}"
        return f"{TXT_FROM} {self.price_from_stars}{EMOJI_STARS}"


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


def build_offer_details(
    tariff: Tariff,
    *,
    baseline_tariff: Tariff | None,
) -> TariffOfferDetails:
    baseline = baseline_tariff if baseline_tariff is not None else tariff
    return TariffOfferDetails(
        tariff_id=int(tariff.id),
        price_per_day_label=price_per_day_label(tariff),
        savings_label=savings_vs_baseline_label(tariff, baseline),
        offer_copy=normalize_offer_copy(getattr(tariff, "offer_copy", None)),
        offer_group=normalize_offer_group(getattr(tariff, "offer_group", None)),
        is_featured=bool(getattr(tariff, "is_featured", False)),
        is_default_offer=bool(getattr(tariff, "is_default_offer", False)),
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