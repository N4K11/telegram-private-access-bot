from __future__ import annotations

from app.services.admin_read_model_reporting import (
    build_admin_read_model_snapshot_digest_payload,
    build_admin_read_model_snapshot_focus_payload,
    build_admin_read_model_snapshot_operator_payload,
)


def compact_lifecycle_offer_mix(payload: dict[str, object]) -> dict[str, object]:
    return {
        "total_sent_count": payload.get("total_sent_count", 0),
        "limited_primary_count": payload.get("limited_primary_count", 0),
        "bundle_primary_count": payload.get("bundle_primary_count", 0),
        "bundle_extra_touch_count": payload.get("bundle_extra_touch_count", 0),
        "cross_sell_touch_count": payload.get("cross_sell_touch_count", 0),
    }


def compact_lifecycle_campaign_attribution(payload: dict[str, object]) -> dict[str, object]:
    return {
        "total_sent_count": payload.get("total_sent_count", 0),
        "total_paid_users": payload.get("total_paid_users", 0),
        "total_payment_count": payload.get("total_payment_count", 0),
        "total_invite_issued_users": payload.get("total_invite_issued_users", 0),
        "revenue_total": payload.get("revenue_total", 0),
    }


def compact_pricing_intelligence(payload: dict[str, object]) -> dict[str, object]:
    return {
        "average_payment_amount": payload.get("average_payment_amount", 0),
        "stars_revenue_total": payload.get("stars_revenue_total", 0),
        "crypto_revenue_total": payload.get("crypto_revenue_total", 0),
        "stars_revenue_share_percent": payload.get("stars_revenue_share_percent", 0),
        "crypto_revenue_share_percent": payload.get("crypto_revenue_share_percent", 0),
        "multi_product_paid_users": payload.get("multi_product_paid_users", 0),
        "multi_product_attach_rate_percent": payload.get("multi_product_attach_rate_percent", 0),
        "featured_revenue_total": payload.get("featured_revenue_total", 0),
        "default_revenue_total": payload.get("default_revenue_total", 0),
        "limited_revenue_total": payload.get("limited_revenue_total", 0),
        "active_limited_offer_count": payload.get("active_limited_offer_count", 0),
        "top_revenue_offer": payload.get("top_revenue_offer"),
        "top_conversion_offer": payload.get("top_conversion_offer"),
    }


def compact_promo_attribution(payload: dict[str, object]) -> dict[str, object]:
    return {
        "total_paid_users": payload.get("total_paid_users", 0),
        "total_payment_count": payload.get("total_payment_count", 0),
        "gross_revenue_total": payload.get("gross_revenue_total", 0),
        "revenue_total": payload.get("revenue_total", 0),
        "discount_total": payload.get("discount_total", 0),
        "discount_share_percent": payload.get("discount_share_percent", 0),
    }


def compact_referral_attribution(payload: dict[str, object]) -> dict[str, object]:
    return {
        "total_referred_users": payload.get("total_referred_users", 0),
        "paid_referred_users": payload.get("paid_referred_users", 0),
        "rewarded_referrals_count": payload.get("rewarded_referrals_count", 0),
        "paid_conversion_percent": payload.get("paid_conversion_percent", 0),
        "suspicious_event_count": payload.get("suspicious_event_count", 0),
        "pending_reward_days_total": payload.get("pending_reward_days_total", 0),
        "reward_days_issued_total": payload.get("reward_days_issued_total", 0),
        "first_paid_revenue_total": payload.get("first_paid_revenue_total", 0),
        "lifetime_referred_revenue_total": payload.get("lifetime_referred_revenue_total", 0),
    }


def compact_read_model_focus(payload: dict[str, object]) -> dict[str, object] | None:
    focus_payload = None
    if isinstance(payload, dict) and payload.get("line"):
        focus_payload = payload
    else:
        focus_payload = build_admin_read_model_snapshot_focus_payload(payload)
    if focus_payload is None:
        return None
    return {
        "kind": focus_payload.get("kind"),
        "kind_label": focus_payload.get("kind_label"),
        "label": focus_payload.get("label"),
        "detail": focus_payload.get("detail"),
        "line": focus_payload.get("line"),
        "source": focus_payload.get("source"),
        "generated_at_label": focus_payload.get("generated_at_label"),
        "staleness_seconds": focus_payload.get("staleness_seconds", 0),
        "tracked_count": focus_payload.get("tracked_count", 0),
        "alert_item_count": focus_payload.get("alert_item_count", 0),
        "missing_count": focus_payload.get("missing_count", 0),
        "stale_count": focus_payload.get("stale_count", 0),
        "budget_exceeded_count": focus_payload.get("budget_exceeded_count", 0),
    }


def compact_read_model_digest(payload: dict[str, object]) -> dict[str, object] | None:
    digest_payload = None
    if (
        isinstance(payload, dict)
        and payload.get("watch_summary_line")
        and payload.get("action_summary_line")
    ):
        digest_payload = payload
    else:
        digest_payload = build_admin_read_model_snapshot_digest_payload(payload)
    if digest_payload is None:
        return None
    return {
        "tracked_count": digest_payload.get("tracked_count", 0),
        "alert_item_count": digest_payload.get("alert_item_count", 0),
        "missing_count": digest_payload.get("missing_count", 0),
        "stale_count": digest_payload.get("stale_count", 0),
        "budget_exceeded_count": digest_payload.get("budget_exceeded_count", 0),
        "watch_summary_line": digest_payload.get("watch_summary_line"),
        "action_summary_line": digest_payload.get("action_summary_line"),
        "top_watch_label": digest_payload.get("top_watch_label"),
        "top_watch_detail": digest_payload.get("top_watch_detail"),
        "top_action_label": digest_payload.get("top_action_label"),
        "top_action_detail": digest_payload.get("top_action_detail"),
        "generated_at_label": digest_payload.get("generated_at_label"),
        "staleness_seconds": digest_payload.get("staleness_seconds", 0),
    }


def compact_read_model_operator_summary(payload: dict[str, object]) -> dict[str, object] | None:
    operator_payload = None
    if isinstance(payload, dict) and payload.get("summary_line"):
        operator_payload = payload
    else:
        operator_payload = build_admin_read_model_snapshot_operator_payload(payload)
    if operator_payload is None:
        return None
    return {
        "summary_line": operator_payload.get("summary_line"),
        "focus_line": operator_payload.get("focus_line"),
        "watch_line": operator_payload.get("watch_line"),
        "action_line": operator_payload.get("action_line"),
        "drift_line": operator_payload.get("drift_line"),
        "tracked_count": operator_payload.get("tracked_count", 0),
        "alert_item_count": operator_payload.get("alert_item_count", 0),
        "missing_count": operator_payload.get("missing_count", 0),
        "stale_count": operator_payload.get("stale_count", 0),
        "budget_exceeded_count": operator_payload.get("budget_exceeded_count", 0),
        "generated_at_label": operator_payload.get("generated_at_label"),
        "staleness_seconds": operator_payload.get("staleness_seconds", 0),
    }


def compact_admin_summary_payload(payload: dict[str, object]) -> dict[str, object]:
    response = dict(payload)
    response.pop("retention_segments", None)
    response["lifecycle_offer_mix"] = compact_lifecycle_offer_mix(
        payload.get("lifecycle_offer_mix", {}),
    )
    response["lifecycle_campaign_attribution"] = compact_lifecycle_campaign_attribution(
        payload.get("lifecycle_campaign_attribution", {}),
    )
    response["pricing_intelligence"] = compact_pricing_intelligence(
        payload.get("pricing_intelligence", {}),
    )
    response["promo_attribution"] = compact_promo_attribution(
        payload.get("promo_attribution", {}),
    )
    response["referral_attribution"] = compact_referral_attribution(
        payload.get("referral_attribution", {}),
    )
    read_model_focus = compact_read_model_focus(payload.get("read_model_focus", {}))
    if read_model_focus is not None:
        response["read_model_focus"] = read_model_focus
    else:
        response.pop("read_model_focus", None)
    read_model_operator_summary = compact_read_model_operator_summary(
        payload.get("read_model_operator_summary", {}),
    )
    if read_model_operator_summary is not None:
        response["read_model_operator_summary"] = read_model_operator_summary
    else:
        response.pop("read_model_operator_summary", None)
    read_model_digest = compact_read_model_digest(payload.get("read_model_digest", {}))
    if read_model_digest is not None:
        response["read_model_digest"] = read_model_digest
    else:
        response.pop("read_model_digest", None)
    return response
