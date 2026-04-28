from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, Payment, Subscription, User
from app.utils.datetime import ensure_aware_utc, utcnow


@dataclass(slots=True)
class AnalyticsSnapshot:
    total_users: int
    active_subscriptions: int
    expired_users: int
    never_paid_users: int
    blocked_users: int
    revenue_today: int
    revenue_7_days: int
    revenue_30_days: int
    revenue_total: int
    stars_payments: int
    crypto_payments: int
    conversion_started: int
    conversion_invoice_created: int
    conversion_paid: int


async def build_analytics_snapshot(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> AnalyticsSnapshot:
    current_time = ensure_aware_utc(now or utcnow())
    today_start = current_time.astimezone(UTC).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    week_start = current_time - timedelta(days=7)
    month_start = current_time - timedelta(days=30)

    users = list((await session.execute(select(User.id, User.is_blocked))).all())
    total_users = len(users)
    blocked_users = sum(1 for _, is_blocked in users if is_blocked)

    paid_rows = list(
        (
            await session.execute(
                select(Payment.user_id, Payment.provider, Payment.amount, Payment.paid_at)
                .where(Payment.status == "paid")
            )
        ).all()
    )
    paid_user_ids = {user_id for user_id, _, _, _ in paid_rows}
    never_paid_users = sum(1 for user_id, _ in users if user_id not in paid_user_ids)

    revenue_total = sum(int(amount) for _, _, amount, _ in paid_rows)
    revenue_today = sum(
        int(amount)
        for _, _, amount, paid_at in paid_rows
        if paid_at is not None and ensure_aware_utc(paid_at) >= today_start
    )
    revenue_7_days = sum(
        int(amount)
        for _, _, amount, paid_at in paid_rows
        if paid_at is not None and ensure_aware_utc(paid_at) >= week_start
    )
    revenue_30_days = sum(
        int(amount)
        for _, _, amount, paid_at in paid_rows
        if paid_at is not None and ensure_aware_utc(paid_at) >= month_start
    )
    stars_payments = sum(1 for _, provider, _, _ in paid_rows if provider == "telegram_stars")
    crypto_payments = sum(1 for _, provider, _, _ in paid_rows if provider.startswith("crypto"))

    active_subscriptions = int(
        (
            await session.execute(
                select(func.count(Subscription.id))
                .where(Subscription.status == "active")
                .where(Subscription.revoked_at.is_(None))
                .where(Subscription.expires_at > current_time)
            )
        ).scalar_one()
        or 0
    )

    subscription_rows = list(
        (
            await session.execute(
                select(
                    Subscription.user_id,
                    Subscription.status,
                    Subscription.revoked_at,
                    Subscription.expires_at,
                ).order_by(
                    Subscription.user_id.asc(),
                    Subscription.expires_at.desc(),
                    Subscription.id.desc(),
                )
            )
        ).all()
    )
    latest_expires_by_user: dict[int, datetime] = {}
    has_active_user_ids: set[int] = set()
    for user_id, status, revoked_at, expires_at in subscription_rows:
        aware_expires_at = ensure_aware_utc(expires_at)
        if user_id not in latest_expires_by_user:
            latest_expires_by_user[user_id] = aware_expires_at
        if status == "active" and revoked_at is None and aware_expires_at > current_time:
            has_active_user_ids.add(user_id)

    expired_users = sum(
        1
        for user_id, _ in users
        if user_id not in has_active_user_ids
        and user_id in latest_expires_by_user
        and latest_expires_by_user[user_id] <= current_time
    )

    started = await _distinct_audit_targets(session, "user_start")
    invoice_created = await _distinct_audit_targets(session, "invoice_created_stars")
    paid = await _distinct_audit_targets(session, "payment_paid_stars")

    return AnalyticsSnapshot(
        total_users=total_users,
        active_subscriptions=active_subscriptions,
        expired_users=expired_users,
        never_paid_users=never_paid_users,
        blocked_users=blocked_users,
        revenue_today=revenue_today,
        revenue_7_days=revenue_7_days,
        revenue_30_days=revenue_30_days,
        revenue_total=revenue_total,
        stars_payments=stars_payments,
        crypto_payments=crypto_payments,
        conversion_started=started or total_users,
        conversion_invoice_created=invoice_created or len(paid_user_ids),
        conversion_paid=paid or len(paid_user_ids),
    )


async def _distinct_audit_targets(session: AsyncSession, action: str) -> int:
    value = (
        await session.execute(
            select(func.count(distinct(AuditLog.target_user_id)))
            .where(AuditLog.action == action)
            .where(AuditLog.target_user_id.is_not(None))
        )
    ).scalar_one()
    return int(value or 0)
