from __future__ import annotations


def _build_lifecycle_source_view_items(
    snapshot,
    *,
    attribution,
    view: str,
    limit: int,
) -> tuple[list[dict[str, object]], int] | None:
    if view == "sources":
        source_items = sorted(
            snapshot.source_acquisition,
            key=lambda item: (
                -item.lifecycle_revenue_total,
                -item.lifecycle_second_product_revenue_total,
                -item.lifetime_revenue_total,
                -item.paid_users,
                item.label,
                item.source,
            ),
        )
        return (
            [
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
                    "lifecycle_paid_from_paid_percent": (
                        item.lifecycle_paid_from_paid_percent
                    ),
                    "lifecycle_payment_count": item.lifecycle_payment_count,
                    "lifecycle_invite_issued_users": (
                        item.lifecycle_invite_issued_users
                    ),
                    "lifecycle_revenue_total": item.lifecycle_revenue_total,
                    "lifecycle_second_product_paid_users": (
                        item.lifecycle_second_product_paid_users
                    ),
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
                    "repeat_purchase_rate_percent": (
                        item.repeat_purchase_rate_percent
                    ),
                }
                for item in source_items[:limit]
            ],
            len(source_items),
        )
    if view == "source_campaigns":
        return (
            [
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
                    "second_product_payment_count": (
                        item.second_product_payment_count
                    ),
                    "second_product_revenue_total": (
                        item.second_product_revenue_total
                    ),
                    "paid_conversion_percent": item.paid_conversion_percent,
                    "paid_share_of_source_paid_percent": (
                        item.paid_share_of_source_paid_percent
                    ),
                    "invite_conversion_percent": item.invite_conversion_percent,
                    "second_product_attach_percent": (
                        item.second_product_attach_percent
                    ),
                }
                for item in attribution.source_campaigns[:limit]
            ],
            len(attribution.source_campaigns),
        )
    if view == "source_roi":
        return (
            [
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
                    "second_product_payment_count": (
                        item.second_product_payment_count
                    ),
                    "second_product_revenue_total": (
                        item.second_product_revenue_total
                    ),
                    "paid_conversion_percent": item.paid_conversion_percent,
                    "paid_share_of_source_paid_percent": (
                        item.paid_share_of_source_paid_percent
                    ),
                    "invite_conversion_percent": item.invite_conversion_percent,
                    "second_product_attach_percent": (
                        item.second_product_attach_percent
                    ),
                    "average_revenue_per_paid_user": (
                        item.average_revenue_per_paid_user
                    ),
                    "average_revenue_per_source_paid_user": (
                        item.average_revenue_per_source_paid_user
                    ),
                    "second_product_revenue_share_percent": (
                        item.second_product_revenue_share_percent
                    ),
                    "source_paid_gap_users": item.source_paid_gap_users,
                    "invite_gap_users": item.invite_gap_users,
                    "second_product_upside_users": item.second_product_upside_users,
                }
                for item in attribution.source_roi[:limit]
            ],
            len(attribution.source_roi),
        )
    if view == "source_opportunities":
        return (
            [
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
                    "second_product_payment_count": (
                        item.second_product_payment_count
                    ),
                    "second_product_revenue_total": (
                        item.second_product_revenue_total
                    ),
                    "paid_conversion_percent": item.paid_conversion_percent,
                    "paid_share_of_source_paid_percent": (
                        item.paid_share_of_source_paid_percent
                    ),
                    "invite_conversion_percent": item.invite_conversion_percent,
                    "second_product_attach_percent": (
                        item.second_product_attach_percent
                    ),
                    "average_revenue_per_paid_user": (
                        item.average_revenue_per_paid_user
                    ),
                    "average_revenue_per_source_paid_user": (
                        item.average_revenue_per_source_paid_user
                    ),
                    "second_product_revenue_share_percent": (
                        item.second_product_revenue_share_percent
                    ),
                    "source_paid_gap_users": item.source_paid_gap_users,
                    "invite_gap_users": item.invite_gap_users,
                    "second_product_upside_users": item.second_product_upside_users,
                    "opportunity_score": item.opportunity_score,
                    "opportunity_label": item.opportunity_label,
                }
                for item in attribution.source_opportunities[:limit]
            ],
            len(attribution.source_opportunities),
        )
    if view == "source_actions":
        return (
            [
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
                    "second_product_payment_count": (
                        item.second_product_payment_count
                    ),
                    "second_product_revenue_total": (
                        item.second_product_revenue_total
                    ),
                    "paid_conversion_percent": item.paid_conversion_percent,
                    "paid_share_of_source_paid_percent": (
                        item.paid_share_of_source_paid_percent
                    ),
                    "invite_conversion_percent": item.invite_conversion_percent,
                    "second_product_attach_percent": (
                        item.second_product_attach_percent
                    ),
                    "average_revenue_per_paid_user": (
                        item.average_revenue_per_paid_user
                    ),
                    "average_revenue_per_source_paid_user": (
                        item.average_revenue_per_source_paid_user
                    ),
                    "second_product_revenue_share_percent": (
                        item.second_product_revenue_share_percent
                    ),
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
                for item in attribution.source_actions[:limit]
            ],
            len(attribution.source_actions),
        )
    if view == "source_highlights":
        return (
            [
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
                    "second_product_payment_count": (
                        item.second_product_payment_count
                    ),
                    "second_product_revenue_total": (
                        item.second_product_revenue_total
                    ),
                    "note": item.note,
                    "paid_conversion_percent": item.paid_conversion_percent,
                    "paid_share_of_source_paid_percent": (
                        item.paid_share_of_source_paid_percent
                    ),
                    "invite_conversion_percent": item.invite_conversion_percent,
                    "second_product_attach_percent": (
                        item.second_product_attach_percent
                    ),
                }
                for item in attribution.source_highlights[:limit]
            ],
            len(attribution.source_highlights),
        )
    if view == "source_watchlist":
        return (
            [
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
                    "second_product_payment_count": (
                        item.second_product_payment_count
                    ),
                    "second_product_revenue_total": (
                        item.second_product_revenue_total
                    ),
                    "note": item.note,
                    "paid_conversion_percent": item.paid_conversion_percent,
                    "paid_share_of_source_paid_percent": (
                        item.paid_share_of_source_paid_percent
                    ),
                    "invite_conversion_percent": item.invite_conversion_percent,
                    "second_product_attach_percent": (
                        item.second_product_attach_percent
                    ),
                }
                for item in attribution.source_watchlist[:limit]
            ],
            len(attribution.source_watchlist),
        )
    return None
