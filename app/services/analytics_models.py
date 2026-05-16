from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.services.retention_automation import RetentionSegmentSnapshot

_SOURCE_CAMPAIGN_PRIMARY_ISSUE_LABELS = {
    "reconvert_paid_base": "Source-paid reconversion gap",
    "restore_invite_flow": "Invite delivery gap",
    "push_second_product": "Second-product upside",
    "scale_winner": "Healthy",
}

_SOURCE_CAMPAIGN_RECOMMENDED_ACTION_LABELS = {
    "rerun_paid_base_wave": "Re-run paid-base wave",
    "audit_invite_delivery": "Audit invite delivery",
    "launch_cross_sell_follow_up": "Launch cross-sell follow-up",
    "scale_current_wave": "Scale current wave",
}


def _percent(value: int, total: int) -> int:
    if total <= 0:
        return 0
    return int((value * 100) / total)

@dataclass(slots=True)
class ProductFunnelSnapshot:
    channel_id: int
    channel_title: str
    buy_viewed_users: int
    product_selected_users: int
    tariff_opened_users: int
    offer_clicked_users: int
    invoice_created_users: int
    paid_users: int
    invite_issued_users: int
    repeat_purchase_users: int
    revenue_total: int


@dataclass(slots=True)
class ConversionSourceSnapshot:
    source: str
    label: str
    buy_viewed_users: int
    product_selected_users: int
    tariff_opened_users: int
    offer_clicked_users: int
    invoice_created_users: int
    paid_users: int
    invite_issued_users: int


@dataclass(slots=True)
class SourceAcquisitionSnapshot:
    source: str
    label: str
    acquired_users: int
    paid_users: int
    payment_count: int
    invite_issued_users: int
    repeat_purchase_users: int
    first_paid_revenue_total: int
    lifetime_revenue_total: int
    lifecycle_paid_users: int
    lifecycle_payment_count: int
    lifecycle_invite_issued_users: int
    lifecycle_revenue_total: int
    lifecycle_second_product_paid_users: int
    lifecycle_second_product_payment_count: int
    lifecycle_second_product_revenue_total: int
    top_rule_key: str | None
    top_rule_label: str | None
    top_wave_mode: str | None
    top_wave_label: str | None

    @property
    def paid_conversion_percent(self) -> int:
        return _percent(self.paid_users, self.acquired_users)

    @property
    def repeat_purchase_rate_percent(self) -> int:
        return _percent(self.repeat_purchase_users, self.paid_users)

    @property
    def lifecycle_paid_from_paid_percent(self) -> int:
        return _percent(self.lifecycle_paid_users, self.paid_users)

    @property
    def lifecycle_second_product_attach_percent(self) -> int:
        return _percent(
            self.lifecycle_second_product_paid_users,
            self.lifecycle_paid_users,
        )


@dataclass(slots=True)
class PromoCampaignSnapshot:
    promo_code_id: int
    label: str
    campaign_name: str | None
    paid_users: int
    payment_count: int
    repeat_purchase_users: int
    gross_revenue_total: int
    revenue_total: int
    discount_total: int
    lifetime_revenue_total: int

    @property
    def discount_share_percent(self) -> int:
        return _percent(self.discount_total, self.gross_revenue_total)

    @property
    def repeat_purchase_rate_percent(self) -> int:
        return _percent(self.repeat_purchase_users, self.paid_users)


@dataclass(slots=True)
class PromoAttributionSnapshot:
    total_paid_users: int
    total_payment_count: int
    gross_revenue_total: int
    revenue_total: int
    discount_total: int
    campaigns: tuple[PromoCampaignSnapshot, ...]

    @property
    def discount_share_percent(self) -> int:
        return _percent(self.discount_total, self.gross_revenue_total)


@dataclass(slots=True)
class ReferralTopReferrerSnapshot:
    user_id: int
    telegram_id: int
    display_name: str
    invited_users_count: int
    paid_referrals_count: int
    repeat_purchase_referred_users: int
    pending_reward_days: int
    reward_days_issued: int
    first_paid_revenue_total: int
    lifetime_revenue_total: int

    @property
    def conversion_percent(self) -> int:
        return _percent(self.paid_referrals_count, self.invited_users_count)

    @property
    def repeat_purchase_rate_percent(self) -> int:
        return _percent(self.repeat_purchase_referred_users, self.paid_referrals_count)


@dataclass(slots=True)
class ReferralAttributionSnapshot:
    total_referred_users: int
    paid_referred_users: int
    rewarded_referrals_count: int
    suspicious_event_count: int
    pending_reward_days_total: int
    reward_days_issued_total: int
    first_paid_revenue_total: int
    lifetime_referred_revenue_total: int
    top_referrers: tuple[ReferralTopReferrerSnapshot, ...]

    @property
    def paid_conversion_percent(self) -> int:
        return _percent(self.paid_referred_users, self.total_referred_users)


@dataclass(slots=True)
class LifecycleQueueSnapshot:
    renewal_due_3d_users: int
    renewal_due_1d_users: int
    grace_period_users: int
    win_back_ready_users: int


@dataclass(slots=True)
class LifecycleOfferVariantSnapshot:
    variant: str
    label: str
    sent_count: int


@dataclass(slots=True)
class LifecycleOfferMixSnapshot:
    total_sent_count: int
    limited_primary_count: int
    bundle_primary_count: int
    bundle_extra_touch_count: int
    cross_sell_touch_count: int
    variants: tuple[LifecycleOfferVariantSnapshot, ...]


@dataclass(slots=True)
class LifecycleCampaignPerformanceSnapshot:
    variant: str
    label: str
    sent_count: int
    paid_users: int
    payment_count: int
    invite_issued_users: int
    revenue_total: int
    limited_primary_count: int
    bundle_primary_count: int
    bundle_extra_touch_count: int
    cross_sell_touch_count: int

    @property
    def paid_conversion_percent(self) -> int:
        return _percent(self.paid_users, self.sent_count)

    @property
    def invite_conversion_percent(self) -> int:
        return _percent(self.invite_issued_users, self.sent_count)


@dataclass(slots=True)
class LifecycleCampaignFamilySnapshot:
    family: str
    label: str
    sent_count: int
    paid_users: int
    payment_count: int
    invite_issued_users: int
    revenue_total: int
    limited_primary_count: int
    bundle_primary_count: int
    bundle_extra_touch_count: int
    cross_sell_touch_count: int
    top_variant: str | None
    top_variant_label: str | None

    @property
    def paid_conversion_percent(self) -> int:
        return _percent(self.paid_users, self.sent_count)

    @property
    def invite_conversion_percent(self) -> int:
        return _percent(self.invite_issued_users, self.sent_count)


@dataclass(slots=True)
class LifecycleCampaignRuleSnapshot:
    rule_key: str
    label: str
    family: str
    sent_count: int
    paid_users: int
    payment_count: int
    invite_issued_users: int
    revenue_total: int
    limited_primary_count: int
    bundle_primary_count: int
    bundle_extra_touch_count: int
    cross_sell_touch_count: int
    top_variant: str | None
    top_variant_label: str | None

    @property
    def paid_conversion_percent(self) -> int:
        return _percent(self.paid_users, self.sent_count)

    @property
    def invite_conversion_percent(self) -> int:
        return _percent(self.invite_issued_users, self.sent_count)


@dataclass(slots=True)
class LifecycleCampaignWaveSnapshot:
    wave_mode: str
    label: str
    sent_count: int
    paid_users: int
    payment_count: int
    invite_issued_users: int
    revenue_total: int
    limited_primary_count: int
    bundle_primary_count: int
    bundle_extra_touch_count: int
    cross_sell_touch_count: int
    top_rule_key: str | None
    top_rule_label: str | None

    @property
    def paid_conversion_percent(self) -> int:
        return _percent(self.paid_users, self.sent_count)

    @property
    def invite_conversion_percent(self) -> int:
        return _percent(self.invite_issued_users, self.sent_count)


@dataclass(slots=True)
class LifecycleCampaignHighlightSnapshot:
    scope: str
    scope_label: str
    metric: str
    metric_label: str
    entity_key: str
    entity_label: str
    sent_count: int
    paid_users: int
    payment_count: int
    invite_issued_users: int
    revenue_total: int
    note: str | None

    @property
    def paid_conversion_percent(self) -> int:
        return _percent(self.paid_users, self.sent_count)

    @property
    def invite_conversion_percent(self) -> int:
        return _percent(self.invite_issued_users, self.sent_count)


@dataclass(slots=True)
class LifecycleCampaignRoiSnapshot:
    rule_key: str
    label: str
    family: str
    sent_count: int
    paid_users: int
    payment_count: int
    invite_issued_users: int
    revenue_total: int
    second_product_paid_users: int
    second_product_payment_count: int
    second_product_revenue_total: int
    top_secondary_channel_id: int | None
    top_secondary_channel_title: str | None

    @property
    def second_product_attach_from_paid_percent(self) -> int:
        return _percent(self.second_product_paid_users, self.paid_users)

    @property
    def second_product_attach_from_sent_percent(self) -> int:
        return _percent(self.second_product_paid_users, self.sent_count)


@dataclass(slots=True)
class LifecycleSourceCampaignSnapshot:
    source: str
    source_label: str
    source_acquired_users: int
    source_paid_users: int
    rule_key: str
    rule_label: str
    wave_mode: str
    wave_label: str
    sent_count: int
    paid_users: int
    payment_count: int
    invite_issued_users: int
    revenue_total: int
    second_product_paid_users: int
    second_product_payment_count: int
    second_product_revenue_total: int

    @property
    def paid_conversion_percent(self) -> int:
        return _percent(self.paid_users, self.sent_count)

    @property
    def paid_share_of_source_paid_percent(self) -> int:
        return _percent(self.paid_users, self.source_paid_users)

    @property
    def invite_conversion_percent(self) -> int:
        return _percent(self.invite_issued_users, self.sent_count)

    @property
    def second_product_attach_percent(self) -> int:
        return _percent(self.second_product_paid_users, self.paid_users)

    @property
    def average_revenue_per_paid_user(self) -> int:
        if self.paid_users <= 0:
            return 0
        return int(self.revenue_total / self.paid_users)

    @property
    def average_revenue_per_source_paid_user(self) -> int:
        if self.source_paid_users <= 0:
            return 0
        return int(self.revenue_total / self.source_paid_users)

    @property
    def second_product_revenue_share_percent(self) -> int:
        return _percent(self.second_product_revenue_total, self.revenue_total)

    @property
    def source_paid_gap_users(self) -> int:
        return max(self.source_paid_users - self.paid_users, 0)

    @property
    def invite_gap_users(self) -> int:
        return max(self.paid_users - self.invite_issued_users, 0)

    @property
    def second_product_upside_users(self) -> int:
        return max(self.paid_users - self.second_product_paid_users, 0)

    @property
    def opportunity_score(self) -> int:
        return (
            self.source_paid_gap_users * 50
            + self.invite_gap_users * 35
            + self.second_product_upside_users * 25
            + self.second_product_revenue_total // 25
            + self.revenue_total // 50
        )

    @property
    def opportunity_label(self) -> str:
        score = self.opportunity_score
        if score >= 180:
            return "Critical"
        if score >= 110:
            return "High"
        if score >= 55:
            return "Medium"
        return "Watch"

    @property
    def primary_issue_key(self) -> str:
        candidates = (
            (
                "reconvert_paid_base",
                (
                    self.source_paid_gap_users * 50
                    + max(100 - self.paid_share_of_source_paid_percent, 0)
                    if self.source_paid_gap_users > 0
                    else 0
                ),
                0,
            ),
            (
                "restore_invite_flow",
                (
                    self.invite_gap_users * 45 + max(100 - self.invite_conversion_percent, 0)
                    if self.invite_gap_users > 0
                    else 0
                ),
                1,
            ),
            (
                "push_second_product",
                (
                    self.second_product_upside_users * 35
                    + max(100 - self.second_product_attach_percent, 0)
                    + self.second_product_revenue_total // 25
                    if self.second_product_upside_users > 0
                    else 0
                ),
                2,
            ),
        )
        best_key, best_score, _ = max(candidates, key=lambda item: (item[1], -item[2]))
        if best_score <= 0:
            return "scale_winner"
        return best_key

    @property
    def primary_issue_label(self) -> str:
        return _SOURCE_CAMPAIGN_PRIMARY_ISSUE_LABELS[self.primary_issue_key]

    @property
    def recommended_action_key(self) -> str:
        if self.primary_issue_key == "reconvert_paid_base":
            return "rerun_paid_base_wave"
        if self.primary_issue_key == "restore_invite_flow":
            return "audit_invite_delivery"
        if self.primary_issue_key == "push_second_product":
            return "launch_cross_sell_follow_up"
        return "scale_current_wave"

    @property
    def recommended_action_label(self) -> str:
        return _SOURCE_CAMPAIGN_RECOMMENDED_ACTION_LABELS[self.recommended_action_key]

    @property
    def recommended_action_note(self) -> str:
        if self.recommended_action_key == "rerun_paid_base_wave":
            return (
                f"Re-run the strongest renewal or win-back touch for {self.source_label}; "
                f"{self.source_paid_gap_users} of {self.source_paid_users} paid users "
                "have not purchased again yet."
            )
        if self.recommended_action_key == "audit_invite_delivery":
            return (
                "Audit invite issuance and join follow-through; "
                f"{self.invite_gap_users} paid users still have no invite issued."
            )
        if self.recommended_action_key == "launch_cross_sell_follow_up":
            return (
                "Launch a cross-sell or bundle follow-up; "
                f"{self.second_product_upside_users} paid users still have no second product."
            )
        return f"No dominant gap right now. Keep scaling {self.wave_label} for {self.source_label}."


@dataclass(slots=True)
class LifecycleSourceCampaignHighlightSnapshot:
    metric: str
    metric_label: str
    source: str
    source_label: str
    source_acquired_users: int
    source_paid_users: int
    rule_key: str
    rule_label: str
    wave_mode: str
    wave_label: str
    sent_count: int
    paid_users: int
    payment_count: int
    invite_issued_users: int
    revenue_total: int
    second_product_paid_users: int
    second_product_payment_count: int
    second_product_revenue_total: int
    note: str | None

    @property
    def paid_conversion_percent(self) -> int:
        return _percent(self.paid_users, self.sent_count)

    @property
    def paid_share_of_source_paid_percent(self) -> int:
        return _percent(self.paid_users, self.source_paid_users)

    @property
    def invite_conversion_percent(self) -> int:
        return _percent(self.invite_issued_users, self.sent_count)

    @property
    def second_product_attach_percent(self) -> int:
        return _percent(self.second_product_paid_users, self.paid_users)


@dataclass(slots=True)
class LifecycleCampaignAttributionSnapshot:
    total_sent_count: int
    total_paid_users: int
    total_payment_count: int
    total_invite_issued_users: int
    revenue_total: int
    variants: tuple[LifecycleCampaignPerformanceSnapshot, ...]
    families: tuple[LifecycleCampaignFamilySnapshot, ...]
    rules: tuple[LifecycleCampaignRuleSnapshot, ...]
    waves: tuple[LifecycleCampaignWaveSnapshot, ...]
    highlights: tuple[LifecycleCampaignHighlightSnapshot, ...]
    roi: tuple[LifecycleCampaignRoiSnapshot, ...]
    source_roi: tuple[LifecycleSourceCampaignSnapshot, ...]
    source_opportunities: tuple[LifecycleSourceCampaignSnapshot, ...]
    source_actions: tuple[LifecycleSourceCampaignSnapshot, ...]
    source_highlights: tuple[LifecycleSourceCampaignHighlightSnapshot, ...]
    source_watchlist: tuple[LifecycleSourceCampaignHighlightSnapshot, ...]
    source_campaigns: tuple[LifecycleSourceCampaignSnapshot, ...]


@dataclass(slots=True)
class OfferPerformanceSnapshot:
    tariff_id: int
    tariff_name: str
    channel_id: int
    channel_title: str
    offer_group: str | None
    price_stars: int
    duration_days: int
    is_featured: bool
    is_default_offer: bool
    is_limited_time: bool
    offer_expires_at: datetime | None
    opened_users: int
    clicked_users: int
    invoice_created_users: int
    paid_users: int
    payment_count: int
    revenue_total: int

    @property
    def open_to_click_percent(self) -> int:
        return _percent(self.clicked_users, self.opened_users)

    @property
    def click_to_paid_percent(self) -> int:
        return _percent(self.paid_users, self.clicked_users)

    @property
    def invoice_to_paid_percent(self) -> int:
        return _percent(self.paid_users, self.invoice_created_users)

    @property
    def average_payment_amount(self) -> int:
        if self.payment_count <= 0:
            return 0
        return int(self.revenue_total / self.payment_count)


@dataclass(slots=True)
class ProductPairPerformanceSnapshot:
    primary_channel_id: int
    primary_channel_title: str
    secondary_channel_id: int
    secondary_channel_title: str
    attached_paid_users: int
    base_paid_users: int
    secondary_revenue_total: int
    pair_revenue_total: int

    @property
    def attach_rate_percent(self) -> int:
        return _percent(self.attached_paid_users, self.base_paid_users)


@dataclass(slots=True)
class ProductPairCampaignSnapshot:
    primary_channel_id: int
    primary_channel_title: str
    secondary_channel_id: int
    secondary_channel_title: str
    rule_key: str
    rule_label: str
    wave_mode: str
    wave_label: str
    attached_paid_users: int
    base_paid_users: int
    payment_count: int
    secondary_revenue_total: int

    @property
    def attach_rate_percent(self) -> int:
        return _percent(self.attached_paid_users, self.base_paid_users)


@dataclass(slots=True)
class PricingIntelligenceSnapshot:
    average_payment_amount: int
    stars_revenue_total: int
    crypto_revenue_total: int
    stars_revenue_share_percent: int
    crypto_revenue_share_percent: int
    multi_product_paid_users: int
    multi_product_attach_rate_percent: int
    featured_revenue_total: int
    default_revenue_total: int
    limited_revenue_total: int
    active_limited_offer_count: int
    top_product_pairs: tuple[ProductPairPerformanceSnapshot, ...]
    top_pair_campaigns: tuple[ProductPairCampaignSnapshot, ...]
    top_offers: tuple[OfferPerformanceSnapshot, ...]
    top_revenue_offer: OfferPerformanceSnapshot | None
    top_conversion_offer: OfferPerformanceSnapshot | None


@dataclass(slots=True)
class AnalyticsSnapshot:
    total_users: int
    active_subscriptions: int
    expired_users: int
    never_paid_users: int
    blocked_users: int
    revenue_today: int
    revenue_7_days: int
    revenue_30_days: int
    revenue_total: int
    stars_payments: int
    crypto_payments: int
    paid_users_total: int
    conversion_started: int
    conversion_buy_viewed: int
    conversion_product_selected: int
    conversion_tariff_opened: int
    conversion_offer_clicked: int
    conversion_invoice_created: int
    conversion_paid: int
    conversion_invite_issued: int
    repeat_purchase_users: int
    lifecycle_queues: LifecycleQueueSnapshot
    lifecycle_offer_mix: LifecycleOfferMixSnapshot
    lifecycle_campaign_attribution: LifecycleCampaignAttributionSnapshot
    retention_segments: tuple[RetentionSegmentSnapshot, ...]
    product_funnel: tuple[ProductFunnelSnapshot, ...]
    source_funnel: tuple[ConversionSourceSnapshot, ...]
    source_acquisition: tuple[SourceAcquisitionSnapshot, ...]
    pricing_intelligence: PricingIntelligenceSnapshot
    promo_attribution: PromoAttributionSnapshot
    referral_attribution: ReferralAttributionSnapshot

    @property
    def repeat_purchase_rate_percent(self) -> int:
        if self.paid_users_total <= 0:
            return 0
        return int((self.repeat_purchase_users * 100) / self.paid_users_total)


