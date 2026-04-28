from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from aiogram.types import LabeledPrice, Message, SuccessfulPayment
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, Subscription, Tariff
from app.db.repositories.payments import PaymentRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.services.subscriptions import activate_or_extend_subscription
from app.utils.datetime import ensure_aware_utc, utcnow

STARS_CURRENCY = "XTR"
STARS_PROVIDER = "telegram_stars"
_STARS_PAYLOAD_PREFIX = "stars:tariff:"


class StarsInvoiceError(ValueError):
    """Raised when invoice payload or successful payment data is invalid."""


@dataclass(slots=True)
class StarsInvoicePayload:
    tariff_id: int


@dataclass(slots=True)
class StarsPaymentProcessingResult:
    payment: Payment | None
    subscription: Subscription | None
    is_duplicate: bool
    is_extension: bool


def build_stars_invoice_payload(tariff_id: int) -> str:
    return f"{_STARS_PAYLOAD_PREFIX}{tariff_id}"


def parse_stars_invoice_payload(payload: str) -> StarsInvoicePayload:
    if not payload.startswith(_STARS_PAYLOAD_PREFIX):
        raise StarsInvoiceError("Неизвестный payload платежа.")

    raw_tariff_id = payload.removeprefix(_STARS_PAYLOAD_PREFIX)
    if not raw_tariff_id.isdigit():
        raise StarsInvoiceError("Payload платежа повреждён.")

    return StarsInvoicePayload(tariff_id=int(raw_tariff_id))


def build_stars_prices(tariff: Tariff) -> list[LabeledPrice]:
    return [LabeledPrice(label=tariff.name, amount=tariff.price_stars)]


def build_stars_invoice_title(tariff: Tariff) -> str:
    title = tariff.name.strip()
    return title[:32] if title else "Подписка"


def build_stars_invoice_description(tariff: Tariff) -> str:
    channel_title = tariff.channel.title if tariff.channel is not None else "приватный канал"
    return (
        f"Доступ на {tariff.duration_days} дн. в {channel_title}. "
        "После оплаты подписка активируется автоматически."
    )[:255]


async def send_stars_invoice(message: Message, tariff: Tariff) -> Message:
    return await message.answer_invoice(
        title=build_stars_invoice_title(tariff),
        description=build_stars_invoice_description(tariff),
        payload=build_stars_invoice_payload(tariff.id),
        provider_token="",
        currency=STARS_CURRENCY,
        prices=build_stars_prices(tariff),
    )


async def process_successful_stars_payment(
    session: AsyncSession,
    *,
    user_id: int,
    tariff: Tariff,
    successful_payment: SuccessfulPayment,
    paid_at: datetime | None = None,
) -> StarsPaymentProcessingResult:
    if successful_payment.currency != STARS_CURRENCY:
        raise StarsInvoiceError("Поддерживаются только Telegram Stars.")

    payload = parse_stars_invoice_payload(successful_payment.invoice_payload)
    if payload.tariff_id != tariff.id:
        raise StarsInvoiceError("Payload не соответствует выбранному тарифу.")
    if successful_payment.total_amount != tariff.price_stars:
        raise StarsInvoiceError("Сумма платежа не соответствует тарифу.")

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

    payment_time = ensure_aware_utc(paid_at or utcnow())
    subscription_change = await activate_or_extend_subscription(
        session,
        user_id=user_id,
        tariff=tariff,
        paid_at=payment_time,
        source="purchase",
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