from __future__ import annotations

import json
from collections import defaultdict

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, Channel, InviteLink, Payment, Tariff, User
from app.utils.encoding import safe_ui_text


def _display_user_label(user: User) -> str:
    if user.username:
        return safe_ui_text(f"@{user.username}", f"ID {user.telegram_id}")
    full_name = " ".join(part for part in (user.first_name, user.last_name) if part).strip()
    if full_name:
        return safe_ui_text(full_name, f"ID {user.telegram_id}")
    return f"ID {user.telegram_id}"


async def _load_channel_titles(session: AsyncSession) -> dict[int, str]:
    rows = list((await session.execute(select(Channel.id, Channel.title))).all())
    return {
        int(channel_id): safe_ui_text(title, f"????? #{channel_id}")
        for channel_id, title in rows
    }


async def _load_tariff_channel_map(session: AsyncSession) -> dict[int, int]:
    rows = list((await session.execute(select(Tariff.id, Tariff.channel_id))).all())
    return {int(tariff_id): int(channel_id) for tariff_id, channel_id in rows}


async def _audit_targets_by_tariff(
    session: AsyncSession,
    *,
    actions: tuple[str, ...],
) -> dict[int, set[int]]:
    rows = list(
        (
            await session.execute(
                select(AuditLog.target_user_id, AuditLog.payload).where(
                    AuditLog.action.in_(actions)
                )
            )
        ).all()
    )
    grouped: dict[int, set[int]] = defaultdict(set)
    for target_user_id, raw_payload in rows:
        if target_user_id is None:
            continue
        payload = _parse_payload(raw_payload)
        tariff_id = _coerce_int(payload.get("tariff_id"))
        if tariff_id is None:
            continue
        grouped[tariff_id].add(int(target_user_id))
    return grouped


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
    value = (await session.execute(select(func.count(distinct(InviteLink.user_id))))).scalar_one()
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


async def _load_paid_user_metrics(
    session: AsyncSession,
    *,
    user_ids: set[int] | None = None,
) -> dict[int, dict[str, int]]:
    if user_ids is not None and not user_ids:
        return {}
    stmt = (
        select(Payment.user_id, Payment.amount, Payment.paid_at, Payment.id)
        .where(Payment.status == "paid")
        .order_by(Payment.user_id.asc(), Payment.paid_at.asc(), Payment.id.asc())
    )
    if user_ids is not None:
        stmt = stmt.where(Payment.user_id.in_(user_ids))
    rows = list((await session.execute(stmt)).all())
    grouped: dict[int, dict[str, int]] = defaultdict(
        lambda: {
            "payment_count": 0,
            "first_paid_revenue_total": 0,
            "lifetime_revenue_total": 0,
        }
    )
    for user_id, amount, _paid_at, _payment_id in rows:
        user_key = int(user_id)
        payment_amount = int(amount or 0)
        bucket = grouped[user_key]
        bucket["payment_count"] = int(bucket["payment_count"]) + 1
        bucket["lifetime_revenue_total"] = int(bucket["lifetime_revenue_total"]) + payment_amount
        if int(bucket["payment_count"]) == 1:
            bucket["first_paid_revenue_total"] = payment_amount
    return {user_id: dict(bucket) for user_id, bucket in grouped.items()}


async def _load_invite_user_ids(
    session: AsyncSession,
    *,
    user_ids: set[int] | None = None,
) -> set[int]:
    if user_ids is not None and not user_ids:
        return set()
    stmt = (
        select(distinct(AuditLog.target_user_id))
        .where(AuditLog.action == "invite_issued")
        .where(AuditLog.target_user_id.is_not(None))
    )
    if user_ids is not None:
        stmt = stmt.where(AuditLog.target_user_id.in_(user_ids))
    rows = list((await session.execute(stmt)).scalars())
    return {int(user_id) for user_id in rows if user_id is not None}


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


def _percent(value: int, total: int) -> int:
    if total <= 0:
        return 0
    return int((value * 100) / total)


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



