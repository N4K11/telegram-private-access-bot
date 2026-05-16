from __future__ import annotations

from app.services.analytics import PricingIntelligenceSnapshot
from app.services.web_admin_dashboard_limits import ADMIN_DETAIL_DEFAULT_LIMIT


def _build_product_catalog_for_dashboard(tariffs) -> list:
    from app.services.product_service import build_product_catalog

    return build_product_catalog(list(tariffs))


def _serialize_offer_inventory_preview(snapshot) -> dict[str, object]:
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
            {
                "channel_id": item.channel_id,
                "channel_title": item.channel_title,
                "tariff_id": item.tariff_id,
                "tariff_name": item.tariff_name,
                "price_stars": item.price_stars,
                "reason_label": item.reason_label,
                "offer_group": item.offer_group,
                "is_featured": item.is_featured,
                "is_default_offer": item.is_default_offer,
                "is_limited_time": item.is_limited_time,
                "offer_expires_at": item.offer_expires_at.isoformat()
                if item.offer_expires_at is not None
                else None,
            }
            for item in inventory.hero_offers
        ],
    }


def _serialize_pricing_intelligence_preview(
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
        "top_revenue_offer": _serialize_offer_performance_preview(snapshot.top_revenue_offer),
        "top_conversion_offer": _serialize_offer_performance_preview(snapshot.top_conversion_offer),
    }


def _serialize_source_funnel_detail(
    items,
    *,
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
) -> list[dict[str, object]]:
    source_items = sorted(
        items,
        key=lambda item: (
            -item.paid_users,
            -item.offer_clicked_users,
            -item.buy_viewed_users,
            item.label,
            item.source,
        ),
    )
    return [
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
        for item in source_items[:limit]
    ]


def _serialize_source_acquisition_detail(
    items,
    *,
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
) -> list[dict[str, object]]:
    source_items = sorted(
        items,
        key=lambda item: (
            -item.lifetime_revenue_total,
            -item.paid_users,
            -item.acquired_users,
            item.label,
            item.source,
        ),
    )
    return [
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
            "paid_conversion_percent": item.paid_conversion_percent,
            "repeat_purchase_rate_percent": item.repeat_purchase_rate_percent,
        }
        for item in source_items[:limit]
    ]


def _serialize_product_funnel_detail(
    items,
    *,
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
) -> list[dict[str, object]]:
    product_items = sorted(
        items,
        key=lambda item: (
            -item.paid_users,
            -item.offer_clicked_users,
            -item.buy_viewed_users,
            item.channel_title,
            item.channel_id,
        ),
    )
    return [
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
        for item in product_items[:limit]
    ]


def _serialize_promo_attribution_summary(snapshot) -> dict[str, object]:
    return {
        "total_paid_users": snapshot.total_paid_users,
        "total_payment_count": snapshot.total_payment_count,
        "gross_revenue_total": snapshot.gross_revenue_total,
        "revenue_total": snapshot.revenue_total,
        "discount_total": snapshot.discount_total,
        "discount_share_percent": snapshot.discount_share_percent,
    }


def _serialize_referral_attribution_summary(snapshot) -> dict[str, object]:
    return {
        "total_referred_users": snapshot.total_referred_users,
        "paid_referred_users": snapshot.paid_referred_users,
        "rewarded_referrals_count": snapshot.rewarded_referrals_count,
        "paid_conversion_percent": snapshot.paid_conversion_percent,
        "suspicious_event_count": snapshot.suspicious_event_count,
        "pending_reward_days_total": snapshot.pending_reward_days_total,
        "reward_days_issued_total": snapshot.reward_days_issued_total,
        "first_paid_revenue_total": snapshot.first_paid_revenue_total,
        "lifetime_referred_revenue_total": snapshot.lifetime_referred_revenue_total,
    }


def _serialize_promo_attribution_detail(
    snapshot,
    *,
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
) -> dict[str, object]:
    return {
        **_serialize_promo_attribution_summary(snapshot),
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
            for item in snapshot.campaigns[:limit]
        ],
    }


def _serialize_referral_attribution_detail(
    snapshot,
    *,
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
) -> dict[str, object]:
    return {
        **_serialize_referral_attribution_summary(snapshot),
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
            for item in snapshot.top_referrers[:limit]
        ],
    }


def _serialize_pricing_intelligence_detail(
    snapshot: PricingIntelligenceSnapshot,
    *,
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
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
            _serialize_product_pair_preview(item)
            for item in snapshot.top_product_pairs[:limit]
        ],
        "top_pair_campaigns": [
            _serialize_product_pair_campaign_preview(item)
            for item in snapshot.top_pair_campaigns[:limit]
        ],
        "top_revenue_offer": _serialize_offer_performance_preview(snapshot.top_revenue_offer),
        "top_conversion_offer": _serialize_offer_performance_preview(snapshot.top_conversion_offer),
        "top_offers": [
            _serialize_offer_performance_preview(item) for item in snapshot.top_offers[:limit]
        ],
    }


def _serialize_product_pair_preview(item) -> dict[str, object] | None:
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


def _serialize_product_pair_campaign_preview(item) -> dict[str, object] | None:
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


def _serialize_offer_performance_preview(item) -> dict[str, object] | None:
    if item is None:
        return None
    return {
        "tariff_id": item.tariff_id,
        "tariff_name": item.tariff_name,
        "channel_id": item.channel_id,
        "channel_title": item.channel_title,
        "offer_group": item.offer_group,
        "price_stars": item.price_stars,
        "duration_days": item.duration_days,
        "is_featured": item.is_featured,
        "is_default_offer": item.is_default_offer,
        "is_limited_time": item.is_limited_time,
        "offer_expires_at": item.offer_expires_at.isoformat()
        if item.offer_expires_at is not None
        else None,
        "opened_users": item.opened_users,
        "clicked_users": item.clicked_users,
        "invoice_created_users": item.invoice_created_users,
        "paid_users": item.paid_users,
        "payment_count": item.payment_count,
        "revenue_total": item.revenue_total,
        "open_to_click_percent": item.open_to_click_percent,
        "click_to_paid_percent": item.click_to_paid_percent,
        "invoice_to_paid_percent": item.invoice_to_paid_percent,
        "average_payment_amount": item.average_payment_amount,
    }
