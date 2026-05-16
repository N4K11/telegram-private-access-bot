from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, PromoCode, PromoRedemption, User
from app.services.analytics_common import (
    _coerce_int,
    _display_user_label,
    _load_paid_user_metrics,
    _parse_payload,
)
from app.services.analytics_models import (
    PromoAttributionSnapshot,
    PromoCampaignSnapshot,
    ReferralAttributionSnapshot,
    ReferralTopReferrerSnapshot,
)
from app.utils.encoding import safe_ui_text


async def _build_promo_attribution(session: AsyncSession) -> PromoAttributionSnapshot:
    result = await session.execute(
        select(PromoRedemption, PromoCode)
        .join(PromoCode, PromoCode.id == PromoRedemption.promo_code_id)
        .where(PromoRedemption.status == "consumed")
        .where(PromoRedemption.payment_id.is_not(None))
    )
    grouped: dict[int, dict[str, object]] = {}
    total_paid_users: set[int] = set()
    total_payment_count = 0
    gross_revenue_total = 0
    revenue_total = 0
    discount_total = 0
    for redemption, promo_code in result.all():
        total_paid_users.add(int(redemption.user_id))
        total_payment_count += 1
        bucket = grouped.setdefault(
            int(promo_code.id),
            {
                "label": safe_ui_text(promo_code.campaign_name, promo_code.code),
                "campaign_name": promo_code.campaign_name,
                "user_ids": set(),
                "payment_count": 0,
                "gross_revenue_total": 0,
                "revenue_total": 0,
                "discount_total": 0,
            },
        )
        bucket["user_ids"].add(int(redemption.user_id))
        bucket["payment_count"] = int(bucket["payment_count"]) + 1
        amount_before = int(redemption.amount_before or redemption.amount_after or 0)
        amount_after = int(redemption.amount_after or redemption.amount_before or 0)
        applied_discount = max(amount_before - amount_after, 0)
        bucket["gross_revenue_total"] = int(bucket["gross_revenue_total"]) + amount_before
        bucket["revenue_total"] = int(bucket["revenue_total"]) + amount_after
        bucket["discount_total"] = int(bucket["discount_total"]) + applied_discount
        gross_revenue_total += amount_before
        revenue_total += amount_after
        discount_total += applied_discount

    paid_metrics_by_user = await _load_paid_user_metrics(session, user_ids=total_paid_users)
    campaigns = []
    for promo_code_id, bucket in grouped.items():
        user_ids = bucket["user_ids"]
        repeat_purchase_users = 0
        lifetime_revenue_total = 0
        if isinstance(user_ids, set):
            for user_id in user_ids:
                metrics = paid_metrics_by_user.get(int(user_id))
                if metrics is None:
                    continue
                lifetime_revenue_total += int(metrics["lifetime_revenue_total"])
                if int(metrics["payment_count"]) > 1:
                    repeat_purchase_users += 1
        campaigns.append(
            PromoCampaignSnapshot(
                promo_code_id=promo_code_id,
                label=str(bucket["label"]),
                campaign_name=(
                    str(bucket["campaign_name"])
                    if isinstance(bucket["campaign_name"], str)
                    else None
                ),
                paid_users=len(bucket["user_ids"]),
                payment_count=int(bucket["payment_count"]),
                repeat_purchase_users=repeat_purchase_users,
                gross_revenue_total=int(bucket["gross_revenue_total"]),
                revenue_total=int(bucket["revenue_total"]),
                discount_total=int(bucket["discount_total"]),
                lifetime_revenue_total=lifetime_revenue_total,
            )
        )
    campaigns.sort(
        key=lambda item: (-item.revenue_total, -item.payment_count, item.label, item.promo_code_id)
    )
    return PromoAttributionSnapshot(
        total_paid_users=len(total_paid_users),
        total_payment_count=total_payment_count,
        gross_revenue_total=gross_revenue_total,
        revenue_total=revenue_total,
        discount_total=discount_total,
        campaigns=tuple(campaigns),
    )


async def _build_referral_attribution(
    session: AsyncSession,
    *,
    limit: int = 5,
) -> ReferralAttributionSnapshot:
    result = await session.execute(
        select(
            User.id,
            User.referred_by_user_id,
            User.referral_reward_granted_at,
        ).where(User.referred_by_user_id.is_not(None))
    )
    invited_rows = list(result.all())
    total_referred_users = len(invited_rows)
    paid_referred_users = sum(
        1
        for _user_id, _referrer_id, rewarded_at in invited_rows
        if rewarded_at is not None
    )
    rewarded_referrals_count = paid_referred_users

    grouped: dict[int, dict[str, int]] = defaultdict(lambda: {"invited": 0, "paid": 0})
    referrer_ids: set[int] = set()
    referred_user_ids: set[int] = set()
    referred_user_to_referrer: dict[int, int] = {}
    for user_id, referrer_id, rewarded_at in invited_rows:
        if referrer_id is None:
            continue
        referred_user_key = int(user_id)
        referrer_key = int(referrer_id)
        referrer_ids.add(referrer_key)
        referred_user_ids.add(referred_user_key)
        referred_user_to_referrer[referred_user_key] = referrer_key
        grouped[referrer_key]["invited"] += 1
        if rewarded_at is not None:
            grouped[referrer_key]["paid"] += 1

    paid_metrics_by_user = await _load_paid_user_metrics(session, user_ids=referred_user_ids)
    first_paid_revenue_by_user = {
        user_id: int(metrics["first_paid_revenue_total"])
        for user_id, metrics in paid_metrics_by_user.items()
    }
    lifetime_revenue_by_user = {
        user_id: int(metrics["lifetime_revenue_total"])
        for user_id, metrics in paid_metrics_by_user.items()
    }

    reward_days_by_referrer: dict[int, int] = defaultdict(int)
    reward_rows = list(
        (
            await session.execute(
                select(AuditLog.target_user_id, AuditLog.payload).where(
                    AuditLog.action == "referral_reward_granted"
                )
            )
        ).all()
    )
    for target_user_id, raw_payload in reward_rows:
        referrer_id = _coerce_int(target_user_id)
        if referrer_id is None:
            continue
        payload = _parse_payload(raw_payload)
        reward_days_by_referrer[referrer_id] += int(payload.get("reward_days", 0) or 0)

    referrers_by_id: dict[int, User] = {}
    if referrer_ids:
        referrer_result = await session.execute(select(User).where(User.id.in_(referrer_ids)))
        referrers_by_id = {int(user.id): user for user in referrer_result.scalars()}

    first_paid_revenue_total = sum(first_paid_revenue_by_user.values())
    lifetime_referred_revenue_total = sum(lifetime_revenue_by_user.values())
    reward_days_issued_total = sum(reward_days_by_referrer.values())

    revenue_by_referrer: dict[int, dict[str, int]] = defaultdict(
        lambda: {
            "first_paid_revenue_total": 0,
            "lifetime_revenue_total": 0,
            "repeat_purchase_referred_users": 0,
        }
    )
    for referred_user_id, referrer_id in referred_user_to_referrer.items():
        first_paid_revenue = first_paid_revenue_by_user.get(referred_user_id, 0)
        lifetime_revenue = lifetime_revenue_by_user.get(referred_user_id, 0)
        revenue_by_referrer[referrer_id]["first_paid_revenue_total"] += first_paid_revenue
        revenue_by_referrer[referrer_id]["lifetime_revenue_total"] += lifetime_revenue
        user_paid_metrics = paid_metrics_by_user.get(referred_user_id)
        if user_paid_metrics is not None and int(user_paid_metrics["payment_count"]) > 1:
            revenue_by_referrer[referrer_id]["repeat_purchase_referred_users"] += 1

    top_referrers: list[ReferralTopReferrerSnapshot] = []
    pending_reward_days_total = 0
    for referrer_id, metrics in grouped.items():
        referrer = referrers_by_id.get(referrer_id)
        if referrer is None:
            continue
        pending_reward_days = int(referrer.pending_referral_reward_days or 0)
        pending_reward_days_total += pending_reward_days
        revenue_metrics = revenue_by_referrer.get(referrer_id, {})
        top_referrers.append(
            ReferralTopReferrerSnapshot(
                user_id=referrer_id,
                telegram_id=int(referrer.telegram_id),
                display_name=_display_user_label(referrer),
                invited_users_count=int(metrics["invited"]),
                paid_referrals_count=int(metrics["paid"]),
                repeat_purchase_referred_users=int(
                    revenue_metrics.get("repeat_purchase_referred_users", 0)
                ),
                pending_reward_days=pending_reward_days,
                reward_days_issued=int(reward_days_by_referrer.get(referrer_id, 0)),
                first_paid_revenue_total=int(revenue_metrics.get("first_paid_revenue_total", 0)),
                lifetime_revenue_total=int(revenue_metrics.get("lifetime_revenue_total", 0)),
            )
        )
    top_referrers.sort(
        key=lambda item: (
            -item.lifetime_revenue_total,
            -item.paid_referrals_count,
            -item.invited_users_count,
            -item.repeat_purchase_referred_users,
            -item.pending_reward_days,
            item.display_name,
            item.user_id,
        )
    )

    suspicious_event_count = int(
        (
            await session.execute(
                select(func.count(AuditLog.id)).where(AuditLog.action == "referral_suspicious")
            )
        ).scalar_one()
        or 0
    )

    return ReferralAttributionSnapshot(
        total_referred_users=total_referred_users,
        paid_referred_users=paid_referred_users,
        rewarded_referrals_count=rewarded_referrals_count,
        suspicious_event_count=suspicious_event_count,
        pending_reward_days_total=pending_reward_days_total,
        reward_days_issued_total=reward_days_issued_total,
        first_paid_revenue_total=first_paid_revenue_total,
        lifetime_referred_revenue_total=lifetime_referred_revenue_total,
        top_referrers=tuple(top_referrers[:limit]),
    )
