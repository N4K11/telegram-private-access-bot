from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from aiogram.types import LabeledPrice, Message, SuccessfulPayment
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, Subscription, Tariff
from app.db.repositories.payments import PaymentRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.services.observability import EVENT_PAYMENT_STARS_PAID
from app.services.referral_service import (
    consume_pending_referral_reward_days,
    get_pending_referral_reward_days,
    grant_referral_reward_for_first_payment,
)
from app.services.subscriptions import activate_or_extend_subscription
from app.utils.datetime import ensure_aware_utc, utcnow
from app.utils.encoding import safe_ui_text

STARS_CURRENCY = "XTR"
STARS_PROVIDER = "telegram_stars"
_STARS_PAYLOAD_PREFIX = "stars:tariff:"
_PROMO_PAYLOAD_SEPARATOR = ":promo:"

logger = logging.getLogger(__name__)


class StarsInvoiceError(ValueError):
    """Raised when invoice payload or successful payment data is invalid."""


@dataclass(slots=True)
class StarsInvoicePayload:
    tariff_id: int
    promo_redemption_id: int | None = None


@dataclass(slots=True)
class StarsPaymentProcessingResult:
    payment: Payment | None
    subscription: Subscription | None
    is_duplicate: bool
    is_extension: bool


def build_stars_invoice_payload(tariff_id: int, promo_redemption_id: int | None = None) -> str:
    if promo_redemption_id is None:
        return f"{_STARS_PAYLOAD_PREFIX}{tariff_id}"
    return f"{_STARS_PAYLOAD_PREFIX}{tariff_id}{_PROMO_PAYLOAD_SEPARATOR}{promo_redemption_id}"


def parse_stars_invoice_payload(payload: str) -> StarsInvoicePayload:
    if not payload.startswith(_STARS_PAYLOAD_PREFIX):
        raise StarsInvoiceError("Неизвестный payload платежа.")

    payload_body = payload.removeprefix(_STARS_PAYLOAD_PREFIX)
    if _PROMO_PAYLOAD_SEPARATOR not in payload_body:
        if not payload_body.isdigit():
            raise StarsInvoiceError("Payload платежа повреждён.")
        return StarsInvoicePayload(tariff_id=int(payload_body))

    raw_tariff_id, raw_promo_id = payload_body.split(_PROMO_PAYLOAD_SEPARATOR, maxsplit=1)
    if not raw_tariff_id.isdigit() or not raw_promo_id.isdigit():
        raise StarsInvoiceError("Payload платежа повреждён.")
    return StarsInvoicePayload(
        tariff_id=int(raw_tariff_id),
        promo_redemption_id=int(raw_promo_id),
    )


def build_stars_prices(tariff: Tariff, *, amount: int | None = None) -> list[LabeledPrice]:
    label = safe_ui_text(tariff.name, f"Тариф #{tariff.id}")[:32]
    return [LabeledPrice(label=label, amount=amount or tariff.price_stars)]


def build_stars_invoice_title(tariff: Tariff) -> str:
    return safe_ui_text(tariff.name, f"Тариф #{tariff.id}")[:32]


def build_stars_invoice_description(tariff: Tariff) -> str:
    channel_title = safe_ui_text(
        tariff.channel.title if tariff.channel is not None else None,
        "приватный канал",
    )
    return (
        f"Доступ на {tariff.duration_days} дн. в {channel_title}. "
        "После оплаты подписка активируется автоматически."
    )[:255]


async def send_stars_invoice(
    message: Message,
    tariff: Tariff,
    *,
    amount: int | None = None,
    payload: str | None = None,
) -> Message:
    return await message.answer_invoice(
        title=build_stars_invoice_title(tariff),
        description=build_stars_invoice_description(tariff),
        payload=payload or build_stars_invoice_payload(tariff.id),
        provider_token="",
        currency=STARS_CURRENCY,
        prices=build_stars_prices(tariff, amount=amount),
    )


async def process_successful_stars_payment(
    session: AsyncSession,
    *,
    user_id: int,
    tariff: Tariff,
    successful_payment: SuccessfulPayment,
    expected_amount: int | None = None,
    paid_at: datetime | None = None,
    referral_reward_days: int = 0,
) -> StarsPaymentProcessingResult:
    if successful_payment.currency != STARS_CURRENCY:
        raise StarsInvoiceError("Поддерживаются только Telegram Stars.")

    payload = parse_stars_invoice_payload(successful_payment.invoice_payload)
    if payload.tariff_id != tariff.id:
        raise StarsInvoiceError("Payload не соответствует выбранному тарифу.")

    repository = PaymentRepository(session)
    existing = await repository.get_by_telegram_charge_id(
        successful_payment.telegram_payment_charge_id
    )
    if existing is not None:
        subscription = await SubscriptionRepository(session).get_latest_for_user_channel(
            user_id,
            tariff.channel_id,
        )
        return StarsPaymentProcessingResult(
            payment=existing,
            subscription=subscription,
            is_duplicate=True,
            is_extension=False,
        )

    required_amount = expected_amount if expected_amount is not None else tariff.price_stars
    if successful_payment.total_amount != required_amount:
        raise StarsInvoiceError("Сумма платежа не соответствует счёту.")

    payment_time = ensure_aware_utc(paid_at or utcnow())
    referral_bonus_days = await get_pending_referral_reward_days(session, user_id=user_id)
    duration_override = (
        tariff.duration_days + referral_bonus_days if referral_bonus_days > 0 else None
    )
    subscription_change = await activate_or_extend_subscription(
        session,
        user_id=user_id,
        tariff=tariff,
        paid_at=payment_time,
        source="purchase",
        duration_days_override=duration_override,
    )
    payment = await repository.create_paid(
        user_id=user_id,
        tariff_id=tariff.id,
        channel_id=tariff.channel_id,
        amount=successful_payment.total_amount,
        currency=successful_payment.currency,
        provider=STARS_PROVIDER,
        telegram_payment_charge_id=successful_payment.telegram_payment_charge_id,
        provider_payment_charge_id=successful_payment.provider_payment_charge_id or None,
        invoice_payload=successful_payment.invoice_payload,
        raw_payload=successful_payment.model_dump_json(exclude_none=True),
        paid_at=payment_time,
    )
    if referral_bonus_days > 0:
        await consume_pending_referral_reward_days(
            session,
            user_id=user_id,
            payment=payment,
            consumed_days=referral_bonus_days,
            consumed_at=payment_time,
        )
    await grant_referral_reward_for_first_payment(
        session,
        referred_user_id=user_id,
        payment=payment,
        reward_days=referral_reward_days,
        paid_at=payment_time,
    )
    logger.info(
        "Processed Telegram Stars payment %s for tariff %s.",
        payment.id,
        tariff.id,
        extra={
            "event_name": EVENT_PAYMENT_STARS_PAID,
            "user_id": user_id,
            "tariff_id": tariff.id,
            "payment_id": payment.id,
            "subscription_id": subscription_change.subscription.id,
            "provider": STARS_PROVIDER,
        },
    )
    return StarsPaymentProcessingResult(
        payment=payment,
        subscription=subscription_change.subscription,
        is_duplicate=False,
        is_extension=subscription_change.is_extension,
    )


async def refund_stars_payment(
    bot: Bot,
    *,
    user_id: int,
    telegram_payment_charge_id: str,
) -> bool:
    return await bot.refund_star_payment(
        user_id=user_id,
        telegram_payment_charge_id=telegram_payment_charge_id,
    )
