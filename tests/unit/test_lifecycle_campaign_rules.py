from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.lifecycle_campaign_rules import (
    PRIMARY_SOURCE_CROSS_SELL,
    PRIMARY_SOURCE_LIMITED,
    PRIMARY_SOURCE_RECOMMENDED,
    get_retention_campaign_rule,
    get_subscription_campaign_rule,
    select_lifecycle_campaign_offers,
)


def _offer(
    tariff_id: int,
    channel_id: int,
    *,
    reason_code: str,
    reason_label: str,
    limited: bool = False,
):
    return SimpleNamespace(
        tariff_id=tariff_id,
        channel_id=channel_id,
        tariff_name=f"Tariff {tariff_id}",
        channel_title=f"Channel {channel_id}",
        price_stars=100,
        price_per_day_label="10/day",
        savings_label=None,
        offer_copy=None,
        offer_group=None,
        is_featured=False,
        is_default_offer=False,
        is_limited_time=limited,
        offer_expires_at=datetime(2026, 5, 8, tzinfo=UTC) if limited else None,
        reason_code=reason_code,
        reason_label=reason_label,
    )


def test_select_lifecycle_campaign_offers_prefers_limited_win_back_wave() -> None:
    rule = get_retention_campaign_rule("expired_recently")
    assert rule is not None

    selection = select_lifecycle_campaign_offers(
        rule,
        recommended_offer=_offer(1, 10, reason_code="return_primary", reason_label="Return"),
        limited_offer=_offer(
            2,
            10,
            reason_code="limited_product",
            reason_label="Limited",
            limited=True,
        ),
        bundle_offer=_offer(3, 10, reason_code="bundle", reason_label="Bundle"),
        cross_sell_offers=(
            _offer(4, 20, reason_code="cross_sell", reason_label="Cross-sell"),
        ),
    )

    assert selection.primary_offer is not None
    assert selection.primary_offer.tariff_id == 2
    assert selection.primary_source == PRIMARY_SOURCE_LIMITED
    assert [item.tariff_id for item in selection.bundle_offers] == [3]
    assert [item.tariff_id for item in selection.cross_sell_offers] == [4]
    assert selection.offer_strategy == "win_back_limited"
    assert selection.campaign_rule_key == "win_back_wave"
    assert selection.campaign_family == "win_back"
    assert selection.campaign_wave_mode == "limited_bundle_wave"
    assert selection.campaign_wave_label == "Limited + bundle wave"


def test_select_lifecycle_campaign_offers_turns_bundle_into_renewal_bundle_strategy() -> None:
    rule = get_subscription_campaign_rule("renewal")

    selection = select_lifecycle_campaign_offers(
        rule,
        recommended_offer=_offer(1, 10, reason_code="renewal", reason_label="Renewal"),
        limited_offer=None,
        bundle_offer=_offer(2, 10, reason_code="bundle", reason_label="Bundle"),
        cross_sell_offers=(
            _offer(3, 20, reason_code="cross_sell", reason_label="Cross-sell"),
        ),
    )

    assert selection.primary_offer is not None
    assert selection.primary_offer.tariff_id == 1
    assert selection.primary_source == PRIMARY_SOURCE_RECOMMENDED
    assert [item.tariff_id for item in selection.bundle_offers] == [2]
    assert selection.cross_sell_offers == ()
    assert selection.offer_strategy == "renewal_bundle"
    assert selection.campaign_rule_key == "renewal_wave"
    assert selection.campaign_wave_mode == "recommended_bundle_wave"
    assert selection.campaign_wave_label == "Recommended + bundle wave"


def test_select_lifecycle_campaign_offers_can_promote_cross_sell_for_trial_recovery() -> None:
    rule = get_retention_campaign_rule("lost_after_trial")
    assert rule is not None

    selection = select_lifecycle_campaign_offers(
        rule,
        recommended_offer=None,
        limited_offer=None,
        bundle_offer=_offer(5, 10, reason_code="bundle", reason_label="Bundle"),
        cross_sell_offers=(
            _offer(6, 20, reason_code="start_here", reason_label="Start here"),
            _offer(7, 21, reason_code="cross_sell", reason_label="Cross-sell"),
        ),
    )

    assert selection.primary_offer is not None
    assert selection.primary_offer.tariff_id == 6
    assert selection.primary_source == PRIMARY_SOURCE_CROSS_SELL
    assert [item.tariff_id for item in selection.bundle_offers] == [5]
    assert [item.tariff_id for item in selection.cross_sell_offers] == [7]
    assert selection.offer_strategy == "trial_to_paid"
    assert selection.campaign_rule_key == "trial_recovery_wave"
    assert selection.campaign_wave_mode == "cross_sell_bundle_wave"
    assert selection.campaign_wave_label == "Cross-sell + bundle wave"
