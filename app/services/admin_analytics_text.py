from __future__ import annotations

from app.services.analytics import (
    AnalyticsSnapshot,
    ConversionSourceSnapshot,
    LifecycleCampaignAttributionSnapshot,
    LifecycleOfferMixSnapshot,
    LifecycleQueueSnapshot,
    OfferPerformanceSnapshot,
    PricingIntelligenceSnapshot,
    ProductFunnelSnapshot,
    PromoAttributionSnapshot,
    ReferralAttributionSnapshot,
    ReferralTopReferrerSnapshot,
    SourceAcquisitionSnapshot,
)
from app.services.retention_automation import RetentionSegmentSnapshot

ANALYTICS_TITLE = "Аналитика"


def _conversion_percent(value: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{(value / total) * 100:.0f}%"


def _render_product_funnel(items: tuple[ProductFunnelSnapshot, ...]) -> list[str]:
    lines = ["Top products by revenue:"]
    if not items:
        lines.append("- No product data yet.")
        return lines
    for item in items[:5]:
        paid_percent = _conversion_percent(item.paid_users, item.buy_viewed_users)
        invite_percent = _conversion_percent(item.invite_issued_users, item.paid_users)
        lines.append(
            "- "
            f"{item.channel_title}: buy {item.buy_viewed_users} "
            f"-> offer {item.offer_clicked_users} "
            f"-> invoice {item.invoice_created_users} "
            f"-> paid {item.paid_users} ({paid_percent})"
        )
        lines.append(
            "  "
            f"product {item.product_selected_users} | "
            f"tariff {item.tariff_opened_users} | "
            f"invite {item.invite_issued_users} ({invite_percent}) | "
            f"repeat {item.repeat_purchase_users} | revenue {item.revenue_total}"
        )
    return lines


def _render_source_funnel(items: tuple[ConversionSourceSnapshot, ...]) -> list[str]:
    lines = ["Conversion sources:"]
    if not items:
        lines.append("- No attributed buy-flow traffic yet.")
        return lines
    for item in items[:5]:
        paid_percent = _conversion_percent(item.paid_users, item.buy_viewed_users)
        invoice_percent = _conversion_percent(item.invoice_created_users, item.buy_viewed_users)
        lines.append(
            "- "
            f"{item.label}: buy {item.buy_viewed_users} "
            f"-> offer {item.offer_clicked_users} "
            f"-> invoice {item.invoice_created_users} ({invoice_percent}) "
            f"-> paid {item.paid_users} ({paid_percent})"
        )
        if (
            item.product_selected_users
            or item.tariff_opened_users
            or item.invite_issued_users
            or item.offer_clicked_users
        ):
            lines.append(
                "  "
                f"product {item.product_selected_users} | "
                f"tariff {item.tariff_opened_users} | "
                f"offer {item.offer_clicked_users} | "
                f"invite {item.invite_issued_users}"
            )
    return lines


def _render_source_acquisition(items: tuple[SourceAcquisitionSnapshot, ...]) -> list[str]:
    lines = ["Acquisition ROI:"]
    if not items:
        lines.append("- No acquisition cohorts yet.")
        return lines
    for item in items[:5]:
        lines.append(
            "- "
            f"{item.label}: acquired {item.acquired_users} -> paid {item.paid_users} "
            f"({item.paid_conversion_percent}%)"
        )
        lines.append(
            "  "
            f"payments {item.payment_count} | invite {item.invite_issued_users} | "
            f"repeat {item.repeat_purchase_users} ({item.repeat_purchase_rate_percent}%)"
        )
        lines.append(
            "  "
            f"first-paid revenue {item.first_paid_revenue_total} | "
            f"lifetime revenue {item.lifetime_revenue_total}"
        )
        lines.append(
            "  "
            f"lifecycle 30d paid {item.lifecycle_paid_users} "
            f"({item.lifecycle_paid_from_paid_percent}%) | "
            f"payments {item.lifecycle_payment_count} | "
            f"invite {item.lifecycle_invite_issued_users} | "
            f"revenue {item.lifecycle_revenue_total}"
        )
        if (
            item.lifecycle_second_product_paid_users
            or item.top_rule_label is not None
            or item.top_wave_label is not None
        ):
            lines.append(
                "  "
                f"2nd product {item.lifecycle_second_product_paid_users} "
                f"({item.lifecycle_second_product_attach_percent}%) | "
                f"top rule {item.top_rule_label or '?'} | "
                f"top wave {item.top_wave_label or '?'}"
            )
    return lines


def _render_lifecycle_queues(queues: LifecycleQueueSnapshot) -> list[str]:
    return [
        "Renewal / Win-back:",
        f"- Renewal due 3d: {queues.renewal_due_3d_users}",
        f"- Renewal due 1d: {queues.renewal_due_1d_users}",
        f"- In grace period: {queues.grace_period_users}",
        f"- Win-back ready: {queues.win_back_ready_users}",
    ]


def _render_lifecycle_offer_mix(snapshot: LifecycleOfferMixSnapshot) -> list[str]:
    lines = [
        "Lifecycle offer mix:",
        f"- Touches 30d: {snapshot.total_sent_count}",
        f"- Limited primary: {snapshot.limited_primary_count}",
        f"- Bundle primary: {snapshot.bundle_primary_count}",
        f"- Bundle extras: {snapshot.bundle_extra_touch_count}",
        f"- Cross-sell touches: {snapshot.cross_sell_touch_count}",
    ]
    if not snapshot.variants:
        lines.append("- No lifecycle campaign data yet.")
        return lines
    lines.append("")
    lines.append("Top lifecycle variants:")
    for item in snapshot.variants:
        lines.append(f"- {item.label}: {item.sent_count}")
    return lines


def _render_lifecycle_campaign_attribution(
    snapshot: LifecycleCampaignAttributionSnapshot,
) -> list[str]:
    lines = [
        "Lifecycle campaign effectiveness:",
        f"- Touches 30d: {snapshot.total_sent_count}",
        f"- Paid users after touch: {snapshot.total_paid_users}",
        f"- Payments after touch: {snapshot.total_payment_count}",
        f"- Invite issued after touch: {snapshot.total_invite_issued_users}",
        f"- Revenue after touch: {snapshot.revenue_total}",
    ]
    if not snapshot.variants:
        lines.append("- No attributed lifecycle conversions yet.")
        return lines
    if snapshot.highlights:
        lines.append("")
        lines.append("CRM highlights:")
        for item in snapshot.highlights[:8]:
            note = f" | {item.note}" if item.note else ""
            lines.append(
                "- "
                f"{item.metric_label} [{item.scope_label}]: {item.entity_label} | "
                f"sent {item.sent_count} -> paid {item.paid_users} "
                f"({item.paid_conversion_percent}%)"
            )
            lines.append(
                "  "
                f"invite {item.invite_issued_users} ({item.invite_conversion_percent}%) | "
                f"payments {item.payment_count} | revenue {item.revenue_total}{note}"
            )
    lines.append("")
    lines.append("Top lifecycle campaigns:")
    for item in snapshot.variants:
        lines.append(
            "- "
            f"{item.label}: sent {item.sent_count} -> paid {item.paid_users} "
            f"({item.paid_conversion_percent}%) -> invite {item.invite_issued_users} "
            f"({item.invite_conversion_percent}%)"
        )
        lines.append(
            "  "
            f"payments {item.payment_count} | revenue {item.revenue_total} | "
            f"limited {item.limited_primary_count} | bundle {item.bundle_extra_touch_count} | "
            f"cross-sell {item.cross_sell_touch_count}"
        )
    if snapshot.roi:
        lines.append("")
        lines.append("Commercial ROI:")
        for item in snapshot.roi[:5]:
            secondary = (
                f" | top secondary {item.top_secondary_channel_title}"
                if item.top_secondary_channel_title
                else ""
            )
            lines.append(
                "- "
                f"{item.label}: paid {item.paid_users} | invite {item.invite_issued_users} | "
                f"2nd product {item.second_product_paid_users} "
                f"({item.second_product_attach_from_paid_percent}% of paid)"
            )
            lines.append(
                "  "
                f"2nd payments {item.second_product_payment_count} | "
                f"2nd revenue {item.second_product_revenue_total} | "
                f"total revenue {item.revenue_total}{secondary}"
            )
    if snapshot.source_roi:
        lines.append("")
        lines.append("Source ROI leaders:")
        for item in snapshot.source_roi[:5]:
            lines.append(
                "- "
                f"{item.source_label}: {item.rule_label} | {item.wave_label} | "
                f"revenue {item.revenue_total} | 2nd revenue {item.second_product_revenue_total}"
            )
            lines.append(
                "  "
                f"avg/source-paid {item.average_revenue_per_source_paid_user} | "
                f"source paid share {item.paid_share_of_source_paid_percent}% | "
                f"2nd share {item.second_product_revenue_share_percent}% | "
                f"2nd upside {item.second_product_upside_users}"
            )
    if snapshot.source_opportunities:
        lines.append("")
        lines.append("Source opportunities:")
        for item in snapshot.source_opportunities[:5]:
            lines.append(
                "- "
                f"{item.opportunity_label}: {item.source_label} | "
                f"{item.rule_label} | {item.wave_label}"
            )
            lines.append(
                "  "
                f"score {item.opportunity_score} | source gap {item.source_paid_gap_users} | "
                f"invite gap {item.invite_gap_users} | "
                f"2nd upside {item.second_product_upside_users} | "
                f"revenue {item.revenue_total}"
            )
    if snapshot.source_actions:
        lines.append("")
        lines.append("Source actions:")
        for item in snapshot.source_actions[:5]:
            lines.append(
                "- "
                f"{item.recommended_action_label}: {item.source_label} | "
                f"{item.rule_label} | {item.wave_label}"
            )
            lines.append(
                "  "
                f"issue {item.primary_issue_label} | score {item.opportunity_score} | "
                f"source gap {item.source_paid_gap_users} | invite gap {item.invite_gap_users} | "
                f"2nd upside {item.second_product_upside_users}"
            )
            lines.append(f"  {item.recommended_action_note}")
    if snapshot.source_highlights:
        lines.append("")
        lines.append("Source leaders:")
        for item in snapshot.source_highlights[:6]:
            note = f" | {item.note}" if item.note else ""
            lines.append(
                "- "
                f"{item.metric_label}: {item.source_label} | {item.rule_label} | {item.wave_label}"
            )
            lines.append(
                "  "
                f"sent {item.sent_count} -> paid {item.paid_users} "
                f"({item.paid_conversion_percent}%) | source paid share "
                f"{item.paid_share_of_source_paid_percent}% | invite "
                f"{item.invite_issued_users} ({item.invite_conversion_percent}%) | "
                f"2nd product {item.second_product_paid_users} "
                f"({item.second_product_attach_percent}%) | revenue {item.revenue_total}{note}"
            )
    if snapshot.source_watchlist:
        lines.append("")
        lines.append("Source watchlist:")
        for item in snapshot.source_watchlist[:6]:
            note = f" | {item.note}" if item.note else ""
            lines.append(
                "- "
                f"{item.metric_label}: {item.source_label} | {item.rule_label} | {item.wave_label}"
            )
            lines.append(
                "  "
                f"sent {item.sent_count} -> paid {item.paid_users} "
                f"({item.paid_conversion_percent}%) | source paid share "
                f"{item.paid_share_of_source_paid_percent}% | invite "
                f"{item.invite_issued_users} ({item.invite_conversion_percent}%) | "
                f"2nd product {item.second_product_paid_users} "
                f"({item.second_product_attach_percent}%) | revenue {item.revenue_total}{note}"
            )
    if snapshot.source_campaigns:
        lines.append("")
        lines.append("Source x campaign:")
        for item in snapshot.source_campaigns[:5]:
            lines.append(
                "- "
                f"{item.source_label}: {item.rule_label} | {item.wave_label} | "
                f"sent {item.sent_count} -> paid {item.paid_users} "
                f"({item.paid_conversion_percent}%)"
            )
            lines.append(
                "  "
                f"source paid share {item.paid_share_of_source_paid_percent}% | "
                f"invite {item.invite_issued_users} ({item.invite_conversion_percent}%) | "
                f"2nd product {item.second_product_paid_users} "
                f"({item.second_product_attach_percent}%) | revenue {item.revenue_total}"
            )
    if snapshot.rules:
        lines.append("")
        lines.append("Managed waves:")
        for item in snapshot.rules:
            family = item.family.replace("_", " ").title()
            top_variant = f" | top {item.top_variant_label}" if item.top_variant_label else ""
            lines.append(
                "- "
                f"{item.label}: sent {item.sent_count} -> paid {item.paid_users} "
                f"({item.paid_conversion_percent}%) -> invite {item.invite_issued_users} "
                f"({item.invite_conversion_percent}%)"
            )
            lines.append(
                "  "
                f"family {family} | payments {item.payment_count} | "
                f"revenue {item.revenue_total}{top_variant}"
            )
    if snapshot.waves:
        lines.append("")
        lines.append("Wave modes:")
        for item in snapshot.waves:
            top_rule = f" | top {item.top_rule_label}" if item.top_rule_label else ""
            lines.append(
                "- "
                f"{item.label}: sent {item.sent_count} -> paid {item.paid_users} "
                f"({item.paid_conversion_percent}%) -> invite {item.invite_issued_users} "
                f"({item.invite_conversion_percent}%)"
            )
            lines.append(
                "  "
                f"payments {item.payment_count} | revenue {item.revenue_total}{top_rule}"
            )
    if snapshot.families:
        lines.append("")
        lines.append("Touch families:")
        for item in snapshot.families:
            top_variant = f" | top {item.top_variant_label}" if item.top_variant_label else ""
            lines.append(
                "- "
                f"{item.label}: sent {item.sent_count} -> paid {item.paid_users} "
                f"({item.paid_conversion_percent}%) -> invite {item.invite_issued_users} "
                f"({item.invite_conversion_percent}%)"
            )
            lines.append(
                "  "
                f"payments {item.payment_count} | revenue {item.revenue_total}{top_variant}"
            )
    return lines


def _render_retention_segments(
    snapshot: AnalyticsSnapshot,
    items: tuple[RetentionSegmentSnapshot, ...],
) -> list[str]:
    lines = [
        "Retention / CRM:",
        f"- Paid users total: {snapshot.paid_users_total}",
        f"- Repeat purchase rate: {snapshot.repeat_purchase_rate_percent}%",
    ]
    if not items:
        lines.append("- No retention segments yet.")
        return lines
    for item in items:
        lines.append(
            "- "
            f"{item.label}: candidates {item.candidate_count} | "
            f"recently sent {item.recent_sent_count} | "
            f"dedupe {item.dedupe_window_hours}h"
        )
    return lines


def _render_top_referrers(items: tuple[ReferralTopReferrerSnapshot, ...]) -> list[str]:
    lines = ["Top referrers:"]
    if not items:
        lines.append("- No referral leaders yet.")
        return lines
    for item in items[:3]:
        lines.append(
            "- "
            f"{item.display_name}: invited {item.invited_users_count} | "
            f"paid {item.paid_referrals_count} ({item.conversion_percent}%) | "
            f"lifetime revenue {item.lifetime_revenue_total}"
        )
        lines.append(
            "  "
            f"first-paid revenue {item.first_paid_revenue_total} | "
            f"issued {item.reward_days_issued}d | pending {item.pending_reward_days}d"
        )
    return lines


def _render_promo_and_referral(
    promo: PromoAttributionSnapshot,
    referral: ReferralAttributionSnapshot,
) -> list[str]:
    lines = [
        "Promo / Referral:",
        f"- Promo payments: {promo.total_payment_count}",
        f"- Promo paid users: {promo.total_paid_users}",
        f"- Promo gross revenue: {promo.gross_revenue_total}",
        f"- Promo net revenue: {promo.revenue_total}",
        f"- Promo discount total: {promo.discount_total} ({promo.discount_share_percent}%)",
        f"- Referred users: {referral.total_referred_users}",
        f"- Paid referrals: {referral.paid_referred_users} ({referral.paid_conversion_percent}%)",
        f"- Rewarded referrals: {referral.rewarded_referrals_count}",
        f"- Referral first-paid revenue: {referral.first_paid_revenue_total}",
        f"- Referral lifetime revenue: {referral.lifetime_referred_revenue_total}",
        f"- Reward days issued: {referral.reward_days_issued_total}",
        f"- Pending referral bonus days: {referral.pending_reward_days_total}",
        f"- Suspicious referral events: {referral.suspicious_event_count}",
    ]
    if promo.campaigns:
        lines.append("")
        lines.append("Top promo campaigns:")
        for item in promo.campaigns[:3]:
            lines.append(
                "- "
                f"{item.label}: users {item.paid_users} | payments {item.payment_count} | "
                f"net {item.revenue_total}"
            )
            lines.append(
                "  "
                f"gross {item.gross_revenue_total} | discount {item.discount_total} "
                f"({item.discount_share_percent}%)"
            )
    lines.append("")
    lines.extend(_render_top_referrers(referral.top_referrers))
    return lines


def _render_offer_row(item: OfferPerformanceSnapshot) -> list[str]:
    flags: list[str] = []
    if item.offer_group:
        flags.append(f"group {item.offer_group}")
    if item.is_featured:
        flags.append("featured")
    if item.is_default_offer:
        flags.append("default")
    suffix = f" | {' | '.join(flags)}" if flags else ""
    return [
        "- "
        f"{item.channel_title} / {item.tariff_name}: open {item.opened_users} "
        f"-> click {item.clicked_users} ({item.open_to_click_percent}%) "
        f"-> paid {item.paid_users} ({item.click_to_paid_percent}%)",
        "  "
        f"invoice {item.invoice_created_users} ({item.invoice_to_paid_percent}%) | "
        f"payments {item.payment_count} | avg {item.average_payment_amount} | "
        f"revenue {item.revenue_total} | {item.price_stars} Stars / {item.duration_days}d{suffix}",
    ]


def _render_pricing_intelligence(snapshot: PricingIntelligenceSnapshot) -> list[str]:
    lines = [
        "Pricing / Offers:",
        f"- Average payment amount: {snapshot.average_payment_amount}",
        (
            f"- Stars revenue: {snapshot.stars_revenue_total} "
            f"({snapshot.stars_revenue_share_percent}%)"
        ),
        (
            f"- Crypto revenue: {snapshot.crypto_revenue_total} "
            f"({snapshot.crypto_revenue_share_percent}%)"
        ),
        (
            f"- Multi-product paid users: {snapshot.multi_product_paid_users} "
            f"({snapshot.multi_product_attach_rate_percent}%)"
        ),
        f"- Featured-offer revenue: {snapshot.featured_revenue_total}",
        f"- Default-offer revenue: {snapshot.default_revenue_total}",
    ]
    if snapshot.top_revenue_offer is not None:
        lines.append(
            "- Revenue leader: "
            f"{snapshot.top_revenue_offer.channel_title} / "
            f"{snapshot.top_revenue_offer.tariff_name} "
            f"({snapshot.top_revenue_offer.revenue_total})"
        )
    if snapshot.top_conversion_offer is not None:
        lines.append(
            "- Conversion leader: "
            f"{snapshot.top_conversion_offer.channel_title} / "
            f"{snapshot.top_conversion_offer.tariff_name} "
            f"({snapshot.top_conversion_offer.click_to_paid_percent}% click->paid)"
        )
    if snapshot.top_product_pairs:
        lines.append("")
        lines.append("Top product pairs:")
        for item in snapshot.top_product_pairs[:3]:
            lines.append(
                "- "
                f"{item.primary_channel_title} -> {item.secondary_channel_title}: "
                f"attached {item.attached_paid_users}/{item.base_paid_users} "
                f"({item.attach_rate_percent}%)"
            )
            lines.append(
                "  "
                f"secondary revenue {item.secondary_revenue_total} | "
                f"pair revenue {item.pair_revenue_total}"
            )
    if snapshot.top_pair_campaigns:
        lines.append("")
        lines.append("Cross-sell wave leaders:")
        for item in snapshot.top_pair_campaigns[:3]:
            lines.append(
                "- "
                f"{item.primary_channel_title} -> {item.secondary_channel_title} via "
                f"{item.rule_label}: attached {item.attached_paid_users}/{item.base_paid_users} "
                f"({item.attach_rate_percent}%)"
            )
            lines.append(
                "  "
                f"wave {item.wave_label} | payments {item.payment_count} | "
                f"secondary revenue {item.secondary_revenue_total}"
            )
    if not snapshot.top_offers:
        lines.append("- No offer-performance data yet.")
        return lines
    lines.append("")
    lines.append("Top offers:")
    for item in snapshot.top_offers[:5]:
        lines.extend(_render_offer_row(item))
    return lines


def render_admin_analytics_text(snapshot: AnalyticsSnapshot) -> str:
    buy_percent = _conversion_percent(
        snapshot.conversion_buy_viewed,
        snapshot.conversion_started,
    )
    product_percent = _conversion_percent(
        snapshot.conversion_product_selected,
        snapshot.conversion_buy_viewed,
    )
    detail_percent = _conversion_percent(
        snapshot.conversion_tariff_opened,
        snapshot.conversion_buy_viewed,
    )
    offer_percent = _conversion_percent(
        snapshot.conversion_offer_clicked,
        snapshot.conversion_buy_viewed,
    )
    invoice_percent = _conversion_percent(
        snapshot.conversion_invoice_created,
        snapshot.conversion_buy_viewed,
    )
    paid_percent = _conversion_percent(
        snapshot.conversion_paid,
        snapshot.conversion_buy_viewed,
    )
    invite_percent = _conversion_percent(
        snapshot.conversion_invite_issued,
        snapshot.conversion_paid,
    )
    lines = [
        ANALYTICS_TITLE,
        "",
        "Users and subscriptions:",
        f"- Total users: {snapshot.total_users}",
        f"- Active subscriptions: {snapshot.active_subscriptions}",
        f"- Expired subscriptions: {snapshot.expired_users}",
        f"- Never paid: {snapshot.never_paid_users}",
        f"- Blocked: {snapshot.blocked_users}",
        "",
        "Revenue:",
        f"- Today: {snapshot.revenue_today}",
        f"- 7 days: {snapshot.revenue_7_days}",
        f"- 30 days: {snapshot.revenue_30_days}",
        f"- All time: {snapshot.revenue_total}",
        "",
        "Payments:",
        f"- Stars: {snapshot.stars_payments}",
        f"- Crypto: {snapshot.crypto_payments}",
        "",
        "Funnel:",
        f"- /start: {snapshot.conversion_started}",
        f"- Buy screen: {snapshot.conversion_buy_viewed} ({buy_percent})",
        f"- Product selected: {snapshot.conversion_product_selected} ({product_percent})",
        f"- Tariff opened: {snapshot.conversion_tariff_opened} ({detail_percent})",
        f"- Offer clicked: {snapshot.conversion_offer_clicked} ({offer_percent})",
        f"- Invoice created: {snapshot.conversion_invoice_created} ({invoice_percent})",
        f"- Paid: {snapshot.conversion_paid} ({paid_percent})",
        f"- Invite issued: {snapshot.conversion_invite_issued} ({invite_percent})",
        f"- Repeat purchases: {snapshot.repeat_purchase_users}",
        "",
    ]
    lines.extend(_render_lifecycle_queues(snapshot.lifecycle_queues))
    lines.append("")
    lines.extend(_render_lifecycle_offer_mix(snapshot.lifecycle_offer_mix))
    lines.append("")
    lines.extend(_render_lifecycle_campaign_attribution(snapshot.lifecycle_campaign_attribution))
    lines.append("")
    lines.extend(_render_retention_segments(snapshot, snapshot.retention_segments))
    lines.append("")
    lines.extend(_render_pricing_intelligence(snapshot.pricing_intelligence))
    lines.append("")
    lines.extend(_render_source_funnel(snapshot.source_funnel))
    lines.append("")
    lines.extend(_render_source_acquisition(snapshot.source_acquisition))
    lines.extend(
        [
            "",
            *_render_promo_and_referral(
                snapshot.promo_attribution,
                snapshot.referral_attribution,
            ),
            "",
        ]
    )
    lines.extend(_render_product_funnel(snapshot.product_funnel))
    return "\n".join(lines)


def append_admin_analytics_meta(
    text: str,
    *,
    source: str,
    staleness_seconds: int,
    build_duration_ms: int,
) -> str:
    return (
        text
        + "\n\n"
        + f"Data source: {source} | staleness: {staleness_seconds}s | build: {build_duration_ms}ms"
    )
