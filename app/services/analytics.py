from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AuditLog,
    Channel,
    InviteLink,
    Payment,
    PromoCode,
    PromoRedemption,
    Subscription,
    Tariff,
    User,
)
from app.services.conversion import conversion_source_label, normalize_conversion_source
from app.services.lifecycle_campaign_rules import CAMPAIGN_WAVE_LABELS
from app.services.product_service import normalize_offer_group
from app.services.retention_automation import (
    RECENT_EXPIRED_MAX_AGE,
    RECENT_EXPIRED_MIN_AGE,
    RetentionSegmentSnapshot,
    build_retention_segment_snapshots,
)
from app.utils.datetime import ensure_aware_utc, utcnow
from app.utils.encoding import safe_ui_text


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


async def build_analytics_snapshot(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> AnalyticsSnapshot:
    current_time = ensure_aware_utc(now or utcnow())
    today_start = current_time.astimezone(UTC).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    week_start = current_time - timedelta(days=7)
    month_start = current_time - timedelta(days=30)

    users = list((await session.execute(select(User.id, User.is_blocked))).all())
    total_users = len(users)
    blocked_users = sum(1 for _, is_blocked in users if is_blocked)

    paid_rows = list(
        (
            await session.execute(
                select(
                    Payment.user_id,
                    Payment.provider,
                    Payment.amount,
                    Payment.paid_at,
                    Payment.channel_id,
                ).where(Payment.status == "paid")
            )
        ).all()
    )
    paid_user_ids = {user_id for user_id, _, _, _, _ in paid_rows}
    never_paid_users = sum(1 for user_id, _ in users if user_id not in paid_user_ids)

    revenue_total = sum(int(amount) for _, _, amount, _, _ in paid_rows)
    revenue_today = sum(
        int(amount)
        for _, _, amount, paid_at, _ in paid_rows
        if paid_at is not None and ensure_aware_utc(paid_at) >= today_start
    )
    revenue_7_days = sum(
        int(amount)
        for _, _, amount, paid_at, _ in paid_rows
        if paid_at is not None and ensure_aware_utc(paid_at) >= week_start
    )
    revenue_30_days = sum(
        int(amount)
        for _, _, amount, paid_at, _ in paid_rows
        if paid_at is not None and ensure_aware_utc(paid_at) >= month_start
    )
    stars_payments = sum(1 for _, provider, _, _, _ in paid_rows if provider == "telegram_stars")
    crypto_payments = sum(1 for _, provider, _, _, _ in paid_rows if provider.startswith("crypto"))

    active_subscriptions = int(
        (
            await session.execute(
                select(func.count(Subscription.id))
                .where(Subscription.status == "active")
                .where(Subscription.revoked_at.is_(None))
                .where(Subscription.expires_at > current_time)
            )
        ).scalar_one()
        or 0
    )

    subscription_rows = list(
        (
            await session.execute(
                select(
                    Subscription.user_id,
                    Subscription.status,
                    Subscription.revoked_at,
                    Subscription.expires_at,
                ).order_by(
                    Subscription.user_id.asc(),
                    Subscription.expires_at.desc(),
                    Subscription.id.desc(),
                )
            )
        ).all()
    )
    latest_expires_by_user: dict[int, datetime] = {}
    has_active_user_ids: set[int] = set()
    for user_id, status, revoked_at, expires_at in subscription_rows:
        aware_expires_at = ensure_aware_utc(expires_at)
        if user_id not in latest_expires_by_user:
            latest_expires_by_user[user_id] = aware_expires_at
        if status == "active" and revoked_at is None and aware_expires_at > current_time:
            has_active_user_ids.add(user_id)

    expired_users = sum(
        1
        for user_id, _ in users
        if user_id not in has_active_user_ids
        and user_id in latest_expires_by_user
        and latest_expires_by_user[user_id] <= current_time
    )

    started = await _distinct_audit_targets(session, "user_start")
    buy_viewed = await _distinct_audit_targets(session, "buy_screen_viewed")
    product_selected = await _distinct_audit_targets(session, "product_selected")
    tariff_opened = await _distinct_audit_targets(session, "tariff_detail_opened")
    offer_clicked = await _distinct_audit_targets(session, "offer_clicked")
    invoice_created = await _distinct_audit_targets_multi(
        session,
        ("invoice_created_stars", "invoice_created_crypto"),
    )
    paid = await _distinct_audit_targets_multi(
        session,
        ("payment_paid_stars", "payment_paid_crypto"),
    )
    invite_issued = await _distinct_invite_users(session)
    repeat_purchase_users = await _repeat_purchase_user_count(session)
    lifecycle_queues = await _build_lifecycle_queue_snapshot(session, now=current_time)
    lifecycle_offer_mix = await _build_lifecycle_offer_mix(session, now=current_time)
    channel_titles = await _load_channel_titles(session)
    lifecycle_campaign_attribution = await _build_lifecycle_campaign_attribution(
        session,
        channel_titles=channel_titles,
        now=current_time,
    )
    retention_segments = await build_retention_segment_snapshots(session, now=current_time)

    tariff_channel_map = await _load_tariff_channel_map(session)
    product_funnel = await _build_product_funnel(
        session,
        channel_titles=channel_titles,
        tariff_channel_map=tariff_channel_map,
        paid_rows=paid_rows,
    )
    source_funnel = await _build_source_funnel(session)
    source_acquisition = await _build_source_acquisition(session, now=current_time)
    promo_attribution = await _build_promo_attribution(session)
    referral_attribution = await _build_referral_attribution(session, limit=5)
    pricing_intelligence = await _build_pricing_intelligence(
        session,
        channel_titles=channel_titles,
        now=current_time,
    )

    return AnalyticsSnapshot(
        total_users=total_users,
        active_subscriptions=active_subscriptions,
        expired_users=expired_users,
        never_paid_users=never_paid_users,
        blocked_users=blocked_users,
        revenue_today=revenue_today,
        revenue_7_days=revenue_7_days,
        revenue_30_days=revenue_30_days,
        revenue_total=revenue_total,
        stars_payments=stars_payments,
        crypto_payments=crypto_payments,
        paid_users_total=len(paid_user_ids),
        conversion_started=started or total_users,
        conversion_buy_viewed=buy_viewed,
        conversion_product_selected=product_selected,
        conversion_tariff_opened=tariff_opened,
        conversion_offer_clicked=offer_clicked,
        conversion_invoice_created=invoice_created or len(paid_user_ids),
        conversion_paid=paid or len(paid_user_ids),
        conversion_invite_issued=invite_issued,
        repeat_purchase_users=repeat_purchase_users,
        lifecycle_queues=lifecycle_queues,
        lifecycle_offer_mix=lifecycle_offer_mix,
        lifecycle_campaign_attribution=lifecycle_campaign_attribution,
        retention_segments=retention_segments,
        product_funnel=product_funnel,
        source_funnel=source_funnel,
        source_acquisition=source_acquisition,
        pricing_intelligence=pricing_intelligence,
        promo_attribution=promo_attribution,
        referral_attribution=referral_attribution,
    )


async def _build_product_funnel(
    session: AsyncSession,
    *,
    channel_titles: dict[int, str],
    tariff_channel_map: dict[int, int],
    paid_rows: list[tuple[int, str, int, datetime | None, int | None]],
) -> tuple[ProductFunnelSnapshot, ...]:
    buy_viewed_by_channel = await _audit_targets_by_channel(
        session,
        actions=("buy_screen_viewed",),
        tariff_channel_map=tariff_channel_map,
    )
    product_selected_by_channel = await _audit_targets_by_channel(
        session,
        actions=("product_selected",),
        tariff_channel_map=tariff_channel_map,
    )
    tariff_opened_by_channel = await _audit_targets_by_channel(
        session,
        actions=("tariff_detail_opened",),
        tariff_channel_map=tariff_channel_map,
    )
    offer_clicked_by_channel = await _audit_targets_by_channel(
        session,
        actions=("offer_clicked",),
        tariff_channel_map=tariff_channel_map,
    )
    invoice_created_by_channel = await _audit_targets_by_channel(
        session,
        actions=("invoice_created_stars", "invoice_created_crypto"),
        tariff_channel_map=tariff_channel_map,
    )
    repeat_purchase_by_channel = await _audit_targets_by_channel(
        session,
        actions=("repeat_purchase_paid",),
        tariff_channel_map=tariff_channel_map,
    )

    paid_by_channel: dict[int, set[int]] = defaultdict(set)
    revenue_by_channel: dict[int, int] = defaultdict(int)
    for user_id, _provider, amount, _paid_at, channel_id in paid_rows:
        if channel_id is None:
            continue
        paid_by_channel[channel_id].add(user_id)
        revenue_by_channel[channel_id] += int(amount)

    invite_by_channel: dict[int, set[int]] = defaultdict(set)
    invite_rows = list(
        (
            await session.execute(
                select(InviteLink.channel_id, InviteLink.user_id)
            )
        ).all()
    )
    for channel_id, user_id in invite_rows:
        invite_by_channel[int(channel_id)].add(int(user_id))

    all_channel_ids = set(channel_titles)
    all_channel_ids.update(buy_viewed_by_channel)
    all_channel_ids.update(product_selected_by_channel)
    all_channel_ids.update(tariff_opened_by_channel)
    all_channel_ids.update(offer_clicked_by_channel)
    all_channel_ids.update(invoice_created_by_channel)
    all_channel_ids.update(paid_by_channel)
    all_channel_ids.update(invite_by_channel)
    all_channel_ids.update(repeat_purchase_by_channel)

    items: list[ProductFunnelSnapshot] = []
    for channel_id in sorted(
        all_channel_ids,
        key=lambda item: (-revenue_by_channel.get(item, 0), channel_titles.get(item, ""), item),
    ):
        items.append(
            ProductFunnelSnapshot(
                channel_id=channel_id,
                channel_title=channel_titles.get(channel_id, f"????? #{channel_id}"),
                buy_viewed_users=len(buy_viewed_by_channel.get(channel_id, set())),
                product_selected_users=len(product_selected_by_channel.get(channel_id, set())),
                tariff_opened_users=len(tariff_opened_by_channel.get(channel_id, set())),
                offer_clicked_users=len(offer_clicked_by_channel.get(channel_id, set())),
                invoice_created_users=len(invoice_created_by_channel.get(channel_id, set())),
                paid_users=len(paid_by_channel.get(channel_id, set())),
                invite_issued_users=len(invite_by_channel.get(channel_id, set())),
                repeat_purchase_users=len(repeat_purchase_by_channel.get(channel_id, set())),
                revenue_total=revenue_by_channel.get(channel_id, 0),
            )
        )
    return tuple(items)


async def _build_source_funnel(session: AsyncSession) -> tuple[ConversionSourceSnapshot, ...]:
    action_map = {
        "buy_screen_viewed": "buy_viewed_users",
        "product_selected": "product_selected_users",
        "tariff_detail_opened": "tariff_opened_users",
        "offer_clicked": "offer_clicked_users",
        "invoice_created_stars": "invoice_created_users",
        "invoice_created_crypto": "invoice_created_users",
        "payment_paid_stars": "paid_users",
        "payment_paid_crypto": "paid_users",
        "invite_issued": "invite_issued_users",
    }
    result = await session.execute(
        select(AuditLog.action, AuditLog.target_user_id, AuditLog.payload).where(
            AuditLog.action.in_(tuple(action_map))
        )
    )
    grouped: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    for action, target_user_id, raw_payload in result.all():
        if target_user_id is None:
            continue
        payload = _parse_payload(raw_payload)
        source = normalize_conversion_source(payload.get("source"))
        if source is None:
            continue
        grouped[source][action_map[action]].add(int(target_user_id))

    items: list[ConversionSourceSnapshot] = []
    for source, metrics in grouped.items():
        items.append(
            ConversionSourceSnapshot(
                source=source,
                label=conversion_source_label(source),
                buy_viewed_users=len(metrics.get("buy_viewed_users", set())),
                product_selected_users=len(metrics.get("product_selected_users", set())),
                tariff_opened_users=len(metrics.get("tariff_opened_users", set())),
                offer_clicked_users=len(metrics.get("offer_clicked_users", set())),
                invoice_created_users=len(metrics.get("invoice_created_users", set())),
                paid_users=len(metrics.get("paid_users", set())),
                invite_issued_users=len(metrics.get("invite_issued_users", set())),
            )
        )
    items.sort(
        key=lambda item: (
            -item.paid_users,
            -item.invoice_created_users,
            -item.buy_viewed_users,
            item.label,
        )
    )
    return tuple(items)


async def _build_source_acquisition(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 5,
    lookback_days: int = 30,
) -> tuple[SourceAcquisitionSnapshot, ...]:
    action_names = (
        "buy_screen_viewed",
        "product_selected",
        "tariff_detail_opened",
        "offer_clicked",
        "invoice_created_stars",
        "invoice_created_crypto",
        "payment_paid_stars",
        "payment_paid_crypto",
        "invite_issued",
    )
    result = await session.execute(
        select(
            AuditLog.target_user_id,
            AuditLog.payload,
            AuditLog.created_at,
            AuditLog.id,
        )
        .where(AuditLog.action.in_(action_names))
        .where(AuditLog.target_user_id.is_not(None))
        .order_by(
            AuditLog.target_user_id.asc(),
            AuditLog.created_at.asc(),
            AuditLog.id.asc(),
        )
    )
    first_source_by_user: dict[int, str] = {}
    for target_user_id, raw_payload, _created_at, _audit_id in result.all():
        user_id = _coerce_int(target_user_id)
        if user_id is None or user_id in first_source_by_user:
            continue
        payload = _parse_payload(raw_payload)
        source = normalize_conversion_source(payload.get("source"))
        if source is None:
            continue
        first_source_by_user[user_id] = source

    if not first_source_by_user:
        return tuple()

    cohort_user_ids = set(first_source_by_user)
    paid_metrics_by_user = await _load_paid_user_metrics(session, user_ids=cohort_user_ids)
    invite_user_ids = await _load_invite_user_ids(session, user_ids=cohort_user_ids)
    current_time = ensure_aware_utc(now or utcnow())
    cutoff = current_time - timedelta(days=lookback_days)

    lifecycle_touch_rows = list(
        (
            await session.execute(
                select(
                    AuditLog.action,
                    AuditLog.target_user_id,
                    AuditLog.payload,
                    AuditLog.created_at,
                )
                .where(AuditLog.action.in_(_LIFECYCLE_TOUCH_ACTIONS))
                .where(AuditLog.target_user_id.in_(cohort_user_ids))
                .where(AuditLog.created_at >= cutoff)
            )
        ).all()
    )
    lifecycle_touches_by_user: dict[int, list[dict[str, object]]] = defaultdict(list)
    for action, target_user_id, raw_payload, created_at in lifecycle_touch_rows:
        user_id = _coerce_int(target_user_id)
        if user_id is None:
            continue
        payload = _parse_payload(raw_payload)
        rule_key, rule_label = _lifecycle_rule_from_audit(str(action), payload)
        wave_mode, wave_label = _lifecycle_wave_from_audit(payload)
        lifecycle_touches_by_user[user_id].append(
            {
                "created_at": ensure_aware_utc(created_at),
                "rule_key": rule_key,
                "rule_label": rule_label,
                "wave_mode": wave_mode,
                "wave_label": wave_label,
            }
        )
    for user_touches in lifecycle_touches_by_user.values():
        user_touches.sort(key=lambda item: item["created_at"])

    payment_history_rows = list(
        (
            await session.execute(
                select(Payment.user_id, Payment.channel_id, Payment.paid_at)
                .where(Payment.status == "paid")
                .where(Payment.user_id.in_(cohort_user_ids))
                .where(Payment.channel_id.is_not(None))
                .where(Payment.paid_at.is_not(None))
            )
        ).all()
    )
    user_channel_first_paid_at: dict[int, dict[int, datetime]] = defaultdict(dict)
    for payment_user_id, payment_channel_id, payment_paid_at in payment_history_rows:
        user_key = _coerce_int(payment_user_id)
        channel_key = _coerce_int(payment_channel_id)
        if user_key is None or channel_key is None or payment_paid_at is None:
            continue
        paid_time = ensure_aware_utc(payment_paid_at)
        previous_first_paid = user_channel_first_paid_at[user_key].get(channel_key)
        if previous_first_paid is None or paid_time < previous_first_paid:
            user_channel_first_paid_at[user_key][channel_key] = paid_time

    lifecycle_payment_rows = list(
        (
            await session.execute(
                select(
                    Payment.id,
                    Payment.user_id,
                    Payment.channel_id,
                    Payment.amount,
                    Payment.paid_at,
                )
                .where(Payment.status == "paid")
                .where(Payment.user_id.in_(cohort_user_ids))
                .where(Payment.paid_at.is_not(None))
                .where(Payment.paid_at >= cutoff)
            )
        ).all()
    )
    lifecycle_invite_rows = list(
        (
            await session.execute(
                select(InviteLink.user_id, InviteLink.created_at)
                .where(InviteLink.user_id.in_(cohort_user_ids))
                .where(InviteLink.created_at >= cutoff)
            )
        ).all()
    )

    grouped: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "label": "",
            "acquired_user_ids": set(),
            "paid_user_ids": set(),
            "invite_user_ids": set(),
            "repeat_purchase_user_ids": set(),
            "payment_count": 0,
            "first_paid_revenue_total": 0,
            "lifetime_revenue_total": 0,
            "lifecycle_paid_user_ids": set(),
            "lifecycle_payment_ids": set(),
            "lifecycle_invite_user_ids": set(),
            "lifecycle_revenue_total": 0,
            "lifecycle_second_product_user_ids": set(),
            "lifecycle_second_product_payment_ids": set(),
            "lifecycle_second_product_revenue_total": 0,
            "rule_revenue_totals": defaultdict(int),
            "wave_revenue_totals": defaultdict(int),
            "rule_labels": {},
            "wave_labels": {},
        }
    )
    for user_id, source in first_source_by_user.items():
        bucket = grouped[source]
        bucket["label"] = conversion_source_label(source)
        acquired_user_ids = bucket["acquired_user_ids"]
        if isinstance(acquired_user_ids, set):
            acquired_user_ids.add(user_id)
        if user_id in invite_user_ids:
            invite_users = bucket["invite_user_ids"]
            if isinstance(invite_users, set):
                invite_users.add(user_id)
        metrics = paid_metrics_by_user.get(user_id)
        if metrics is None:
            continue
        paid_user_ids = bucket["paid_user_ids"]
        repeat_user_ids = bucket["repeat_purchase_user_ids"]
        if isinstance(paid_user_ids, set):
            paid_user_ids.add(user_id)
        if isinstance(repeat_user_ids, set) and int(metrics["payment_count"]) > 1:
            repeat_user_ids.add(user_id)
        bucket["payment_count"] = int(bucket["payment_count"]) + int(metrics["payment_count"])
        bucket["first_paid_revenue_total"] = int(bucket["first_paid_revenue_total"]) + int(
            metrics["first_paid_revenue_total"]
        )
        bucket["lifetime_revenue_total"] = int(bucket["lifetime_revenue_total"]) + int(
            metrics["lifetime_revenue_total"]
        )

    for payment_id, payment_user_id, payment_channel_id, amount, paid_at in lifecycle_payment_rows:
        user_key = _coerce_int(payment_user_id)
        if user_key is None or paid_at is None:
            continue
        user_touches = lifecycle_touches_by_user.get(user_key)
        if not user_touches:
            continue
        payment_time = ensure_aware_utc(paid_at)
        matched = [
            touch
            for touch in user_touches
            if (
                touch["created_at"]
                <= payment_time
                <= touch["created_at"] + LIFECYCLE_ATTRIBUTION_WINDOW
            )
        ]
        if not matched:
            continue
        source = first_source_by_user.get(user_key)
        if source is None:
            continue
        touch = matched[-1]
        bucket = grouped[source]
        lifecycle_paid_user_ids = bucket["lifecycle_paid_user_ids"]
        lifecycle_payment_ids = bucket["lifecycle_payment_ids"]
        if isinstance(lifecycle_paid_user_ids, set):
            lifecycle_paid_user_ids.add(user_key)
        payment_key = _coerce_int(payment_id)
        if isinstance(lifecycle_payment_ids, set) and payment_key is not None:
            lifecycle_payment_ids.add(payment_key)
        payment_amount = int(amount or 0)
        bucket["lifecycle_revenue_total"] = int(bucket["lifecycle_revenue_total"]) + payment_amount
        rule_key = str(touch["rule_key"])
        rule_label = str(touch["rule_label"])
        wave_mode = str(touch["wave_mode"])
        wave_label = str(touch["wave_label"])
        rule_revenue_totals = bucket["rule_revenue_totals"]
        wave_revenue_totals = bucket["wave_revenue_totals"]
        rule_labels = bucket["rule_labels"]
        wave_labels = bucket["wave_labels"]
        if isinstance(rule_revenue_totals, defaultdict):
            rule_revenue_totals[rule_key] += payment_amount
        if isinstance(wave_revenue_totals, defaultdict):
            wave_revenue_totals[wave_mode] += payment_amount
        if isinstance(rule_labels, dict):
            rule_labels[rule_key] = rule_label
        if isinstance(wave_labels, dict):
            wave_labels[wave_mode] = wave_label

        payment_channel_key = _coerce_int(payment_channel_id)
        if payment_channel_key is not None:
            prior_paid_channels = [
                previous_channel_id
                for previous_channel_id, first_paid_at in (
                    user_channel_first_paid_at[user_key].items()
                )
                if previous_channel_id != payment_channel_key and first_paid_at < payment_time
            ]
            if prior_paid_channels:
                second_product_user_ids = bucket["lifecycle_second_product_user_ids"]
                second_product_payment_ids = bucket["lifecycle_second_product_payment_ids"]
                if isinstance(second_product_user_ids, set):
                    second_product_user_ids.add(user_key)
                if isinstance(second_product_payment_ids, set) and payment_key is not None:
                    second_product_payment_ids.add(payment_key)
                bucket["lifecycle_second_product_revenue_total"] = int(
                    bucket["lifecycle_second_product_revenue_total"]
                ) + payment_amount

    for invite_user_id, created_at in lifecycle_invite_rows:
        user_key = _coerce_int(invite_user_id)
        if user_key is None or created_at is None:
            continue
        user_touches = lifecycle_touches_by_user.get(user_key)
        if not user_touches:
            continue
        invite_time = ensure_aware_utc(created_at)
        matched = [
            touch
            for touch in user_touches
            if (
                touch["created_at"]
                <= invite_time
                <= touch["created_at"] + LIFECYCLE_ATTRIBUTION_WINDOW
            )
        ]
        if not matched:
            continue
        source = first_source_by_user.get(user_key)
        if source is None:
            continue
        lifecycle_invite_user_ids = grouped[source]["lifecycle_invite_user_ids"]
        if isinstance(lifecycle_invite_user_ids, set):
            lifecycle_invite_user_ids.add(user_key)

    items: list[SourceAcquisitionSnapshot] = []
    for source, bucket in grouped.items():
        rule_revenue_totals = bucket["rule_revenue_totals"]
        wave_revenue_totals = bucket["wave_revenue_totals"]
        rule_labels = bucket["rule_labels"]
        wave_labels = bucket["wave_labels"]
        top_rule_key = None
        top_rule_label = None
        top_wave_mode = None
        top_wave_label = None
        if isinstance(rule_revenue_totals, defaultdict) and rule_revenue_totals:
            top_rule_key = min(
                rule_revenue_totals,
                key=lambda key: (
                    -int(rule_revenue_totals[key]),
                    str(rule_labels.get(key) or key),
                ),
            )
            top_rule_label = str(
                rule_labels.get(top_rule_key)
                or _LIFECYCLE_RULE_LABELS.get(
                    top_rule_key,
                    top_rule_key.replace("_", " ").title(),
                )
            )
        if isinstance(wave_revenue_totals, defaultdict) and wave_revenue_totals:
            top_wave_mode = min(
                wave_revenue_totals,
                key=lambda key: (
                    -int(wave_revenue_totals[key]),
                    str(wave_labels.get(key) or key),
                ),
            )
            top_wave_label = str(
                wave_labels.get(top_wave_mode)
                or _LIFECYCLE_WAVE_LABELS.get(
                    top_wave_mode,
                    top_wave_mode.replace("_", " ").title(),
                )
            )
        items.append(
            SourceAcquisitionSnapshot(
                source=source,
                label=str(bucket["label"]),
                acquired_users=len(bucket["acquired_user_ids"]),
                paid_users=len(bucket["paid_user_ids"]),
                payment_count=int(bucket["payment_count"]),
                invite_issued_users=len(bucket["invite_user_ids"]),
                repeat_purchase_users=len(bucket["repeat_purchase_user_ids"]),
                first_paid_revenue_total=int(bucket["first_paid_revenue_total"]),
                lifetime_revenue_total=int(bucket["lifetime_revenue_total"]),
                lifecycle_paid_users=len(bucket["lifecycle_paid_user_ids"]),
                lifecycle_payment_count=len(bucket["lifecycle_payment_ids"]),
                lifecycle_invite_issued_users=len(bucket["lifecycle_invite_user_ids"]),
                lifecycle_revenue_total=int(bucket["lifecycle_revenue_total"]),
                lifecycle_second_product_paid_users=len(
                    bucket["lifecycle_second_product_user_ids"]
                ),
                lifecycle_second_product_payment_count=len(
                    bucket["lifecycle_second_product_payment_ids"]
                ),
                lifecycle_second_product_revenue_total=int(
                    bucket["lifecycle_second_product_revenue_total"]
                ),
                top_rule_key=top_rule_key,
                top_rule_label=top_rule_label,
                top_wave_mode=top_wave_mode,
                top_wave_label=top_wave_label,
            )
        )
    items.sort(
        key=lambda item: (
            -item.lifetime_revenue_total,
            -item.lifecycle_revenue_total,
            -item.paid_users,
            -item.acquired_users,
            item.label,
            item.source,
        )
    )
    return tuple(items[:limit])


async def _load_paid_user_metrics(
    session: AsyncSession,
    *,
    user_ids: set[int] | None = None,
) -> dict[int, dict[str, int]]:
    if user_ids is not None and not user_ids:
        return {}
    stmt = (
        select(Payment.user_id, Payment.amount, Payment.paid_at, Payment.id)
        .where(Payment.status == "paid")
        .order_by(Payment.user_id.asc(), Payment.paid_at.asc(), Payment.id.asc())
    )
    if user_ids is not None:
        stmt = stmt.where(Payment.user_id.in_(user_ids))
    rows = list((await session.execute(stmt)).all())
    grouped: dict[int, dict[str, int]] = defaultdict(
        lambda: {
            "payment_count": 0,
            "first_paid_revenue_total": 0,
            "lifetime_revenue_total": 0,
        }
    )
    for user_id, amount, _paid_at, _payment_id in rows:
        user_key = int(user_id)
        payment_amount = int(amount or 0)
        bucket = grouped[user_key]
        bucket["payment_count"] = int(bucket["payment_count"]) + 1
        bucket["lifetime_revenue_total"] = int(bucket["lifetime_revenue_total"]) + payment_amount
        if int(bucket["payment_count"]) == 1:
            bucket["first_paid_revenue_total"] = payment_amount
    return {user_id: dict(bucket) for user_id, bucket in grouped.items()}


async def _load_invite_user_ids(
    session: AsyncSession,
    *,
    user_ids: set[int] | None = None,
) -> set[int]:
    if user_ids is not None and not user_ids:
        return set()
    stmt = (
        select(distinct(AuditLog.target_user_id))
        .where(AuditLog.action == "invite_issued")
        .where(AuditLog.target_user_id.is_not(None))
    )
    if user_ids is not None:
        stmt = stmt.where(AuditLog.target_user_id.in_(user_ids))
    rows = list((await session.execute(stmt)).scalars())
    return {int(user_id) for user_id in rows if user_id is not None}


async def _build_pricing_intelligence(
    session: AsyncSession,
    *,
    channel_titles: dict[int, str],
    now: datetime | None = None,
    limit: int = 5,
) -> PricingIntelligenceSnapshot:
    tariff_rows = list(
        (
            await session.execute(
                select(
                    Tariff.id,
                    Tariff.name,
                    Tariff.channel_id,
                    Tariff.price_stars,
                    Tariff.duration_days,
                    Tariff.offer_group,
                    Tariff.is_featured,
                    Tariff.is_default_offer,
                    Tariff.offer_expires_at,
                )
            )
        ).all()
    )
    tariffs_by_id = {
        int(tariff_id): {
            "tariff_name": safe_ui_text(tariff_name, f"????? #{tariff_id}"),
            "channel_id": int(channel_id),
            "channel_title": channel_titles.get(int(channel_id), f"????? #{channel_id}"),
            "offer_group": normalize_offer_group(offer_group),
            "price_stars": int(price_stars or 0),
            "duration_days": int(duration_days or 0),
            "is_featured": bool(is_featured),
            "is_default_offer": bool(is_default_offer),
            "offer_expires_at": (
                ensure_aware_utc(offer_expires_at)
                if offer_expires_at is not None
                else None
            ),
        }
        for (
            tariff_id,
            tariff_name,
            channel_id,
            price_stars,
            duration_days,
            offer_group,
            is_featured,
            is_default_offer,
            offer_expires_at,
        ) in tariff_rows
    }

    opened_by_tariff = await _audit_targets_by_tariff(
        session,
        actions=("tariff_detail_opened",),
    )
    clicked_by_tariff = await _audit_targets_by_tariff(
        session,
        actions=("offer_clicked",),
    )
    invoice_by_tariff = await _audit_targets_by_tariff(
        session,
        actions=("invoice_created_stars", "invoice_created_crypto"),
    )

    payment_rows = list(
        (
            await session.execute(
                select(
                    Payment.user_id,
                    Payment.tariff_id,
                    Payment.channel_id,
                    Payment.amount,
                    Payment.provider,
                    Payment.paid_at,
                ).where(Payment.status == "paid")
            )
        ).all()
    )

    payment_metrics: dict[int, dict[str, object]] = defaultdict(
        lambda: {
            "paid_user_ids": set(),
            "payment_count": 0,
            "revenue_total": 0,
        }
    )
    lifecycle_touch_rows = list(
        (
            await session.execute(
                select(
                    AuditLog.action,
                    AuditLog.target_user_id,
                    AuditLog.payload,
                    AuditLog.created_at,
                )
                .where(AuditLog.action.in_(_LIFECYCLE_TOUCH_ACTIONS))
                .where(AuditLog.target_user_id.is_not(None))
            )
        ).all()
    )
    user_channels: dict[int, set[int]] = defaultdict(set)
    channel_paid_users: dict[int, set[int]] = defaultdict(set)
    user_channel_revenue: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    user_channel_first_paid_at: dict[int, dict[int, datetime]] = defaultdict(dict)
    lifecycle_touches_by_user: dict[int, list[dict[str, object]]] = defaultdict(list)
    normalized_payment_rows: list[dict[str, object]] = []
    current_time = ensure_aware_utc(now or utcnow())
    for action, target_user_id, raw_payload, created_at in lifecycle_touch_rows:
        if target_user_id is None:
            continue
        payload = _parse_payload(raw_payload)
        rule_key, rule_label = _lifecycle_rule_from_audit(action, payload)
        wave_mode, wave_label = _lifecycle_wave_from_audit(payload)
        lifecycle_touches_by_user[int(target_user_id)].append(
            {
                "created_at": ensure_aware_utc(created_at),
                "rule_key": rule_key,
                "rule_label": rule_label,
                "wave_mode": wave_mode,
                "wave_label": wave_label,
            }
        )
    for user_touches in lifecycle_touches_by_user.values():
        user_touches.sort(key=lambda item: item["created_at"])

    total_revenue = 0
    total_payment_count = 0
    stars_revenue_total = 0
    crypto_revenue_total = 0
    featured_revenue_total = 0
    default_revenue_total = 0
    limited_revenue_total = 0

    for user_id, tariff_id, channel_id, amount, provider, paid_at in payment_rows:
        if user_id is None or tariff_id is None or channel_id is None:
            continue
        user_key = int(user_id)
        tariff_key = int(tariff_id)
        channel_key = int(channel_id)
        amount_value = int(amount or 0)
        user_channels[user_key].add(channel_key)
        channel_paid_users[channel_key].add(user_key)
        user_channel_revenue[user_key][channel_key] += amount_value
        paid_at_value = ensure_aware_utc(paid_at or current_time)
        normalized_payment_rows.append(
            {
                "user_id": user_key,
                "channel_id": channel_key,
                "amount": amount_value,
                "paid_at": paid_at_value,
            }
        )
        first_paid_at = user_channel_first_paid_at[user_key].get(channel_key)
        if first_paid_at is None or paid_at_value < first_paid_at:
            user_channel_first_paid_at[user_key][channel_key] = paid_at_value
        total_revenue += amount_value
        total_payment_count += 1
        if provider == "telegram_stars":
            stars_revenue_total += amount_value
        elif isinstance(provider, str) and provider.startswith("crypto"):
            crypto_revenue_total += amount_value

        metrics = payment_metrics[tariff_key]
        paid_user_ids = metrics["paid_user_ids"]
        if isinstance(paid_user_ids, set):
            paid_user_ids.add(user_key)
        metrics["payment_count"] = int(metrics["payment_count"]) + 1
        metrics["revenue_total"] = int(metrics["revenue_total"]) + amount_value

        tariff_meta = tariffs_by_id.get(tariff_key)
        if tariff_meta is not None:
            if bool(tariff_meta["is_featured"]):
                featured_revenue_total += amount_value
            if bool(tariff_meta["is_default_offer"]):
                default_revenue_total += amount_value
            if (
                bool(tariff_meta.get("offer_expires_at"))
                and tariff_meta["offer_expires_at"] > current_time
            ):
                limited_revenue_total += amount_value

    all_tariff_ids = set(tariffs_by_id)
    all_tariff_ids.update(opened_by_tariff)
    all_tariff_ids.update(clicked_by_tariff)
    all_tariff_ids.update(invoice_by_tariff)
    all_tariff_ids.update(payment_metrics)

    offers: list[OfferPerformanceSnapshot] = []
    for tariff_id in all_tariff_ids:
        tariff_meta = tariffs_by_id.get(int(tariff_id))
        payment_bucket = payment_metrics.get(int(tariff_id), {})
        opened_users = len(opened_by_tariff.get(int(tariff_id), set()))
        clicked_users = len(clicked_by_tariff.get(int(tariff_id), set()))
        invoice_created_users = len(invoice_by_tariff.get(int(tariff_id), set()))
        paid_user_ids = payment_bucket.get("paid_user_ids", set())
        paid_users = len(paid_user_ids if isinstance(paid_user_ids, set) else set())
        payment_count = int(payment_bucket.get("payment_count", 0) or 0)
        revenue_total = int(payment_bucket.get("revenue_total", 0) or 0)
        if not any(
            (
                opened_users,
                clicked_users,
                invoice_created_users,
                paid_users,
                payment_count,
                revenue_total,
            )
        ):
            continue
        channel_id = int(tariff_meta["channel_id"]) if tariff_meta is not None else 0
        offers.append(
            OfferPerformanceSnapshot(
                tariff_id=int(tariff_id),
                tariff_name=(
                    str(tariff_meta["tariff_name"])
                    if tariff_meta is not None
                    else f"????? #{tariff_id}"
                ),
                channel_id=channel_id,
                channel_title=(
                    str(tariff_meta["channel_title"])
                    if tariff_meta is not None
                    else f"????? #{channel_id or '?'}"
                ),
                offer_group=(
                    str(tariff_meta["offer_group"])
                    if tariff_meta is not None and tariff_meta["offer_group"] is not None
                    else None
                ),
                price_stars=(
                    int(tariff_meta["price_stars"]) if tariff_meta is not None else 0
                ),
                duration_days=(
                    int(tariff_meta["duration_days"]) if tariff_meta is not None else 0
                ),
                is_featured=(
                    bool(tariff_meta["is_featured"]) if tariff_meta is not None else False
                ),
                is_default_offer=(
                    bool(tariff_meta["is_default_offer"]) if tariff_meta is not None else False
                ),
                is_limited_time=(
                    bool(tariff_meta.get("offer_expires_at"))
                    and tariff_meta["offer_expires_at"] > current_time
                    if tariff_meta is not None
                    else False
                ),
                offer_expires_at=(
                    tariff_meta.get("offer_expires_at") if tariff_meta is not None else None
                ),
                opened_users=opened_users,
                clicked_users=clicked_users,
                invoice_created_users=invoice_created_users,
                paid_users=paid_users,
                payment_count=payment_count,
                revenue_total=revenue_total,
            )
        )

    offers.sort(
        key=lambda item: (
            -item.revenue_total,
            -item.paid_users,
            -item.clicked_users,
            -item.invoice_created_users,
            item.tariff_name,
            item.tariff_id,
        )
    )
    top_revenue_offer = offers[0] if offers else None
    convertible_offers = [item for item in offers if item.clicked_users > 0]
    top_conversion_offer = (
        max(
            convertible_offers,
            key=lambda item: (
                item.click_to_paid_percent,
                item.paid_users,
                item.revenue_total,
                item.clicked_users,
                -item.tariff_id,
            ),
        )
        if convertible_offers
        else None
    )
    multi_product_paid_users = sum(1 for channels in user_channels.values() if len(channels) > 1)

    pair_buckets: dict[tuple[int, int], dict[str, object]] = defaultdict(
        lambda: {
            "user_ids": set(),
            "secondary_revenue_total": 0,
            "pair_revenue_total": 0,
        }
    )
    for user_id, channels in user_channels.items():
        if len(channels) < 2:
            continue
        ordered_channels = sorted(
            channels,
            key=lambda channel_key: (
                user_channel_first_paid_at[user_id].get(channel_key, current_time),
                channel_key,
            ),
        )
        for index, primary_channel in enumerate(ordered_channels[:-1]):
            primary_revenue = int(user_channel_revenue[user_id].get(primary_channel, 0) or 0)
            for secondary_channel in ordered_channels[index + 1 :]:
                secondary_revenue = int(
                    user_channel_revenue[user_id].get(secondary_channel, 0) or 0
                )
                bucket = pair_buckets[(primary_channel, secondary_channel)]
                user_ids = bucket["user_ids"]
                if isinstance(user_ids, set) and user_id not in user_ids:
                    user_ids.add(user_id)
                    bucket["secondary_revenue_total"] = int(
                        bucket["secondary_revenue_total"]
                    ) + secondary_revenue
                    bucket["pair_revenue_total"] = int(bucket["pair_revenue_total"]) + (
                        primary_revenue + secondary_revenue
                    )

    top_product_pairs = [
        ProductPairPerformanceSnapshot(
            primary_channel_id=primary_channel,
            primary_channel_title=channel_titles.get(
                primary_channel,
                f"????? #{primary_channel}",
            ),
            secondary_channel_id=secondary_channel,
            secondary_channel_title=channel_titles.get(
                secondary_channel,
                f"????? #{secondary_channel}",
            ),
            attached_paid_users=len(bucket["user_ids"]),
            base_paid_users=len(channel_paid_users.get(primary_channel, set())),
            secondary_revenue_total=int(bucket["secondary_revenue_total"]),
            pair_revenue_total=int(bucket["pair_revenue_total"]),
        )
        for (primary_channel, secondary_channel), bucket in pair_buckets.items()
        if bucket["user_ids"]
    ]
    top_product_pairs.sort(
        key=lambda item: (
            -item.attached_paid_users,
            -item.attach_rate_percent,
            -item.secondary_revenue_total,
            -item.pair_revenue_total,
            item.primary_channel_title,
            item.secondary_channel_title,
        )
    )

    pair_campaign_buckets: dict[tuple[int, int, str, str], dict[str, object]] = defaultdict(
        lambda: {
            "user_ids": set(),
            "payment_count": 0,
            "secondary_revenue_total": 0,
            "rule_label": "",
            "wave_label": "",
        }
    )
    for payment_row in normalized_payment_rows:
        user_key = int(payment_row["user_id"])
        secondary_channel = int(payment_row["channel_id"])
        paid_at_value = ensure_aware_utc(payment_row["paid_at"])
        amount_value = int(payment_row["amount"])
        user_touches = lifecycle_touches_by_user.get(user_key)
        if not user_touches:
            continue
        matched_touches = [
            touch
            for touch in user_touches
            if (
                touch["created_at"]
                <= paid_at_value
                <= touch["created_at"] + LIFECYCLE_ATTRIBUTION_WINDOW
            )
        ]
        if not matched_touches:
            continue
        touch = matched_touches[-1]
        primary_channels = [
            channel_key
            for channel_key, first_paid_at in user_channel_first_paid_at[user_key].items()
            if channel_key != secondary_channel and first_paid_at < paid_at_value
        ]
        if not primary_channels:
            continue
        for primary_channel in sorted(primary_channels):
            bucket = pair_campaign_buckets[
                (
                    primary_channel,
                    secondary_channel,
                    str(touch["rule_key"]),
                    str(touch["wave_mode"]),
                )
            ]
            user_ids = bucket["user_ids"]
            if isinstance(user_ids, set):
                user_ids.add(user_key)
            bucket["payment_count"] = int(bucket["payment_count"]) + 1
            bucket["secondary_revenue_total"] = (
                int(bucket["secondary_revenue_total"]) + amount_value
            )
            bucket["rule_label"] = str(touch["rule_label"])
            bucket["wave_label"] = str(touch["wave_label"])

    top_pair_campaigns = [
        ProductPairCampaignSnapshot(
            primary_channel_id=primary_channel,
            primary_channel_title=channel_titles.get(
                primary_channel,
                f"????? #{primary_channel}",
            ),
            secondary_channel_id=secondary_channel,
            secondary_channel_title=channel_titles.get(
                secondary_channel,
                f"????? #{secondary_channel}",
            ),
            rule_key=rule_key,
            rule_label=str(bucket["rule_label"]),
            wave_mode=wave_mode,
            wave_label=str(bucket["wave_label"]),
            attached_paid_users=len(bucket["user_ids"]),
            base_paid_users=len(channel_paid_users.get(primary_channel, set())),
            payment_count=int(bucket["payment_count"]),
            secondary_revenue_total=int(bucket["secondary_revenue_total"]),
        )
        for (
            primary_channel,
            secondary_channel,
            rule_key,
            wave_mode,
        ), bucket in pair_campaign_buckets.items()
        if bucket["user_ids"]
    ]
    top_pair_campaigns.sort(
        key=lambda item: (
            -item.secondary_revenue_total,
            -item.attached_paid_users,
            -item.attach_rate_percent,
            -item.payment_count,
            item.primary_channel_title,
            item.secondary_channel_title,
            item.rule_label,
        )
    )

    active_limited_offer_count = sum(
        1
        for tariff_meta in tariffs_by_id.values()
        if bool(tariff_meta.get("offer_expires_at"))
        and tariff_meta["offer_expires_at"] > current_time
    )

    return PricingIntelligenceSnapshot(
        average_payment_amount=(
            int(total_revenue / total_payment_count) if total_payment_count > 0 else 0
        ),
        stars_revenue_total=stars_revenue_total,
        crypto_revenue_total=crypto_revenue_total,
        stars_revenue_share_percent=_percent(stars_revenue_total, total_revenue),
        crypto_revenue_share_percent=_percent(crypto_revenue_total, total_revenue),
        multi_product_paid_users=multi_product_paid_users,
        multi_product_attach_rate_percent=_percent(multi_product_paid_users, len(user_channels)),
        featured_revenue_total=featured_revenue_total,
        default_revenue_total=default_revenue_total,
        limited_revenue_total=limited_revenue_total,
        active_limited_offer_count=active_limited_offer_count,
        top_product_pairs=tuple(top_product_pairs[:limit]),
        top_pair_campaigns=tuple(top_pair_campaigns[:limit]),
        top_offers=tuple(offers[:limit]),
        top_revenue_offer=top_revenue_offer,
        top_conversion_offer=top_conversion_offer,
    )


async def _build_promo_attribution(session: AsyncSession) -> PromoAttributionSnapshot:
    result = await session.execute(
        select(PromoRedemption, PromoCode)
        .join(PromoCode, PromoCode.id == PromoRedemption.promo_code_id)
        .where(PromoRedemption.status == "consumed")
        .where(PromoRedemption.payment_id.is_not(None))
    )
    grouped: dict[int, dict[str, object]] = {}
    total_paid_users: set[int] = set()
    total_payment_count = 0
    gross_revenue_total = 0
    revenue_total = 0
    discount_total = 0
    for redemption, promo_code in result.all():
        total_paid_users.add(int(redemption.user_id))
        total_payment_count += 1
        bucket = grouped.setdefault(
            int(promo_code.id),
            {
                "label": safe_ui_text(promo_code.campaign_name, promo_code.code),
                "campaign_name": promo_code.campaign_name,
                "user_ids": set(),
                "payment_count": 0,
                "gross_revenue_total": 0,
                "revenue_total": 0,
                "discount_total": 0,
            },
        )
        bucket["user_ids"].add(int(redemption.user_id))
        bucket["payment_count"] = int(bucket["payment_count"]) + 1
        amount_before = int(redemption.amount_before or redemption.amount_after or 0)
        amount_after = int(redemption.amount_after or redemption.amount_before or 0)
        applied_discount = max(amount_before - amount_after, 0)
        bucket["gross_revenue_total"] = int(bucket["gross_revenue_total"]) + amount_before
        bucket["revenue_total"] = int(bucket["revenue_total"]) + amount_after
        bucket["discount_total"] = int(bucket["discount_total"]) + applied_discount
        gross_revenue_total += amount_before
        revenue_total += amount_after
        discount_total += applied_discount

    paid_metrics_by_user = await _load_paid_user_metrics(session, user_ids=total_paid_users)
    campaigns = []
    for promo_code_id, bucket in grouped.items():
        user_ids = bucket["user_ids"]
        repeat_purchase_users = 0
        lifetime_revenue_total = 0
        if isinstance(user_ids, set):
            for user_id in user_ids:
                metrics = paid_metrics_by_user.get(int(user_id))
                if metrics is None:
                    continue
                lifetime_revenue_total += int(metrics["lifetime_revenue_total"])
                if int(metrics["payment_count"]) > 1:
                    repeat_purchase_users += 1
        campaigns.append(
            PromoCampaignSnapshot(
                promo_code_id=promo_code_id,
                label=str(bucket["label"]),
                campaign_name=(
                    str(bucket["campaign_name"])
                    if isinstance(bucket["campaign_name"], str)
                    else None
                ),
                paid_users=len(bucket["user_ids"]),
                payment_count=int(bucket["payment_count"]),
                repeat_purchase_users=repeat_purchase_users,
                gross_revenue_total=int(bucket["gross_revenue_total"]),
                revenue_total=int(bucket["revenue_total"]),
                discount_total=int(bucket["discount_total"]),
                lifetime_revenue_total=lifetime_revenue_total,
            )
        )
    campaigns.sort(
        key=lambda item: (-item.revenue_total, -item.payment_count, item.label, item.promo_code_id)
    )
    return PromoAttributionSnapshot(
        total_paid_users=len(total_paid_users),
        total_payment_count=total_payment_count,
        gross_revenue_total=gross_revenue_total,
        revenue_total=revenue_total,
        discount_total=discount_total,
        campaigns=tuple(campaigns),
    )


async def _build_referral_attribution(
    session: AsyncSession,
    *,
    limit: int = 5,
) -> ReferralAttributionSnapshot:
    result = await session.execute(
        select(
            User.id,
            User.referred_by_user_id,
            User.referral_reward_granted_at,
        ).where(User.referred_by_user_id.is_not(None))
    )
    invited_rows = list(result.all())
    total_referred_users = len(invited_rows)
    paid_referred_users = sum(
        1
        for _user_id, _referrer_id, rewarded_at in invited_rows
        if rewarded_at is not None
    )
    rewarded_referrals_count = paid_referred_users

    grouped: dict[int, dict[str, int]] = defaultdict(lambda: {"invited": 0, "paid": 0})
    referrer_ids: set[int] = set()
    referred_user_ids: set[int] = set()
    referred_user_to_referrer: dict[int, int] = {}
    for user_id, referrer_id, rewarded_at in invited_rows:
        if referrer_id is None:
            continue
        referred_user_key = int(user_id)
        referrer_key = int(referrer_id)
        referrer_ids.add(referrer_key)
        referred_user_ids.add(referred_user_key)
        referred_user_to_referrer[referred_user_key] = referrer_key
        grouped[referrer_key]["invited"] += 1
        if rewarded_at is not None:
            grouped[referrer_key]["paid"] += 1

    paid_metrics_by_user = await _load_paid_user_metrics(session, user_ids=referred_user_ids)
    first_paid_revenue_by_user = {
        user_id: int(metrics["first_paid_revenue_total"])
        for user_id, metrics in paid_metrics_by_user.items()
    }
    lifetime_revenue_by_user = {
        user_id: int(metrics["lifetime_revenue_total"])
        for user_id, metrics in paid_metrics_by_user.items()
    }

    reward_days_by_referrer: dict[int, int] = defaultdict(int)
    reward_rows = list(
        (
            await session.execute(
                select(AuditLog.target_user_id, AuditLog.payload).where(
                    AuditLog.action == "referral_reward_granted"
                )
            )
        ).all()
    )
    for target_user_id, raw_payload in reward_rows:
        referrer_id = _coerce_int(target_user_id)
        if referrer_id is None:
            continue
        payload = _parse_payload(raw_payload)
        reward_days_by_referrer[referrer_id] += int(payload.get("reward_days", 0) or 0)

    referrers_by_id: dict[int, User] = {}
    if referrer_ids:
        referrer_result = await session.execute(select(User).where(User.id.in_(referrer_ids)))
        referrers_by_id = {int(user.id): user for user in referrer_result.scalars()}

    first_paid_revenue_total = sum(first_paid_revenue_by_user.values())
    lifetime_referred_revenue_total = sum(lifetime_revenue_by_user.values())
    reward_days_issued_total = sum(reward_days_by_referrer.values())

    revenue_by_referrer: dict[int, dict[str, int]] = defaultdict(
        lambda: {
            "first_paid_revenue_total": 0,
            "lifetime_revenue_total": 0,
            "repeat_purchase_referred_users": 0,
        }
    )
    for referred_user_id, referrer_id in referred_user_to_referrer.items():
        first_paid_revenue = first_paid_revenue_by_user.get(referred_user_id, 0)
        lifetime_revenue = lifetime_revenue_by_user.get(referred_user_id, 0)
        revenue_by_referrer[referrer_id]["first_paid_revenue_total"] += first_paid_revenue
        revenue_by_referrer[referrer_id]["lifetime_revenue_total"] += lifetime_revenue
        user_paid_metrics = paid_metrics_by_user.get(referred_user_id)
        if user_paid_metrics is not None and int(user_paid_metrics["payment_count"]) > 1:
            revenue_by_referrer[referrer_id]["repeat_purchase_referred_users"] += 1

    top_referrers: list[ReferralTopReferrerSnapshot] = []
    pending_reward_days_total = 0
    for referrer_id, metrics in grouped.items():
        referrer = referrers_by_id.get(referrer_id)
        if referrer is None:
            continue
        pending_reward_days = int(referrer.pending_referral_reward_days or 0)
        pending_reward_days_total += pending_reward_days
        revenue_metrics = revenue_by_referrer.get(referrer_id, {})
        top_referrers.append(
            ReferralTopReferrerSnapshot(
                user_id=referrer_id,
                telegram_id=int(referrer.telegram_id),
                display_name=_display_user_label(referrer),
                invited_users_count=int(metrics["invited"]),
                paid_referrals_count=int(metrics["paid"]),
                repeat_purchase_referred_users=int(
                    revenue_metrics.get("repeat_purchase_referred_users", 0)
                ),
                pending_reward_days=pending_reward_days,
                reward_days_issued=int(reward_days_by_referrer.get(referrer_id, 0)),
                first_paid_revenue_total=int(revenue_metrics.get("first_paid_revenue_total", 0)),
                lifetime_revenue_total=int(revenue_metrics.get("lifetime_revenue_total", 0)),
            )
        )
    top_referrers.sort(
        key=lambda item: (
            -item.lifetime_revenue_total,
            -item.paid_referrals_count,
            -item.invited_users_count,
            -item.repeat_purchase_referred_users,
            -item.pending_reward_days,
            item.display_name,
            item.user_id,
        )
    )

    suspicious_event_count = int(
        (
            await session.execute(
                select(func.count(AuditLog.id)).where(AuditLog.action == "referral_suspicious")
            )
        ).scalar_one()
        or 0
    )

    return ReferralAttributionSnapshot(
        total_referred_users=total_referred_users,
        paid_referred_users=paid_referred_users,
        rewarded_referrals_count=rewarded_referrals_count,
        suspicious_event_count=suspicious_event_count,
        pending_reward_days_total=pending_reward_days_total,
        reward_days_issued_total=reward_days_issued_total,
        first_paid_revenue_total=first_paid_revenue_total,
        lifetime_referred_revenue_total=lifetime_referred_revenue_total,
        top_referrers=tuple(top_referrers[:limit]),
    )


async def _build_lifecycle_queue_snapshot(
    session: AsyncSession,
    *,
    now: datetime,
) -> LifecycleQueueSnapshot:
    rows = list(
        (
            await session.execute(
                select(
                    Subscription.user_id,
                    Subscription.status,
                    Subscription.revoked_at,
                    Subscription.expires_at,
                    Subscription.warning_3d_sent_at,
                    Subscription.warning_1d_sent_at,
                    Subscription.expired_notice_sent_at,
                    Subscription.grace_revoke_after,
                )
            )
        ).all()
    )
    renewal_due_3d_users: set[int] = set()
    renewal_due_1d_users: set[int] = set()
    grace_period_users: set[int] = set()
    active_user_ids: set[int] = set()
    latest_expired_by_user: dict[int, datetime] = {}

    for (
        user_id,
        status,
        revoked_at,
        expires_at,
        warning_3d_sent_at,
        warning_1d_sent_at,
        _expired_notice_sent_at,
        grace_revoke_after,
    ) in rows:
        user_key = int(user_id)
        aware_expires_at = ensure_aware_utc(expires_at)
        if status == "active" and revoked_at is None and aware_expires_at > now:
            active_user_ids.add(user_key)
            if aware_expires_at <= now + timedelta(days=1) and warning_1d_sent_at is None:
                renewal_due_1d_users.add(user_key)
            elif aware_expires_at <= now + timedelta(days=3) and warning_3d_sent_at is None:
                renewal_due_3d_users.add(user_key)
        if (
            grace_revoke_after is not None
            and revoked_at is None
            and aware_expires_at <= now
            and ensure_aware_utc(grace_revoke_after) > now
        ):
            grace_period_users.add(user_key)
        if aware_expires_at <= now:
            previous = latest_expired_by_user.get(user_key)
            if previous is None or aware_expires_at > previous:
                latest_expired_by_user[user_key] = aware_expires_at

    win_back_ready_users = 0
    for user_id, expired_at in latest_expired_by_user.items():
        if user_id in active_user_ids:
            continue
        expired_delta = now - expired_at
        if RECENT_EXPIRED_MIN_AGE <= expired_delta <= RECENT_EXPIRED_MAX_AGE:
            win_back_ready_users += 1

    return LifecycleQueueSnapshot(
        renewal_due_3d_users=len(renewal_due_3d_users),
        renewal_due_1d_users=len(renewal_due_1d_users),
        grace_period_users=len(grace_period_users),
        win_back_ready_users=win_back_ready_users,
    )


_LIFECYCLE_TOUCH_ACTIONS = (
    "retention_first_payment_follow_up_sent",
    "retention_pending_join_sent",
    "retention_win_back_sent",
    "retention_inactive_paid_sent",
    "retention_lost_after_trial_sent",
    "subscription_warning_3d_sent",
    "subscription_warning_1d_sent",
    "subscription_expired_notice_sent",
    "subscription_expired",
)
LIFECYCLE_ATTRIBUTION_WINDOW = timedelta(days=14)


_LIFECYCLE_VARIANT_LABELS = {
    "trial_to_paid": "Trial -> paid",
    "trial_to_limited": "Trial -> limited",
    "trial_to_bundle": "Trial -> bundle",
    "win_back_recent": "Win-back recent",
    "win_back_limited": "Win-back limited",
    "win_back_bundle": "Win-back bundle",
    "reactivation": "Reactivation",
    "reactivation_limited": "Reactivation limited",
    "reactivation_bundle": "Reactivation bundle",
    "renewal": "Renewal",
    "renewal_limited": "Renewal limited",
    "renewal_bundle": "Renewal bundle",
    "expired_grace": "Grace recovery",
    "expired_grace_limited": "Grace limited",
    "expired_grace_bundle": "Grace bundle",
    "expired_final": "Final win-back",
    "expired_final_limited": "Final limited",
    "expired_final_bundle": "Final bundle",
}

_LIFECYCLE_FAMILY_LABELS = {
    "first_follow_up": "First payment",
    "pending_join": "Pending join",
    "renewal": "Renewal",
    "grace": "Grace period",
    "win_back": "Win-back",
    "inactive_paid": "Inactive paid",
    "lost_after_trial": "Lost after trial",
    "expired_final": "Final expiry",
}

_LIFECYCLE_RULE_LABELS = {
    "first_follow_up_nudge": "First payment follow-up",
    "pending_join_nudge": "Pending join nudge",
    "trial_recovery_wave": "Trial recovery wave",
    "win_back_wave": "Win-back wave",
    "reactivation_wave": "Reactivation wave",
    "renewal_wave": "Renewal wave",
    "grace_recovery_wave": "Grace recovery wave",
    "final_reactivation_wave": "Final reactivation wave",
}

_LIFECYCLE_RULE_FALLBACKS = {
    "retention_first_payment_follow_up_sent": "first_follow_up_nudge",
    "retention_pending_join_sent": "pending_join_nudge",
    "retention_lost_after_trial_sent": "trial_recovery_wave",
    "retention_win_back_sent": "win_back_wave",
    "retention_inactive_paid_sent": "reactivation_wave",
    "subscription_warning_3d_sent": "renewal_wave",
    "subscription_warning_1d_sent": "renewal_wave",
    "subscription_expired_notice_sent": "grace_recovery_wave",
    "subscription_expired": "final_reactivation_wave",
}

_LIFECYCLE_WAVE_LABELS = dict(CAMPAIGN_WAVE_LABELS)

_LIFECYCLE_HIGHLIGHT_SCOPE_LABELS = {
    "rules": "Managed wave",
    "waves": "Wave mode",
    "families": "Touch family",
    "variants": "Campaign variant",
}

_LIFECYCLE_HIGHLIGHT_METRIC_LABELS = {
    "top_paid_conversion": "Best paid conversion",
    "top_revenue": "Top revenue",
    "watch_paid_conversion": "Needs attention",
}

_SOURCE_CAMPAIGN_HIGHLIGHT_METRIC_LABELS = {
    "top_paid_conversion": "Best paid conversion",
    "top_revenue": "Top revenue",
    "top_second_product_attach": "Best second-product attach",
    "watch_paid_conversion": "Needs attention",
}

_SOURCE_CAMPAIGN_WATCHLIST_METRIC_LABELS = {
    "largest_source_paid_gap": "Largest paid-user gap",
    "largest_invite_gap": "Invite follow-through gap",
    "largest_second_product_gap": "Second-product opportunity",
}

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

_LIFECYCLE_HIGHLIGHT_MIN_SENT_COUNT = 2


def _lifecycle_touch_family(action: str) -> str:
    if action in {"subscription_warning_3d_sent", "subscription_warning_1d_sent"}:
        return "renewal"
    if action == "subscription_expired_notice_sent":
        return "grace"
    if action == "subscription_expired":
        return "expired_final"
    if action == "retention_first_payment_follow_up_sent":
        return "first_follow_up"
    if action == "retention_pending_join_sent":
        return "pending_join"
    if action == "retention_win_back_sent":
        return "win_back"
    if action == "retention_inactive_paid_sent":
        return "inactive_paid"
    if action == "retention_lost_after_trial_sent":
        return "lost_after_trial"
    return action


def _lifecycle_rule_from_audit(action: str, payload: dict[str, object]) -> tuple[str, str]:
    rule_key = payload.get("campaign_rule_key")
    if isinstance(rule_key, str) and rule_key:
        label = payload.get("campaign_rule_label")
        if isinstance(label, str) and label:
            return rule_key, label
        return rule_key, _LIFECYCLE_RULE_LABELS.get(rule_key, rule_key.replace("_", " ").title())
    fallback_key = _LIFECYCLE_RULE_FALLBACKS.get(action, action)
    return fallback_key, _LIFECYCLE_RULE_LABELS.get(
        fallback_key,
        fallback_key.replace("_", " ").title(),
    )


def _lifecycle_wave_from_audit(payload: dict[str, object]) -> tuple[str, str]:
    wave_mode = payload.get("campaign_wave_mode")
    if isinstance(wave_mode, str) and wave_mode:
        label = payload.get("campaign_wave_label")
        if isinstance(label, str) and label:
            return wave_mode, label
        return wave_mode, _LIFECYCLE_WAVE_LABELS.get(wave_mode, wave_mode.replace("_", " ").title())

    primary_source = payload.get("primary_offer_source")
    bundle_count = int(payload.get("bundle_count", 0) or 0)
    has_bundle_extras = bundle_count > 0
    fallback_mode = "recommended_wave"
    if primary_source == "limited" or bool(payload.get("limited_primary")):
        fallback_mode = "limited_bundle_wave" if has_bundle_extras else "limited_wave"
    elif primary_source == "bundle" or bool(payload.get("bundle_primary")):
        fallback_mode = "bundle_primary_wave"
    elif primary_source == "cross_sell":
        fallback_mode = "cross_sell_bundle_wave" if has_bundle_extras else "cross_sell_wave"
    elif has_bundle_extras:
        fallback_mode = "recommended_bundle_wave"
    return fallback_mode, _LIFECYCLE_WAVE_LABELS.get(
        fallback_mode,
        fallback_mode.replace("_", " ").title(),
    )


def _new_lifecycle_metric_bucket(label: str) -> dict[str, object]:
    return {
        "label": label,
        "sent_count": 0,
        "limited_primary_count": 0,
        "bundle_primary_count": 0,
        "bundle_extra_touch_count": 0,
        "cross_sell_touch_count": 0,
        "paid_user_ids": set(),
        "payment_ids": set(),
        "invite_user_ids": set(),
        "revenue_total": 0,
        "variant_sent_counts": defaultdict(int),
        "family_sent_counts": defaultdict(int),
        "rule_sent_counts": defaultdict(int),
        "second_product_user_ids": set(),
        "second_product_payment_ids": set(),
        "second_product_revenue_total": 0,
        "secondary_channel_counts": defaultdict(int),
    }


async def _build_lifecycle_offer_mix(
    session: AsyncSession,
    *,
    now: datetime,
    lookback_days: int = 30,
) -> LifecycleOfferMixSnapshot:
    cutoff = now - timedelta(days=lookback_days)
    rows = list(
        (
            await session.execute(
                select(AuditLog.action, AuditLog.payload, AuditLog.created_at)
                .where(AuditLog.action.in_(_LIFECYCLE_TOUCH_ACTIONS))
                .where(AuditLog.created_at >= cutoff)
            )
        ).all()
    )

    total_sent_count = 0
    limited_primary_count = 0
    bundle_primary_count = 0
    bundle_extra_touch_count = 0
    cross_sell_touch_count = 0
    variant_counts: dict[str, int] = defaultdict(int)

    for action, raw_payload, created_at in rows:
        if ensure_aware_utc(created_at) < cutoff:
            continue
        payload = _parse_payload(raw_payload)
        total_sent_count += 1
        if bool(payload.get("limited_primary")):
            limited_primary_count += 1
        if bool(payload.get("bundle_primary")):
            bundle_primary_count += 1
        if int(payload.get("bundle_count", 0) or 0) > 0:
            bundle_extra_touch_count += 1
        if int(payload.get("cross_sell_count", 0) or 0) > 0:
            cross_sell_touch_count += 1
        variant = payload.get("offer_strategy") or payload.get("campaign_variant") or str(action)
        if isinstance(variant, str) and variant:
            variant_counts[variant] += 1

    variants = [
        LifecycleOfferVariantSnapshot(
            variant=variant,
            label=_LIFECYCLE_VARIANT_LABELS.get(variant, variant.replace("_", " ").title()),
            sent_count=sent_count,
        )
        for variant, sent_count in variant_counts.items()
    ]
    variants.sort(key=lambda item: (-item.sent_count, item.label, item.variant))
    return LifecycleOfferMixSnapshot(
        total_sent_count=total_sent_count,
        limited_primary_count=limited_primary_count,
        bundle_primary_count=bundle_primary_count,
        bundle_extra_touch_count=bundle_extra_touch_count,
        cross_sell_touch_count=cross_sell_touch_count,
        variants=tuple(variants[:5]),
    )


LifecycleHighlightItem = (
    LifecycleCampaignPerformanceSnapshot
    | LifecycleCampaignFamilySnapshot
    | LifecycleCampaignRuleSnapshot
    | LifecycleCampaignWaveSnapshot
)



def _lifecycle_highlight_identity(
    scope: str,
    item: LifecycleHighlightItem,
) -> tuple[str, str]:
    if scope == "rules":
        return str(item.rule_key), str(item.label)
    if scope == "waves":
        return str(item.wave_mode), str(item.label)
    if scope == "families":
        return str(item.family), str(item.label)
    return str(item.variant), str(item.label)



def _lifecycle_highlight_note(
    scope: str,
    item: LifecycleHighlightItem,
) -> str | None:
    if scope == "rules":
        family = str(item.family)
        family_label = _LIFECYCLE_FAMILY_LABELS.get(
            family,
            family.replace("_", " ").title(),
        )
        top_variant_label = item.top_variant_label
        if top_variant_label:
            return f"{family_label} | {top_variant_label}"
        return family_label
    if scope == "waves":
        return item.top_rule_label or None
    if scope == "families":
        return item.top_variant_label or None

    parts: list[str] = []
    limited_count = int(item.limited_primary_count or 0)
    bundle_count = int(item.bundle_extra_touch_count or 0)
    cross_sell_count = int(item.cross_sell_touch_count or 0)
    if limited_count > 0:
        parts.append(f"limited {limited_count}")
    if bundle_count > 0:
        parts.append(f"bundle {bundle_count}")
    if cross_sell_count > 0:
        parts.append(f"cross-sell {cross_sell_count}")
    return " | ".join(parts) if parts else None



def _sorted_lifecycle_items_for_metric(
    items: list[LifecycleHighlightItem],
    *,
    metric: str,
) -> list[LifecycleHighlightItem]:
    if metric == "top_paid_conversion":
        return sorted(
            items,
            key=lambda item: (
                -item.paid_conversion_percent,
                -item.invite_conversion_percent,
                -item.revenue_total,
                -item.sent_count,
                item.label,
            ),
        )
    if metric == "top_revenue":
        return sorted(
            items,
            key=lambda item: (
                -item.revenue_total,
                -item.paid_users,
                -item.paid_conversion_percent,
                -item.sent_count,
                item.label,
            ),
        )
    return sorted(
        items,
        key=lambda item: (
            item.paid_conversion_percent,
            item.invite_conversion_percent,
            -item.sent_count,
            -item.revenue_total,
            item.label,
        ),
    )



def _build_lifecycle_highlights_for_scope(
    scope: str,
    items: list[LifecycleHighlightItem],
) -> list[LifecycleCampaignHighlightSnapshot]:
    all_items = [item for item in items if item.sent_count > 0]
    if not all_items:
        return []
    eligible_items = [
        item
        for item in all_items
        if item.sent_count >= _LIFECYCLE_HIGHLIGHT_MIN_SENT_COUNT
    ]
    scope_label = _LIFECYCLE_HIGHLIGHT_SCOPE_LABELS[scope]
    highlights: list[LifecycleCampaignHighlightSnapshot] = []

    def add_highlight(metric: str, pool: list[LifecycleHighlightItem]) -> None:
        if not pool:
            return
        candidate = _sorted_lifecycle_items_for_metric(pool, metric=metric)[0]
        entity_key, entity_label = _lifecycle_highlight_identity(scope, candidate)
        highlights.append(
            LifecycleCampaignHighlightSnapshot(
                scope=scope,
                scope_label=scope_label,
                metric=metric,
                metric_label=_LIFECYCLE_HIGHLIGHT_METRIC_LABELS[metric],
                entity_key=entity_key,
                entity_label=entity_label,
                sent_count=candidate.sent_count,
                paid_users=candidate.paid_users,
                payment_count=candidate.payment_count,
                invite_issued_users=candidate.invite_issued_users,
                revenue_total=candidate.revenue_total,
                note=_lifecycle_highlight_note(scope, candidate),
            )
        )

    add_highlight("top_paid_conversion", eligible_items or all_items)
    add_highlight("top_revenue", all_items)
    if len(eligible_items) > 1:
        add_highlight("watch_paid_conversion", eligible_items)
    return highlights


def _source_campaign_highlight_note(
    metric: str,
    item: LifecycleSourceCampaignSnapshot,
) -> str | None:
    if metric == "top_second_product_attach":
        return (
            f"2nd payments {item.second_product_payment_count} | "
            f"2nd revenue {item.second_product_revenue_total}"
        )
    if metric == "watch_paid_conversion":
        return (
            f"Source base {item.source_acquired_users} acquired / "
            f"{item.source_paid_users} paid"
        )
    return f"Source base {item.source_acquired_users} acquired / {item.source_paid_users} paid"


def _sorted_source_campaign_items_for_metric(
    items: list[LifecycleSourceCampaignSnapshot],
    *,
    metric: str,
) -> list[LifecycleSourceCampaignSnapshot]:
    if metric == "top_paid_conversion":
        return sorted(
            items,
            key=lambda item: (
                -item.paid_conversion_percent,
                -item.paid_share_of_source_paid_percent,
                -item.revenue_total,
                -item.second_product_attach_percent,
                -item.sent_count,
                item.source_label,
                item.rule_label,
                item.wave_label,
            ),
        )
    if metric == "top_revenue":
        return sorted(
            items,
            key=lambda item: (
                -item.revenue_total,
                -item.paid_users,
                -item.paid_conversion_percent,
                -item.second_product_revenue_total,
                -item.sent_count,
                item.source_label,
                item.rule_label,
                item.wave_label,
            ),
        )
    if metric == "top_second_product_attach":
        return sorted(
            items,
            key=lambda item: (
                -item.second_product_attach_percent,
                -item.second_product_paid_users,
                -item.second_product_revenue_total,
                -item.revenue_total,
                -item.sent_count,
                item.source_label,
                item.rule_label,
                item.wave_label,
            ),
        )
    return sorted(
        items,
        key=lambda item: (
            item.paid_conversion_percent,
            item.paid_share_of_source_paid_percent,
            -item.sent_count,
            item.revenue_total,
            item.source_label,
            item.rule_label,
            item.wave_label,
        ),
    )


def _build_source_campaign_highlights(
    items: list[LifecycleSourceCampaignSnapshot],
) -> list[LifecycleSourceCampaignHighlightSnapshot]:
    all_items = [item for item in items if item.sent_count > 0]
    if not all_items:
        return []
    eligible_items = [
        item
        for item in all_items
        if item.sent_count >= _LIFECYCLE_HIGHLIGHT_MIN_SENT_COUNT
    ]
    attach_items = [item for item in all_items if item.second_product_paid_users > 0]
    highlights: list[LifecycleSourceCampaignHighlightSnapshot] = []

    def add_highlight(metric: str, pool: list[LifecycleSourceCampaignSnapshot]) -> None:
        if not pool:
            return
        candidate = _sorted_source_campaign_items_for_metric(pool, metric=metric)[0]
        highlights.append(
            LifecycleSourceCampaignHighlightSnapshot(
                metric=metric,
                metric_label=_SOURCE_CAMPAIGN_HIGHLIGHT_METRIC_LABELS[metric],
                source=candidate.source,
                source_label=candidate.source_label,
                source_acquired_users=candidate.source_acquired_users,
                source_paid_users=candidate.source_paid_users,
                rule_key=candidate.rule_key,
                rule_label=candidate.rule_label,
                wave_mode=candidate.wave_mode,
                wave_label=candidate.wave_label,
                sent_count=candidate.sent_count,
                paid_users=candidate.paid_users,
                payment_count=candidate.payment_count,
                invite_issued_users=candidate.invite_issued_users,
                revenue_total=candidate.revenue_total,
                second_product_paid_users=candidate.second_product_paid_users,
                second_product_payment_count=candidate.second_product_payment_count,
                second_product_revenue_total=candidate.second_product_revenue_total,
                note=_source_campaign_highlight_note(metric, candidate),
            )
        )

    add_highlight("top_paid_conversion", eligible_items or all_items)
    add_highlight("top_revenue", all_items)
    if attach_items:
        add_highlight("top_second_product_attach", attach_items)
    if len(eligible_items) > 1:
        add_highlight("watch_paid_conversion", eligible_items)
    return highlights


def _source_campaign_watchlist_note(
    metric: str,
    item: LifecycleSourceCampaignSnapshot,
) -> str | None:
    if metric == "largest_source_paid_gap":
        gap = max(item.source_paid_users - item.paid_users, 0)
        return f"{gap} source-paid users not reconverted yet"
    if metric == "largest_invite_gap":
        gap = max(item.paid_users - item.invite_issued_users, 0)
        return f"{gap} paid users still missing invite"
    if metric == "largest_second_product_gap":
        gap = max(item.paid_users - item.second_product_paid_users, 0)
        return f"{gap} paid users without second product"
    return None


def _sorted_source_campaign_items_for_watch_metric(
    items: list[LifecycleSourceCampaignSnapshot],
    *,
    metric: str,
) -> list[LifecycleSourceCampaignSnapshot]:
    if metric == "largest_source_paid_gap":
        return sorted(
            items,
            key=lambda item: (
                -(item.source_paid_users - item.paid_users),
                -item.source_paid_users,
                -item.sent_count,
                -item.revenue_total,
                item.source_label,
                item.rule_label,
                item.wave_label,
            ),
        )
    if metric == "largest_invite_gap":
        return sorted(
            items,
            key=lambda item: (
                -(item.paid_users - item.invite_issued_users),
                -item.paid_users,
                -item.revenue_total,
                -item.sent_count,
                item.source_label,
                item.rule_label,
                item.wave_label,
            ),
        )
    return sorted(
        items,
        key=lambda item: (
            -(item.paid_users - item.second_product_paid_users),
            -item.paid_users,
            -item.revenue_total,
            -item.sent_count,
            item.source_label,
            item.rule_label,
            item.wave_label,
        ),
    )


def _build_source_campaign_watchlist(
    items: list[LifecycleSourceCampaignSnapshot],
) -> list[LifecycleSourceCampaignHighlightSnapshot]:
    source_gap_items = [item for item in items if item.source_paid_users > item.paid_users]
    invite_gap_items = [item for item in items if item.paid_users > item.invite_issued_users]
    second_gap_items = [item for item in items if item.paid_users > item.second_product_paid_users]
    watchlist: list[LifecycleSourceCampaignHighlightSnapshot] = []

    def add_signal(metric: str, pool: list[LifecycleSourceCampaignSnapshot]) -> None:
        if not pool:
            return
        candidate = _sorted_source_campaign_items_for_watch_metric(pool, metric=metric)[0]
        watchlist.append(
            LifecycleSourceCampaignHighlightSnapshot(
                metric=metric,
                metric_label=_SOURCE_CAMPAIGN_WATCHLIST_METRIC_LABELS[metric],
                source=candidate.source,
                source_label=candidate.source_label,
                source_acquired_users=candidate.source_acquired_users,
                source_paid_users=candidate.source_paid_users,
                rule_key=candidate.rule_key,
                rule_label=candidate.rule_label,
                wave_mode=candidate.wave_mode,
                wave_label=candidate.wave_label,
                sent_count=candidate.sent_count,
                paid_users=candidate.paid_users,
                payment_count=candidate.payment_count,
                invite_issued_users=candidate.invite_issued_users,
                revenue_total=candidate.revenue_total,
                second_product_paid_users=candidate.second_product_paid_users,
                second_product_payment_count=candidate.second_product_payment_count,
                second_product_revenue_total=candidate.second_product_revenue_total,
                note=_source_campaign_watchlist_note(metric, candidate),
            )
        )

    add_signal("largest_source_paid_gap", source_gap_items)
    add_signal("largest_invite_gap", invite_gap_items)
    add_signal("largest_second_product_gap", second_gap_items)
    return watchlist


def _sorted_source_campaign_items_for_roi(
    items: list[LifecycleSourceCampaignSnapshot],
) -> list[LifecycleSourceCampaignSnapshot]:
    return sorted(
        items,
        key=lambda item: (
            -item.second_product_revenue_total,
            -item.revenue_total,
            -item.average_revenue_per_source_paid_user,
            -item.paid_share_of_source_paid_percent,
            -item.second_product_attach_percent,
            -item.paid_users,
            -item.sent_count,
            item.source_label,
            item.rule_label,
            item.wave_label,
        ),
    )


def _sorted_source_campaign_items_for_opportunity(
    items: list[LifecycleSourceCampaignSnapshot],
) -> list[LifecycleSourceCampaignSnapshot]:
    candidates = [
        item
        for item in items
        if item.opportunity_score > 0
    ]
    return sorted(
        candidates,
        key=lambda item: (
            -item.opportunity_score,
            -item.source_paid_gap_users,
            -item.invite_gap_users,
            -item.second_product_upside_users,
            -item.revenue_total,
            item.source_label,
            item.rule_label,
            item.wave_label,
        ),
    )


def _sorted_source_campaign_items_for_action(
    items: list[LifecycleSourceCampaignSnapshot],
) -> list[LifecycleSourceCampaignSnapshot]:
    issue_priority = {
        "reconvert_paid_base": 0,
        "restore_invite_flow": 1,
        "push_second_product": 2,
        "scale_winner": 3,
    }
    candidates = [
        item
        for item in items
        if item.opportunity_score > 0
    ]
    return sorted(
        candidates,
        key=lambda item: (
            issue_priority[item.primary_issue_key],
            -item.opportunity_score,
            -item.revenue_total,
            -item.source_paid_gap_users,
            -item.invite_gap_users,
            -item.second_product_upside_users,
            item.source_label,
            item.rule_label,
            item.wave_label,
        ),
    )


async def _build_lifecycle_campaign_attribution(
    session: AsyncSession,
    *,
    channel_titles: dict[int, str],
    now: datetime,
    lookback_days: int = 30,
) -> LifecycleCampaignAttributionSnapshot:
    cutoff = now - timedelta(days=lookback_days)
    touch_rows = list(
        (
            await session.execute(
                select(
                    AuditLog.action,
                    AuditLog.target_user_id,
                    AuditLog.payload,
                    AuditLog.created_at,
                )
                .where(AuditLog.action.in_(_LIFECYCLE_TOUCH_ACTIONS))
                .where(AuditLog.target_user_id.is_not(None))
                .where(AuditLog.created_at >= cutoff)
            )
        ).all()
    )

    touches_by_user: dict[int, list[dict[str, object]]] = defaultdict(list)
    variant_buckets: dict[str, dict[str, object]] = {}
    family_buckets: dict[str, dict[str, object]] = {}
    rule_buckets: dict[str, dict[str, object]] = {}
    wave_buckets: dict[str, dict[str, object]] = {}

    conversion_source_actions = (
        "buy_screen_viewed",
        "product_selected",
        "tariff_detail_opened",
        "offer_clicked",
        "invoice_created_stars",
        "invoice_created_crypto",
        "payment_paid_stars",
        "payment_paid_crypto",
        "invite_issued",
    )
    first_source_rows = list(
        (
            await session.execute(
                select(
                    AuditLog.target_user_id,
                    AuditLog.payload,
                    AuditLog.created_at,
                    AuditLog.id,
                )
                .where(AuditLog.action.in_(conversion_source_actions))
                .where(AuditLog.target_user_id.is_not(None))
                .order_by(
                    AuditLog.target_user_id.asc(),
                    AuditLog.created_at.asc(),
                    AuditLog.id.asc(),
                )
            )
        ).all()
    )
    first_source_by_user: dict[int, str] = {}
    for target_user_id, raw_payload, _created_at, _audit_id in first_source_rows:
        user_id = _coerce_int(target_user_id)
        if user_id is None or user_id in first_source_by_user:
            continue
        payload = _parse_payload(raw_payload)
        source = normalize_conversion_source(payload.get("source"))
        if source is None:
            continue
        first_source_by_user[user_id] = source

    source_paid_metrics = await _load_paid_user_metrics(
        session,
        user_ids=set(first_source_by_user),
    )
    source_acquired_users: dict[str, set[int]] = defaultdict(set)
    source_paid_users: dict[str, set[int]] = defaultdict(set)
    for user_id, source in first_source_by_user.items():
        source_acquired_users[source].add(user_id)
        metrics = source_paid_metrics.get(user_id)
        if metrics is not None and int(metrics["payment_count"]) > 0:
            source_paid_users[source].add(user_id)
    source_campaign_buckets: dict[tuple[str, str, str], dict[str, object]] = {}

    for action, target_user_id, raw_payload, created_at in touch_rows:
        if target_user_id is None:
            continue
        touch_time = ensure_aware_utc(created_at)
        payload = _parse_payload(raw_payload)
        action_name = str(action)
        variant = payload.get("offer_strategy") or payload.get("campaign_variant") or action_name
        if not isinstance(variant, str) or not variant:
            continue
        label = _LIFECYCLE_VARIANT_LABELS.get(variant, variant.replace("_", " ").title())
        family = _lifecycle_touch_family(action_name)
        family_label = _LIFECYCLE_FAMILY_LABELS.get(family, family.replace("_", " ").title())
        rule_key, rule_label = _lifecycle_rule_from_audit(action_name, payload)
        wave_mode, wave_label = _lifecycle_wave_from_audit(payload)
        user_id = int(target_user_id)
        touches_by_user[user_id].append(
            {
                "variant": variant,
                "family": family,
                "rule_key": rule_key,
                "wave_mode": wave_mode,
                "created_at": touch_time,
            }
        )
        variant_bucket = variant_buckets.setdefault(
            variant,
            _new_lifecycle_metric_bucket(label),
        )
        family_bucket = family_buckets.setdefault(
            family,
            _new_lifecycle_metric_bucket(family_label),
        )
        rule_bucket = rule_buckets.setdefault(
            rule_key,
            _new_lifecycle_metric_bucket(rule_label),
        )
        wave_bucket = wave_buckets.setdefault(
            wave_mode,
            _new_lifecycle_metric_bucket(wave_label),
        )
        source = first_source_by_user.get(user_id)
        if source is not None:
            source_key = (source, rule_key, wave_mode)
            source_bucket = source_campaign_buckets.setdefault(
                source_key,
                {
                    "source_label": conversion_source_label(source),
                    "source_acquired_users": len(source_acquired_users.get(source, set())),
                    "source_paid_users": len(source_paid_users.get(source, set())),
                    "rule_label": rule_label,
                    "wave_label": wave_label,
                    "sent_count": 0,
                    "paid_user_ids": set(),
                    "payment_ids": set(),
                    "invite_user_ids": set(),
                    "revenue_total": 0,
                    "second_product_user_ids": set(),
                    "second_product_payment_ids": set(),
                    "second_product_revenue_total": 0,
                },
            )
            source_bucket["sent_count"] = int(source_bucket["sent_count"]) + 1
        for bucket in (variant_bucket, family_bucket, rule_bucket, wave_bucket):
            bucket["sent_count"] = int(bucket["sent_count"]) + 1
            if bool(payload.get("limited_primary")):
                bucket["limited_primary_count"] = int(bucket["limited_primary_count"]) + 1
            if bool(payload.get("bundle_primary")):
                bucket["bundle_primary_count"] = int(bucket["bundle_primary_count"]) + 1
            if int(payload.get("bundle_count", 0) or 0) > 0:
                bucket["bundle_extra_touch_count"] = int(bucket["bundle_extra_touch_count"]) + 1
            if int(payload.get("cross_sell_count", 0) or 0) > 0:
                bucket["cross_sell_touch_count"] = int(bucket["cross_sell_touch_count"]) + 1
        family_variant_counts = family_bucket["variant_sent_counts"]
        if isinstance(family_variant_counts, defaultdict):
            family_variant_counts[variant] += 1
        rule_variant_counts = rule_bucket["variant_sent_counts"]
        if isinstance(rule_variant_counts, defaultdict):
            rule_variant_counts[variant] += 1
        rule_family_counts = rule_bucket["family_sent_counts"]
        if isinstance(rule_family_counts, defaultdict):
            rule_family_counts[family] += 1
        wave_rule_counts = wave_bucket["rule_sent_counts"]
        if isinstance(wave_rule_counts, defaultdict):
            wave_rule_counts[rule_key] += 1

    for user_touches in touches_by_user.values():
        user_touches.sort(key=lambda item: item["created_at"])

    payment_history_rows = list(
        (
            await session.execute(
                select(Payment.user_id, Payment.channel_id, Payment.paid_at)
                .where(Payment.status == "paid")
                .where(Payment.user_id.is_not(None))
                .where(Payment.channel_id.is_not(None))
                .where(Payment.paid_at.is_not(None))
            )
        ).all()
    )
    user_channel_first_paid_at: dict[int, dict[int, datetime]] = defaultdict(dict)
    for payment_user_id, payment_channel_id, payment_paid_at in payment_history_rows:
        if payment_user_id is None or payment_channel_id is None or payment_paid_at is None:
            continue
        user_key = int(payment_user_id)
        channel_key = int(payment_channel_id)
        paid_time = ensure_aware_utc(payment_paid_at)
        previous_first_paid = user_channel_first_paid_at[user_key].get(channel_key)
        if previous_first_paid is None or paid_time < previous_first_paid:
            user_channel_first_paid_at[user_key][channel_key] = paid_time

    payment_rows = list(
        (
            await session.execute(
                select(
                    Payment.id,
                    Payment.user_id,
                    Payment.channel_id,
                    Payment.amount,
                    Payment.paid_at,
                )
                .where(Payment.status == "paid")
                .where(Payment.user_id.is_not(None))
                .where(Payment.paid_at.is_not(None))
                .where(Payment.paid_at >= cutoff)
            )
        ).all()
    )
    total_paid_user_ids: set[int] = set()
    total_payment_ids: set[int] = set()
    total_revenue = 0
    for payment_id, user_id, channel_id, amount, paid_at in payment_rows:
        user_touches = touches_by_user.get(int(user_id))
        if not user_touches or paid_at is None:
            continue
        payment_time = ensure_aware_utc(paid_at)
        matched = [
            touch
            for touch in user_touches
            if (
                touch["created_at"]
                <= payment_time
                <= touch["created_at"] + LIFECYCLE_ATTRIBUTION_WINDOW
            )
        ]
        if not matched:
            continue
        touch = matched[-1]
        variant_bucket = variant_buckets[str(touch["variant"])]
        family_bucket = family_buckets[str(touch["family"])]
        rule_bucket = rule_buckets[str(touch["rule_key"])]
        wave_bucket = wave_buckets[str(touch["wave_mode"])]
        for bucket in (variant_bucket, family_bucket, rule_bucket, wave_bucket):
            paid_user_ids = bucket["paid_user_ids"]
            payment_ids = bucket["payment_ids"]
            if isinstance(paid_user_ids, set):
                paid_user_ids.add(int(user_id))
            if isinstance(payment_ids, set):
                payment_ids.add(int(payment_id))
            bucket["revenue_total"] = int(bucket["revenue_total"]) + int(amount or 0)

        source = first_source_by_user.get(int(user_id))
        source_bucket = None
        if source is not None:
            source_bucket = source_campaign_buckets.get(
                (source, str(touch["rule_key"]), str(touch["wave_mode"]))
            )
            if source_bucket is not None:
                paid_user_ids = source_bucket["paid_user_ids"]
                payment_ids = source_bucket["payment_ids"]
                if isinstance(paid_user_ids, set):
                    paid_user_ids.add(int(user_id))
                if isinstance(payment_ids, set):
                    payment_ids.add(int(payment_id))
                source_bucket["revenue_total"] = int(source_bucket["revenue_total"]) + int(
                    amount or 0
                )

        payment_channel_id = _coerce_int(channel_id)
        if payment_channel_id is not None:
            prior_paid_channels = [
                previous_channel_id
                for previous_channel_id, first_paid_at in (
                    user_channel_first_paid_at[int(user_id)].items()
                )
                if previous_channel_id != payment_channel_id and first_paid_at < payment_time
            ]
            if prior_paid_channels:
                second_product_user_ids = rule_bucket["second_product_user_ids"]
                second_product_payment_ids = rule_bucket["second_product_payment_ids"]
                secondary_channel_counts = rule_bucket["secondary_channel_counts"]
                if isinstance(second_product_user_ids, set):
                    second_product_user_ids.add(int(user_id))
                if isinstance(second_product_payment_ids, set):
                    second_product_payment_ids.add(int(payment_id))
                if isinstance(secondary_channel_counts, defaultdict):
                    secondary_channel_counts[payment_channel_id] += 1
                rule_bucket["second_product_revenue_total"] = (
                    int(rule_bucket["second_product_revenue_total"]) + int(amount or 0)
                )
                if source_bucket is not None:
                    second_product_user_ids = source_bucket["second_product_user_ids"]
                    second_product_payment_ids = source_bucket["second_product_payment_ids"]
                    if isinstance(second_product_user_ids, set):
                        second_product_user_ids.add(int(user_id))
                    if isinstance(second_product_payment_ids, set):
                        second_product_payment_ids.add(int(payment_id))
                    source_bucket["second_product_revenue_total"] = int(
                        source_bucket["second_product_revenue_total"]
                    ) + int(amount or 0)
        total_paid_user_ids.add(int(user_id))
        total_payment_ids.add(int(payment_id))
        total_revenue += int(amount or 0)

    invite_rows = list(
        (
            await session.execute(
                select(InviteLink.id, InviteLink.user_id, InviteLink.created_at)
                .where(InviteLink.created_at >= cutoff)
            )
        ).all()
    )
    total_invite_user_ids: set[int] = set()
    for _invite_id, user_id, created_at in invite_rows:
        user_touches = touches_by_user.get(int(user_id))
        if not user_touches:
            continue
        invite_time = ensure_aware_utc(created_at)
        matched = [
            touch
            for touch in user_touches
            if (
                touch["created_at"]
                <= invite_time
                <= touch["created_at"] + LIFECYCLE_ATTRIBUTION_WINDOW
            )
        ]
        if not matched:
            continue
        touch = matched[-1]
        variant_bucket = variant_buckets[str(touch["variant"])]
        family_bucket = family_buckets[str(touch["family"])]
        rule_bucket = rule_buckets[str(touch["rule_key"])]
        wave_bucket = wave_buckets[str(touch["wave_mode"])]
        for bucket in (variant_bucket, family_bucket, rule_bucket, wave_bucket):
            invite_user_ids = bucket["invite_user_ids"]
            if isinstance(invite_user_ids, set):
                invite_user_ids.add(int(user_id))
        source = first_source_by_user.get(int(user_id))
        if source is not None:
            source_bucket = source_campaign_buckets.get(
                (source, str(touch["rule_key"]), str(touch["wave_mode"]))
            )
            if source_bucket is not None:
                invite_user_ids = source_bucket["invite_user_ids"]
                if isinstance(invite_user_ids, set):
                    invite_user_ids.add(int(user_id))
        total_invite_user_ids.add(int(user_id))

    variants = [
        LifecycleCampaignPerformanceSnapshot(
            variant=variant,
            label=str(bucket["label"]),
            sent_count=int(bucket["sent_count"]),
            paid_users=len(bucket["paid_user_ids"]),
            payment_count=len(bucket["payment_ids"]),
            invite_issued_users=len(bucket["invite_user_ids"]),
            revenue_total=int(bucket["revenue_total"]),
            limited_primary_count=int(bucket["limited_primary_count"]),
            bundle_primary_count=int(bucket["bundle_primary_count"]),
            bundle_extra_touch_count=int(bucket["bundle_extra_touch_count"]),
            cross_sell_touch_count=int(bucket["cross_sell_touch_count"]),
        )
        for variant, bucket in variant_buckets.items()
    ]
    variants.sort(
        key=lambda item: (
            -item.revenue_total,
            -item.paid_users,
            -item.invite_issued_users,
            -item.sent_count,
            item.label,
            item.variant,
        )
    )

    families = []
    for family, bucket in family_buckets.items():
        variant_counts = bucket["variant_sent_counts"]
        top_variant = None
        top_variant_label = None
        if isinstance(variant_counts, defaultdict) and variant_counts:
            top_variant = min(
                variant_counts,
                key=lambda key: (
                    -int(variant_counts[key]),
                    _LIFECYCLE_VARIANT_LABELS.get(key, key),
                ),
            )
            top_variant_label = _LIFECYCLE_VARIANT_LABELS.get(
                top_variant,
                top_variant.replace("_", " ").title(),
            )
        families.append(
            LifecycleCampaignFamilySnapshot(
                family=family,
                label=str(bucket["label"]),
                sent_count=int(bucket["sent_count"]),
                paid_users=len(bucket["paid_user_ids"]),
                payment_count=len(bucket["payment_ids"]),
                invite_issued_users=len(bucket["invite_user_ids"]),
                revenue_total=int(bucket["revenue_total"]),
                limited_primary_count=int(bucket["limited_primary_count"]),
                bundle_primary_count=int(bucket["bundle_primary_count"]),
                bundle_extra_touch_count=int(bucket["bundle_extra_touch_count"]),
                cross_sell_touch_count=int(bucket["cross_sell_touch_count"]),
                top_variant=top_variant,
                top_variant_label=top_variant_label,
            )
        )
    families.sort(
        key=lambda item: (
            -item.revenue_total,
            -item.paid_users,
            -item.invite_issued_users,
            -item.sent_count,
            item.label,
            item.family,
        )
    )

    rules = []
    for rule_key, bucket in rule_buckets.items():
        variant_counts = bucket["variant_sent_counts"]
        top_variant = None
        top_variant_label = None
        if isinstance(variant_counts, defaultdict) and variant_counts:
            top_variant = min(
                variant_counts,
                key=lambda key: (
                    -int(variant_counts[key]),
                    _LIFECYCLE_VARIANT_LABELS.get(key, key),
                ),
            )
            top_variant_label = _LIFECYCLE_VARIANT_LABELS.get(
                top_variant,
                top_variant.replace("_", " ").title(),
            )
        family_counts = bucket["family_sent_counts"]
        family = "unclassified"
        if isinstance(family_counts, defaultdict) and family_counts:
            family = min(
                family_counts,
                key=lambda key: (-int(family_counts[key]), _LIFECYCLE_FAMILY_LABELS.get(key, key)),
            )
        rules.append(
            LifecycleCampaignRuleSnapshot(
                rule_key=rule_key,
                label=str(bucket["label"]),
                family=family,
                sent_count=int(bucket["sent_count"]),
                paid_users=len(bucket["paid_user_ids"]),
                payment_count=len(bucket["payment_ids"]),
                invite_issued_users=len(bucket["invite_user_ids"]),
                revenue_total=int(bucket["revenue_total"]),
                limited_primary_count=int(bucket["limited_primary_count"]),
                bundle_primary_count=int(bucket["bundle_primary_count"]),
                bundle_extra_touch_count=int(bucket["bundle_extra_touch_count"]),
                cross_sell_touch_count=int(bucket["cross_sell_touch_count"]),
                top_variant=top_variant,
                top_variant_label=top_variant_label,
            )
        )
    rules.sort(
        key=lambda item: (
            -item.revenue_total,
            -item.paid_users,
            -item.invite_issued_users,
            -item.sent_count,
            item.label,
            item.rule_key,
        )
    )

    waves = []
    for wave_mode, bucket in wave_buckets.items():
        rule_counts = bucket["rule_sent_counts"]
        top_rule_key = None
        top_rule_label = None
        if isinstance(rule_counts, defaultdict) and rule_counts:
            top_rule_key = min(
                rule_counts,
                key=lambda key: (-int(rule_counts[key]), _LIFECYCLE_RULE_LABELS.get(key, key)),
            )
            top_rule_label = _LIFECYCLE_RULE_LABELS.get(
                top_rule_key,
                top_rule_key.replace("_", " ").title(),
            )
        waves.append(
            LifecycleCampaignWaveSnapshot(
                wave_mode=wave_mode,
                label=str(bucket["label"]),
                sent_count=int(bucket["sent_count"]),
                paid_users=len(bucket["paid_user_ids"]),
                payment_count=len(bucket["payment_ids"]),
                invite_issued_users=len(bucket["invite_user_ids"]),
                revenue_total=int(bucket["revenue_total"]),
                limited_primary_count=int(bucket["limited_primary_count"]),
                bundle_primary_count=int(bucket["bundle_primary_count"]),
                bundle_extra_touch_count=int(bucket["bundle_extra_touch_count"]),
                cross_sell_touch_count=int(bucket["cross_sell_touch_count"]),
                top_rule_key=top_rule_key,
                top_rule_label=top_rule_label,
            )
        )
    waves.sort(
        key=lambda item: (
            -item.revenue_total,
            -item.paid_users,
            -item.invite_issued_users,
            -item.sent_count,
            item.label,
            item.wave_mode,
        )
    )

    roi = []
    for rule_key, bucket in rule_buckets.items():
        family_counts = bucket["family_sent_counts"]
        family = "unclassified"
        if isinstance(family_counts, defaultdict) and family_counts:
            family = min(
                family_counts,
                key=lambda key: (
                    -int(family_counts[key]),
                    _LIFECYCLE_FAMILY_LABELS.get(key, key),
                ),
            )
        secondary_channel_counts = bucket["secondary_channel_counts"]
        top_secondary_channel_id = None
        top_secondary_channel_title = None
        if isinstance(secondary_channel_counts, defaultdict) and secondary_channel_counts:
            top_secondary_channel_id = min(
                secondary_channel_counts,
                key=lambda key: (
                    -int(secondary_channel_counts[key]),
                    channel_titles.get(key, f"????? #{key}"),
                ),
            )
            top_secondary_channel_title = channel_titles.get(
                top_secondary_channel_id,
                f"????? #{top_secondary_channel_id}",
            )
        roi.append(
            LifecycleCampaignRoiSnapshot(
                rule_key=rule_key,
                label=str(bucket["label"]),
                family=family,
                sent_count=int(bucket["sent_count"]),
                paid_users=len(bucket["paid_user_ids"]),
                payment_count=len(bucket["payment_ids"]),
                invite_issued_users=len(bucket["invite_user_ids"]),
                revenue_total=int(bucket["revenue_total"]),
                second_product_paid_users=len(bucket["second_product_user_ids"]),
                second_product_payment_count=len(bucket["second_product_payment_ids"]),
                second_product_revenue_total=int(bucket["second_product_revenue_total"]),
                top_secondary_channel_id=top_secondary_channel_id,
                top_secondary_channel_title=top_secondary_channel_title,
            )
        )
    roi.sort(
        key=lambda item: (
            -item.second_product_revenue_total,
            -item.second_product_paid_users,
            -item.revenue_total,
            -item.paid_users,
            item.label,
            item.rule_key,
        )
    )

    source_campaigns = [
        LifecycleSourceCampaignSnapshot(
            source=source,
            source_label=str(bucket["source_label"]),
            source_acquired_users=int(bucket["source_acquired_users"]),
            source_paid_users=int(bucket["source_paid_users"]),
            rule_key=rule_key,
            rule_label=str(bucket["rule_label"]),
            wave_mode=wave_mode,
            wave_label=str(bucket["wave_label"]),
            sent_count=int(bucket["sent_count"]),
            paid_users=len(bucket["paid_user_ids"]),
            payment_count=len(bucket["payment_ids"]),
            invite_issued_users=len(bucket["invite_user_ids"]),
            revenue_total=int(bucket["revenue_total"]),
            second_product_paid_users=len(bucket["second_product_user_ids"]),
            second_product_payment_count=len(bucket["second_product_payment_ids"]),
            second_product_revenue_total=int(bucket["second_product_revenue_total"]),
        )
        for (source, rule_key, wave_mode), bucket in source_campaign_buckets.items()
    ]
    source_campaigns.sort(
        key=lambda item: (
            -item.second_product_revenue_total,
            -item.revenue_total,
            -item.paid_users,
            -item.sent_count,
            item.source_label,
            item.rule_label,
            item.wave_label,
        )
    )
    source_roi = _sorted_source_campaign_items_for_roi(source_campaigns)
    source_opportunities = _sorted_source_campaign_items_for_opportunity(source_campaigns)
    source_actions = _sorted_source_campaign_items_for_action(source_campaigns)
    source_highlights = _build_source_campaign_highlights(source_campaigns)
    source_watchlist = _build_source_campaign_watchlist(source_campaigns)

    highlights: list[LifecycleCampaignHighlightSnapshot] = []
    for scope, scope_items in (
        ("rules", rules),
        ("waves", waves),
        ("families", families),
        ("variants", variants),
    ):
        highlights.extend(_build_lifecycle_highlights_for_scope(scope, scope_items))

    return LifecycleCampaignAttributionSnapshot(
        total_sent_count=sum(int(bucket["sent_count"]) for bucket in variant_buckets.values()),
        total_paid_users=len(total_paid_user_ids),
        total_payment_count=len(total_payment_ids),
        total_invite_issued_users=len(total_invite_user_ids),
        revenue_total=total_revenue,
        variants=tuple(variants[:5]),
        families=tuple(families),
        rules=tuple(rules),
        waves=tuple(waves),
        highlights=tuple(highlights),
        roi=tuple(roi),
        source_roi=tuple(source_roi),
        source_opportunities=tuple(source_opportunities),
        source_actions=tuple(source_actions),
        source_highlights=tuple(source_highlights),
        source_watchlist=tuple(source_watchlist),
        source_campaigns=tuple(source_campaigns),
    )


def _display_user_label(user: User) -> str:
    if user.username:
        return safe_ui_text(f"@{user.username}", f"ID {user.telegram_id}")
    full_name = " ".join(part for part in (user.first_name, user.last_name) if part).strip()
    if full_name:
        return safe_ui_text(full_name, f"ID {user.telegram_id}")
    return f"ID {user.telegram_id}"


async def _load_channel_titles(session: AsyncSession) -> dict[int, str]:
    rows = list((await session.execute(select(Channel.id, Channel.title))).all())
    return {
        int(channel_id): safe_ui_text(title, f"????? #{channel_id}")
        for channel_id, title in rows
    }


async def _load_tariff_channel_map(session: AsyncSession) -> dict[int, int]:
    rows = list((await session.execute(select(Tariff.id, Tariff.channel_id))).all())
    return {int(tariff_id): int(channel_id) for tariff_id, channel_id in rows}


async def _audit_targets_by_tariff(
    session: AsyncSession,
    *,
    actions: tuple[str, ...],
) -> dict[int, set[int]]:
    rows = list(
        (
            await session.execute(
                select(AuditLog.target_user_id, AuditLog.payload).where(
                    AuditLog.action.in_(actions)
                )
            )
        ).all()
    )
    grouped: dict[int, set[int]] = defaultdict(set)
    for target_user_id, raw_payload in rows:
        if target_user_id is None:
            continue
        payload = _parse_payload(raw_payload)
        tariff_id = _coerce_int(payload.get("tariff_id"))
        if tariff_id is None:
            continue
        grouped[tariff_id].add(int(target_user_id))
    return grouped


async def _audit_targets_by_channel(
    session: AsyncSession,
    *,
    actions: tuple[str, ...],
    tariff_channel_map: dict[int, int],
) -> dict[int, set[int]]:
    rows = list(
        (
            await session.execute(
                select(AuditLog.action, AuditLog.target_user_id, AuditLog.payload).where(
                    AuditLog.action.in_(actions)
                )
            )
        ).all()
    )
    grouped: dict[int, set[int]] = defaultdict(set)
    for _action, target_user_id, raw_payload in rows:
        if target_user_id is None:
            continue
        payload = _parse_payload(raw_payload)
        channel_id = _resolve_channel_id(payload, tariff_channel_map)
        if channel_id is None:
            continue
        grouped[channel_id].add(int(target_user_id))
    return grouped


async def _distinct_paid_users(session: AsyncSession) -> int:
    value = (
        await session.execute(
            select(func.count(distinct(Payment.user_id))).where(Payment.status == "paid")
        )
    ).scalar_one()
    return int(value or 0)


async def _distinct_invite_users(session: AsyncSession) -> int:
    value = (await session.execute(select(func.count(distinct(InviteLink.user_id))))).scalar_one()
    return int(value or 0)


async def _repeat_purchase_user_count(session: AsyncSession) -> int:
    rows = list(
        (
            await session.execute(
                select(Payment.user_id, func.count(Payment.id))
                .where(Payment.status == "paid")
                .group_by(Payment.user_id)
            )
        ).all()
    )
    return sum(1 for _user_id, payment_count in rows if int(payment_count or 0) > 1)


async def _distinct_audit_targets(session: AsyncSession, action: str) -> int:
    value = (
        await session.execute(
            select(func.count(distinct(AuditLog.target_user_id)))
            .where(AuditLog.action == action)
            .where(AuditLog.target_user_id.is_not(None))
        )
    ).scalar_one()
    return int(value or 0)


async def _distinct_audit_targets_multi(session: AsyncSession, actions: tuple[str, ...]) -> int:
    value = (
        await session.execute(
            select(func.count(distinct(AuditLog.target_user_id)))
            .where(AuditLog.action.in_(actions))
            .where(AuditLog.target_user_id.is_not(None))
        )
    ).scalar_one()
    return int(value or 0)


def _percent(value: int, total: int) -> int:
    if total <= 0:
        return 0
    return int((value * 100) / total)


def _parse_payload(raw_payload: str | None) -> dict[str, object]:
    if not raw_payload:
        return {}
    try:
        value = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _resolve_channel_id(
    payload: dict[str, object],
    tariff_channel_map: dict[int, int],
) -> int | None:
    direct_channel_id = _coerce_int(payload.get("channel_id"))
    if direct_channel_id is not None:
        return direct_channel_id
    tariff_id = _coerce_int(payload.get("tariff_id"))
    if tariff_id is None:
        return None
    return tariff_channel_map.get(tariff_id)


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None



