from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, PromoCode, PromoRedemption, Tariff
from app.db.repositories.promo_codes import PromoCodeRepository
from app.db.repositories.promo_redemptions import PromoRedemptionRepository
from app.db.repositories.tariffs import TariffRepository
from app.services.subscriptions import SubscriptionChange, activate_or_extend_subscription
from app.utils.datetime import ensure_aware_utc, utcnow

PROMO_TYPE_FREE_DAYS = "free_days"
PROMO_TYPE_DISCOUNT_PERCENT = "discount_percent"
PROMO_TYPE_DISCOUNT_STARS = "discount_stars"
PROMO_TYPE_FIXED_PRICE = "fixed_price"
PROMO_TYPES = {
    PROMO_TYPE_FREE_DAYS,
    PROMO_TYPE_DISCOUNT_PERCENT,
    PROMO_TYPE_DISCOUNT_STARS,
    PROMO_TYPE_FIXED_PRICE,
}
DISCOUNT_PROMO_TYPES = {
    PROMO_TYPE_DISCOUNT_PERCENT,
    PROMO_TYPE_DISCOUNT_STARS,
    PROMO_TYPE_FIXED_PRICE,
}
PROMO_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,63}$")


class PromoCodeError(ValueError):
    """Raised when promo code validation or application fails."""


@dataclass(slots=True)
class PromoApplyResult:
    promo_code: PromoCode
    redemption: PromoRedemption
    action: str
    subscription_change: SubscriptionChange | None = None


@dataclass(slots=True)
class PromoDiscountQuote:
    promo_code: PromoCode
    redemption: PromoRedemption
    tariff: Tariff
    original_amount: int
    final_amount: int
    savings_amount: int
    description: str


@dataclass(slots=True)
class PromoStats:
    promo_code: PromoCode
    pending_count: int
    consumed_count: int
    cancelled_count: int

    @property
    def total_uses(self) -> int:
        return self.pending_count + self.consumed_count


@dataclass(slots=True)
class PromoDraft:
    code: str
    promo_type: str
    value: int
    max_uses: int
    tariff_id: int | None
    valid_days: int | None



def normalize_promo_code(raw_code: str) -> str:
    code = raw_code.strip().upper()
    if not code:
        raise PromoCodeError("Укажите промокод после команды.")
    if not PROMO_CODE_PATTERN.fullmatch(code):
        raise PromoCodeError(
            "Промокод должен содержать 3-64 символа: латиницу, цифры, '_' или '-'."
        )
    return code



def parse_promo_draft(
    *,
    code: str,
    promo_type: str,
    value: str,
    max_uses: str,
    tariff_id: str | None = None,
    valid_days: str | None = None,
) -> PromoDraft:
    normalized_code = normalize_promo_code(code)
    normalized_type = promo_type.strip().lower()
    if normalized_type not in PROMO_TYPES:
        raise PromoCodeError(
            "Тип промокода должен быть одним из: free_days, discount_percent, "
            "discount_stars, fixed_price."
        )

    try:
        parsed_value = int(value)
        parsed_limit = int(max_uses)
    except ValueError as exc:
        raise PromoCodeError("VALUE и LIMIT должны быть целыми числами.") from exc

    if parsed_value <= 0:
        raise PromoCodeError("VALUE должен быть больше нуля.")
    if parsed_limit <= 0:
        raise PromoCodeError("LIMIT должен быть больше нуля.")

    parsed_tariff_id: int | None = None
    if tariff_id and tariff_id != "-":
        try:
            parsed_tariff_id = int(tariff_id)
        except ValueError as exc:
            raise PromoCodeError("TARIFF_ID должен быть целым числом или '-'.") from exc
        if parsed_tariff_id <= 0:
            raise PromoCodeError("TARIFF_ID должен быть больше нуля.")

    parsed_valid_days: int | None = None
    if valid_days and valid_days != "-":
        try:
            parsed_valid_days = int(valid_days)
        except ValueError as exc:
            raise PromoCodeError("VALID_DAYS должен быть целым числом или '-'.") from exc
        if parsed_valid_days <= 0:
            raise PromoCodeError("VALID_DAYS должен быть больше нуля.")

    return PromoDraft(
        code=normalized_code,
        promo_type=normalized_type,
        value=parsed_value,
        max_uses=parsed_limit,
        tariff_id=parsed_tariff_id,
        valid_days=parsed_valid_days,
    )



def build_discount_description(
    promo_code: PromoCode,
    *,
    original_amount: int,
    final_amount: int,
) -> str:
    if promo_code.promo_type == PROMO_TYPE_DISCOUNT_PERCENT:
        return f"-{promo_code.value}%"
    if promo_code.promo_type == PROMO_TYPE_DISCOUNT_STARS:
        return f"-{original_amount - final_amount} Stars"
    return f"фиксированная цена {final_amount} Stars"


async def create_promo_code(
    session: AsyncSession,
    *,
    actor_user_id: int | None,
    draft: PromoDraft,
    now: datetime | None = None,
) -> PromoCode:
    repository = PromoCodeRepository(session)
    if await repository.get_by_code(draft.code) is not None:
        raise PromoCodeError("Промокод с таким кодом уже существует.")

    tariff: Tariff | None = None
    if draft.tariff_id is not None:
        tariff = await TariffRepository(session).get_by_id(draft.tariff_id)
        if tariff is None or not tariff.is_active or tariff.archived_at is not None:
            raise PromoCodeError("Тариф для промокода не найден или недоступен.")

    _validate_promo_value(draft, tariff=tariff)
    event_time = ensure_aware_utc(now or utcnow())
    expires_at = None
    if draft.valid_days is not None:
        expires_at = event_time + timedelta(days=draft.valid_days)

    return await repository.create(
        code=draft.code,
        promo_type=draft.promo_type,
        value=draft.value,
        max_uses=draft.max_uses,
        tariff_id=draft.tariff_id,
        expires_at=expires_at,
        is_active=True,
        created_by_user_id=actor_user_id,
    )


async def disable_promo_code(session: AsyncSession, *, code: str) -> PromoCode:
    normalized_code = normalize_promo_code(code)
    repository = PromoCodeRepository(session)
    promo_code = await repository.get_by_code(normalized_code)
    if promo_code is None:
        raise PromoCodeError("Промокод не найден.")
    await repository.set_active(promo_code, is_active=False)
    return promo_code


async def get_promo_stats(session: AsyncSession, *, code: str) -> PromoStats:
    normalized_code = normalize_promo_code(code)
    promo_code = await PromoCodeRepository(session).get_by_code(normalized_code)
    if promo_code is None:
        raise PromoCodeError("Промокод не найден.")

    summary = await PromoRedemptionRepository(session).summarize_for_promo(promo_code.id)
    return PromoStats(
        promo_code=promo_code,
        pending_count=summary.get("pending", 0),
        consumed_count=summary.get("consumed", 0),
        cancelled_count=summary.get("cancelled", 0),
    )


async def apply_promo_code(
    session: AsyncSession,
    *,
    user_id: int,
    code: str,
    now: datetime | None = None,
) -> PromoApplyResult:
    event_time = ensure_aware_utc(now or utcnow())
    normalized_code = normalize_promo_code(code)
    promo_code = await PromoCodeRepository(session).get_by_code(normalized_code)
    if promo_code is None:
        raise PromoCodeError("Промокод не найден.")
    _ensure_promo_is_available(promo_code, at=event_time)

    redemptions = PromoRedemptionRepository(session)
    existing = await redemptions.get_by_promo_and_user(promo_code.id, user_id)
    if existing is not None and existing.status == "consumed":
        raise PromoCodeError("Этот промокод уже использован этим пользователем.")

    if promo_code.promo_type == PROMO_TYPE_FREE_DAYS:
        return await _grant_free_days_promo(
            session,
            redemptions=redemptions,
            promo_code=promo_code,
            user_id=user_id,
            existing=existing,
            at=event_time,
        )

    return await _activate_discount_promo(
        session,
        redemptions=redemptions,
        promo_code=promo_code,
        user_id=user_id,
        existing=existing,
    )


async def get_pending_discount_quote_for_tariff(
    session: AsyncSession,
    *,
    user_id: int,
    tariff: Tariff,
    now: datetime | None = None,
) -> PromoDiscountQuote | None:
    event_time = ensure_aware_utc(now or utcnow())
    pending = await PromoRedemptionRepository(session).list_pending_for_user(user_id)
    for redemption in pending:
        promo_code = redemption.promo_code
        if promo_code is None or promo_code.promo_type not in DISCOUNT_PROMO_TYPES:
            continue
        try:
            _ensure_promo_is_available(promo_code, at=event_time)
            return _build_discount_quote(
                redemption=redemption,
                promo_code=promo_code,
                tariff=tariff,
            )
        except PromoCodeError:
            continue
    return None


async def get_discount_quote_for_redemption(
    session: AsyncSession,
    *,
    redemption_id: int,
    user_id: int,
    tariff: Tariff,
    now: datetime | None = None,
) -> PromoDiscountQuote:
    event_time = ensure_aware_utc(now or utcnow())
    redemption = await PromoRedemptionRepository(session).get_by_id(redemption_id)
    if redemption is None or redemption.user_id != user_id:
        raise PromoCodeError("Промокод больше недоступен.")
    if redemption.status != "pending":
        raise PromoCodeError("Промокод уже использован или отменён.")

    promo_code = redemption.promo_code
    if promo_code is None:
        raise PromoCodeError("Промокод больше недоступен.")

    _ensure_promo_is_available(promo_code, at=event_time)
    return _build_discount_quote(
        redemption=redemption,
        promo_code=promo_code,
        tariff=tariff,
    )


async def consume_discount_redemption(
    session: AsyncSession,
    *,
    quote: PromoDiscountQuote,
    payment: Payment,
    used_at: datetime | None = None,
) -> PromoRedemption:
    event_time = ensure_aware_utc(used_at or utcnow())
    repository = PromoRedemptionRepository(session)
    return await repository.mark_consumed(
        quote.redemption,
        payment_id=payment.id,
        applied_tariff_id=quote.tariff.id,
        amount_before=quote.original_amount,
        amount_after=quote.final_amount,
        used_at=event_time,
    )



def _validate_promo_value(draft: PromoDraft, *, tariff: Tariff | None) -> None:
    if draft.promo_type == PROMO_TYPE_FREE_DAYS and draft.tariff_id is None:
        raise PromoCodeError("Для free_days нужно указать TARIFF_ID.")
    if draft.promo_type == PROMO_TYPE_DISCOUNT_PERCENT and not 1 <= draft.value <= 99:
        raise PromoCodeError("discount_percent должен быть в диапазоне 1..99.")
    if draft.promo_type == PROMO_TYPE_FIXED_PRICE and draft.value <= 0:
        raise PromoCodeError("fixed_price должен быть больше нуля.")
    if (
        tariff is not None
        and draft.promo_type == PROMO_TYPE_FIXED_PRICE
        and draft.value >= tariff.price_stars
    ):
        raise PromoCodeError(
            "fixed_price должен быть меньше обычной цены выбранного тарифа."
        )



def _ensure_promo_is_available(promo_code: PromoCode, *, at: datetime) -> None:
    if not promo_code.is_active:
        raise PromoCodeError("Промокод отключён.")
    if promo_code.expires_at is not None and promo_code.expires_at <= at:
        raise PromoCodeError("Срок действия промокода истёк.")


async def _grant_free_days_promo(
    session: AsyncSession,
    *,
    redemptions: PromoRedemptionRepository,
    promo_code: PromoCode,
    user_id: int,
    existing: PromoRedemption | None,
    at: datetime,
) -> PromoApplyResult:
    if promo_code.tariff is None:
        raise PromoCodeError("Для free_days не найден привязанный тариф.")

    if existing is None:
        await _ensure_usage_available(redemptions, promo_code=promo_code)
        redemption = await redemptions.create(
            promo_code_id=promo_code.id,
            user_id=user_id,
            status="consumed",
            applied_tariff_id=promo_code.tariff.id,
            used_at=at,
        )
    else:
        await _ensure_usage_available(redemptions, promo_code=promo_code)
        redemption = await redemptions.mark_consumed(
            existing,
            payment_id=None,
            applied_tariff_id=promo_code.tariff.id,
            amount_before=None,
            amount_after=None,
            used_at=at,
        )

    subscription_change = await activate_or_extend_subscription(
        session,
        user_id=user_id,
        tariff=promo_code.tariff,
        paid_at=at,
        source="promo",
        duration_days_override=promo_code.value,
    )
    return PromoApplyResult(
        promo_code=promo_code,
        redemption=redemption,
        action="granted_free_days",
        subscription_change=subscription_change,
    )


async def _activate_discount_promo(
    session: AsyncSession,
    *,
    redemptions: PromoRedemptionRepository,
    promo_code: PromoCode,
    user_id: int,
    existing: PromoRedemption | None,
) -> PromoApplyResult:
    if existing is not None and existing.status == "pending":
        await redemptions.cancel_other_pending_for_user(
            user_id=user_id,
            exclude_redemption_id=existing.id,
        )
        return PromoApplyResult(
            promo_code=promo_code,
            redemption=existing,
            action="pending_discount",
        )

    await _ensure_usage_available(redemptions, promo_code=promo_code)
    if existing is None:
        redemption = await redemptions.create(
            promo_code_id=promo_code.id,
            user_id=user_id,
            status="pending",
        )
    else:
        redemption = await redemptions.activate_pending(existing)
    await redemptions.cancel_other_pending_for_user(
        user_id=user_id,
        exclude_redemption_id=redemption.id,
    )
    return PromoApplyResult(
        promo_code=promo_code,
        redemption=redemption,
        action="pending_discount",
    )


async def _ensure_usage_available(
    redemptions: PromoRedemptionRepository,
    *,
    promo_code: PromoCode,
) -> None:
    reserved_or_consumed = await redemptions.count_for_promo_by_statuses(
        promo_code.id,
        ("pending", "consumed"),
    )
    if reserved_or_consumed >= promo_code.max_uses:
        raise PromoCodeError("Лимит использований промокода исчерпан.")



def _build_discount_quote(
    *,
    redemption: PromoRedemption,
    promo_code: PromoCode,
    tariff: Tariff,
) -> PromoDiscountQuote:
    if promo_code.tariff_id is not None and promo_code.tariff_id != tariff.id:
        raise PromoCodeError("Этот промокод не подходит для выбранного тарифа.")

    original_amount = tariff.price_stars
    final_amount = _calculate_discounted_amount(
        promo_code=promo_code,
        original_amount=original_amount,
    )
    if final_amount <= 0:
        raise PromoCodeError(
            "Промокод делает цену некорректной. Обратитесь к администратору."
        )
    if final_amount >= original_amount:
        raise PromoCodeError("Этот промокод не даёт скидку на выбранный тариф.")

    savings_amount = original_amount - final_amount
    return PromoDiscountQuote(
        promo_code=promo_code,
        redemption=redemption,
        tariff=tariff,
        original_amount=original_amount,
        final_amount=final_amount,
        savings_amount=savings_amount,
        description=build_discount_description(
            promo_code,
            original_amount=original_amount,
            final_amount=final_amount,
        ),
    )



def _calculate_discounted_amount(*, promo_code: PromoCode, original_amount: int) -> int:
    if promo_code.promo_type == PROMO_TYPE_DISCOUNT_PERCENT:
        return (original_amount * (100 - promo_code.value)) // 100
    if promo_code.promo_type == PROMO_TYPE_DISCOUNT_STARS:
        return original_amount - promo_code.value
    if promo_code.promo_type == PROMO_TYPE_FIXED_PRICE:
        return promo_code.value
    raise PromoCodeError("Этот промокод нельзя применить к оплате.")
