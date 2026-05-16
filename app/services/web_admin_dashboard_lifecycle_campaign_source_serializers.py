from __future__ import annotations


def _serialize_lifecycle_source_roi_items(snapshot) -> list[dict[str, object]]:
    return [
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
            "paid_share_of_source_paid_percent": (
                item.paid_share_of_source_paid_percent
            ),
            "invite_conversion_percent": item.invite_conversion_percent,
            "second_product_attach_percent": item.second_product_attach_percent,
            "average_revenue_per_paid_user": item.average_revenue_per_paid_user,
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
        for item in snapshot.source_roi
    ]


def _serialize_lifecycle_source_opportunity_items(snapshot) -> list[dict[str, object]]:
    return [
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
            "paid_share_of_source_paid_percent": (
                item.paid_share_of_source_paid_percent
            ),
            "invite_conversion_percent": item.invite_conversion_percent,
            "second_product_attach_percent": item.second_product_attach_percent,
            "average_revenue_per_paid_user": item.average_revenue_per_paid_user,
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
        for item in snapshot.source_opportunities
    ]


def _serialize_lifecycle_source_action_items(snapshot) -> list[dict[str, object]]:
    return [
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
            "paid_share_of_source_paid_percent": (
                item.paid_share_of_source_paid_percent
            ),
            "invite_conversion_percent": item.invite_conversion_percent,
            "second_product_attach_percent": item.second_product_attach_percent,
            "average_revenue_per_paid_user": item.average_revenue_per_paid_user,
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
        for item in snapshot.source_actions
    ]


def _serialize_lifecycle_source_highlight_items(snapshot) -> list[dict[str, object]]:
    return [
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
            "paid_share_of_source_paid_percent": (
                item.paid_share_of_source_paid_percent
            ),
            "invite_conversion_percent": item.invite_conversion_percent,
            "second_product_attach_percent": item.second_product_attach_percent,
        }
        for item in snapshot.source_highlights
    ]


def _serialize_lifecycle_source_watchlist_items(snapshot) -> list[dict[str, object]]:
    return [
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
            "paid_share_of_source_paid_percent": (
                item.paid_share_of_source_paid_percent
            ),
            "invite_conversion_percent": item.invite_conversion_percent,
            "second_product_attach_percent": item.second_product_attach_percent,
        }
        for item in snapshot.source_watchlist
    ]


def _serialize_lifecycle_source_campaign_items(snapshot) -> list[dict[str, object]]:
    return [
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
            "paid_share_of_source_paid_percent": (
                item.paid_share_of_source_paid_percent
            ),
            "invite_conversion_percent": item.invite_conversion_percent,
            "second_product_attach_percent": item.second_product_attach_percent,
        }
        for item in snapshot.source_campaigns
    ]
