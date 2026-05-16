from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from app.services.analytics_models import (
    LifecycleCampaignFamilySnapshot,
    LifecycleCampaignHighlightSnapshot,
    LifecycleCampaignPerformanceSnapshot,
    LifecycleCampaignRuleSnapshot,
    LifecycleCampaignWaveSnapshot,
    LifecycleSourceCampaignHighlightSnapshot,
    LifecycleSourceCampaignSnapshot,
)
from app.services.lifecycle_campaign_rules import CAMPAIGN_WAVE_LABELS

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


