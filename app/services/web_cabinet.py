from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Payment, PromoCode, PromoRedemption, SupportTicket, Tariff, User
from app.db.repositories.payments import PaymentRepository
from app.db.repositories.promo_redemptions import PromoRedemptionRepository
from app.db.repositories.tariffs import TariffRepository
from app.services.analytics import PricingIntelligenceSnapshot, build_analytics_snapshot
from app.services.multi_channel_access_service import load_active_product_access
from app.services.offer_engine import (
    OfferEngineSnapshot,
    build_offer_engine_snapshot,
)
from app.services.product_service import (
    CatalogRecommendations,
    ProductCatalogEntry,
    RecommendedTariffOffer,
    build_catalog_recommendations,
    build_offer_details,
    build_product_catalog,
    pick_default_tariff,
    recommended_tariff_for_entry,
)
from app.services.profile import UserProfileSnapshot, build_user_profile_snapshot
from app.services.promo_service import (
    PROMO_TYPE_DISCOUNT_PERCENT,
    PROMO_TYPE_DISCOUNT_STARS,
    PROMO_TYPE_FIXED_PRICE,
    PROMO_TYPE_FREE_DAYS,
    effective_promo_valid_until,
)
from app.services.referral_service import build_user_referral_dashboard
from app.services.support import (
    SupportUserDashboard,
    build_user_support_dashboard,
    support_category_label,
    support_status_label,
)
from app.utils.datetime import ensure_aware_utc, format_datetime
from app.utils.encoding import safe_ui_text

MAX_CABINET_PAYMENT_ITEMS = 10
MAX_CABINET_PROMO_ITEMS = 5
MAX_CABINET_SUPPORT_ITEMS = 5
PROMO_STATUS_PENDING = "pending"
PROMO_STATUS_CONSUMED = "consumed"
PROMO_STATUS_CANCELLED = "cancelled"
PROMO_STATUS_LABELS = {
    PROMO_STATUS_PENDING: "Р–РґС‘С‚ РїСЂРёРјРµРЅРµРЅРёСЏ",
    PROMO_STATUS_CONSUMED: "РСЃРїРѕР»СЊР·РѕРІР°РЅ",
    PROMO_STATUS_CANCELLED: "РћС‚РјРµРЅС‘РЅ",
}


async def build_cabinet_bootstrap_payload(
    session: AsyncSession,
    *,
    user: User,
    settings: Settings,
) -> dict[str, object]:
    snapshot = await build_user_profile_snapshot(
        session,
        telegram_user_id=user.telegram_id,
        history_limit=MAX_CABINET_PAYMENT_ITEMS,
    )
    referral_dashboard = await build_user_referral_dashboard(
        session,
        user_id=user.id,
        bot_username=settings.bot_public_username,
    )
    support_dashboard = await build_user_support_dashboard(
        session,
        user_id=user.id,
        limit=MAX_CABINET_SUPPORT_ITEMS,
    )
    pending_promos = await PromoRedemptionRepository(session).list_pending_for_user(user.id)
    tariffs = await TariffRepository(session).list_active()
    product_catalog = build_product_catalog(tariffs)
    active_products = await load_active_product_access(session, user_id=user.id)
    recommendations = build_catalog_recommendations(
        product_catalog,
        active_channel_ids=[product.channel_id for product in active_products],
        primary_channel_id=snapshot.primary_channel_id if snapshot is not None else None,
    )
    offer_engine = build_offer_engine_snapshot(
        product_catalog,
        active_products=active_products,
        primary_channel_id=snapshot.primary_channel_id if snapshot is not None else None,
    )
    recent_payments = await PaymentRepository(session).list_recent_paid_for_user(
        user.id,
        limit=MAX_CABINET_PAYMENT_ITEMS,
    )
    return {
        "viewer": _serialize_user(user),
        "profile": _serialize_profile_snapshot(snapshot, settings=settings),
        "products": [_serialize_product(product, settings=settings) for product in product_catalog],
        "recommendations": _serialize_catalog_recommendations(
            recommendations,
            settings=settings,
        ),
        "offer_engine": _serialize_offer_engine_snapshot(offer_engine, settings=settings),
        "active_products": [
            _serialize_active_product(product, settings=settings)
            for product in active_products
        ],
        "tariffs": [
            _serialize_tariff(tariff, baseline_tariff=None, settings=settings)
            for tariff in tariffs
        ],
        "recent_payments": [
            _serialize_payment(payment, settings=settings)
            for payment in recent_payments
        ],
        "referrals": _serialize_referral_dashboard(referral_dashboard),
        "pending_promos": [
            _serialize_pending_promo(redemption, settings=settings)
            for redemption in pending_promos[:MAX_CABINET_PROMO_ITEMS]
            if redemption.promo_code is not None
        ],
        "support": _serialize_support_dashboard(support_dashboard, settings=settings),
        "actions": _serialize_cabinet_actions(settings=settings, snapshot=snapshot),
        "mini_app_path": settings.mini_app_path,
    }


async def build_cabinet_profile_payload(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    settings: Settings,
) -> dict[str, object] | None:
    snapshot = await build_user_profile_snapshot(
        session,
        telegram_user_id=telegram_user_id,
        history_limit=MAX_CABINET_PAYMENT_ITEMS,
    )
    if snapshot is None:
        return None
    recent_payments = await PaymentRepository(session).list_recent_paid_for_user(
        snapshot.user.id,
        limit=MAX_CABINET_PAYMENT_ITEMS,
    )
    referral_dashboard = await build_user_referral_dashboard(
        session,
        user_id=snapshot.user.id,
        bot_username=settings.bot_public_username,
    )
    support_dashboard = await build_user_support_dashboard(
        session,
        user_id=snapshot.user.id,
        limit=MAX_CABINET_SUPPORT_ITEMS,
    )
    pending_promos = await PromoRedemptionRepository(session).list_pending_for_user(
        snapshot.user.id,
    )
    tariffs = await TariffRepository(session).list_active()
    product_catalog = build_product_catalog(tariffs)
    active_products = await load_active_product_access(session, user_id=snapshot.user.id)
    recommendations = build_catalog_recommendations(
        product_catalog,
        active_channel_ids=[product.channel_id for product in active_products],
        primary_channel_id=snapshot.primary_channel_id,
    )
    offer_engine = build_offer_engine_snapshot(
        product_catalog,
        active_products=active_products,
        primary_channel_id=snapshot.primary_channel_id,
    )
    return {
        "viewer": _serialize_user(snapshot.user),
        "profile": _serialize_profile_snapshot(snapshot, settings=settings),
        "products": [_serialize_product(product, settings=settings) for product in product_catalog],
        "recommendations": _serialize_catalog_recommendations(
            recommendations,
            settings=settings,
        ),
        "offer_engine": _serialize_offer_engine_snapshot(offer_engine, settings=settings),
        "active_products": [
            _serialize_active_product(product, settings=settings)
            for product in active_products
        ],
        "tariffs": [
            _serialize_tariff(tariff, baseline_tariff=None, settings=settings)
            for tariff in tariffs
        ],
        "recent_payments": [
            _serialize_payment(payment, settings=settings)
            for payment in recent_payments
        ],
        "referrals": _serialize_referral_dashboard(referral_dashboard),
        "pending_promos": [
            _serialize_pending_promo(redemption, settings=settings)
            for redemption in pending_promos[:MAX_CABINET_PROMO_ITEMS]
            if redemption.promo_code is not None
        ],
        "support": _serialize_support_dashboard(support_dashboard, settings=settings),
        "actions": _serialize_cabinet_actions(settings=settings, snapshot=snapshot),
    }


async def build_cabinet_admin_summary_payload(
    session: AsyncSession,
    *,
    settings: Settings,
) -> dict[str, object]:
    snapshot = await build_analytics_snapshot(session)
    tariffs = await TariffRepository(session).list_active()
    product_catalog = build_product_catalog(tariffs)
    offer_engine = build_offer_engine_snapshot(product_catalog)
    return {
        "timezone": settings.timezone,
        "total_users": snapshot.total_users,
        "active_subscriptions": snapshot.active_subscriptions,
        "expired_users": snapshot.expired_users,
        "never_paid_users": snapshot.never_paid_users,
        "blocked_users": snapshot.blocked_users,
        "revenue_today": snapshot.revenue_today,
        "revenue_7_days": snapshot.revenue_7_days,
        "revenue_30_days": snapshot.revenue_30_days,
        "revenue_total": snapshot.revenue_total,
        "stars_payments": snapshot.stars_payments,
        "crypto_payments": snapshot.crypto_payments,
        "paid_users_total": snapshot.paid_users_total,
        "conversion_started": snapshot.conversion_started,
        "conversion_buy_viewed": snapshot.conversion_buy_viewed,
        "conversion_product_selected": snapshot.conversion_product_selected,
        "conversion_tariff_opened": snapshot.conversion_tariff_opened,
        "conversion_offer_clicked": snapshot.conversion_offer_clicked,
        "conversion_invoice_created": snapshot.conversion_invoice_created,
        "conversion_paid": snapshot.conversion_paid,
        "conversion_invite_issued": snapshot.conversion_invite_issued,
        "repeat_purchase_users": snapshot.repeat_purchase_users,
        "repeat_purchase_rate_percent": snapshot.repeat_purchase_rate_percent,
        "lifecycle_queues": {
            "renewal_due_3d_users": snapshot.lifecycle_queues.renewal_due_3d_users,
            "renewal_due_1d_users": snapshot.lifecycle_queues.renewal_due_1d_users,
            "grace_period_users": snapshot.lifecycle_queues.grace_period_users,
            "win_back_ready_users": snapshot.lifecycle_queues.win_back_ready_users,
        },
        "lifecycle_offer_mix": _serialize_lifecycle_offer_mix(snapshot.lifecycle_offer_mix),
        "lifecycle_campaign_attribution": _serialize_lifecycle_campaign_attribution(
            snapshot.lifecycle_campaign_attribution
        ),
        "retention_segments": [
            {
                "segment": item.segment,
                "label": item.label,
                "candidate_count": item.candidate_count,
                "recent_sent_count": item.recent_sent_count,
                "dedupe_window_hours": item.dedupe_window_hours,
            }
            for item in snapshot.retention_segments
        ],
        "product_funnel": [
            {
                "channel_id": item.channel_id,
                "channel_title": item.channel_title,
                "buy_viewed_users": item.buy_viewed_users,
                "product_selected_users": item.product_selected_users,
                "tariff_opened_users": item.tariff_opened_users,
                "offer_clicked_users": item.offer_clicked_users,
                "invoice_created_users": item.invoice_created_users,
                "paid_users": item.paid_users,
                "invite_issued_users": item.invite_issued_users,
                "repeat_purchase_users": item.repeat_purchase_users,
                "revenue_total": item.revenue_total,
            }
            for item in snapshot.product_funnel
        ],
        "source_funnel": [
            {
                "source": item.source,
                "label": item.label,
                "buy_viewed_users": item.buy_viewed_users,
                "product_selected_users": item.product_selected_users,
                "tariff_opened_users": item.tariff_opened_users,
                "offer_clicked_users": item.offer_clicked_users,
                "invoice_created_users": item.invoice_created_users,
                "paid_users": item.paid_users,
                "invite_issued_users": item.invite_issued_users,
            }
            for item in snapshot.source_funnel
        ],
        "source_acquisition": [
            {
                "source": item.source,
                "label": item.label,
                "acquired_users": item.acquired_users,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "repeat_purchase_users": item.repeat_purchase_users,
                "first_paid_revenue_total": item.first_paid_revenue_total,
                "lifetime_revenue_total": item.lifetime_revenue_total,
                "lifecycle_paid_users": item.lifecycle_paid_users,
                "lifecycle_paid_from_paid_percent": item.lifecycle_paid_from_paid_percent,
                "lifecycle_payment_count": item.lifecycle_payment_count,
                "lifecycle_invite_issued_users": item.lifecycle_invite_issued_users,
                "lifecycle_revenue_total": item.lifecycle_revenue_total,
                "lifecycle_second_product_paid_users": item.lifecycle_second_product_paid_users,
                "lifecycle_second_product_payment_count": (
                    item.lifecycle_second_product_payment_count
                ),
                "lifecycle_second_product_revenue_total": (
                    item.lifecycle_second_product_revenue_total
                ),
                "lifecycle_second_product_attach_percent": (
                    item.lifecycle_second_product_attach_percent
                ),
                "top_rule_key": item.top_rule_key,
                "top_rule_label": item.top_rule_label,
                "top_wave_mode": item.top_wave_mode,
                "top_wave_label": item.top_wave_label,
                "paid_conversion_percent": item.paid_conversion_percent,
                "repeat_purchase_rate_percent": item.repeat_purchase_rate_percent,
            }
            for item in snapshot.source_acquisition
        ],
        "promo_attribution": {
            "total_paid_users": snapshot.promo_attribution.total_paid_users,
            "total_payment_count": snapshot.promo_attribution.total_payment_count,
            "gross_revenue_total": snapshot.promo_attribution.gross_revenue_total,
            "revenue_total": snapshot.promo_attribution.revenue_total,
            "discount_total": snapshot.promo_attribution.discount_total,
            "discount_share_percent": snapshot.promo_attribution.discount_share_percent,
            "campaigns": [
                {
                    "promo_code_id": item.promo_code_id,
                    "label": item.label,
                    "campaign_name": item.campaign_name,
                    "paid_users": item.paid_users,
                    "payment_count": item.payment_count,
                    "repeat_purchase_users": item.repeat_purchase_users,
                    "repeat_purchase_rate_percent": item.repeat_purchase_rate_percent,
                    "gross_revenue_total": item.gross_revenue_total,
                    "revenue_total": item.revenue_total,
                    "discount_total": item.discount_total,
                    "discount_share_percent": item.discount_share_percent,
                    "lifetime_revenue_total": item.lifetime_revenue_total,
                }
                for item in snapshot.promo_attribution.campaigns
            ],
        },
        "offer_inventory": _serialize_offer_inventory(offer_engine, settings=settings),
        "pricing_intelligence": _serialize_pricing_intelligence(snapshot.pricing_intelligence),
        "referral_attribution": {
            "total_referred_users": snapshot.referral_attribution.total_referred_users,
            "paid_referred_users": snapshot.referral_attribution.paid_referred_users,
            "rewarded_referrals_count": snapshot.referral_attribution.rewarded_referrals_count,
            "paid_conversion_percent": snapshot.referral_attribution.paid_conversion_percent,
            "suspicious_event_count": snapshot.referral_attribution.suspicious_event_count,
            "pending_reward_days_total": snapshot.referral_attribution.pending_reward_days_total,
            "reward_days_issued_total": snapshot.referral_attribution.reward_days_issued_total,
            "first_paid_revenue_total": snapshot.referral_attribution.first_paid_revenue_total,
            "lifetime_referred_revenue_total": (
                snapshot.referral_attribution.lifetime_referred_revenue_total
            ),
            "top_referrers": [
                {
                    "user_id": item.user_id,
                    "telegram_id": item.telegram_id,
                    "display_name": item.display_name,
                    "invited_users_count": item.invited_users_count,
                    "paid_referrals_count": item.paid_referrals_count,
                    "repeat_purchase_referred_users": item.repeat_purchase_referred_users,
                    "repeat_purchase_rate_percent": item.repeat_purchase_rate_percent,
                    "pending_reward_days": item.pending_reward_days,
                    "reward_days_issued": item.reward_days_issued,
                    "first_paid_revenue_total": item.first_paid_revenue_total,
                    "lifetime_revenue_total": item.lifetime_revenue_total,
                    "conversion_percent": item.conversion_percent,
                }
                for item in snapshot.referral_attribution.top_referrers
            ],
        },
    }


def _serialize_catalog_recommendations(
    recommendations: CatalogRecommendations,
    *,
    settings: Settings,
) -> dict[str, object]:
    return {
        "primary_offer": _serialize_recommended_offer(
            recommendations.primary_offer,
            settings=settings,
        ),
        "renewal_offer": _serialize_recommended_offer(
            recommendations.renewal_offer,
            settings=settings,
        ),
        "cross_sell_offers": [
            _serialize_recommended_offer(item, settings=settings)
            for item in recommendations.cross_sell_offers
        ],
    }


def _serialize_offer_engine_snapshot(
    snapshot: OfferEngineSnapshot,
    *,
    settings: Settings,
) -> dict[str, object]:
    return {
        "hero_offer": _serialize_recommended_offer(snapshot.hero_offer, settings=settings),
        "renewal_offer": _serialize_recommended_offer(snapshot.renewal_offer, settings=settings),
        "upgrade_offers": [
            _serialize_recommended_offer(item, settings=settings)
            for item in snapshot.upgrade_offers
        ],
        "cross_sell_offers": [
            _serialize_recommended_offer(item, settings=settings)
            for item in snapshot.cross_sell_offers
        ],
        "bundle_offers": [
            _serialize_recommended_offer(item, settings=settings)
            for item in snapshot.bundle_offers
        ],
        "limited_offers": [
            _serialize_recommended_offer(item, settings=settings)
            for item in snapshot.limited_offers
        ],
        "inventory": _serialize_offer_inventory(snapshot, settings=settings),
        "product_lanes": [
            {
                "channel_id": item.channel_id,
                "channel_title": item.channel_title,
                "has_active_access": item.has_active_access,
                "hero_offer": _serialize_recommended_offer(item.hero_offer, settings=settings),
                "limited_offer": _serialize_recommended_offer(
                    item.limited_offer, settings=settings
                ),
                "upgrade_offer": _serialize_recommended_offer(
                    item.upgrade_offer, settings=settings
                ),
                "bundle_offer": _serialize_recommended_offer(item.bundle_offer, settings=settings),
            }
            for item in snapshot.product_lanes
        ],
    }


def _serialize_offer_inventory(
    snapshot: OfferEngineSnapshot,
    *,
    settings: Settings,
) -> dict[str, object]:
    inventory = snapshot.inventory
    return {
        "total_products": inventory.total_products,
        "featured_products": inventory.featured_products,
        "default_products": inventory.default_products,
        "bundle_group_count": inventory.bundle_group_count,
        "upgrade_ready_products": inventory.upgrade_ready_products,
        "cross_sell_product_count": inventory.cross_sell_product_count,
        "limited_offer_count": inventory.limited_offer_count,
        "hero_offers": [
            _serialize_recommended_offer(item, settings=settings)
            for item in inventory.hero_offers
        ],
    }


def _serialize_lifecycle_offer_mix(snapshot) -> dict[str, object]:
    return {
        "total_sent_count": snapshot.total_sent_count,
        "limited_primary_count": snapshot.limited_primary_count,
        "bundle_primary_count": snapshot.bundle_primary_count,
        "bundle_extra_touch_count": snapshot.bundle_extra_touch_count,
        "cross_sell_touch_count": snapshot.cross_sell_touch_count,
        "variants": [
            {
                "variant": item.variant,
                "label": item.label,
                "sent_count": item.sent_count,
            }
            for item in snapshot.variants
        ],
    }


def _serialize_lifecycle_campaign_attribution(snapshot) -> dict[str, object]:
    return {
        "total_sent_count": snapshot.total_sent_count,
        "total_paid_users": snapshot.total_paid_users,
        "total_payment_count": snapshot.total_payment_count,
        "total_invite_issued_users": snapshot.total_invite_issued_users,
        "revenue_total": snapshot.revenue_total,
        "variants": [
            {
                "variant": item.variant,
                "label": item.label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "limited_primary_count": item.limited_primary_count,
                "bundle_primary_count": item.bundle_primary_count,
                "bundle_extra_touch_count": item.bundle_extra_touch_count,
                "cross_sell_touch_count": item.cross_sell_touch_count,
                "paid_conversion_percent": item.paid_conversion_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
            }
            for item in snapshot.variants
        ],
        "families": [
            {
                "family": item.family,
                "label": item.label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "limited_primary_count": item.limited_primary_count,
                "bundle_primary_count": item.bundle_primary_count,
                "bundle_extra_touch_count": item.bundle_extra_touch_count,
                "cross_sell_touch_count": item.cross_sell_touch_count,
                "top_variant": item.top_variant,
                "top_variant_label": item.top_variant_label,
                "paid_conversion_percent": item.paid_conversion_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
            }
            for item in snapshot.families
        ],
        "rules": [
            {
                "rule_key": item.rule_key,
                "label": item.label,
                "family": item.family,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "limited_primary_count": item.limited_primary_count,
                "bundle_primary_count": item.bundle_primary_count,
                "bundle_extra_touch_count": item.bundle_extra_touch_count,
                "cross_sell_touch_count": item.cross_sell_touch_count,
                "top_variant": item.top_variant,
                "top_variant_label": item.top_variant_label,
                "paid_conversion_percent": item.paid_conversion_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
            }
            for item in snapshot.rules
        ],
        "waves": [
            {
                "wave_mode": item.wave_mode,
                "label": item.label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "limited_primary_count": item.limited_primary_count,
                "bundle_primary_count": item.bundle_primary_count,
                "bundle_extra_touch_count": item.bundle_extra_touch_count,
                "cross_sell_touch_count": item.cross_sell_touch_count,
                "top_rule_key": item.top_rule_key,
                "top_rule_label": item.top_rule_label,
                "paid_conversion_percent": item.paid_conversion_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
            }
            for item in snapshot.waves
        ],
        "highlights": [
            {
                "scope": item.scope,
                "scope_label": item.scope_label,
                "metric": item.metric,
                "metric_label": item.metric_label,
                "entity_key": item.entity_key,
                "entity_label": item.entity_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "note": item.note,
                "paid_conversion_percent": item.paid_conversion_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
            }
            for item in snapshot.highlights
        ],
        "roi": [
            {
                "rule_key": item.rule_key,
                "label": item.label,
                "family": item.family,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "top_secondary_channel_id": item.top_secondary_channel_id,
                "top_secondary_channel_title": item.top_secondary_channel_title,
                "second_product_attach_from_paid_percent": (
                    item.second_product_attach_from_paid_percent
                ),
                "second_product_attach_from_sent_percent": (
                    item.second_product_attach_from_sent_percent
                ),
            }
            for item in snapshot.roi
        ],
        "source_roi": [
            {
                "source": item.source,
                "source_label": item.source_label,
                "source_acquired_users": item.source_acquired_users,
                "source_paid_users": item.source_paid_users,
                "rule_key": item.rule_key,
                "rule_label": item.rule_label,
                "wave_mode": item.wave_mode,
                "wave_label": item.wave_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "paid_conversion_percent": item.paid_conversion_percent,
                "paid_share_of_source_paid_percent": item.paid_share_of_source_paid_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
                "second_product_attach_percent": item.second_product_attach_percent,
                "average_revenue_per_paid_user": item.average_revenue_per_paid_user,
                "average_revenue_per_source_paid_user": item.average_revenue_per_source_paid_user,
                "second_product_revenue_share_percent": item.second_product_revenue_share_percent,
                "source_paid_gap_users": item.source_paid_gap_users,
                "invite_gap_users": item.invite_gap_users,
                "second_product_upside_users": item.second_product_upside_users,
            }
            for item in snapshot.source_roi
        ],
        "source_opportunities": [
            {
                "source": item.source,
                "source_label": item.source_label,
                "source_acquired_users": item.source_acquired_users,
                "source_paid_users": item.source_paid_users,
                "rule_key": item.rule_key,
                "rule_label": item.rule_label,
                "wave_mode": item.wave_mode,
                "wave_label": item.wave_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "paid_conversion_percent": item.paid_conversion_percent,
                "paid_share_of_source_paid_percent": item.paid_share_of_source_paid_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
                "second_product_attach_percent": item.second_product_attach_percent,
                "average_revenue_per_paid_user": item.average_revenue_per_paid_user,
                "average_revenue_per_source_paid_user": item.average_revenue_per_source_paid_user,
                "second_product_revenue_share_percent": item.second_product_revenue_share_percent,
                "source_paid_gap_users": item.source_paid_gap_users,
                "invite_gap_users": item.invite_gap_users,
                "second_product_upside_users": item.second_product_upside_users,
                "opportunity_score": item.opportunity_score,
                "opportunity_label": item.opportunity_label,
            }
            for item in snapshot.source_opportunities
        ],
        "source_actions": [
            {
                "source": item.source,
                "source_label": item.source_label,
                "source_acquired_users": item.source_acquired_users,
                "source_paid_users": item.source_paid_users,
                "rule_key": item.rule_key,
                "rule_label": item.rule_label,
                "wave_mode": item.wave_mode,
                "wave_label": item.wave_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "paid_conversion_percent": item.paid_conversion_percent,
                "paid_share_of_source_paid_percent": item.paid_share_of_source_paid_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
                "second_product_attach_percent": item.second_product_attach_percent,
                "average_revenue_per_paid_user": item.average_revenue_per_paid_user,
                "average_revenue_per_source_paid_user": item.average_revenue_per_source_paid_user,
                "second_product_revenue_share_percent": item.second_product_revenue_share_percent,
                "source_paid_gap_users": item.source_paid_gap_users,
                "invite_gap_users": item.invite_gap_users,
                "second_product_upside_users": item.second_product_upside_users,
                "opportunity_score": item.opportunity_score,
                "opportunity_label": item.opportunity_label,
                "primary_issue_key": item.primary_issue_key,
                "primary_issue_label": item.primary_issue_label,
                "recommended_action_key": item.recommended_action_key,
                "recommended_action_label": item.recommended_action_label,
                "recommended_action_note": item.recommended_action_note,
            }
            for item in snapshot.source_actions
        ],
        "source_highlights": [
            {
                "metric": item.metric,
                "metric_label": item.metric_label,
                "source": item.source,
                "source_label": item.source_label,
                "source_acquired_users": item.source_acquired_users,
                "source_paid_users": item.source_paid_users,
                "rule_key": item.rule_key,
                "rule_label": item.rule_label,
                "wave_mode": item.wave_mode,
                "wave_label": item.wave_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "note": item.note,
                "paid_conversion_percent": item.paid_conversion_percent,
                "paid_share_of_source_paid_percent": item.paid_share_of_source_paid_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
                "second_product_attach_percent": item.second_product_attach_percent,
            }
            for item in snapshot.source_highlights
        ],
        "source_watchlist": [
            {
                "metric": item.metric,
                "metric_label": item.metric_label,
                "source": item.source,
                "source_label": item.source_label,
                "source_acquired_users": item.source_acquired_users,
                "source_paid_users": item.source_paid_users,
                "rule_key": item.rule_key,
                "rule_label": item.rule_label,
                "wave_mode": item.wave_mode,
                "wave_label": item.wave_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "note": item.note,
                "paid_conversion_percent": item.paid_conversion_percent,
                "paid_share_of_source_paid_percent": item.paid_share_of_source_paid_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
                "second_product_attach_percent": item.second_product_attach_percent,
            }
            for item in snapshot.source_watchlist
        ],
        "source_campaigns": [
            {
                "source": item.source,
                "source_label": item.source_label,
                "source_acquired_users": item.source_acquired_users,
                "source_paid_users": item.source_paid_users,
                "rule_key": item.rule_key,
                "rule_label": item.rule_label,
                "wave_mode": item.wave_mode,
                "wave_label": item.wave_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "paid_conversion_percent": item.paid_conversion_percent,
                "paid_share_of_source_paid_percent": item.paid_share_of_source_paid_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
                "second_product_attach_percent": item.second_product_attach_percent,
            }
            for item in snapshot.source_campaigns
        ],
    }


def _serialize_pricing_intelligence(
    snapshot: PricingIntelligenceSnapshot,
) -> dict[str, object]:
    return {
        "average_payment_amount": snapshot.average_payment_amount,
        "stars_revenue_total": snapshot.stars_revenue_total,
        "crypto_revenue_total": snapshot.crypto_revenue_total,
        "stars_revenue_share_percent": snapshot.stars_revenue_share_percent,
        "crypto_revenue_share_percent": snapshot.crypto_revenue_share_percent,
        "multi_product_paid_users": snapshot.multi_product_paid_users,
        "multi_product_attach_rate_percent": snapshot.multi_product_attach_rate_percent,
        "featured_revenue_total": snapshot.featured_revenue_total,
        "default_revenue_total": snapshot.default_revenue_total,
        "limited_revenue_total": snapshot.limited_revenue_total,
        "active_limited_offer_count": snapshot.active_limited_offer_count,
        "top_product_pairs": [
            _serialize_product_pair(item)
            for item in snapshot.top_product_pairs
        ],
        "top_pair_campaigns": [
            _serialize_product_pair_campaign(item)
            for item in snapshot.top_pair_campaigns
        ],
        "top_revenue_offer": _serialize_offer_performance(snapshot.top_revenue_offer),
        "top_conversion_offer": _serialize_offer_performance(snapshot.top_conversion_offer),
        "top_offers": [
            _serialize_offer_performance(item)
            for item in snapshot.top_offers
        ],
    }


def _serialize_product_pair(item) -> dict[str, object] | None:
    if item is None:
        return None
    return {
        "primary_channel_id": item.primary_channel_id,
        "primary_channel_title": item.primary_channel_title,
        "secondary_channel_id": item.secondary_channel_id,
        "secondary_channel_title": item.secondary_channel_title,
        "attached_paid_users": item.attached_paid_users,
        "base_paid_users": item.base_paid_users,
        "attach_rate_percent": item.attach_rate_percent,
        "secondary_revenue_total": item.secondary_revenue_total,
        "pair_revenue_total": item.pair_revenue_total,
    }



def _serialize_product_pair_campaign(item) -> dict[str, object] | None:
    if item is None:
        return None
    return {
        "primary_channel_id": item.primary_channel_id,
        "primary_channel_title": item.primary_channel_title,
        "secondary_channel_id": item.secondary_channel_id,
        "secondary_channel_title": item.secondary_channel_title,
        "rule_key": item.rule_key,
        "rule_label": item.rule_label,
        "wave_mode": item.wave_mode,
        "wave_label": item.wave_label,
        "attached_paid_users": item.attached_paid_users,
        "base_paid_users": item.base_paid_users,
        "attach_rate_percent": item.attach_rate_percent,
        "payment_count": item.payment_count,
        "secondary_revenue_total": item.secondary_revenue_total,
    }



def _serialize_offer_performance(offer) -> dict[str, object] | None:
    if offer is None:
        return None
    return {
        "tariff_id": offer.tariff_id,
        "tariff_name": offer.tariff_name,
        "channel_id": offer.channel_id,
        "channel_title": offer.channel_title,
        "offer_group": offer.offer_group,
        "price_stars": offer.price_stars,
        "duration_days": offer.duration_days,
        "is_featured": offer.is_featured,
        "is_default_offer": offer.is_default_offer,
        "is_limited_time": offer.is_limited_time,
        "offer_expires_at": _isoformat(offer.offer_expires_at),
        "opened_users": offer.opened_users,
        "clicked_users": offer.clicked_users,
        "invoice_created_users": offer.invoice_created_users,
        "paid_users": offer.paid_users,
        "payment_count": offer.payment_count,
        "revenue_total": offer.revenue_total,
        "open_to_click_percent": offer.open_to_click_percent,
        "click_to_paid_percent": offer.click_to_paid_percent,
        "invoice_to_paid_percent": offer.invoice_to_paid_percent,
        "average_payment_amount": offer.average_payment_amount,
    }


def _serialize_recommended_offer(
    offer: RecommendedTariffOffer | None,
    *,
    settings: Settings,
) -> dict[str, object] | None:
    if offer is None:
        return None
    return {
        "channel_id": offer.channel_id,
        "channel_title": offer.channel_title,
        "tariff_id": offer.tariff_id,
        "tariff_name": offer.tariff_name,
        "price_stars": offer.price_stars,
        "price_per_day_label": offer.price_per_day_label,
        "savings_label": offer.savings_label,
        "offer_copy": offer.offer_copy,
        "offer_expires_at": _isoformat(offer.offer_expires_at),
        "offer_expires_at_label": _format_optional_datetime(
            offer.offer_expires_at,
            settings.timezone,
        ),
        "offer_group": offer.offer_group,
        "is_featured": offer.is_featured,
        "is_default_offer": offer.is_default_offer,
        "is_limited_time": offer.is_limited_time,
        "reason_code": offer.reason_code,
        "reason_label": offer.reason_label,
        "buy_link": settings.bot_start_link(f"buy_{offer.channel_id}"),
        "tariffs_link": settings.bot_start_link(f"tariffs_{offer.channel_id}"),
    }


def _serialize_user(user: User) -> dict[str, object]:
    return {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "display_name": _display_name(user),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "language_code": user.language_code,
        "role": user.role,
        "is_admin": bool(user.is_admin),
        "is_blocked": bool(user.is_blocked),
        "last_seen_at": _isoformat(user.last_seen_at),
    }


def _serialize_profile_snapshot(
    snapshot: UserProfileSnapshot | None,
    *,
    settings: Settings,
) -> dict[str, object] | None:
    if snapshot is None:
        return None
    return {
        "status": snapshot.status,
        "status_label": snapshot.status_label,
        "has_active_subscription": snapshot.has_active_subscription,
        "active_subscription_count": snapshot.active_subscription_count,
        "latest_expires_at": _isoformat(snapshot.latest_expires_at),
        "latest_expires_at_label": _format_optional_datetime(
            snapshot.latest_expires_at,
            settings.timezone,
        ),
        "remaining_label": snapshot.remaining_label,
        "current_tariff_label": snapshot.current_tariff_label,
        "current_channel_label": snapshot.current_channel_label,
        "total_stars_amount": snapshot.total_stars_amount,
        "total_crypto_amounts": {
            asset: _serialize_decimal(amount)
            for asset, amount in snapshot.total_crypto_amounts.items()
        },
        "last_payment_at": _isoformat(snapshot.last_payment_at),
        "last_payment_at_label": _format_optional_datetime(
            snapshot.last_payment_at,
            settings.timezone,
        ),
        "referral_payload": snapshot.referral_payload,
        "pending_referral_reward_days": snapshot.pending_referral_reward_days,
        "rewarded_referrals_count": snapshot.rewarded_referrals_count,
        "primary_channel_id": snapshot.primary_channel_id,
    }


def _serialize_referral_dashboard(dashboard: object) -> dict[str, object] | None:
    if dashboard is None:
        return None
    return {
        "referral_payload": dashboard.referral_payload,
        "referral_link": dashboard.referral_link,
        "invited_users_count": dashboard.invited_users_count,
        "paid_referrals_count": dashboard.paid_referrals_count,
        "earned_days": dashboard.earned_days,
        "pending_reward_days": dashboard.pending_reward_days,
    }


def _serialize_support_dashboard(
    dashboard: SupportUserDashboard,
    *,
    settings: Settings,
) -> dict[str, object]:
    return {
        "open_ticket": _serialize_support_ticket(
            dashboard.open_ticket,
            settings=settings,
        ),
        "recent_tickets": [
            _serialize_support_ticket(ticket, settings=settings)
            for ticket in dashboard.recent_tickets[:MAX_CABINET_SUPPORT_ITEMS]
        ],
        "open_count": dashboard.open_count,
        "closed_count": dashboard.closed_count,
    }


def _serialize_support_ticket(
    ticket: SupportTicket | None,
    *,
    settings: Settings,
) -> dict[str, object] | None:
    if ticket is None:
        return None
    return {
        "id": ticket.id,
        "category": ticket.category,
        "category_label": support_category_label(ticket.category),
        "status": ticket.status,
        "status_label": support_status_label(ticket.status),
        "message_count": len(ticket.messages or []),
        "updated_at": _isoformat(ticket.updated_at),
        "updated_at_label": _format_optional_datetime(ticket.updated_at, settings.timezone),
        "last_user_message_at_label": _format_optional_datetime(
            ticket.last_user_message_at,
            settings.timezone,
        ),
        "last_admin_message_at_label": _format_optional_datetime(
            ticket.last_admin_message_at,
            settings.timezone,
        ),
        "closed_at_label": _format_optional_datetime(ticket.closed_at, settings.timezone),
    }


def _serialize_pending_promo(
    redemption: PromoRedemption,
    *,
    settings: Settings,
) -> dict[str, object]:
    promo_code = redemption.promo_code
    if promo_code is None:
        raise ValueError("Pending promo redemption must include promo code")
    tariff_name = None
    if promo_code.tariff is not None:
        tariff_name = safe_ui_text(
            promo_code.tariff.name,
            f"Tariff #{promo_code.tariff_id or '?'}",
        )
    elif redemption.tariff is not None:
        tariff_name = safe_ui_text(
            redemption.tariff.name,
            f"Tariff #{redemption.applied_tariff_id or '?'}",
        )
    valid_until = effective_promo_valid_until(promo_code)
    return {
        "id": redemption.id,
        "code": promo_code.code,
        "promo_type": promo_code.promo_type,
        "status": redemption.status,
        "status_label": PROMO_STATUS_LABELS.get(redemption.status, redemption.status),
        "discount_label": _serialize_promo_value(promo_code),
        "tariff_name": tariff_name,
        "campaign_name": promo_code.campaign_name,
        "first_purchase_only": bool(promo_code.first_purchase_only),
        "valid_until": _isoformat(valid_until),
        "valid_until_label": _format_optional_datetime(valid_until, settings.timezone),
    }


def _serialize_cabinet_actions(
    *,
    settings: Settings,
    snapshot: UserProfileSnapshot | None,
) -> dict[str, object]:
    primary_channel_id = snapshot.primary_channel_id if snapshot is not None else None
    renew_payload = f"buy_{primary_channel_id}" if primary_channel_id is not None else "buy"
    tariffs_payload = (
        f"tariffs_{primary_channel_id}"
        if primary_channel_id is not None
        else "tariffs"
    )
    return {
        "bot_username": settings.bot_public_username,
        "bot_link": settings.bot_public_link,
        "buy_link": settings.bot_start_link("buy"),
        "renew_link": settings.bot_start_link(renew_payload),
        "tariffs_link": settings.bot_start_link(tariffs_payload),
        "support_link": settings.bot_start_link("help"),
        "link_link": settings.bot_start_link("link"),
        "promo_command": "/promo CODE",
        "support_command": "/support",
        "cabinet_path": settings.mini_app_path,
    }


def _serialize_product(
    product: ProductCatalogEntry,
    *,
    settings: Settings,
) -> dict[str, object]:
    default_tariff = pick_default_tariff(product.tariffs)
    recommended_tariff = recommended_tariff_for_entry(product)
    return {
        "channel_id": product.channel_id,
        "title": product.channel_title,
        "username": product.channel_username,
        "tariff_count": product.tariff_count,
        "price_from_stars": product.price_from_stars,
        "price_to_stars": product.price_to_stars,
        "price_range_label": product.price_range_label,
        "featured_tariff_id": product.featured_tariff_id,
        "default_tariff_id": product.default_tariff_id,
        "recommended_tariff_id": product.recommended_tariff_id,
        "bundle_names": list(product.bundle_names),
        "buy_link": settings.bot_start_link(f"buy_{product.channel_id}"),
        "tariffs_link": settings.bot_start_link(f"tariffs_{product.channel_id}"),
        "recommended_offer": (
            _serialize_tariff(recommended_tariff, baseline_tariff=default_tariff, settings=settings)
            if recommended_tariff is not None
            else None
        ),
        "tariffs": [
            _serialize_tariff(tariff, baseline_tariff=default_tariff, settings=settings)
            for tariff in product.tariffs
        ],
    }


def _serialize_active_product(product, *, settings: Settings) -> dict[str, object]:
    return {
        "channel_id": product.channel_id,
        "title": product.channel_title,
        "latest_expires_at": _isoformat(product.latest_expires_at),
        "latest_expires_at_label": _format_optional_datetime(
            product.latest_expires_at,
            settings.timezone,
        ),
        "subscription_count": product.subscription_count,
        "tariff_names": list(product.tariff_names),
        "tariff_ids": list(product.tariff_ids),
        "primary_tariff_id": product.primary_tariff_id,
        "subscription_ids": list(product.subscription_ids),
        "renew_link": settings.bot_start_link(f"buy_{product.channel_id}"),
    }


def _serialize_tariff(
    tariff: Tariff,
    *,
    baseline_tariff: Tariff | None,
    settings: Settings,
) -> dict[str, object]:
    crypto_amount = getattr(tariff, "crypto_price_amount", None)
    if crypto_amount is None:
        crypto_amount = getattr(tariff, "price_crypto", None)
    channel_title = None
    if tariff.channel is not None:
        channel_title = safe_ui_text(
            tariff.channel.title,
            f"Channel #{tariff.channel_id}",
        )
    offer = build_offer_details(tariff, baseline_tariff=baseline_tariff)
    return {
        "id": tariff.id,
        "name": safe_ui_text(tariff.name, f"Tariff #{tariff.id}"),
        "description": tariff.description,
        "badge": tariff.badge,
        "duration_days": tariff.duration_days,
        "is_trial": bool(tariff.is_trial),
        "is_lifetime": bool(tariff.is_lifetime),
        "price_stars": tariff.price_stars,
        "crypto_price_amount": _serialize_decimal(crypto_amount),
        "crypto_asset": tariff.crypto_asset,
        "channel_id": tariff.channel_id,
        "channel_title": channel_title,
        "offer_copy": offer.offer_copy,
        "offer_group": offer.offer_group,
        "offer_expires_at": _isoformat(offer.offer_expires_at),
        "offer_expires_at_label": _format_optional_datetime(
            offer.offer_expires_at,
            settings.timezone,
        ),
        "price_per_day_label": offer.price_per_day_label,
        "savings_label": offer.savings_label,
        "is_featured": offer.is_featured,
        "is_default_offer": offer.is_default_offer,
        "is_limited_time": offer.is_limited_time,
    }


def _serialize_payment(payment: Payment, *, settings: Settings) -> dict[str, object]:
    tariff_name = safe_ui_text(
        payment.tariff.name if payment.tariff is not None else None,
        f"Tariff #{payment.tariff_id or '?'}",
    )
    channel_title = None
    if payment.tariff is not None and payment.tariff.channel is not None:
        channel_title = safe_ui_text(
            payment.tariff.channel.title,
            f"Channel #{payment.channel_id or '?'}",
        )
    amount_label = f"{payment.amount} {payment.currency}"
    if payment.currency == "XTR":
        amount_label = f"{payment.amount} Stars"
    return {
        "id": payment.id,
        "provider": payment.provider,
        "status": payment.status,
        "amount": payment.amount,
        "currency": payment.currency,
        "amount_label": amount_label,
        "tariff_name": tariff_name,
        "channel_title": channel_title,
        "paid_at": _isoformat(payment.paid_at),
        "paid_at_label": _format_optional_datetime(
            payment.paid_at,
            settings.timezone,
        ),
    }


def _serialize_promo_value(promo_code: PromoCode) -> str:
    if promo_code.promo_type == PROMO_TYPE_DISCOUNT_PERCENT:
        return f"-{promo_code.value}%"
    if promo_code.promo_type == PROMO_TYPE_DISCOUNT_STARS:
        return f"-{promo_code.value} Stars"
    if promo_code.promo_type == PROMO_TYPE_FIXED_PRICE:
        return f"{promo_code.value} Stars"
    if promo_code.promo_type == PROMO_TYPE_FREE_DAYS:
        return f"+{promo_code.value} РґРЅ."
    return promo_code.promo_type


def _display_name(user: User) -> str:
    parts = [
        part
        for part in [user.first_name, user.last_name]
        if isinstance(part, str) and part.strip()
    ]
    if parts:
        return " ".join(parts)
    if user.username:
        return f"@{user.username}"
    return f"User {user.telegram_id}"


def _format_optional_datetime(value: datetime | None, timezone: str) -> str | None:
    if value is None:
        return None
    return format_datetime(ensure_aware_utc(value), timezone)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return ensure_aware_utc(value).isoformat()


def _serialize_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")
