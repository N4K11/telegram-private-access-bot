from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

PRIMARY_SOURCE_RECOMMENDED = "recommended"
PRIMARY_SOURCE_LIMITED = "limited"
PRIMARY_SOURCE_BUNDLE = "bundle"
PRIMARY_SOURCE_CROSS_SELL = "cross_sell"
PRIMARY_SOURCE_RECOMMENDED_WITH_BUNDLE = "recommended_with_bundle"

WAVE_MODE_LIMITED = "limited_wave"
WAVE_MODE_LIMITED_WITH_BUNDLE = "limited_bundle_wave"
WAVE_MODE_RECOMMENDED = "recommended_wave"
WAVE_MODE_RECOMMENDED_WITH_BUNDLE = "recommended_bundle_wave"
WAVE_MODE_BUNDLE_PRIMARY = "bundle_primary_wave"
WAVE_MODE_CROSS_SELL = "cross_sell_wave"
WAVE_MODE_CROSS_SELL_WITH_BUNDLE = "cross_sell_bundle_wave"

CAMPAIGN_WAVE_LABELS = {
    WAVE_MODE_LIMITED: "Limited wave",
    WAVE_MODE_LIMITED_WITH_BUNDLE: "Limited + bundle wave",
    WAVE_MODE_RECOMMENDED: "Recommended wave",
    WAVE_MODE_RECOMMENDED_WITH_BUNDLE: "Recommended + bundle wave",
    WAVE_MODE_BUNDLE_PRIMARY: "Bundle-primary wave",
    WAVE_MODE_CROSS_SELL: "Cross-sell wave",
    WAVE_MODE_CROSS_SELL_WITH_BUNDLE: "Cross-sell + bundle wave",
}


@dataclass(frozen=True, slots=True)
class LifecycleCampaignRule:
    key: str
    label: str
    family: str
    campaign_variant: str | None
    primary_source_order: tuple[str, ...]
    bundle_extra_limit: int = 0
    cross_sell_limit: int = 0
    heading_by_source: Mapping[str, str] | None = None
    strategy_by_source: Mapping[str, str] | None = None

    def _effective_source_key(self, primary_source: str | None, has_bundle_extras: bool) -> str:
        if primary_source == PRIMARY_SOURCE_RECOMMENDED and has_bundle_extras:
            return PRIMARY_SOURCE_RECOMMENDED_WITH_BUNDLE
        return primary_source or PRIMARY_SOURCE_RECOMMENDED

    def heading_for(self, *, primary_source: str | None, has_bundle_extras: bool) -> str:
        effective_source = self._effective_source_key(primary_source, has_bundle_extras)
        if self.heading_by_source and effective_source in self.heading_by_source:
            return self.heading_by_source[effective_source]
        return self.label

    def strategy_for(self, *, primary_source: str | None, has_bundle_extras: bool) -> str | None:
        effective_source = self._effective_source_key(primary_source, has_bundle_extras)
        if self.strategy_by_source and effective_source in self.strategy_by_source:
            return self.strategy_by_source[effective_source]
        return self.campaign_variant


@dataclass(slots=True)
class LifecycleCampaignSelection:
    primary_offer: Any | None
    primary_source: str | None
    bundle_offers: tuple[Any, ...]
    cross_sell_offers: tuple[Any, ...]
    heading: str
    offer_strategy: str | None
    campaign_variant: str | None
    campaign_rule_key: str
    campaign_rule_label: str
    campaign_family: str
    campaign_wave_mode: str
    campaign_wave_label: str
    extras_label: str | None

    @property
    def extra_offer_limit(self) -> int:
        return len(self.bundle_offers) + len(self.cross_sell_offers)


RETENTION_CAMPAIGN_RULES: dict[str, LifecycleCampaignRule] = {
    "lost_after_trial": LifecycleCampaignRule(
        key="trial_recovery_wave",
        label="Trial recovery wave",
        family="trial_recovery",
        campaign_variant="trial_to_paid",
        primary_source_order=(
            PRIMARY_SOURCE_LIMITED,
            PRIMARY_SOURCE_CROSS_SELL,
            PRIMARY_SOURCE_BUNDLE,
        ),
        bundle_extra_limit=1,
        cross_sell_limit=1,
        heading_by_source={
            PRIMARY_SOURCE_LIMITED: "Ограниченное предложение после trial",
            PRIMARY_SOURCE_CROSS_SELL: "Перейди с trial на полный доступ",
            PRIMARY_SOURCE_BUNDLE: "Пакетное предложение после trial",
        },
        strategy_by_source={
            PRIMARY_SOURCE_LIMITED: "trial_to_limited",
            PRIMARY_SOURCE_CROSS_SELL: "trial_to_paid",
            PRIMARY_SOURCE_BUNDLE: "trial_to_bundle",
        },
    ),
    "expired_recently": LifecycleCampaignRule(
        key="win_back_wave",
        label="Win-back wave",
        family="win_back",
        campaign_variant="win_back_recent",
        primary_source_order=(
            PRIMARY_SOURCE_LIMITED,
            PRIMARY_SOURCE_RECOMMENDED,
            PRIMARY_SOURCE_BUNDLE,
        ),
        bundle_extra_limit=1,
        cross_sell_limit=1,
        heading_by_source={
            PRIMARY_SOURCE_LIMITED: "Ограниченное предложение для возврата",
            PRIMARY_SOURCE_RECOMMENDED: "Предложение для возврата",
            PRIMARY_SOURCE_RECOMMENDED_WITH_BUNDLE: "Пакетное предложение для возврата",
            PRIMARY_SOURCE_BUNDLE: "Пакетное предложение для возврата",
        },
        strategy_by_source={
            PRIMARY_SOURCE_LIMITED: "win_back_limited",
            PRIMARY_SOURCE_RECOMMENDED: "win_back_recent",
            PRIMARY_SOURCE_RECOMMENDED_WITH_BUNDLE: "win_back_bundle",
            PRIMARY_SOURCE_BUNDLE: "win_back_bundle",
        },
    ),
    "inactive_paid": LifecycleCampaignRule(
        key="reactivation_wave",
        label="Reactivation wave",
        family="reactivation",
        campaign_variant="reactivation",
        primary_source_order=(
            PRIMARY_SOURCE_LIMITED,
            PRIMARY_SOURCE_RECOMMENDED,
            PRIMARY_SOURCE_BUNDLE,
        ),
        bundle_extra_limit=1,
        cross_sell_limit=1,
        heading_by_source={
            PRIMARY_SOURCE_LIMITED: "Ограниченное предложение для реактивации",
            PRIMARY_SOURCE_RECOMMENDED: "Предложение для реактивации",
            PRIMARY_SOURCE_RECOMMENDED_WITH_BUNDLE: "Пакетное предложение для реактивации",
            PRIMARY_SOURCE_BUNDLE: "Пакетное предложение для реактивации",
        },
        strategy_by_source={
            PRIMARY_SOURCE_LIMITED: "reactivation_limited",
            PRIMARY_SOURCE_RECOMMENDED: "reactivation",
            PRIMARY_SOURCE_RECOMMENDED_WITH_BUNDLE: "reactivation_bundle",
            PRIMARY_SOURCE_BUNDLE: "reactivation_bundle",
        },
    ),
}

SUBSCRIPTION_CAMPAIGN_RULES: dict[str, LifecycleCampaignRule] = {
    "renewal": LifecycleCampaignRule(
        key="renewal_wave",
        label="Renewal wave",
        family="renewal",
        campaign_variant=None,
        primary_source_order=(
            PRIMARY_SOURCE_LIMITED,
            PRIMARY_SOURCE_RECOMMENDED,
            PRIMARY_SOURCE_BUNDLE,
        ),
        bundle_extra_limit=1,
        cross_sell_limit=0,
        heading_by_source={
            PRIMARY_SOURCE_LIMITED: "Ограниченное предложение для продления",
            PRIMARY_SOURCE_RECOMMENDED: "Предложение для продления",
            PRIMARY_SOURCE_RECOMMENDED_WITH_BUNDLE: "Пакетное предложение для продления",
            PRIMARY_SOURCE_BUNDLE: "Пакетное предложение для продления",
        },
        strategy_by_source={
            PRIMARY_SOURCE_LIMITED: "renewal_limited",
            PRIMARY_SOURCE_RECOMMENDED: "renewal",
            PRIMARY_SOURCE_RECOMMENDED_WITH_BUNDLE: "renewal_bundle",
            PRIMARY_SOURCE_BUNDLE: "renewal_bundle",
        },
    ),
    "expired_grace": LifecycleCampaignRule(
        key="grace_recovery_wave",
        label="Grace recovery wave",
        family="grace_recovery",
        campaign_variant=None,
        primary_source_order=(
            PRIMARY_SOURCE_LIMITED,
            PRIMARY_SOURCE_RECOMMENDED,
            PRIMARY_SOURCE_BUNDLE,
        ),
        bundle_extra_limit=1,
        cross_sell_limit=1,
        heading_by_source={
            PRIMARY_SOURCE_LIMITED: "Ограниченное предложение до отключения",
            PRIMARY_SOURCE_RECOMMENDED: "Предложение до отключения",
            PRIMARY_SOURCE_RECOMMENDED_WITH_BUNDLE: "Пакетное предложение до отключения",
            PRIMARY_SOURCE_BUNDLE: "Пакетное предложение до отключения",
        },
        strategy_by_source={
            PRIMARY_SOURCE_LIMITED: "expired_grace_limited",
            PRIMARY_SOURCE_RECOMMENDED: "expired_grace",
            PRIMARY_SOURCE_RECOMMENDED_WITH_BUNDLE: "expired_grace_bundle",
            PRIMARY_SOURCE_BUNDLE: "expired_grace_bundle",
        },
    ),
    "expired_final": LifecycleCampaignRule(
        key="final_reactivation_wave",
        label="Final reactivation wave",
        family="final_reactivation",
        campaign_variant=None,
        primary_source_order=(
            PRIMARY_SOURCE_LIMITED,
            PRIMARY_SOURCE_RECOMMENDED,
            PRIMARY_SOURCE_BUNDLE,
        ),
        bundle_extra_limit=1,
        cross_sell_limit=1,
        heading_by_source={
            PRIMARY_SOURCE_LIMITED: "Ограниченное предложение после отключения",
            PRIMARY_SOURCE_RECOMMENDED: "Предложение после отключения",
            PRIMARY_SOURCE_RECOMMENDED_WITH_BUNDLE: "Пакетное предложение после отключения",
            PRIMARY_SOURCE_BUNDLE: "Пакетное предложение после отключения",
        },
        strategy_by_source={
            PRIMARY_SOURCE_LIMITED: "expired_final_limited",
            PRIMARY_SOURCE_RECOMMENDED: "expired_final",
            PRIMARY_SOURCE_RECOMMENDED_WITH_BUNDLE: "expired_final_bundle",
            PRIMARY_SOURCE_BUNDLE: "expired_final_bundle",
        },
    ),
}


def get_retention_campaign_rule(segment: str) -> LifecycleCampaignRule | None:
    return RETENTION_CAMPAIGN_RULES.get(segment)


def get_subscription_campaign_rule(mode: str) -> LifecycleCampaignRule:
    rule = SUBSCRIPTION_CAMPAIGN_RULES.get(mode)
    if rule is None:
        raise KeyError(f"Unknown subscription campaign mode: {mode}")
    return rule


def _resolve_campaign_wave_mode(
    *,
    primary_source: str | None,
    has_bundle_extras: bool,
) -> tuple[str, str]:
    if primary_source == PRIMARY_SOURCE_LIMITED:
        mode = WAVE_MODE_LIMITED_WITH_BUNDLE if has_bundle_extras else WAVE_MODE_LIMITED
    elif primary_source == PRIMARY_SOURCE_BUNDLE:
        mode = WAVE_MODE_BUNDLE_PRIMARY
    elif primary_source == PRIMARY_SOURCE_CROSS_SELL:
        mode = WAVE_MODE_CROSS_SELL_WITH_BUNDLE if has_bundle_extras else WAVE_MODE_CROSS_SELL
    else:
        mode = WAVE_MODE_RECOMMENDED_WITH_BUNDLE if has_bundle_extras else WAVE_MODE_RECOMMENDED
    return mode, CAMPAIGN_WAVE_LABELS[mode]


def select_lifecycle_campaign_offers(
    rule: LifecycleCampaignRule,
    *,
    recommended_offer: Any | None,
    limited_offer: Any | None,
    bundle_offer: Any | None,
    cross_sell_offers: Sequence[Any] = (),
) -> LifecycleCampaignSelection:
    available_cross_sells = _dedupe_offers(cross_sell_offers)
    primary_offer = None
    primary_source: str | None = None

    for source in rule.primary_source_order:
        if source == PRIMARY_SOURCE_RECOMMENDED and recommended_offer is not None:
            primary_offer = recommended_offer
            primary_source = source
            break
        if source == PRIMARY_SOURCE_LIMITED and limited_offer is not None:
            primary_offer = limited_offer
            primary_source = source
            break
        if source == PRIMARY_SOURCE_BUNDLE and bundle_offer is not None:
            primary_offer = bundle_offer
            primary_source = source
            break
        if source == PRIMARY_SOURCE_CROSS_SELL and available_cross_sells:
            primary_offer = available_cross_sells[0]
            primary_source = source
            available_cross_sells = tuple(available_cross_sells[1:])
            break

    bundle_extras: tuple[Any, ...] = ()
    if (
        bundle_offer is not None
        and rule.bundle_extra_limit > 0
        and (primary_offer is None or int(bundle_offer.tariff_id) != int(primary_offer.tariff_id))
    ):
        bundle_extras = (bundle_offer,)[: rule.bundle_extra_limit]
    if primary_source == PRIMARY_SOURCE_BUNDLE:
        bundle_extras = ()

    primary_tariff_id = int(primary_offer.tariff_id) if primary_offer is not None else None
    cross_sell_pool: list[Any] = []
    seen_tariff_ids: set[int] = set()
    for offer in available_cross_sells:
        tariff_id = int(offer.tariff_id)
        if primary_tariff_id is not None and tariff_id == primary_tariff_id:
            continue
        if tariff_id in seen_tariff_ids:
            continue
        seen_tariff_ids.add(tariff_id)
        cross_sell_pool.append(offer)
    cross_sell_extras = tuple(cross_sell_pool[: rule.cross_sell_limit])

    extras_label = None
    if bundle_extras and cross_sell_extras:
        extras_label = "Дополнительно можно взять и другой продукт:"
    elif bundle_extras:
        extras_label = "Ещё один пакетный вариант:"
    elif cross_sell_extras:
        extras_label = "Ещё можно посмотреть:"

    heading = rule.heading_for(
        primary_source=primary_source,
        has_bundle_extras=bool(bundle_extras),
    )
    offer_strategy = None
    if primary_offer is not None:
        offer_strategy = rule.strategy_for(
            primary_source=primary_source,
            has_bundle_extras=bool(bundle_extras),
        )

    campaign_wave_mode, campaign_wave_label = _resolve_campaign_wave_mode(
        primary_source=primary_source,
        has_bundle_extras=bool(bundle_extras),
    )

    return LifecycleCampaignSelection(
        primary_offer=primary_offer,
        primary_source=primary_source,
        bundle_offers=bundle_extras,
        cross_sell_offers=cross_sell_extras,
        heading=heading,
        offer_strategy=offer_strategy,
        campaign_variant=rule.campaign_variant,
        campaign_rule_key=rule.key,
        campaign_rule_label=rule.label,
        campaign_family=rule.family,
        campaign_wave_mode=campaign_wave_mode,
        campaign_wave_label=campaign_wave_label,
        extras_label=extras_label,
    )


def _dedupe_offers(items: Sequence[Any]) -> tuple[Any, ...]:
    seen: set[int] = set()
    result: list[Any] = []
    for item in items:
        tariff_id = int(item.tariff_id)
        if tariff_id in seen:
            continue
        seen.add(tariff_id)
        result.append(item)
    return tuple(result)
