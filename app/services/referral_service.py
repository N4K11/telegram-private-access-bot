from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, Payment, User
from app.db.repositories.payments import PaymentRepository
from app.db.repositories.users import UserRepository
from app.services.audit import write_audit_log
from app.utils.datetime import ensure_aware_utc, format_datetime, utcnow
from app.utils.referrals import build_referral_payload, normalize_referral_code


@dataclass(slots=True)
class ReferralBindResult:
    status: str
    referral_code: str
    referrer: User | None = None


@dataclass(slots=True)
class ReferralRewardGrantResult:
    is_granted: bool
    reward_days: int
    referrer: User | None = None
    referred_user: User | None = None
    reason: str | None = None


@dataclass(slots=True)
class UserReferralDashboard:
    referral_payload: str | None
    referral_link: str | None
    invited_users_count: int
    paid_referrals_count: int
    earned_days: int
    pending_reward_days: int


@dataclass(slots=True)
class TopReferrerEntry:
    user: User
    invited_users_count: int
    paid_referrals_count: int
    earned_days: int
    pending_reward_days: int

    @property
    def conversion_percent(self) -> int:
        if self.invited_users_count <= 0:
            return 0
        return int((self.paid_referrals_count * 100) / self.invited_users_count)


@dataclass(slots=True)
class SuspiciousReferralEntry:
    created_at: datetime
    actor_user_id: int | None
    target_user_id: int | None
    reason: str
    referral_code: str | None


@dataclass(slots=True)
class AdminReferralSnapshot:
    total_invited_users: int
    total_paid_referrals: int
    rewards_issued_count: int
    reward_days_issued: int
    top_referrers: list[TopReferrerEntry]
    suspicious_events: list[SuspiciousReferralEntry]

    @property
    def conversion_percent(self) -> int:
        if self.total_invited_users <= 0:
            return 0
        return int((self.total_paid_referrals * 100) / self.total_invited_users)


async def bind_referrer_for_user(
    session: AsyncSession,
    *,
    user: User,
    raw_code: str,
    at_time: datetime | None = None,
) -> ReferralBindResult:
    referral_code = normalize_referral_code(raw_code)
    if not referral_code:
        return ReferralBindResult(status="invalid", referral_code=referral_code)

    if user.referred_by_user_id is not None:
        await _write_referral_suspicious(
            session,
            actor_user_id=user.id,
            target_user_id=user.id,
            reason="already_bound",
            referral_code=referral_code,
            payload={"existing_referrer_user_id": user.referred_by_user_id},
        )
        return ReferralBindResult(status="already_bound", referral_code=referral_code)

    paid_count = await PaymentRepository(session).count_paid_for_user(user.id)
    if paid_count > 0:
        await _write_referral_suspicious(
            session,
            actor_user_id=user.id,
            target_user_id=user.id,
            reason="already_customer",
            referral_code=referral_code,
        )
        return ReferralBindResult(status="already_customer", referral_code=referral_code)

    user_repository = UserRepository(session)
    referrer = await user_repository.get_by_referral_code(referral_code)
    if referrer is None:
        return ReferralBindResult(status="not_found", referral_code=referral_code)

    if referrer.id == user.id or referrer.telegram_id == user.telegram_id:
        await _write_referral_suspicious(
            session,
            actor_user_id=user.id,
            target_user_id=user.id,
            reason="self_referral",
            referral_code=referral_code,
        )
        return ReferralBindResult(status="self_referral", referral_code=referral_code)

    referred_at = ensure_aware_utc(at_time or utcnow())
    user.referred_by_user_id = referrer.id
    user.referred_at = referred_at
    await write_audit_log(
        session,
        action="referral_bound",
        actor_user_id=user.id,
        target_user_id=user.id,
        payload={
            "referrer_user_id": referrer.id,
            "referral_code": referral_code,
        },
    )
    return ReferralBindResult(status="bound", referral_code=referral_code, referrer=referrer)


async def get_pending_referral_reward_days(session: AsyncSession, *, user_id: int) -> int:
    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        return 0
    return max(int(user.pending_referral_reward_days or 0), 0)


async def consume_pending_referral_reward_days(
    session: AsyncSession,
    *,
    user_id: int,
    payment: Payment,
    consumed_days: int,
    consumed_at: datetime | None = None,
) -> int:
    if consumed_days <= 0:
        return 0

    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        return 0

    actual_days = min(int(user.pending_referral_reward_days or 0), consumed_days)
    if actual_days <= 0:
        return 0

    user.pending_referral_reward_days = int(user.pending_referral_reward_days or 0) - actual_days
    await write_audit_log(
        session,
        action="referral_reward_applied",
        actor_user_id=user.id,
        target_user_id=user.id,
        payload={
            "payment_id": payment.id,
            "bonus_days": actual_days,
            "consumed_at": ensure_aware_utc(consumed_at or utcnow()).isoformat(),
        },
    )
    return actual_days


async def grant_referral_reward_for_first_payment(
    session: AsyncSession,
    *,
    referred_user_id: int,
    payment: Payment,
    reward_days: int,
    paid_at: datetime | None = None,
) -> ReferralRewardGrantResult:
    if reward_days <= 0:
        return ReferralRewardGrantResult(
            is_granted=False,
            reward_days=0,
            reason="disabled",
        )

    user_repository = UserRepository(session)
    referred_user = await user_repository.get_by_id(referred_user_id)
    if referred_user is None:
        return ReferralRewardGrantResult(
            is_granted=False,
            reward_days=0,
            reason="missing_user",
        )

    if referred_user.referred_by_user_id is None:
        return ReferralRewardGrantResult(
            is_granted=False,
            reward_days=0,
            referred_user=referred_user,
            reason="not_referred",
        )

    if referred_user.referral_reward_granted_at is not None:
        await _write_referral_suspicious(
            session,
            actor_user_id=referred_user.id,
            target_user_id=referred_user.referred_by_user_id,
            reason="duplicate_reward_attempt",
            referral_code=referred_user.referral_code,
            payload={"payment_id": payment.id},
        )
        return ReferralRewardGrantResult(
            is_granted=False,
            reward_days=0,
            referred_user=referred_user,
            reason="already_granted",
        )

    referrer = await user_repository.get_by_id(referred_user.referred_by_user_id)
    if referrer is None:
        return ReferralRewardGrantResult(
            is_granted=False,
            reward_days=0,
            referred_user=referred_user,
            reason="missing_referrer",
        )

    if referrer.id == referred_user.id:
        await _write_referral_suspicious(
            session,
            actor_user_id=referred_user.id,
            target_user_id=referrer.id,
            reason="self_referral",
            referral_code=referred_user.referral_code,
            payload={"payment_id": payment.id},
        )
        return ReferralRewardGrantResult(
            is_granted=False,
            reward_days=0,
            referrer=referrer,
            referred_user=referred_user,
            reason="self_referral",
        )

    granted_at = ensure_aware_utc(paid_at or utcnow())
    referred_user.referral_reward_granted_at = granted_at
    referrer.pending_referral_reward_days = (
        int(referrer.pending_referral_reward_days or 0) + reward_days
    )
    await write_audit_log(
        session,
        action="referral_reward_granted",
        actor_user_id=referred_user.id,
        target_user_id=referrer.id,
        payload={
            "referred_user_id": referred_user.id,
            "payment_id": payment.id,
            "reward_days": reward_days,
        },
    )
    return ReferralRewardGrantResult(
        is_granted=True,
        reward_days=reward_days,
        referrer=referrer,
        referred_user=referred_user,
    )


async def build_user_referral_dashboard(
    session: AsyncSession,
    *,
    user_id: int,
    bot_username: str | None = None,
) -> UserReferralDashboard | None:
    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        return None

    invited_result = await session.execute(
        select(User)
        .where(User.referred_by_user_id == user.id)
        .order_by(User.referred_at.desc(), User.id.desc())
    )
    invited_users = list(invited_result.scalars())
    referral_payload = build_referral_payload(user.referral_code) if user.referral_code else None
    referral_link = None
    if referral_payload is not None and bot_username:
        referral_link = f"https://t.me/{bot_username}?start={referral_payload}"

    return UserReferralDashboard(
        referral_payload=referral_payload,
        referral_link=referral_link,
        invited_users_count=len(invited_users),
        paid_referrals_count=sum(
            1 for invited in invited_users if invited.referral_reward_granted_at is not None
        ),
        earned_days=await _sum_reward_days_for_target_user(session, target_user_id=user.id),
        pending_reward_days=int(user.pending_referral_reward_days or 0),
    )


async def build_admin_referral_snapshot(
    session: AsyncSession,
    *,
    limit: int = 10,
) -> AdminReferralSnapshot:
    invited_result = await session.execute(
        select(User)
        .where(User.referred_by_user_id.is_not(None))
        .order_by(User.referred_at.desc(), User.id.desc())
    )
    invited_users = list(invited_result.scalars())

    referrer_ids = {user.referred_by_user_id for user in invited_users if user.referred_by_user_id}
    referrers: dict[int, User] = {}
    if referrer_ids:
        referrer_result = await session.execute(select(User).where(User.id.in_(referrer_ids)))
        referrers = {user.id: user for user in referrer_result.scalars()}

    reward_days_by_target = await _sum_reward_days_by_target_user(
        session,
        target_user_ids=list(referrer_ids),
    )
    grouped: dict[int, list[User]] = {}
    for invited in invited_users:
        if invited.referred_by_user_id is None:
            continue
        grouped.setdefault(invited.referred_by_user_id, []).append(invited)

    top_referrers: list[TopReferrerEntry] = []
    for referrer_id, group in grouped.items():
        referrer = referrers.get(referrer_id)
        if referrer is None:
            continue
        paid_count = sum(1 for invited in group if invited.referral_reward_granted_at is not None)
        top_referrers.append(
            TopReferrerEntry(
                user=referrer,
                invited_users_count=len(group),
                paid_referrals_count=paid_count,
                earned_days=reward_days_by_target.get(referrer_id, 0),
                pending_reward_days=int(referrer.pending_referral_reward_days or 0),
            )
        )
    top_referrers.sort(
        key=lambda entry: (
            entry.paid_referrals_count,
            entry.invited_users_count,
            entry.earned_days,
            entry.user.id,
        ),
        reverse=True,
    )

    reward_events = await _load_audit_entries(session, action="referral_reward_granted")
    suspicious_events = await _load_audit_entries(
        session,
        action="referral_suspicious",
        limit=limit,
    )

    return AdminReferralSnapshot(
        total_invited_users=len(invited_users),
        total_paid_referrals=sum(
            1 for invited in invited_users if invited.referral_reward_granted_at is not None
        ),
        rewards_issued_count=len(reward_events),
        reward_days_issued=sum(
            int(event.get("payload", {}).get("reward_days", 0) or 0)
            for event in reward_events
        ),
        top_referrers=top_referrers[:limit],
        suspicious_events=[
            SuspiciousReferralEntry(
                created_at=event["created_at"],
                actor_user_id=event["actor_user_id"],
                target_user_id=event["target_user_id"],
                reason=str(event.get("payload", {}).get("reason", "unknown")),
                referral_code=event.get("payload", {}).get("referral_code"),
            )
            for event in suspicious_events
        ],
    )


def render_referral_status_message(result: ReferralBindResult) -> str | None:
    messages = {
        "bound": (
            "🎁 Реферальный код принят. Бонус пригласившему будет начислен "
            "после вашей первой оплаты."
        ),
        "self_referral": "⚠️ Нельзя использовать собственный реферальный код.",
        "already_bound": "ℹ️ Реферальный код уже привязан к вашему аккаунту.",
        "already_customer": "ℹ️ Реферальный код доступен только до первой успешной оплаты.",
        "not_found": "⚠️ Реферальный код не найден.",
        "invalid": "⚠️ Реферальный код указан некорректно.",
    }
    return messages.get(result.status)


def render_user_referral_dashboard(dashboard: UserReferralDashboard) -> str:
    referral_line = dashboard.referral_link or dashboard.referral_payload or "—"
    return (
        "🎁 Реферальная программа\n\n"
        f"Ссылка: {referral_line}\n"
        f"Приглашено друзей: {dashboard.invited_users_count}\n"
        f"Оплатили доступ: {dashboard.paid_referrals_count}\n"
        f"Заработано дней: {dashboard.earned_days}\n"
        f"Ожидает начисления: {dashboard.pending_reward_days} дн."
    )


def render_admin_referral_snapshot(
    snapshot: AdminReferralSnapshot,
    *,
    timezone: str,
) -> str:
    lines = [
        "🎁 Реферальная аналитика",
        "",
        f"Всего приглашённых: {snapshot.total_invited_users}",
        f"Оплативших: {snapshot.total_paid_referrals}",
        f"Конверсия: {snapshot.conversion_percent}%",
        f"Наград выдано: {snapshot.rewards_issued_count}",
        f"Выдано дней: {snapshot.reward_days_issued}",
        "",
        "Топ рефереров:",
    ]
    if not snapshot.top_referrers:
        lines.append("— нет данных")
    else:
        for index, entry in enumerate(snapshot.top_referrers, start=1):
            username = (
                f"@{entry.user.username}"
                if entry.user.username
                else f"ID {entry.user.telegram_id}"
            )
            lines.append(
                f"{index}. {username} — приглашено {entry.invited_users_count}, "
                f"оплатили {entry.paid_referrals_count}, "
                f"конверсия {entry.conversion_percent}%, "
                f"заработано {entry.earned_days} дн., "
                f"pending {entry.pending_reward_days} дн."
            )
    lines.extend(["", "Подозрительные кейсы:"])
    if not snapshot.suspicious_events:
        lines.append("— нет")
    else:
        for event in snapshot.suspicious_events:
            lines.append(
                f"• {format_datetime(event.created_at, timezone)} — {event.reason} "
                f"(actor={event.actor_user_id}, target={event.target_user_id}, "
                f"code={event.referral_code or '—'})"
            )
    return "\n".join(lines)


def build_profile_referral_block(
    *,
    referral_code: str | None,
    pending_reward_days: int,
    rewarded_referrals_count: int,
) -> str:
    if referral_code is None:
        return "Реферальный код: —\nБонус к следующей оплате: 0 дн.\nУспешных друзей: 0"

    return (
        f"Реферальный код: {build_referral_payload(referral_code)}\n"
        f"Бонус к следующей оплате: {pending_reward_days} дн.\n"
        f"Успешных друзей: {rewarded_referrals_count}"
    )


async def _sum_reward_days_for_target_user(
    session: AsyncSession,
    *,
    target_user_id: int,
) -> int:
    totals = await _sum_reward_days_by_target_user(session, target_user_ids=[target_user_id])
    return totals.get(target_user_id, 0)


async def _sum_reward_days_by_target_user(
    session: AsyncSession,
    *,
    target_user_ids: list[int],
) -> dict[int, int]:
    if not target_user_ids:
        return {}
    entries = await _load_audit_entries(session, action="referral_reward_granted")
    totals: dict[int, int] = {user_id: 0 for user_id in target_user_ids}
    for entry in entries:
        target_user_id = entry.get("target_user_id")
        if target_user_id not in totals:
            continue
        payload = entry.get("payload", {})
        totals[target_user_id] += int(payload.get("reward_days", 0) or 0)
    return totals


async def _load_audit_entries(
    session: AsyncSession,
    *,
    action: str,
    limit: int | None = None,
) -> list[dict[str, object]]:
    statement = select(AuditLog).where(AuditLog.action == action).order_by(
        AuditLog.created_at.desc(),
        AuditLog.id.desc(),
    )
    if limit is not None:
        statement = statement.limit(limit)
    result = await session.execute(statement)
    entries: list[dict[str, object]] = []
    for log in result.scalars():
        payload = _parse_payload(log.payload)
        entries.append(
            {
                "actor_user_id": log.actor_user_id,
                "target_user_id": log.target_user_id,
                "created_at": ensure_aware_utc(log.created_at),
                "payload": payload,
            }
        )
    return entries


def _parse_payload(raw_payload: str | None) -> dict[str, object]:
    if not raw_payload:
        return {}
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


async def _write_referral_suspicious(
    session: AsyncSession,
    *,
    actor_user_id: int | None,
    target_user_id: int | None,
    reason: str,
    referral_code: str | None,
    payload: dict[str, object] | None = None,
) -> None:
    event_payload: dict[str, object] = {"reason": reason}
    if referral_code:
        event_payload["referral_code"] = referral_code
    if payload:
        event_payload.update(payload)
    await write_audit_log(
        session,
        action="referral_suspicious",
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        payload=event_payload,
    )


