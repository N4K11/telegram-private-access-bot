from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, InviteLink, Payment, Subscription
from app.services.analytics_common import (
    _coerce_int,
    _load_paid_user_metrics,
    _parse_payload,
)
from app.services.analytics_lifecycle import (
    _LIFECYCLE_FAMILY_LABELS,
    _LIFECYCLE_RULE_LABELS,
    _LIFECYCLE_TOUCH_ACTIONS,
    _LIFECYCLE_VARIANT_LABELS,
    LIFECYCLE_ATTRIBUTION_WINDOW,
    _build_lifecycle_highlights_for_scope,
    _build_source_campaign_highlights,
    _build_source_campaign_watchlist,
    _lifecycle_rule_from_audit,
    _lifecycle_touch_family,
    _lifecycle_wave_from_audit,
    _new_lifecycle_metric_bucket,
    _sorted_source_campaign_items_for_action,
    _sorted_source_campaign_items_for_opportunity,
    _sorted_source_campaign_items_for_roi,
)
from app.services.analytics_models import (
    LifecycleCampaignAttributionSnapshot,
    LifecycleCampaignFamilySnapshot,
    LifecycleCampaignHighlightSnapshot,
    LifecycleCampaignPerformanceSnapshot,
    LifecycleCampaignRoiSnapshot,
    LifecycleCampaignRuleSnapshot,
    LifecycleCampaignWaveSnapshot,
    LifecycleOfferMixSnapshot,
    LifecycleOfferVariantSnapshot,
    LifecycleQueueSnapshot,
    LifecycleSourceCampaignSnapshot,
)
from app.services.conversion import conversion_source_label, normalize_conversion_source
from app.services.retention_automation import RECENT_EXPIRED_MAX_AGE, RECENT_EXPIRED_MIN_AGE
from app.utils.datetime import ensure_aware_utc


async def _build_lifecycle_queue_snapshot(
    session: AsyncSession,
    *,
    now: datetime,
) -> LifecycleQueueSnapshot:
    rows = list(
        (
            await session.execute(
                select(
                    Subscription.user_id,
                    Subscription.status,
                    Subscription.revoked_at,
                    Subscription.expires_at,
                    Subscription.warning_3d_sent_at,
                    Subscription.warning_1d_sent_at,
                    Subscription.expired_notice_sent_at,
                    Subscription.grace_revoke_after,
                )
            )
        ).all()
    )
    renewal_due_3d_users: set[int] = set()
    renewal_due_1d_users: set[int] = set()
    grace_period_users: set[int] = set()
    active_user_ids: set[int] = set()
    latest_expired_by_user: dict[int, datetime] = {}

    for (
        user_id,
        status,
        revoked_at,
        expires_at,
        warning_3d_sent_at,
        warning_1d_sent_at,
        _expired_notice_sent_at,
        grace_revoke_after,
    ) in rows:
        user_key = int(user_id)
        aware_expires_at = ensure_aware_utc(expires_at)
        if status == "active" and revoked_at is None and aware_expires_at > now:
            active_user_ids.add(user_key)
            if aware_expires_at <= now + timedelta(days=1) and warning_1d_sent_at is None:
                renewal_due_1d_users.add(user_key)
            elif aware_expires_at <= now + timedelta(days=3) and warning_3d_sent_at is None:
                renewal_due_3d_users.add(user_key)
        if (
            grace_revoke_after is not None
            and revoked_at is None
            and aware_expires_at <= now
            and ensure_aware_utc(grace_revoke_after) > now
        ):
            grace_period_users.add(user_key)
        if aware_expires_at <= now:
            previous = latest_expired_by_user.get(user_key)
            if previous is None or aware_expires_at > previous:
                latest_expired_by_user[user_key] = aware_expires_at

    win_back_ready_users = 0
    for user_id, expired_at in latest_expired_by_user.items():
        if user_id in active_user_ids:
            continue
        expired_delta = now - expired_at
        if RECENT_EXPIRED_MIN_AGE <= expired_delta <= RECENT_EXPIRED_MAX_AGE:
            win_back_ready_users += 1

    return LifecycleQueueSnapshot(
        renewal_due_3d_users=len(renewal_due_3d_users),
        renewal_due_1d_users=len(renewal_due_1d_users),
        grace_period_users=len(grace_period_users),
        win_back_ready_users=win_back_ready_users,
    )


async def _build_lifecycle_offer_mix(
    session: AsyncSession,
    *,
    now: datetime,
    lookback_days: int = 30,
) -> LifecycleOfferMixSnapshot:
    cutoff = now - timedelta(days=lookback_days)
    rows = list(
        (
            await session.execute(
                select(AuditLog.action, AuditLog.payload, AuditLog.created_at)
                .where(AuditLog.action.in_(_LIFECYCLE_TOUCH_ACTIONS))
                .where(AuditLog.created_at >= cutoff)
            )
        ).all()
    )

    total_sent_count = 0
    limited_primary_count = 0
    bundle_primary_count = 0
    bundle_extra_touch_count = 0
    cross_sell_touch_count = 0
    variant_counts: dict[str, int] = defaultdict(int)

    for action, raw_payload, created_at in rows:
        if ensure_aware_utc(created_at) < cutoff:
            continue
        payload = _parse_payload(raw_payload)
        total_sent_count += 1
        if bool(payload.get("limited_primary")):
            limited_primary_count += 1
        if bool(payload.get("bundle_primary")):
            bundle_primary_count += 1
        if int(payload.get("bundle_count", 0) or 0) > 0:
            bundle_extra_touch_count += 1
        if int(payload.get("cross_sell_count", 0) or 0) > 0:
            cross_sell_touch_count += 1
        variant = payload.get("offer_strategy") or payload.get("campaign_variant") or str(action)
        if isinstance(variant, str) and variant:
            variant_counts[variant] += 1

    variants = [
        LifecycleOfferVariantSnapshot(
            variant=variant,
            label=_LIFECYCLE_VARIANT_LABELS.get(variant, variant.replace("_", " ").title()),
            sent_count=sent_count,
        )
        for variant, sent_count in variant_counts.items()
    ]
    variants.sort(key=lambda item: (-item.sent_count, item.label, item.variant))
    return LifecycleOfferMixSnapshot(
        total_sent_count=total_sent_count,
        limited_primary_count=limited_primary_count,
        bundle_primary_count=bundle_primary_count,
        bundle_extra_touch_count=bundle_extra_touch_count,
        cross_sell_touch_count=cross_sell_touch_count,
        variants=tuple(variants[:5]),
    )


async def _build_lifecycle_campaign_attribution(
    session: AsyncSession,
    *,
    channel_titles: dict[int, str],
    now: datetime,
    lookback_days: int = 30,
) -> LifecycleCampaignAttributionSnapshot:
    cutoff = now - timedelta(days=lookback_days)
    touch_rows = list(
        (
            await session.execute(
                select(
                    AuditLog.action,
                    AuditLog.target_user_id,
                    AuditLog.payload,
                    AuditLog.created_at,
                )
                .where(AuditLog.action.in_(_LIFECYCLE_TOUCH_ACTIONS))
                .where(AuditLog.target_user_id.is_not(None))
                .where(AuditLog.created_at >= cutoff)
            )
        ).all()
    )

    touches_by_user: dict[int, list[dict[str, object]]] = defaultdict(list)
    variant_buckets: dict[str, dict[str, object]] = {}
    family_buckets: dict[str, dict[str, object]] = {}
    rule_buckets: dict[str, dict[str, object]] = {}
    wave_buckets: dict[str, dict[str, object]] = {}

    conversion_source_actions = (
        "buy_screen_viewed",
        "product_selected",
        "tariff_detail_opened",
        "offer_clicked",
        "invoice_created_stars",
        "invoice_created_crypto",
        "payment_paid_stars",
        "payment_paid_crypto",
        "invite_issued",
    )
    first_source_rows = list(
        (
            await session.execute(
                select(
                    AuditLog.target_user_id,
                    AuditLog.payload,
                    AuditLog.created_at,
                    AuditLog.id,
                )
                .where(AuditLog.action.in_(conversion_source_actions))
                .where(AuditLog.target_user_id.is_not(None))
                .order_by(
                    AuditLog.target_user_id.asc(),
                    AuditLog.created_at.asc(),
                    AuditLog.id.asc(),
                )
            )
        ).all()
    )
    first_source_by_user: dict[int, str] = {}
    for target_user_id, raw_payload, _created_at, _audit_id in first_source_rows:
        user_id = _coerce_int(target_user_id)
        if user_id is None or user_id in first_source_by_user:
            continue
        payload = _parse_payload(raw_payload)
        source = normalize_conversion_source(payload.get("source"))
        if source is None:
            continue
        first_source_by_user[user_id] = source

    source_paid_metrics = await _load_paid_user_metrics(
        session,
        user_ids=set(first_source_by_user),
    )
    source_acquired_users: dict[str, set[int]] = defaultdict(set)
    source_paid_users: dict[str, set[int]] = defaultdict(set)
    for user_id, source in first_source_by_user.items():
        source_acquired_users[source].add(user_id)
        metrics = source_paid_metrics.get(user_id)
        if metrics is not None and int(metrics["payment_count"]) > 0:
            source_paid_users[source].add(user_id)
    source_campaign_buckets: dict[tuple[str, str, str], dict[str, object]] = {}

    for action, target_user_id, raw_payload, created_at in touch_rows:
        if target_user_id is None:
            continue
        touch_time = ensure_aware_utc(created_at)
        payload = _parse_payload(raw_payload)
        action_name = str(action)
        variant = payload.get("offer_strategy") or payload.get("campaign_variant") or action_name
        if not isinstance(variant, str) or not variant:
            continue
        label = _LIFECYCLE_VARIANT_LABELS.get(variant, variant.replace("_", " ").title())
        family = _lifecycle_touch_family(action_name)
        family_label = _LIFECYCLE_FAMILY_LABELS.get(family, family.replace("_", " ").title())
        rule_key, rule_label = _lifecycle_rule_from_audit(action_name, payload)
        wave_mode, wave_label = _lifecycle_wave_from_audit(payload)
        user_id = int(target_user_id)
        touches_by_user[user_id].append(
            {
                "variant": variant,
                "family": family,
                "rule_key": rule_key,
                "wave_mode": wave_mode,
                "created_at": touch_time,
            }
        )
        variant_bucket = variant_buckets.setdefault(
            variant,
            _new_lifecycle_metric_bucket(label),
        )
        family_bucket = family_buckets.setdefault(
            family,
            _new_lifecycle_metric_bucket(family_label),
        )
        rule_bucket = rule_buckets.setdefault(
            rule_key,
            _new_lifecycle_metric_bucket(rule_label),
        )
        wave_bucket = wave_buckets.setdefault(
            wave_mode,
            _new_lifecycle_metric_bucket(wave_label),
        )
        source = first_source_by_user.get(user_id)
        if source is not None:
            source_key = (source, rule_key, wave_mode)
            source_bucket = source_campaign_buckets.setdefault(
                source_key,
                {
                    "source_label": conversion_source_label(source),
                    "source_acquired_users": len(source_acquired_users.get(source, set())),
                    "source_paid_users": len(source_paid_users.get(source, set())),
                    "rule_label": rule_label,
                    "wave_label": wave_label,
                    "sent_count": 0,
                    "paid_user_ids": set(),
                    "payment_ids": set(),
                    "invite_user_ids": set(),
                    "revenue_total": 0,
                    "second_product_user_ids": set(),
                    "second_product_payment_ids": set(),
                    "second_product_revenue_total": 0,
                },
            )
            source_bucket["sent_count"] = int(source_bucket["sent_count"]) + 1
        for bucket in (variant_bucket, family_bucket, rule_bucket, wave_bucket):
            bucket["sent_count"] = int(bucket["sent_count"]) + 1
            if bool(payload.get("limited_primary")):
                bucket["limited_primary_count"] = int(bucket["limited_primary_count"]) + 1
            if bool(payload.get("bundle_primary")):
                bucket["bundle_primary_count"] = int(bucket["bundle_primary_count"]) + 1
            if int(payload.get("bundle_count", 0) or 0) > 0:
                bucket["bundle_extra_touch_count"] = int(bucket["bundle_extra_touch_count"]) + 1
            if int(payload.get("cross_sell_count", 0) or 0) > 0:
                bucket["cross_sell_touch_count"] = int(bucket["cross_sell_touch_count"]) + 1
        family_variant_counts = family_bucket["variant_sent_counts"]
        if isinstance(family_variant_counts, defaultdict):
            family_variant_counts[variant] += 1
        rule_variant_counts = rule_bucket["variant_sent_counts"]
        if isinstance(rule_variant_counts, defaultdict):
            rule_variant_counts[variant] += 1
        rule_family_counts = rule_bucket["family_sent_counts"]
        if isinstance(rule_family_counts, defaultdict):
            rule_family_counts[family] += 1
        wave_rule_counts = wave_bucket["rule_sent_counts"]
        if isinstance(wave_rule_counts, defaultdict):
            wave_rule_counts[rule_key] += 1

    for user_touches in touches_by_user.values():
        user_touches.sort(key=lambda item: item["created_at"])

    payment_history_rows = list(
        (
            await session.execute(
                select(Payment.user_id, Payment.channel_id, Payment.paid_at)
                .where(Payment.status == "paid")
                .where(Payment.user_id.is_not(None))
                .where(Payment.channel_id.is_not(None))
                .where(Payment.paid_at.is_not(None))
            )
        ).all()
    )
    user_channel_first_paid_at: dict[int, dict[int, datetime]] = defaultdict(dict)
    for payment_user_id, payment_channel_id, payment_paid_at in payment_history_rows:
        if payment_user_id is None or payment_channel_id is None or payment_paid_at is None:
            continue
        user_key = int(payment_user_id)
        channel_key = int(payment_channel_id)
        paid_time = ensure_aware_utc(payment_paid_at)
        previous_first_paid = user_channel_first_paid_at[user_key].get(channel_key)
        if previous_first_paid is None or paid_time < previous_first_paid:
            user_channel_first_paid_at[user_key][channel_key] = paid_time

    payment_rows = list(
        (
            await session.execute(
                select(
                    Payment.id,
                    Payment.user_id,
                    Payment.channel_id,
                    Payment.amount,
                    Payment.paid_at,
                )
                .where(Payment.status == "paid")
                .where(Payment.user_id.is_not(None))
                .where(Payment.paid_at.is_not(None))
                .where(Payment.paid_at >= cutoff)
            )
        ).all()
    )
    total_paid_user_ids: set[int] = set()
    total_payment_ids: set[int] = set()
    total_revenue = 0
    for payment_id, user_id, channel_id, amount, paid_at in payment_rows:
        user_touches = touches_by_user.get(int(user_id))
        if not user_touches or paid_at is None:
            continue
        payment_time = ensure_aware_utc(paid_at)
        matched = [
            touch
            for touch in user_touches
            if (
                touch["created_at"]
                <= payment_time
                <= touch["created_at"] + LIFECYCLE_ATTRIBUTION_WINDOW
            )
        ]
        if not matched:
            continue
        touch = matched[-1]
        variant_bucket = variant_buckets[str(touch["variant"])]
        family_bucket = family_buckets[str(touch["family"])]
        rule_bucket = rule_buckets[str(touch["rule_key"])]
        wave_bucket = wave_buckets[str(touch["wave_mode"])]
        for bucket in (variant_bucket, family_bucket, rule_bucket, wave_bucket):
            paid_user_ids = bucket["paid_user_ids"]
            payment_ids = bucket["payment_ids"]
            if isinstance(paid_user_ids, set):
                paid_user_ids.add(int(user_id))
            if isinstance(payment_ids, set):
                payment_ids.add(int(payment_id))
            bucket["revenue_total"] = int(bucket["revenue_total"]) + int(amount or 0)

        source = first_source_by_user.get(int(user_id))
        source_bucket = None
        if source is not None:
            source_bucket = source_campaign_buckets.get(
                (source, str(touch["rule_key"]), str(touch["wave_mode"]))
            )
            if source_bucket is not None:
                paid_user_ids = source_bucket["paid_user_ids"]
                payment_ids = source_bucket["payment_ids"]
                if isinstance(paid_user_ids, set):
                    paid_user_ids.add(int(user_id))
                if isinstance(payment_ids, set):
                    payment_ids.add(int(payment_id))
                source_bucket["revenue_total"] = int(source_bucket["revenue_total"]) + int(
                    amount or 0
                )

        payment_channel_id = _coerce_int(channel_id)
        if payment_channel_id is not None:
            prior_paid_channels = [
                previous_channel_id
                for previous_channel_id, first_paid_at in (
                    user_channel_first_paid_at[int(user_id)].items()
                )
                if previous_channel_id != payment_channel_id and first_paid_at < payment_time
            ]
            if prior_paid_channels:
                second_product_user_ids = rule_bucket["second_product_user_ids"]
                second_product_payment_ids = rule_bucket["second_product_payment_ids"]
                secondary_channel_counts = rule_bucket["secondary_channel_counts"]
                if isinstance(second_product_user_ids, set):
                    second_product_user_ids.add(int(user_id))
                if isinstance(second_product_payment_ids, set):
                    second_product_payment_ids.add(int(payment_id))
                if isinstance(secondary_channel_counts, defaultdict):
                    secondary_channel_counts[payment_channel_id] += 1
                rule_bucket["second_product_revenue_total"] = (
                    int(rule_bucket["second_product_revenue_total"]) + int(amount or 0)
                )
                if source_bucket is not None:
                    second_product_user_ids = source_bucket["second_product_user_ids"]
                    second_product_payment_ids = source_bucket["second_product_payment_ids"]
                    if isinstance(second_product_user_ids, set):
                        second_product_user_ids.add(int(user_id))
                    if isinstance(second_product_payment_ids, set):
                        second_product_payment_ids.add(int(payment_id))
                    source_bucket["second_product_revenue_total"] = int(
                        source_bucket["second_product_revenue_total"]
                    ) + int(amount or 0)
        total_paid_user_ids.add(int(user_id))
        total_payment_ids.add(int(payment_id))
        total_revenue += int(amount or 0)

    invite_rows = list(
        (
            await session.execute(
                select(InviteLink.id, InviteLink.user_id, InviteLink.created_at)
                .where(InviteLink.created_at >= cutoff)
            )
        ).all()
    )
    total_invite_user_ids: set[int] = set()
    for _invite_id, user_id, created_at in invite_rows:
        user_touches = touches_by_user.get(int(user_id))
        if not user_touches:
            continue
        invite_time = ensure_aware_utc(created_at)
        matched = [
            touch
            for touch in user_touches
            if (
                touch["created_at"]
                <= invite_time
                <= touch["created_at"] + LIFECYCLE_ATTRIBUTION_WINDOW
            )
        ]
        if not matched:
            continue
        touch = matched[-1]
        variant_bucket = variant_buckets[str(touch["variant"])]
        family_bucket = family_buckets[str(touch["family"])]
        rule_bucket = rule_buckets[str(touch["rule_key"])]
        wave_bucket = wave_buckets[str(touch["wave_mode"])]
        for bucket in (variant_bucket, family_bucket, rule_bucket, wave_bucket):
            invite_user_ids = bucket["invite_user_ids"]
            if isinstance(invite_user_ids, set):
                invite_user_ids.add(int(user_id))
        source = first_source_by_user.get(int(user_id))
        if source is not None:
            source_bucket = source_campaign_buckets.get(
                (source, str(touch["rule_key"]), str(touch["wave_mode"]))
            )
            if source_bucket is not None:
                invite_user_ids = source_bucket["invite_user_ids"]
                if isinstance(invite_user_ids, set):
                    invite_user_ids.add(int(user_id))
        total_invite_user_ids.add(int(user_id))

    variants = [
        LifecycleCampaignPerformanceSnapshot(
            variant=variant,
            label=str(bucket["label"]),
            sent_count=int(bucket["sent_count"]),
            paid_users=len(bucket["paid_user_ids"]),
            payment_count=len(bucket["payment_ids"]),
            invite_issued_users=len(bucket["invite_user_ids"]),
            revenue_total=int(bucket["revenue_total"]),
            limited_primary_count=int(bucket["limited_primary_count"]),
            bundle_primary_count=int(bucket["bundle_primary_count"]),
            bundle_extra_touch_count=int(bucket["bundle_extra_touch_count"]),
            cross_sell_touch_count=int(bucket["cross_sell_touch_count"]),
        )
        for variant, bucket in variant_buckets.items()
    ]
    variants.sort(
        key=lambda item: (
            -item.revenue_total,
            -item.paid_users,
            -item.invite_issued_users,
            -item.sent_count,
            item.label,
            item.variant,
        )
    )

    families = []
    for family, bucket in family_buckets.items():
        variant_counts = bucket["variant_sent_counts"]
        top_variant = None
        top_variant_label = None
        if isinstance(variant_counts, defaultdict) and variant_counts:
            top_variant = min(
                variant_counts,
                key=lambda key: (
                    -int(variant_counts[key]),
                    _LIFECYCLE_VARIANT_LABELS.get(key, key),
                ),
            )
            top_variant_label = _LIFECYCLE_VARIANT_LABELS.get(
                top_variant,
                top_variant.replace("_", " ").title(),
            )
        families.append(
            LifecycleCampaignFamilySnapshot(
                family=family,
                label=str(bucket["label"]),
                sent_count=int(bucket["sent_count"]),
                paid_users=len(bucket["paid_user_ids"]),
                payment_count=len(bucket["payment_ids"]),
                invite_issued_users=len(bucket["invite_user_ids"]),
                revenue_total=int(bucket["revenue_total"]),
                limited_primary_count=int(bucket["limited_primary_count"]),
                bundle_primary_count=int(bucket["bundle_primary_count"]),
                bundle_extra_touch_count=int(bucket["bundle_extra_touch_count"]),
                cross_sell_touch_count=int(bucket["cross_sell_touch_count"]),
                top_variant=top_variant,
                top_variant_label=top_variant_label,
            )
        )
    families.sort(
        key=lambda item: (
            -item.revenue_total,
            -item.paid_users,
            -item.invite_issued_users,
            -item.sent_count,
            item.label,
            item.family,
        )
    )

    rules = []
    for rule_key, bucket in rule_buckets.items():
        variant_counts = bucket["variant_sent_counts"]
        top_variant = None
        top_variant_label = None
        if isinstance(variant_counts, defaultdict) and variant_counts:
            top_variant = min(
                variant_counts,
                key=lambda key: (
                    -int(variant_counts[key]),
                    _LIFECYCLE_VARIANT_LABELS.get(key, key),
                ),
            )
            top_variant_label = _LIFECYCLE_VARIANT_LABELS.get(
                top_variant,
                top_variant.replace("_", " ").title(),
            )
        family_counts = bucket["family_sent_counts"]
        family = "unclassified"
        if isinstance(family_counts, defaultdict) and family_counts:
            family = min(
                family_counts,
                key=lambda key: (-int(family_counts[key]), _LIFECYCLE_FAMILY_LABELS.get(key, key)),
            )
        rules.append(
            LifecycleCampaignRuleSnapshot(
                rule_key=rule_key,
                label=str(bucket["label"]),
                family=family,
                sent_count=int(bucket["sent_count"]),
                paid_users=len(bucket["paid_user_ids"]),
                payment_count=len(bucket["payment_ids"]),
                invite_issued_users=len(bucket["invite_user_ids"]),
                revenue_total=int(bucket["revenue_total"]),
                limited_primary_count=int(bucket["limited_primary_count"]),
                bundle_primary_count=int(bucket["bundle_primary_count"]),
                bundle_extra_touch_count=int(bucket["bundle_extra_touch_count"]),
                cross_sell_touch_count=int(bucket["cross_sell_touch_count"]),
                top_variant=top_variant,
                top_variant_label=top_variant_label,
            )
        )
    rules.sort(
        key=lambda item: (
            -item.revenue_total,
            -item.paid_users,
            -item.invite_issued_users,
            -item.sent_count,
            item.label,
            item.rule_key,
        )
    )

    waves = []
    for wave_mode, bucket in wave_buckets.items():
        rule_counts = bucket["rule_sent_counts"]
        top_rule_key = None
        top_rule_label = None
        if isinstance(rule_counts, defaultdict) and rule_counts:
            top_rule_key = min(
                rule_counts,
                key=lambda key: (-int(rule_counts[key]), _LIFECYCLE_RULE_LABELS.get(key, key)),
            )
            top_rule_label = _LIFECYCLE_RULE_LABELS.get(
                top_rule_key,
                top_rule_key.replace("_", " ").title(),
            )
        waves.append(
            LifecycleCampaignWaveSnapshot(
                wave_mode=wave_mode,
                label=str(bucket["label"]),
                sent_count=int(bucket["sent_count"]),
                paid_users=len(bucket["paid_user_ids"]),
                payment_count=len(bucket["payment_ids"]),
                invite_issued_users=len(bucket["invite_user_ids"]),
                revenue_total=int(bucket["revenue_total"]),
                limited_primary_count=int(bucket["limited_primary_count"]),
                bundle_primary_count=int(bucket["bundle_primary_count"]),
                bundle_extra_touch_count=int(bucket["bundle_extra_touch_count"]),
                cross_sell_touch_count=int(bucket["cross_sell_touch_count"]),
                top_rule_key=top_rule_key,
                top_rule_label=top_rule_label,
            )
        )
    waves.sort(
        key=lambda item: (
            -item.revenue_total,
            -item.paid_users,
            -item.invite_issued_users,
            -item.sent_count,
            item.label,
            item.wave_mode,
        )
    )

    roi = []
    for rule_key, bucket in rule_buckets.items():
        family_counts = bucket["family_sent_counts"]
        family = "unclassified"
        if isinstance(family_counts, defaultdict) and family_counts:
            family = min(
                family_counts,
                key=lambda key: (
                    -int(family_counts[key]),
                    _LIFECYCLE_FAMILY_LABELS.get(key, key),
                ),
            )
        secondary_channel_counts = bucket["secondary_channel_counts"]
        top_secondary_channel_id = None
        top_secondary_channel_title = None
        if isinstance(secondary_channel_counts, defaultdict) and secondary_channel_counts:
            top_secondary_channel_id = min(
                secondary_channel_counts,
                key=lambda key: (
                    -int(secondary_channel_counts[key]),
                    channel_titles.get(key, f"????? #{key}"),
                ),
            )
            top_secondary_channel_title = channel_titles.get(
                top_secondary_channel_id,
                f"????? #{top_secondary_channel_id}",
            )
        roi.append(
            LifecycleCampaignRoiSnapshot(
                rule_key=rule_key,
                label=str(bucket["label"]),
                family=family,
                sent_count=int(bucket["sent_count"]),
                paid_users=len(bucket["paid_user_ids"]),
                payment_count=len(bucket["payment_ids"]),
                invite_issued_users=len(bucket["invite_user_ids"]),
                revenue_total=int(bucket["revenue_total"]),
                second_product_paid_users=len(bucket["second_product_user_ids"]),
                second_product_payment_count=len(bucket["second_product_payment_ids"]),
                second_product_revenue_total=int(bucket["second_product_revenue_total"]),
                top_secondary_channel_id=top_secondary_channel_id,
                top_secondary_channel_title=top_secondary_channel_title,
            )
        )
    roi.sort(
        key=lambda item: (
            -item.second_product_revenue_total,
            -item.second_product_paid_users,
            -item.revenue_total,
            -item.paid_users,
            item.label,
            item.rule_key,
        )
    )

    source_campaigns = [
        LifecycleSourceCampaignSnapshot(
            source=source,
            source_label=str(bucket["source_label"]),
            source_acquired_users=int(bucket["source_acquired_users"]),
            source_paid_users=int(bucket["source_paid_users"]),
            rule_key=rule_key,
            rule_label=str(bucket["rule_label"]),
            wave_mode=wave_mode,
            wave_label=str(bucket["wave_label"]),
            sent_count=int(bucket["sent_count"]),
            paid_users=len(bucket["paid_user_ids"]),
            payment_count=len(bucket["payment_ids"]),
            invite_issued_users=len(bucket["invite_user_ids"]),
            revenue_total=int(bucket["revenue_total"]),
            second_product_paid_users=len(bucket["second_product_user_ids"]),
            second_product_payment_count=len(bucket["second_product_payment_ids"]),
            second_product_revenue_total=int(bucket["second_product_revenue_total"]),
        )
        for (source, rule_key, wave_mode), bucket in source_campaign_buckets.items()
    ]
    source_campaigns.sort(
        key=lambda item: (
            -item.second_product_revenue_total,
            -item.revenue_total,
            -item.paid_users,
            -item.sent_count,
            item.source_label,
            item.rule_label,
            item.wave_label,
        )
    )
    source_roi = _sorted_source_campaign_items_for_roi(source_campaigns)
    source_opportunities = _sorted_source_campaign_items_for_opportunity(source_campaigns)
    source_actions = _sorted_source_campaign_items_for_action(source_campaigns)
    source_highlights = _build_source_campaign_highlights(source_campaigns)
    source_watchlist = _build_source_campaign_watchlist(source_campaigns)

    highlights: list[LifecycleCampaignHighlightSnapshot] = []
    for scope, scope_items in (
        ("rules", rules),
        ("waves", waves),
        ("families", families),
        ("variants", variants),
    ):
        highlights.extend(_build_lifecycle_highlights_for_scope(scope, scope_items))

    return LifecycleCampaignAttributionSnapshot(
        total_sent_count=sum(int(bucket["sent_count"]) for bucket in variant_buckets.values()),
        total_paid_users=len(total_paid_user_ids),
        total_payment_count=len(total_payment_ids),
        total_invite_issued_users=len(total_invite_user_ids),
        revenue_total=total_revenue,
        variants=tuple(variants[:5]),
        families=tuple(families),
        rules=tuple(rules),
        waves=tuple(waves),
        highlights=tuple(highlights),
        roi=tuple(roi),
        source_roi=tuple(source_roi),
        source_opportunities=tuple(source_opportunities),
        source_actions=tuple(source_actions),
        source_highlights=tuple(source_highlights),
        source_watchlist=tuple(source_watchlist),
        source_campaigns=tuple(source_campaigns),
    )

