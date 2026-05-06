from __future__ import annotations

from collections.abc import Sequence

from app.config import Settings
from app.db.models import Tariff
from app.services.product_service import (
    CatalogRecommendations,
    RecommendedTariffOffer,
    build_catalog_recommendations,
    build_product_catalog,
)
from app.utils.datetime import format_datetime


def build_recommendations_from_tariffs(
    tariffs: Sequence[Tariff],
    *,
    primary_channel_id: int | None,
    active_channel_ids: Sequence[int] = (),
) -> CatalogRecommendations:
    catalog = build_product_catalog(tariffs)
    return build_catalog_recommendations(
        catalog,
        active_channel_ids=active_channel_ids,
        primary_channel_id=primary_channel_id,
    )


def append_offer_block(
    text: str,
    *,
    settings: Settings,
    primary_offer: RecommendedTariffOffer | None,
    heading: str,
    cross_sell_offers: Sequence[RecommendedTariffOffer] = (),
    cross_sell_limit: int = 1,
    extras_label: str | None = None,
) -> str:
    if primary_offer is None and not cross_sell_offers:
        return text

    lines = ["", "", heading]
    if primary_offer is not None:
        lines.extend(_offer_lines(primary_offer, settings=settings))

    extras = list(cross_sell_offers[: max(int(cross_sell_limit), 0)])
    if extras:
        lines.append(extras_label or "??? ????? ????????:")
        for offer in extras:
            lines.extend(_offer_lines(offer, settings=settings, compact=True))
    return text + "\n" + "\n".join(lines)


def merge_unique_offers(
    *groups: Sequence[RecommendedTariffOffer],
    exclude_tariff_ids: Sequence[int] = (),
) -> tuple[RecommendedTariffOffer, ...]:
    excluded = {int(item) for item in exclude_tariff_ids}
    seen: set[int] = set(excluded)
    result: list[RecommendedTariffOffer] = []
    for group in groups:
        for offer in group:
            tariff_id = int(offer.tariff_id)
            if tariff_id in seen:
                continue
            seen.add(tariff_id)
            result.append(offer)
    return tuple(result)


def _offer_lines(
    offer: RecommendedTariffOffer,
    *,
    settings: Settings,
    compact: bool = False,
) -> list[str]:
    buy_link = settings.bot_start_link(f"buy_{offer.channel_id}") or ""
    line = (
        f"- {offer.reason_label}: {offer.tariff_name} - "
        f"{offer.price_stars} Stars - {offer.price_per_day_label}"
    )
    lines = [line]
    if offer.savings_label:
        lines.append(f"  {offer.savings_label}")
    if offer.is_limited_time and offer.offer_expires_at is not None:
        lines.append(
            f"  ?????????? ?? {format_datetime(offer.offer_expires_at, settings.timezone)}"
        )
    if offer.offer_copy and not compact:
        lines.append(f"  {offer.offer_copy}")
    if buy_link:
        lines.append(f"  {buy_link}")
    return lines
