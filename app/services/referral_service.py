from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, User
from app.db.repositories.payments import PaymentRepository
from app.db.repositories.users import UserRepository
from app.services.audit import write_audit_log
from app.utils.datetime import ensure_aware_utc, utcnow
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
        return ReferralBindResult(status="already_bound", referral_code=referral_code)

    paid_count = await PaymentRepository(session).count_paid_for_user(user.id)
    if paid_count > 0:
        return ReferralBindResult(status="already_customer", referral_code=referral_code)

    user_repository = UserRepository(session)
    referrer = await user_repository.get_by_referral_code(referral_code)
    if referrer is None:
        return ReferralBindResult(status="not_found", referral_code=referral_code)

    if referrer.id == user.id or referrer.telegram_id == user.telegram_id:
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
