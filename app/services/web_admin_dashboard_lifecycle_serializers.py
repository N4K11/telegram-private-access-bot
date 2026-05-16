from __future__ import annotations

from app.services.web_admin_dashboard_lifecycle_campaign_source_serializers import (
    _serialize_lifecycle_source_action_items as _serialize_lifecycle_source_action_items,
)
from app.services.web_admin_dashboard_lifecycle_campaign_source_serializers import (
    _serialize_lifecycle_source_campaign_items as _serialize_lifecycle_source_campaign_items,
)
from app.services.web_admin_dashboard_lifecycle_campaign_source_serializers import (
    _serialize_lifecycle_source_highlight_items as _serialize_lifecycle_source_highlight_items,
)
from app.services.web_admin_dashboard_lifecycle_campaign_source_serializers import (
    _serialize_lifecycle_source_opportunity_items as _serialize_lifecycle_source_opportunity_items,
)
from app.services.web_admin_dashboard_lifecycle_campaign_source_serializers import (
    _serialize_lifecycle_source_roi_items as _serialize_lifecycle_source_roi_items,
)
from app.services.web_admin_dashboard_lifecycle_campaign_source_serializers import (
    _serialize_lifecycle_source_watchlist_items as _serialize_lifecycle_source_watchlist_items,
)


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
        "source_roi": _serialize_lifecycle_source_roi_items(snapshot),
        "source_opportunities": _serialize_lifecycle_source_opportunity_items(snapshot),
        "source_actions": _serialize_lifecycle_source_action_items(snapshot),
        "source_highlights": _serialize_lifecycle_source_highlight_items(snapshot),
        "source_watchlist": _serialize_lifecycle_source_watchlist_items(snapshot),
        "source_campaigns": _serialize_lifecycle_source_campaign_items(snapshot),
    }
