from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Payment,
    Subscription,
    User,
)
from app.services.analytics_acquisition import _build_source_acquisition
from app.services.analytics_common import (
    _distinct_audit_targets,
    _distinct_audit_targets_multi,
    _distinct_invite_users,
    _load_channel_titles,
    _load_tariff_channel_map,
    _repeat_purchase_user_count,
)
from app.services.analytics_common import _parse_payload as _parse_payload
from app.services.analytics_common import _percent as _percent
from app.services.analytics_funnel import _build_product_funnel, _build_source_funnel
from app.services.analytics_lifecycle import (
    _build_source_campaign_watchlist as _build_source_campaign_watchlist,
)
from app.services.analytics_lifecycle import (
    _sorted_source_campaign_items_for_roi as _sorted_source_campaign_items_for_roi,
)
from app.services.analytics_lifecycle_builders import (
    _build_lifecycle_campaign_attribution,
    _build_lifecycle_offer_mix,
    _build_lifecycle_queue_snapshot,
)
from app.services.analytics_models import (
    AnalyticsSnapshot,
)
from app.services.analytics_models import (
    ConversionSourceSnapshot as ConversionSourceSnapshot,
)
from app.services.analytics_models import (
    LifecycleCampaignAttributionSnapshot as LifecycleCampaignAttributionSnapshot,
)
from app.services.analytics_models import (
    LifecycleCampaignFamilySnapshot as LifecycleCampaignFamilySnapshot,
)
from app.services.analytics_models import (
    LifecycleCampaignHighlightSnapshot as LifecycleCampaignHighlightSnapshot,
)
from app.services.analytics_models import (
    LifecycleCampaignPerformanceSnapshot as LifecycleCampaignPerformanceSnapshot,
)
from app.services.analytics_models import (
    LifecycleCampaignRoiSnapshot as LifecycleCampaignRoiSnapshot,
)
from app.services.analytics_models import (
    LifecycleCampaignRuleSnapshot as LifecycleCampaignRuleSnapshot,
)
from app.services.analytics_models import (
    LifecycleCampaignWaveSnapshot as LifecycleCampaignWaveSnapshot,
)
from app.services.analytics_models import (
    LifecycleOfferMixSnapshot as LifecycleOfferMixSnapshot,
)
from app.services.analytics_models import (
    LifecycleOfferVariantSnapshot as LifecycleOfferVariantSnapshot,
)
from app.services.analytics_models import (
    LifecycleQueueSnapshot as LifecycleQueueSnapshot,
)
from app.services.analytics_models import (
    LifecycleSourceCampaignSnapshot as LifecycleSourceCampaignSnapshot,
)
from app.services.analytics_models import (
    OfferPerformanceSnapshot as OfferPerformanceSnapshot,
)
from app.services.analytics_models import (
    PricingIntelligenceSnapshot as PricingIntelligenceSnapshot,
)
from app.services.analytics_models import (
    ProductFunnelSnapshot as ProductFunnelSnapshot,
)
from app.services.analytics_models import (
    ProductPairCampaignSnapshot as ProductPairCampaignSnapshot,
)
from app.services.analytics_models import (
    ProductPairPerformanceSnapshot as ProductPairPerformanceSnapshot,
)
from app.services.analytics_models import (
    PromoAttributionSnapshot as PromoAttributionSnapshot,
)
from app.services.analytics_models import (
    PromoCampaignSnapshot as PromoCampaignSnapshot,
)
from app.services.analytics_models import (
    ReferralAttributionSnapshot as ReferralAttributionSnapshot,
)
from app.services.analytics_models import (
    ReferralTopReferrerSnapshot as ReferralTopReferrerSnapshot,
)
from app.services.analytics_models import (
    SourceAcquisitionSnapshot as SourceAcquisitionSnapshot,
)
from app.services.analytics_pricing import _build_pricing_intelligence
from app.services.analytics_promo_referral import (
    _build_promo_attribution,
    _build_referral_attribution,
)
from app.services.retention_automation import build_retention_segment_snapshots
from app.utils.datetime import ensure_aware_utc, utcnow


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

