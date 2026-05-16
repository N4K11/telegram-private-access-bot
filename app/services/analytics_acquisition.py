from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, InviteLink, Payment
from app.services.analytics_common import (
    _coerce_int,
    _load_invite_user_ids,
    _load_paid_user_metrics,
    _parse_payload,
)
from app.services.analytics_lifecycle import (
    _LIFECYCLE_RULE_LABELS,
    _LIFECYCLE_TOUCH_ACTIONS,
    _LIFECYCLE_WAVE_LABELS,
    LIFECYCLE_ATTRIBUTION_WINDOW,
    _lifecycle_rule_from_audit,
    _lifecycle_wave_from_audit,
)
from app.services.analytics_models import SourceAcquisitionSnapshot
from app.services.conversion import conversion_source_label, normalize_conversion_source
from app.utils.datetime import ensure_aware_utc, utcnow


async def _build_source_acquisition(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 5,
    lookback_days: int = 30,
) -> tuple[SourceAcquisitionSnapshot, ...]:
    action_names = (
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
    result = await session.execute(
        select(
            AuditLog.target_user_id,
            AuditLog.payload,
            AuditLog.created_at,
            AuditLog.id,
        )
        .where(AuditLog.action.in_(action_names))
        .where(AuditLog.target_user_id.is_not(None))
        .order_by(
            AuditLog.target_user_id.asc(),
            AuditLog.created_at.asc(),
            AuditLog.id.asc(),
        )
    )
    first_source_by_user: dict[int, str] = {}
    for target_user_id, raw_payload, _created_at, _audit_id in result.all():
        user_id = _coerce_int(target_user_id)
        if user_id is None or user_id in first_source_by_user:
            continue
        payload = _parse_payload(raw_payload)
        source = normalize_conversion_source(payload.get("source"))
        if source is None:
            continue
        first_source_by_user[user_id] = source

    if not first_source_by_user:
        return tuple()

    cohort_user_ids = set(first_source_by_user)
    paid_metrics_by_user = await _load_paid_user_metrics(session, user_ids=cohort_user_ids)
    invite_user_ids = await _load_invite_user_ids(session, user_ids=cohort_user_ids)
    current_time = ensure_aware_utc(now or utcnow())
    cutoff = current_time - timedelta(days=lookback_days)

    lifecycle_touch_rows = list(
        (
            await session.execute(
                select(
                    AuditLog.action,
                    AuditLog.target_user_id,
                    AuditLog.payload,
                    AuditLog.created_at,
                )
                .where(AuditLog.action.in_(_LIFECYCLE_TOUCH_ACTIONS))
                .where(AuditLog.target_user_id.in_(cohort_user_ids))
                .where(AuditLog.created_at >= cutoff)
            )
        ).all()
    )
    lifecycle_touches_by_user: dict[int, list[dict[str, object]]] = defaultdict(list)
    for action, target_user_id, raw_payload, created_at in lifecycle_touch_rows:
        user_id = _coerce_int(target_user_id)
        if user_id is None:
            continue
        payload = _parse_payload(raw_payload)
        rule_key, rule_label = _lifecycle_rule_from_audit(str(action), payload)
        wave_mode, wave_label = _lifecycle_wave_from_audit(payload)
        lifecycle_touches_by_user[user_id].append(
            {
                "created_at": ensure_aware_utc(created_at),
                "rule_key": rule_key,
                "rule_label": rule_label,
                "wave_mode": wave_mode,
                "wave_label": wave_label,
            }
        )
    for user_touches in lifecycle_touches_by_user.values():
        user_touches.sort(key=lambda item: item["created_at"])

    payment_history_rows = list(
        (
            await session.execute(
                select(Payment.user_id, Payment.channel_id, Payment.paid_at)
                .where(Payment.status == "paid")
                .where(Payment.user_id.in_(cohort_user_ids))
                .where(Payment.channel_id.is_not(None))
                .where(Payment.paid_at.is_not(None))
            )
        ).all()
    )
    user_channel_first_paid_at: dict[int, dict[int, datetime]] = defaultdict(dict)
    for payment_user_id, payment_channel_id, payment_paid_at in payment_history_rows:
        user_key = _coerce_int(payment_user_id)
        channel_key = _coerce_int(payment_channel_id)
        if user_key is None or channel_key is None or payment_paid_at is None:
            continue
        paid_time = ensure_aware_utc(payment_paid_at)
        previous_first_paid = user_channel_first_paid_at[user_key].get(channel_key)
        if previous_first_paid is None or paid_time < previous_first_paid:
            user_channel_first_paid_at[user_key][channel_key] = paid_time

    lifecycle_payment_rows = list(
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
                .where(Payment.user_id.in_(cohort_user_ids))
                .where(Payment.paid_at.is_not(None))
                .where(Payment.paid_at >= cutoff)
            )
        ).all()
    )
    lifecycle_invite_rows = list(
        (
            await session.execute(
                select(InviteLink.user_id, InviteLink.created_at)
                .where(InviteLink.user_id.in_(cohort_user_ids))
                .where(InviteLink.created_at >= cutoff)
            )
        ).all()
    )

    grouped: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "label": "",
            "acquired_user_ids": set(),
            "paid_user_ids": set(),
            "invite_user_ids": set(),
            "repeat_purchase_user_ids": set(),
            "payment_count": 0,
            "first_paid_revenue_total": 0,
            "lifetime_revenue_total": 0,
            "lifecycle_paid_user_ids": set(),
            "lifecycle_payment_ids": set(),
            "lifecycle_invite_user_ids": set(),
            "lifecycle_revenue_total": 0,
            "lifecycle_second_product_user_ids": set(),
            "lifecycle_second_product_payment_ids": set(),
            "lifecycle_second_product_revenue_total": 0,
            "rule_revenue_totals": defaultdict(int),
            "wave_revenue_totals": defaultdict(int),
            "rule_labels": {},
            "wave_labels": {},
        }
    )
    for user_id, source in first_source_by_user.items():
        bucket = grouped[source]
        bucket["label"] = conversion_source_label(source)
        acquired_user_ids = bucket["acquired_user_ids"]
        if isinstance(acquired_user_ids, set):
            acquired_user_ids.add(user_id)
        if user_id in invite_user_ids:
            invite_users = bucket["invite_user_ids"]
            if isinstance(invite_users, set):
                invite_users.add(user_id)
        metrics = paid_metrics_by_user.get(user_id)
        if metrics is None:
            continue
        paid_user_ids = bucket["paid_user_ids"]
        repeat_user_ids = bucket["repeat_purchase_user_ids"]
        if isinstance(paid_user_ids, set):
            paid_user_ids.add(user_id)
        if isinstance(repeat_user_ids, set) and int(metrics["payment_count"]) > 1:
            repeat_user_ids.add(user_id)
        bucket["payment_count"] = int(bucket["payment_count"]) + int(metrics["payment_count"])
        bucket["first_paid_revenue_total"] = int(bucket["first_paid_revenue_total"]) + int(
            metrics["first_paid_revenue_total"]
        )
        bucket["lifetime_revenue_total"] = int(bucket["lifetime_revenue_total"]) + int(
            metrics["lifetime_revenue_total"]
        )

    for payment_id, payment_user_id, payment_channel_id, amount, paid_at in lifecycle_payment_rows:
        user_key = _coerce_int(payment_user_id)
        if user_key is None or paid_at is None:
            continue
        user_touches = lifecycle_touches_by_user.get(user_key)
        if not user_touches:
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
        source = first_source_by_user.get(user_key)
        if source is None:
            continue
        touch = matched[-1]
        bucket = grouped[source]
        lifecycle_paid_user_ids = bucket["lifecycle_paid_user_ids"]
        lifecycle_payment_ids = bucket["lifecycle_payment_ids"]
        if isinstance(lifecycle_paid_user_ids, set):
            lifecycle_paid_user_ids.add(user_key)
        payment_key = _coerce_int(payment_id)
        if isinstance(lifecycle_payment_ids, set) and payment_key is not None:
            lifecycle_payment_ids.add(payment_key)
        payment_amount = int(amount or 0)
        bucket["lifecycle_revenue_total"] = int(bucket["lifecycle_revenue_total"]) + payment_amount
        rule_key = str(touch["rule_key"])
        rule_label = str(touch["rule_label"])
        wave_mode = str(touch["wave_mode"])
        wave_label = str(touch["wave_label"])
        rule_revenue_totals = bucket["rule_revenue_totals"]
        wave_revenue_totals = bucket["wave_revenue_totals"]
        rule_labels = bucket["rule_labels"]
        wave_labels = bucket["wave_labels"]
        if isinstance(rule_revenue_totals, defaultdict):
            rule_revenue_totals[rule_key] += payment_amount
        if isinstance(wave_revenue_totals, defaultdict):
            wave_revenue_totals[wave_mode] += payment_amount
        if isinstance(rule_labels, dict):
            rule_labels[rule_key] = rule_label
        if isinstance(wave_labels, dict):
            wave_labels[wave_mode] = wave_label

        payment_channel_key = _coerce_int(payment_channel_id)
        if payment_channel_key is not None:
            prior_paid_channels = [
                previous_channel_id
                for previous_channel_id, first_paid_at in (
                    user_channel_first_paid_at[user_key].items()
                )
                if previous_channel_id != payment_channel_key and first_paid_at < payment_time
            ]
            if prior_paid_channels:
                second_product_user_ids = bucket["lifecycle_second_product_user_ids"]
                second_product_payment_ids = bucket["lifecycle_second_product_payment_ids"]
                if isinstance(second_product_user_ids, set):
                    second_product_user_ids.add(user_key)
                if isinstance(second_product_payment_ids, set) and payment_key is not None:
                    second_product_payment_ids.add(payment_key)
                bucket["lifecycle_second_product_revenue_total"] = int(
                    bucket["lifecycle_second_product_revenue_total"]
                ) + payment_amount

    for invite_user_id, created_at in lifecycle_invite_rows:
        user_key = _coerce_int(invite_user_id)
        if user_key is None or created_at is None:
            continue
        user_touches = lifecycle_touches_by_user.get(user_key)
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
        source = first_source_by_user.get(user_key)
        if source is None:
            continue
        lifecycle_invite_user_ids = grouped[source]["lifecycle_invite_user_ids"]
        if isinstance(lifecycle_invite_user_ids, set):
            lifecycle_invite_user_ids.add(user_key)

    items: list[SourceAcquisitionSnapshot] = []
    for source, bucket in grouped.items():
        rule_revenue_totals = bucket["rule_revenue_totals"]
        wave_revenue_totals = bucket["wave_revenue_totals"]
        rule_labels = bucket["rule_labels"]
        wave_labels = bucket["wave_labels"]
        top_rule_key = None
        top_rule_label = None
        top_wave_mode = None
        top_wave_label = None
        if isinstance(rule_revenue_totals, defaultdict) and rule_revenue_totals:
            top_rule_key = min(
                rule_revenue_totals,
                key=lambda key: (
                    -int(rule_revenue_totals[key]),
                    str(rule_labels.get(key) or key),
                ),
            )
            top_rule_label = str(
                rule_labels.get(top_rule_key)
                or _LIFECYCLE_RULE_LABELS.get(
                    top_rule_key,
                    top_rule_key.replace("_", " ").title(),
                )
            )
        if isinstance(wave_revenue_totals, defaultdict) and wave_revenue_totals:
            top_wave_mode = min(
                wave_revenue_totals,
                key=lambda key: (
                    -int(wave_revenue_totals[key]),
                    str(wave_labels.get(key) or key),
                ),
            )
            top_wave_label = str(
                wave_labels.get(top_wave_mode)
                or _LIFECYCLE_WAVE_LABELS.get(
                    top_wave_mode,
                    top_wave_mode.replace("_", " ").title(),
                )
            )
        items.append(
            SourceAcquisitionSnapshot(
                source=source,
                label=str(bucket["label"]),
                acquired_users=len(bucket["acquired_user_ids"]),
                paid_users=len(bucket["paid_user_ids"]),
                payment_count=int(bucket["payment_count"]),
                invite_issued_users=len(bucket["invite_user_ids"]),
                repeat_purchase_users=len(bucket["repeat_purchase_user_ids"]),
                first_paid_revenue_total=int(bucket["first_paid_revenue_total"]),
                lifetime_revenue_total=int(bucket["lifetime_revenue_total"]),
                lifecycle_paid_users=len(bucket["lifecycle_paid_user_ids"]),
                lifecycle_payment_count=len(bucket["lifecycle_payment_ids"]),
                lifecycle_invite_issued_users=len(bucket["lifecycle_invite_user_ids"]),
                lifecycle_revenue_total=int(bucket["lifecycle_revenue_total"]),
                lifecycle_second_product_paid_users=len(
                    bucket["lifecycle_second_product_user_ids"]
                ),
                lifecycle_second_product_payment_count=len(
                    bucket["lifecycle_second_product_payment_ids"]
                ),
                lifecycle_second_product_revenue_total=int(
                    bucket["lifecycle_second_product_revenue_total"]
                ),
                top_rule_key=top_rule_key,
                top_rule_label=top_rule_label,
                top_wave_mode=top_wave_mode,
                top_wave_label=top_wave_label,
            )
        )
    items.sort(
        key=lambda item: (
            -item.lifetime_revenue_total,
            -item.lifecycle_revenue_total,
            -item.paid_users,
            -item.acquired_users,
            item.label,
            item.source,
        )
    )
    return tuple(items[:limit])
