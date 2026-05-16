from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, Payment, Tariff
from app.services.analytics_common import _audit_targets_by_tariff, _parse_payload, _percent
from app.services.analytics_lifecycle import (
    _LIFECYCLE_TOUCH_ACTIONS,
    LIFECYCLE_ATTRIBUTION_WINDOW,
    _lifecycle_rule_from_audit,
    _lifecycle_wave_from_audit,
)
from app.services.analytics_models import (
    OfferPerformanceSnapshot,
    PricingIntelligenceSnapshot,
    ProductPairCampaignSnapshot,
    ProductPairPerformanceSnapshot,
)
from app.services.product_service import normalize_offer_group
from app.utils.datetime import ensure_aware_utc, utcnow
from app.utils.encoding import safe_ui_text


async def _build_pricing_intelligence(
    session: AsyncSession,
    *,
    channel_titles: dict[int, str],
    now: datetime | None = None,
    limit: int = 5,
) -> PricingIntelligenceSnapshot:
    tariff_rows = list(
        (
            await session.execute(
                select(
                    Tariff.id,
                    Tariff.name,
                    Tariff.channel_id,
                    Tariff.price_stars,
                    Tariff.duration_days,
                    Tariff.offer_group,
                    Tariff.is_featured,
                    Tariff.is_default_offer,
                    Tariff.offer_expires_at,
                )
            )
        ).all()
    )
    tariffs_by_id = {
        int(tariff_id): {
            "tariff_name": safe_ui_text(tariff_name, f"????? #{tariff_id}"),
            "channel_id": int(channel_id),
            "channel_title": channel_titles.get(int(channel_id), f"????? #{channel_id}"),
            "offer_group": normalize_offer_group(offer_group),
            "price_stars": int(price_stars or 0),
            "duration_days": int(duration_days or 0),
            "is_featured": bool(is_featured),
            "is_default_offer": bool(is_default_offer),
            "offer_expires_at": (
                ensure_aware_utc(offer_expires_at)
                if offer_expires_at is not None
                else None
            ),
        }
        for (
            tariff_id,
            tariff_name,
            channel_id,
            price_stars,
            duration_days,
            offer_group,
            is_featured,
            is_default_offer,
            offer_expires_at,
        ) in tariff_rows
    }

    opened_by_tariff = await _audit_targets_by_tariff(
        session,
        actions=("tariff_detail_opened",),
    )
    clicked_by_tariff = await _audit_targets_by_tariff(
        session,
        actions=("offer_clicked",),
    )
    invoice_by_tariff = await _audit_targets_by_tariff(
        session,
        actions=("invoice_created_stars", "invoice_created_crypto"),
    )

    payment_rows = list(
        (
            await session.execute(
                select(
                    Payment.user_id,
                    Payment.tariff_id,
                    Payment.channel_id,
                    Payment.amount,
                    Payment.provider,
                    Payment.paid_at,
                ).where(Payment.status == "paid")
            )
        ).all()
    )

    payment_metrics: dict[int, dict[str, object]] = defaultdict(
        lambda: {
            "paid_user_ids": set(),
            "payment_count": 0,
            "revenue_total": 0,
        }
    )
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
                .where(AuditLog.target_user_id.is_not(None))
            )
        ).all()
    )
    user_channels: dict[int, set[int]] = defaultdict(set)
    channel_paid_users: dict[int, set[int]] = defaultdict(set)
    user_channel_revenue: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    user_channel_first_paid_at: dict[int, dict[int, datetime]] = defaultdict(dict)
    lifecycle_touches_by_user: dict[int, list[dict[str, object]]] = defaultdict(list)
    normalized_payment_rows: list[dict[str, object]] = []
    current_time = ensure_aware_utc(now or utcnow())
    for action, target_user_id, raw_payload, created_at in lifecycle_touch_rows:
        if target_user_id is None:
            continue
        payload = _parse_payload(raw_payload)
        rule_key, rule_label = _lifecycle_rule_from_audit(action, payload)
        wave_mode, wave_label = _lifecycle_wave_from_audit(payload)
        lifecycle_touches_by_user[int(target_user_id)].append(
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

    total_revenue = 0
    total_payment_count = 0
    stars_revenue_total = 0
    crypto_revenue_total = 0
    featured_revenue_total = 0
    default_revenue_total = 0
    limited_revenue_total = 0

    for user_id, tariff_id, channel_id, amount, provider, paid_at in payment_rows:
        if user_id is None or tariff_id is None or channel_id is None:
            continue
        user_key = int(user_id)
        tariff_key = int(tariff_id)
        channel_key = int(channel_id)
        amount_value = int(amount or 0)
        user_channels[user_key].add(channel_key)
        channel_paid_users[channel_key].add(user_key)
        user_channel_revenue[user_key][channel_key] += amount_value
        paid_at_value = ensure_aware_utc(paid_at or current_time)
        normalized_payment_rows.append(
            {
                "user_id": user_key,
                "channel_id": channel_key,
                "amount": amount_value,
                "paid_at": paid_at_value,
            }
        )
        first_paid_at = user_channel_first_paid_at[user_key].get(channel_key)
        if first_paid_at is None or paid_at_value < first_paid_at:
            user_channel_first_paid_at[user_key][channel_key] = paid_at_value
        total_revenue += amount_value
        total_payment_count += 1
        if provider == "telegram_stars":
            stars_revenue_total += amount_value
        elif isinstance(provider, str) and provider.startswith("crypto"):
            crypto_revenue_total += amount_value

        metrics = payment_metrics[tariff_key]
        paid_user_ids = metrics["paid_user_ids"]
        if isinstance(paid_user_ids, set):
            paid_user_ids.add(user_key)
        metrics["payment_count"] = int(metrics["payment_count"]) + 1
        metrics["revenue_total"] = int(metrics["revenue_total"]) + amount_value

        tariff_meta = tariffs_by_id.get(tariff_key)
        if tariff_meta is not None:
            if bool(tariff_meta["is_featured"]):
                featured_revenue_total += amount_value
            if bool(tariff_meta["is_default_offer"]):
                default_revenue_total += amount_value
            if (
                bool(tariff_meta.get("offer_expires_at"))
                and tariff_meta["offer_expires_at"] > current_time
            ):
                limited_revenue_total += amount_value

    all_tariff_ids = set(tariffs_by_id)
    all_tariff_ids.update(opened_by_tariff)
    all_tariff_ids.update(clicked_by_tariff)
    all_tariff_ids.update(invoice_by_tariff)
    all_tariff_ids.update(payment_metrics)

    offers: list[OfferPerformanceSnapshot] = []
    for tariff_id in all_tariff_ids:
        tariff_meta = tariffs_by_id.get(int(tariff_id))
        payment_bucket = payment_metrics.get(int(tariff_id), {})
        opened_users = len(opened_by_tariff.get(int(tariff_id), set()))
        clicked_users = len(clicked_by_tariff.get(int(tariff_id), set()))
        invoice_created_users = len(invoice_by_tariff.get(int(tariff_id), set()))
        paid_user_ids = payment_bucket.get("paid_user_ids", set())
        paid_users = len(paid_user_ids if isinstance(paid_user_ids, set) else set())
        payment_count = int(payment_bucket.get("payment_count", 0) or 0)
        revenue_total = int(payment_bucket.get("revenue_total", 0) or 0)
        if not any(
            (
                opened_users,
                clicked_users,
                invoice_created_users,
                paid_users,
                payment_count,
                revenue_total,
            )
        ):
            continue
        channel_id = int(tariff_meta["channel_id"]) if tariff_meta is not None else 0
        offers.append(
            OfferPerformanceSnapshot(
                tariff_id=int(tariff_id),
                tariff_name=(
                    str(tariff_meta["tariff_name"])
                    if tariff_meta is not None
                    else f"????? #{tariff_id}"
                ),
                channel_id=channel_id,
                channel_title=(
                    str(tariff_meta["channel_title"])
                    if tariff_meta is not None
                    else f"????? #{channel_id or '?'}"
                ),
                offer_group=(
                    str(tariff_meta["offer_group"])
                    if tariff_meta is not None and tariff_meta["offer_group"] is not None
                    else None
                ),
                price_stars=(
                    int(tariff_meta["price_stars"]) if tariff_meta is not None else 0
                ),
                duration_days=(
                    int(tariff_meta["duration_days"]) if tariff_meta is not None else 0
                ),
                is_featured=(
                    bool(tariff_meta["is_featured"]) if tariff_meta is not None else False
                ),
                is_default_offer=(
                    bool(tariff_meta["is_default_offer"]) if tariff_meta is not None else False
                ),
                is_limited_time=(
                    bool(tariff_meta.get("offer_expires_at"))
                    and tariff_meta["offer_expires_at"] > current_time
                    if tariff_meta is not None
                    else False
                ),
                offer_expires_at=(
                    tariff_meta.get("offer_expires_at") if tariff_meta is not None else None
                ),
                opened_users=opened_users,
                clicked_users=clicked_users,
                invoice_created_users=invoice_created_users,
                paid_users=paid_users,
                payment_count=payment_count,
                revenue_total=revenue_total,
            )
        )

    offers.sort(
        key=lambda item: (
            -item.revenue_total,
            -item.paid_users,
            -item.clicked_users,
            -item.invoice_created_users,
            item.tariff_name,
            item.tariff_id,
        )
    )
    top_revenue_offer = offers[0] if offers else None
    convertible_offers = [item for item in offers if item.clicked_users > 0]
    top_conversion_offer = (
        max(
            convertible_offers,
            key=lambda item: (
                item.click_to_paid_percent,
                item.paid_users,
                item.revenue_total,
                item.clicked_users,
                -item.tariff_id,
            ),
        )
        if convertible_offers
        else None
    )
    multi_product_paid_users = sum(1 for channels in user_channels.values() if len(channels) > 1)

    pair_buckets: dict[tuple[int, int], dict[str, object]] = defaultdict(
        lambda: {
            "user_ids": set(),
            "secondary_revenue_total": 0,
            "pair_revenue_total": 0,
        }
    )
    for user_id, channels in user_channels.items():
        if len(channels) < 2:
            continue
        ordered_channels = sorted(
            channels,
            key=lambda channel_key: (
                user_channel_first_paid_at[user_id].get(channel_key, current_time),
                channel_key,
            ),
        )
        for index, primary_channel in enumerate(ordered_channels[:-1]):
            primary_revenue = int(user_channel_revenue[user_id].get(primary_channel, 0) or 0)
            for secondary_channel in ordered_channels[index + 1 :]:
                secondary_revenue = int(
                    user_channel_revenue[user_id].get(secondary_channel, 0) or 0
                )
                bucket = pair_buckets[(primary_channel, secondary_channel)]
                user_ids = bucket["user_ids"]
                if isinstance(user_ids, set) and user_id not in user_ids:
                    user_ids.add(user_id)
                    bucket["secondary_revenue_total"] = int(
                        bucket["secondary_revenue_total"]
                    ) + secondary_revenue
                    bucket["pair_revenue_total"] = int(bucket["pair_revenue_total"]) + (
                        primary_revenue + secondary_revenue
                    )

    top_product_pairs = [
        ProductPairPerformanceSnapshot(
            primary_channel_id=primary_channel,
            primary_channel_title=channel_titles.get(
                primary_channel,
                f"????? #{primary_channel}",
            ),
            secondary_channel_id=secondary_channel,
            secondary_channel_title=channel_titles.get(
                secondary_channel,
                f"????? #{secondary_channel}",
            ),
            attached_paid_users=len(bucket["user_ids"]),
            base_paid_users=len(channel_paid_users.get(primary_channel, set())),
            secondary_revenue_total=int(bucket["secondary_revenue_total"]),
            pair_revenue_total=int(bucket["pair_revenue_total"]),
        )
        for (primary_channel, secondary_channel), bucket in pair_buckets.items()
        if bucket["user_ids"]
    ]
    top_product_pairs.sort(
        key=lambda item: (
            -item.attached_paid_users,
            -item.attach_rate_percent,
            -item.secondary_revenue_total,
            -item.pair_revenue_total,
            item.primary_channel_title,
            item.secondary_channel_title,
        )
    )

    pair_campaign_buckets: dict[tuple[int, int, str, str], dict[str, object]] = defaultdict(
        lambda: {
            "user_ids": set(),
            "payment_count": 0,
            "secondary_revenue_total": 0,
            "rule_label": "",
            "wave_label": "",
        }
    )
    for payment_row in normalized_payment_rows:
        user_key = int(payment_row["user_id"])
        secondary_channel = int(payment_row["channel_id"])
        paid_at_value = ensure_aware_utc(payment_row["paid_at"])
        amount_value = int(payment_row["amount"])
        user_touches = lifecycle_touches_by_user.get(user_key)
        if not user_touches:
            continue
        matched_touches = [
            touch
            for touch in user_touches
            if (
                touch["created_at"]
                <= paid_at_value
                <= touch["created_at"] + LIFECYCLE_ATTRIBUTION_WINDOW
            )
        ]
        if not matched_touches:
            continue
        touch = matched_touches[-1]
        primary_channels = [
            channel_key
            for channel_key, first_paid_at in user_channel_first_paid_at[user_key].items()
            if channel_key != secondary_channel and first_paid_at < paid_at_value
        ]
        if not primary_channels:
            continue
        for primary_channel in sorted(primary_channels):
            bucket = pair_campaign_buckets[
                (
                    primary_channel,
                    secondary_channel,
                    str(touch["rule_key"]),
                    str(touch["wave_mode"]),
                )
            ]
            user_ids = bucket["user_ids"]
            if isinstance(user_ids, set):
                user_ids.add(user_key)
            bucket["payment_count"] = int(bucket["payment_count"]) + 1
            bucket["secondary_revenue_total"] = (
                int(bucket["secondary_revenue_total"]) + amount_value
            )
            bucket["rule_label"] = str(touch["rule_label"])
            bucket["wave_label"] = str(touch["wave_label"])

    top_pair_campaigns = [
        ProductPairCampaignSnapshot(
            primary_channel_id=primary_channel,
            primary_channel_title=channel_titles.get(
                primary_channel,
                f"????? #{primary_channel}",
            ),
            secondary_channel_id=secondary_channel,
            secondary_channel_title=channel_titles.get(
                secondary_channel,
                f"????? #{secondary_channel}",
            ),
            rule_key=rule_key,
            rule_label=str(bucket["rule_label"]),
            wave_mode=wave_mode,
            wave_label=str(bucket["wave_label"]),
            attached_paid_users=len(bucket["user_ids"]),
            base_paid_users=len(channel_paid_users.get(primary_channel, set())),
            payment_count=int(bucket["payment_count"]),
            secondary_revenue_total=int(bucket["secondary_revenue_total"]),
        )
        for (
            primary_channel,
            secondary_channel,
            rule_key,
            wave_mode,
        ), bucket in pair_campaign_buckets.items()
        if bucket["user_ids"]
    ]
    top_pair_campaigns.sort(
        key=lambda item: (
            -item.secondary_revenue_total,
            -item.attached_paid_users,
            -item.attach_rate_percent,
            -item.payment_count,
            item.primary_channel_title,
            item.secondary_channel_title,
            item.rule_label,
        )
    )

    active_limited_offer_count = sum(
        1
        for tariff_meta in tariffs_by_id.values()
        if bool(tariff_meta.get("offer_expires_at"))
        and tariff_meta["offer_expires_at"] > current_time
    )

    return PricingIntelligenceSnapshot(
        average_payment_amount=(
            int(total_revenue / total_payment_count) if total_payment_count > 0 else 0
        ),
        stars_revenue_total=stars_revenue_total,
        crypto_revenue_total=crypto_revenue_total,
        stars_revenue_share_percent=_percent(stars_revenue_total, total_revenue),
        crypto_revenue_share_percent=_percent(crypto_revenue_total, total_revenue),
        multi_product_paid_users=multi_product_paid_users,
        multi_product_attach_rate_percent=_percent(multi_product_paid_users, len(user_channels)),
        featured_revenue_total=featured_revenue_total,
        default_revenue_total=default_revenue_total,
        limited_revenue_total=limited_revenue_total,
        active_limited_offer_count=active_limited_offer_count,
        top_product_pairs=tuple(top_product_pairs[:limit]),
        top_pair_campaigns=tuple(top_pair_campaigns[:limit]),
        top_offers=tuple(offers[:limit]),
        top_revenue_offer=top_revenue_offer,
        top_conversion_offer=top_conversion_offer,
    )


