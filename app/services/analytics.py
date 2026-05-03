from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, Channel, InviteLink, Payment, Subscription, Tariff, User
from app.utils.datetime import ensure_aware_utc, utcnow
from app.utils.encoding import safe_ui_text


@dataclass(slots=True)
class ProductFunnelSnapshot:
    channel_id: int
    channel_title: str
    buy_viewed_users: int
    product_selected_users: int
    tariff_opened_users: int
    invoice_created_users: int
    paid_users: int
    invite_issued_users: int
    repeat_purchase_users: int
    revenue_total: int


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
    conversion_buy_viewed: int
    conversion_product_selected: int
    conversion_tariff_opened: int
    conversion_invoice_created: int
    conversion_paid: int
    conversion_invite_issued: int
    repeat_purchase_users: int
    product_funnel: tuple[ProductFunnelSnapshot, ...]


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
                select(
                    Payment.user_id,
                    Payment.provider,
                    Payment.amount,
                    Payment.paid_at,
                    Payment.channel_id,
                ).where(Payment.status == "paid")
            )
        ).all()
    )
    paid_user_ids = {user_id for user_id, _, _, _, _ in paid_rows}
    never_paid_users = sum(1 for user_id, _ in users if user_id not in paid_user_ids)

    revenue_total = sum(int(amount) for _, _, amount, _, _ in paid_rows)
    revenue_today = sum(
        int(amount)
        for _, _, amount, paid_at, _ in paid_rows
        if paid_at is not None and ensure_aware_utc(paid_at) >= today_start
    )
    revenue_7_days = sum(
        int(amount)
        for _, _, amount, paid_at, _ in paid_rows
        if paid_at is not None and ensure_aware_utc(paid_at) >= week_start
    )
    revenue_30_days = sum(
        int(amount)
        for _, _, amount, paid_at, _ in paid_rows
        if paid_at is not None and ensure_aware_utc(paid_at) >= month_start
    )
    stars_payments = sum(1 for _, provider, _, _, _ in paid_rows if provider == "telegram_stars")
    crypto_payments = sum(1 for _, provider, _, _, _ in paid_rows if provider.startswith("crypto"))

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
    buy_viewed = await _distinct_audit_targets(session, "buy_screen_viewed")
    product_selected = await _distinct_audit_targets(session, "product_selected")
    tariff_opened = await _distinct_audit_targets(session, "tariff_detail_opened")
    invoice_created = await _distinct_audit_targets_multi(
        session,
        ("invoice_created_stars", "invoice_created_crypto"),
    )
    paid = await _distinct_paid_users(session)
    invite_issued = await _distinct_invite_users(session)
    repeat_purchase_users = await _repeat_purchase_user_count(session)

    channel_titles = await _load_channel_titles(session)
    tariff_channel_map = await _load_tariff_channel_map(session)
    product_funnel = await _build_product_funnel(
        session,
        channel_titles=channel_titles,
        tariff_channel_map=tariff_channel_map,
        paid_rows=paid_rows,
    )

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
        conversion_buy_viewed=buy_viewed,
        conversion_product_selected=product_selected,
        conversion_tariff_opened=tariff_opened,
        conversion_invoice_created=invoice_created or len(paid_user_ids),
        conversion_paid=paid or len(paid_user_ids),
        conversion_invite_issued=invite_issued,
        repeat_purchase_users=repeat_purchase_users,
        product_funnel=product_funnel,
    )


async def _build_product_funnel(
    session: AsyncSession,
    *,
    channel_titles: dict[int, str],
    tariff_channel_map: dict[int, int],
    paid_rows: list[tuple[int, str, int, datetime | None, int | None]],
) -> tuple[ProductFunnelSnapshot, ...]:
    buy_viewed_by_channel = await _audit_targets_by_channel(
        session,
        actions=("buy_screen_viewed",),
        tariff_channel_map=tariff_channel_map,
    )
    product_selected_by_channel = await _audit_targets_by_channel(
        session,
        actions=("product_selected",),
        tariff_channel_map=tariff_channel_map,
    )
    tariff_opened_by_channel = await _audit_targets_by_channel(
        session,
        actions=("tariff_detail_opened",),
        tariff_channel_map=tariff_channel_map,
    )
    invoice_created_by_channel = await _audit_targets_by_channel(
        session,
        actions=("invoice_created_stars", "invoice_created_crypto"),
        tariff_channel_map=tariff_channel_map,
    )
    repeat_purchase_by_channel = await _audit_targets_by_channel(
        session,
        actions=("repeat_purchase_paid",),
        tariff_channel_map=tariff_channel_map,
    )

    paid_by_channel: dict[int, set[int]] = defaultdict(set)
    revenue_by_channel: dict[int, int] = defaultdict(int)
    for user_id, _provider, amount, _paid_at, channel_id in paid_rows:
        if channel_id is None:
            continue
        paid_by_channel[channel_id].add(user_id)
        revenue_by_channel[channel_id] += int(amount)

    invite_by_channel: dict[int, set[int]] = defaultdict(set)
    invite_rows = list(
        (
            await session.execute(
                select(InviteLink.channel_id, InviteLink.user_id)
            )
        ).all()
    )
    for channel_id, user_id in invite_rows:
        invite_by_channel[int(channel_id)].add(int(user_id))

    all_channel_ids = set(channel_titles)
    all_channel_ids.update(buy_viewed_by_channel)
    all_channel_ids.update(product_selected_by_channel)
    all_channel_ids.update(tariff_opened_by_channel)
    all_channel_ids.update(invoice_created_by_channel)
    all_channel_ids.update(paid_by_channel)
    all_channel_ids.update(invite_by_channel)
    all_channel_ids.update(repeat_purchase_by_channel)

    items: list[ProductFunnelSnapshot] = []
    for channel_id in sorted(
        all_channel_ids,
        key=lambda item: (-revenue_by_channel.get(item, 0), channel_titles.get(item, ""), item),
    ):
        items.append(
            ProductFunnelSnapshot(
                channel_id=channel_id,
                channel_title=channel_titles.get(channel_id, f"Канал #{channel_id}"),
                buy_viewed_users=len(buy_viewed_by_channel.get(channel_id, set())),
                product_selected_users=len(product_selected_by_channel.get(channel_id, set())),
                tariff_opened_users=len(tariff_opened_by_channel.get(channel_id, set())),
                invoice_created_users=len(invoice_created_by_channel.get(channel_id, set())),
                paid_users=len(paid_by_channel.get(channel_id, set())),
                invite_issued_users=len(invite_by_channel.get(channel_id, set())),
                repeat_purchase_users=len(repeat_purchase_by_channel.get(channel_id, set())),
                revenue_total=revenue_by_channel.get(channel_id, 0),
            )
        )
    return tuple(items)


async def _load_channel_titles(session: AsyncSession) -> dict[int, str]:
    rows = list((await session.execute(select(Channel.id, Channel.title))).all())
    return {
        int(channel_id): safe_ui_text(title, f"Канал #{channel_id}")
        for channel_id, title in rows
    }


async def _load_tariff_channel_map(session: AsyncSession) -> dict[int, int]:
    rows = list((await session.execute(select(Tariff.id, Tariff.channel_id))).all())
    return {int(tariff_id): int(channel_id) for tariff_id, channel_id in rows}


async def _audit_targets_by_channel(
    session: AsyncSession,
    *,
    actions: tuple[str, ...],
    tariff_channel_map: dict[int, int],
) -> dict[int, set[int]]:
    rows = list(
        (
            await session.execute(
                select(AuditLog.action, AuditLog.target_user_id, AuditLog.payload).where(
                    AuditLog.action.in_(actions)
                )
            )
        ).all()
    )
    grouped: dict[int, set[int]] = defaultdict(set)
    for _action, target_user_id, raw_payload in rows:
        if target_user_id is None:
            continue
        payload = _parse_payload(raw_payload)
        channel_id = _resolve_channel_id(payload, tariff_channel_map)
        if channel_id is None:
            continue
        grouped[channel_id].add(int(target_user_id))
    return grouped


async def _distinct_paid_users(session: AsyncSession) -> int:
    value = (
        await session.execute(
            select(func.count(distinct(Payment.user_id))).where(Payment.status == "paid")
        )
    ).scalar_one()
    return int(value or 0)


async def _distinct_invite_users(session: AsyncSession) -> int:
    value = (
        await session.execute(select(func.count(distinct(InviteLink.user_id))))
    ).scalar_one()
    return int(value or 0)


async def _repeat_purchase_user_count(session: AsyncSession) -> int:
    rows = list(
        (
            await session.execute(
                select(Payment.user_id, func.count(Payment.id))
                .where(Payment.status == "paid")
                .group_by(Payment.user_id)
            )
        ).all()
    )
    return sum(1 for _user_id, payment_count in rows if int(payment_count or 0) > 1)


async def _distinct_audit_targets(session: AsyncSession, action: str) -> int:
    value = (
        await session.execute(
            select(func.count(distinct(AuditLog.target_user_id)))
            .where(AuditLog.action == action)
            .where(AuditLog.target_user_id.is_not(None))
        )
    ).scalar_one()
    return int(value or 0)


async def _distinct_audit_targets_multi(session: AsyncSession, actions: tuple[str, ...]) -> int:
    value = (
        await session.execute(
            select(func.count(distinct(AuditLog.target_user_id)))
            .where(AuditLog.action.in_(actions))
            .where(AuditLog.target_user_id.is_not(None))
        )
    ).scalar_one()
    return int(value or 0)


def _parse_payload(raw_payload: str | None) -> dict[str, object]:
    if not raw_payload:
        return {}
    try:
        value = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _resolve_channel_id(
    payload: dict[str, object],
    tariff_channel_map: dict[int, int],
) -> int | None:
    direct_channel_id = _coerce_int(payload.get("channel_id"))
    if direct_channel_id is not None:
        return direct_channel_id
    tariff_id = _coerce_int(payload.get("tariff_id"))
    if tariff_id is None:
        return None
    return tariff_channel_map.get(tariff_id)


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
