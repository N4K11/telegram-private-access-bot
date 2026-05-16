from __future__ import annotations


def _build_lifecycle_attribution_view_items(
    attribution,
    *,
    view: str,
    limit: int,
) -> tuple[list[dict[str, object]], int]:
    if view == "roi":
        return (
            [
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
                    "second_product_payment_count": (
                        item.second_product_payment_count
                    ),
                    "second_product_revenue_total": (
                        item.second_product_revenue_total
                    ),
                    "top_secondary_channel_id": item.top_secondary_channel_id,
                    "top_secondary_channel_title": (
                        item.top_secondary_channel_title
                    ),
                    "second_product_attach_from_paid_percent": (
                        item.second_product_attach_from_paid_percent
                    ),
                    "second_product_attach_from_sent_percent": (
                        item.second_product_attach_from_sent_percent
                    ),
                }
                for item in attribution.roi[:limit]
            ],
            len(attribution.roi),
        )
    if view == "highlights":
        return (
            [
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
                for item in attribution.highlights[:limit]
            ],
            len(attribution.highlights),
        )
    if view == "waves":
        return (
            [
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
                for item in attribution.waves[:limit]
            ],
            len(attribution.waves),
        )
    if view == "families":
        return (
            [
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
                for item in attribution.families[:limit]
            ],
            len(attribution.families),
        )
    if view == "variants":
        return (
            [
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
                for item in attribution.variants[:limit]
            ],
            len(attribution.variants),
        )
    return (
        [
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
            for item in attribution.rules[:limit]
        ],
        len(attribution.rules),
    )
