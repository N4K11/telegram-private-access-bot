from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, Subscription, User
from app.utils.datetime import ensure_aware_utc, utcnow
from app.utils.encoding import safe_ui_text

_ONBOARDING_STEPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Что это за бот",
        (
            "Этот бот управляет доступом в приватный канал и помнит твою подписку.",
            "Здесь можно купить доступ, посмотреть свой статус и заново получить ссылку.",
        ),
    ),
    (
        "Как работает оплата",
        (
            "Основной способ оплаты — Telegram Stars.",
            "Если у проекта включён Crypto Pay, появится и альтернативный способ оплаты.",
            "После успешной оплаты подписка активируется автоматически.",
        ),
    ),
    (
        "Как попасть в канал",
        (
            "После оплаты открой раздел «Получить ссылку».",
            "Бот выдаст персональную invite-ссылку на активную подписку.",
            "Если что-то пошло не так, используй раздел «Помощь» или /paysupport.",
        ),
    ),
)


@dataclass(slots=True)
class OnboardingStepSnapshot:
    step_index: int
    total_steps: int
    heading: str
    body_lines: tuple[str, ...]

    @property
    def step_number(self) -> int:
        return self.step_index + 1

    @property
    def is_last(self) -> bool:
        return self.step_index >= self.total_steps - 1


async def get_pending_onboarding_step(
    session: AsyncSession,
    *,
    user: User,
    at_time: datetime | None = None,
) -> OnboardingStepSnapshot | None:
    if user.onboarding_completed_at is not None:
        return None

    current_time = ensure_aware_utc(at_time or utcnow())
    if await _has_existing_customer_state(session, user_id=user.id):
        user.onboarding_completed_at = current_time
        user.onboarding_step = len(_ONBOARDING_STEPS) - 1
        return None

    step_index = _normalize_step_index(user.onboarding_step)
    heading, body_lines = _ONBOARDING_STEPS[step_index]
    return OnboardingStepSnapshot(
        step_index=step_index,
        total_steps=len(_ONBOARDING_STEPS),
        heading=heading,
        body_lines=body_lines,
    )


async def advance_onboarding(
    session: AsyncSession,
    *,
    user: User,
    at_time: datetime | None = None,
) -> OnboardingStepSnapshot | None:
    if user.onboarding_completed_at is not None:
        return None

    current_time = ensure_aware_utc(at_time or utcnow())
    current_step = _normalize_step_index(user.onboarding_step)
    next_step = current_step + 1
    if next_step >= len(_ONBOARDING_STEPS):
        user.onboarding_completed_at = current_time
        user.onboarding_step = len(_ONBOARDING_STEPS) - 1
        return None

    user.onboarding_step = next_step
    heading, body_lines = _ONBOARDING_STEPS[next_step]
    return OnboardingStepSnapshot(
        step_index=next_step,
        total_steps=len(_ONBOARDING_STEPS),
        heading=heading,
        body_lines=body_lines,
    )


async def complete_onboarding(*, user: User, at_time: datetime | None = None) -> None:
    user.onboarding_completed_at = ensure_aware_utc(at_time or utcnow())
    user.onboarding_step = len(_ONBOARDING_STEPS) - 1


async def skip_onboarding(*, user: User, at_time: datetime | None = None) -> None:
    await complete_onboarding(user=user, at_time=at_time)


def render_onboarding_text(snapshot: OnboardingStepSnapshot, *, first_name: str | None) -> str:
    safe_name = escape(safe_ui_text(first_name, "друг"))
    progress = "".join(
        "●" if index <= snapshot.step_index else "○"
        for index in range(snapshot.total_steps)
    )
    lines = [
        f"✨ Привет, {safe_name}!",
        "",
        f"Шаг {snapshot.step_number}/{snapshot.total_steps} — {escape(snapshot.heading)}",
        "",
    ]
    lines.extend(f"• {escape(line)}" for line in snapshot.body_lines)
    lines.extend([
        "",
        f"Прогресс: {progress}",
        "Можно пропустить onboarding и вернуться к меню позже.",
    ])
    return "\n".join(lines)


async def _has_existing_customer_state(session: AsyncSession, *, user_id: int) -> bool:
    paid_payment = await session.execute(
        select(Payment.id)
        .where(Payment.user_id == user_id)
        .where(Payment.status == "paid")
        .limit(1)
    )
    if paid_payment.scalar_one_or_none() is not None:
        return True

    subscription = await session.execute(
        select(Subscription.id)
        .where(Subscription.user_id == user_id)
        .limit(1)
    )
    return subscription.scalar_one_or_none() is not None


def _normalize_step_index(value: int | None) -> int:
    if value is None:
        return 0
    if value < 0:
        return 0
    if value >= len(_ONBOARDING_STEPS):
        return len(_ONBOARDING_STEPS) - 1
    return int(value)