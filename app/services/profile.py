# ruff: noqa: E501
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from html import escape

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Payment, Subscription, User
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.users import UserRepository
from app.services.payments.crypto_pay import CRYPTO_PAY_PROVIDER, MINOR_UNITS_MULTIPLIER
from app.services.payments.stars import STARS_CURRENCY, STARS_PROVIDER
from app.services.users import describe_user_status
from app.utils.datetime import ensure_aware_utc, format_datetime, utcnow
from app.utils.encoding import safe_ui_text
from app.utils.referrals import build_referral_payload

DECIMAL_QUANT = Decimal("0.01")
ZERO_DECIMAL = Decimal("0.00")


@dataclass(slots=True)
class ProfilePaymentEntry:
    provider: str
    status: str
    tariff_name: str
    amount_label: str
    paid_at: datetime | None


@dataclass(slots=True)
class UserProfileSnapshot:
    user: User
    status: str
    status_label: str
    has_active_subscription: bool
    active_subscription_count: int
    latest_expires_at: datetime | None
    remaining_label: str
    current_tariff_label: str
    current_channel_label: str
    primary_channel_id: int | None
    total_stars_amount: int
    total_crypto_amounts: dict[str, Decimal]
    last_payment_at: datetime | None
    referral_payload: str | None
    pending_referral_reward_days: int
    rewarded_referrals_count: int
    stars_history: list[ProfilePaymentEntry]
    crypto_history: list[ProfilePaymentEntry]


async def build_user_profile_snapshot(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    now: datetime | None = None,
    history_limit: int = 10,
) -> UserProfileSnapshot | None:
    current_time = ensure_aware_utc(now or utcnow())
    user = await UserRepository(session).get_by_telegram_id(telegram_user_id)
    if user is None:
        return None

    subscription_repository = SubscriptionRepository(session)
    active_subscriptions = await subscription_repository.list_current_for_user(
        user.id,
        at_time=current_time,
    )
    recent_subscriptions = await subscription_repository.list_history_for_user(
        user.id,
        limit=max(history_limit, 1),
    )
    rewarded_referrals_count = await UserRepository(session).count_rewarded_referrals(user.id)

    payment_result = await session.execute(
        select(Payment)
        .options(selectinload(Payment.tariff))
        .where(Payment.user_id == user.id)
        .where(Payment.status == "paid")
        .order_by(Payment.paid_at.desc(), Payment.id.desc())
    )
    paid_payments = list(payment_result.scalars())

    latest_expires_at = _resolve_latest_expires_at(
        active_subscriptions=active_subscriptions,
        recent_subscriptions=recent_subscriptions,
    )
    primary_subscription = _resolve_primary_subscription(
        active_subscriptions=active_subscriptions,
        recent_subscriptions=recent_subscriptions,
    )
    status = describe_user_status(
        user,
        has_active_subscription=bool(active_subscriptions),
        latest_expires_at=latest_expires_at,
        paid_count=len(paid_payments),
    )

    total_stars_amount = 0
    total_crypto_amounts: dict[str, Decimal] = {}
    last_payment_at = None
    for payment in paid_payments:
        paid_at = ensure_aware_utc(payment.paid_at) if payment.paid_at is not None else None
        if last_payment_at is None and paid_at is not None:
            last_payment_at = paid_at

        if payment.provider == STARS_PROVIDER:
            total_stars_amount += int(payment.amount)
            continue

        if payment.provider.startswith(CRYPTO_PAY_PROVIDER):
            currency = (payment.currency or "CRYPTO").upper()
            total_crypto_amounts[currency] = total_crypto_amounts.get(currency, ZERO_DECIMAL) + _minor_units_to_decimal(int(payment.amount))

    stars_history = [
        _build_payment_entry(payment)
        for payment in paid_payments
        if payment.provider == STARS_PROVIDER
    ][:history_limit]
    crypto_history = [
        _build_payment_entry(payment)
        for payment in paid_payments
        if payment.provider.startswith(CRYPTO_PAY_PROVIDER)
    ][:history_limit]

    return UserProfileSnapshot(
        user=user,
        status=status,
        status_label=_status_label(status),
        has_active_subscription=bool(active_subscriptions),
        active_subscription_count=len(active_subscriptions),
        latest_expires_at=latest_expires_at,
        remaining_label=_remaining_label(
            latest_expires_at=latest_expires_at,
            has_active_subscription=bool(active_subscriptions),
            current_time=current_time,
        ),
        current_tariff_label=_current_tariff_label(
            primary_subscription,
            active_subscription_count=len(active_subscriptions),
        ),
        current_channel_label=_current_channel_label(
            primary_subscription,
            active_subscription_count=len(active_subscriptions),
        ),
        primary_channel_id=(
            primary_subscription.channel_id if primary_subscription is not None else None
        ),
        total_stars_amount=total_stars_amount,
        total_crypto_amounts=total_crypto_amounts,
        last_payment_at=last_payment_at,
        referral_payload=build_referral_payload(user.referral_code) if user.referral_code else None,
        pending_referral_reward_days=int(user.pending_referral_reward_days or 0),
        rewarded_referrals_count=rewarded_referrals_count,
        stars_history=stars_history,
        crypto_history=crypto_history,
    )


def render_user_profile(snapshot: UserProfileSnapshot, *, timezone: str) -> str:
    username = _format_username(snapshot.user.username)
    lines = [
        "\U0001f464 \u041c\u043e\u0439 \u043f\u0440\u043e\u0444\u0438\u043b\u044c",
        "",
        f"Telegram ID: <code>{snapshot.user.telegram_id}</code>",
        f"Username: {escape(username)}",
        f"\u0421\u0442\u0430\u0442\u0443\u0441: {escape(snapshot.status_label)}",
        f"\u0414\u043e\u0441\u0442\u0443\u043f \u0434\u043e: {_format_optional_datetime(snapshot.latest_expires_at, timezone)}",
        f"\u041e\u0441\u0442\u0430\u043b\u043e\u0441\u044c: {escape(snapshot.remaining_label)}",
        f"\u0422\u0435\u043a\u0443\u0449\u0438\u0439 \u0442\u0430\u0440\u0438\u0444: {escape(snapshot.current_tariff_label)}",
        f"\u041a\u0430\u043d\u0430\u043b: {escape(snapshot.current_channel_label)}",
    ]
    if snapshot.active_subscription_count > 1:
        lines.append(
            f"\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u043a\u0430\u043d\u0430\u043b\u043e\u0432: {snapshot.active_subscription_count}"
        )

    lines.extend(
        [
            "",
            "\U0001f4b3 \u041f\u043b\u0430\u0442\u0435\u0436\u0438",
            f"\u2b50 Stars: {escape(_format_stars_total(snapshot.total_stars_amount))}",
            f"\u20bf Crypto Pay: {escape(_format_crypto_totals(snapshot.total_crypto_amounts))}",
            f"\U0001f552 \u041f\u043e\u0441\u043b\u0435\u0434\u043d\u044f\u044f \u043e\u043f\u043b\u0430\u0442\u0430: {_format_optional_datetime(snapshot.last_payment_at, timezone)}",
            "",
            "\U0001f381 \u0420\u0435\u0444\u0435\u0440\u0430\u043b\u044b",
            f"\U0001f517 \u041a\u043e\u0434: {_format_referral_payload(snapshot.referral_payload)}",
            f"\U0001f381 \u0411\u043e\u043d\u0443\u0441 \u043a \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0435\u0439 \u043e\u043f\u043b\u0430\u0442\u0435: {snapshot.pending_referral_reward_days} \u0434\u043d.",
            f"\U0001f465 \u0423\u0441\u043f\u0435\u0448\u043d\u044b\u0445 \u0434\u0440\u0443\u0437\u0435\u0439: {snapshot.rewarded_referrals_count}",
        ]
    )
    return "\n".join(lines)


def render_user_payment_history(snapshot: UserProfileSnapshot, *, timezone: str) -> str:
    lines = [
        "\U0001f4dc \u0418\u0441\u0442\u043e\u0440\u0438\u044f \u043f\u043b\u0430\u0442\u0435\u0436\u0435\u0439",
        "",
    ]
    lines.extend(
        _render_payment_section(
            title="\u2b50 Telegram Stars",
            payments=snapshot.stars_history,
            timezone=timezone,
            empty_state="\u041f\u043e\u043a\u0430 \u043d\u0435\u0442 \u0443\u0441\u043f\u0435\u0448\u043d\u044b\u0445 \u043e\u043f\u043b\u0430\u0442 \u0447\u0435\u0440\u0435\u0437 Stars.",
        )
    )
    lines.append("")
    lines.extend(
        _render_payment_section(
            title="\u20bf Crypto Pay",
            payments=snapshot.crypto_history,
            timezone=timezone,
            empty_state="\u041f\u043e\u043a\u0430 \u043d\u0435\u0442 \u0443\u0441\u043f\u0435\u0448\u043d\u044b\u0445 \u043e\u043f\u043b\u0430\u0442 \u0447\u0435\u0440\u0435\u0437 Crypto Pay.",
        )
    )
    return "\n".join(lines)


def _render_payment_section(
    *,
    title: str,
    payments: list[ProfilePaymentEntry],
    timezone: str,
    empty_state: str,
) -> list[str]:
    lines = [title]
    if not payments:
        lines.append(empty_state)
        return lines

    for index, payment in enumerate(payments, start=1):
        lines.append(
            f"{index}. {escape(_payment_status_label(payment.status))} \u2022 {escape(payment.tariff_name)}"
        )
        lines.append(f"   \u0421\u0443\u043c\u043c\u0430: {escape(payment.amount_label)}")
        lines.append(
            f"   \u0414\u0430\u0442\u0430: {_format_optional_datetime(payment.paid_at, timezone)}"
        )
    return lines


def _build_payment_entry(payment: Payment) -> ProfilePaymentEntry:
    return ProfilePaymentEntry(
        provider=payment.provider,
        status=payment.status,
        tariff_name=_payment_tariff_label(payment),
        amount_label=_payment_amount_label(payment),
        paid_at=ensure_aware_utc(payment.paid_at) if payment.paid_at is not None else None,
    )


def _resolve_latest_expires_at(
    *,
    active_subscriptions: list[Subscription],
    recent_subscriptions: list[Subscription],
) -> datetime | None:
    if active_subscriptions:
        return max(ensure_aware_utc(subscription.expires_at) for subscription in active_subscriptions)
    if recent_subscriptions:
        return ensure_aware_utc(recent_subscriptions[0].expires_at)
    return None


def _resolve_primary_subscription(
    *,
    active_subscriptions: list[Subscription],
    recent_subscriptions: list[Subscription],
) -> Subscription | None:
    if active_subscriptions:
        return active_subscriptions[0]
    if recent_subscriptions:
        return recent_subscriptions[0]
    return None


def _remaining_label(
    *,
    latest_expires_at: datetime | None,
    has_active_subscription: bool,
    current_time: datetime,
) -> str:
    if latest_expires_at is None:
        return "\u2014"
    if not has_active_subscription or latest_expires_at <= current_time:
        return "\u0418\u0441\u0442\u0435\u043a\u043b\u0430"
    return _format_timedelta(latest_expires_at - current_time)


def _current_tariff_label(
    subscription: Subscription | None,
    active_subscription_count: int,
) -> str:
    if subscription is None:
        return "\u2014"
    base = safe_ui_text(
        subscription.tariff.name if subscription.tariff is not None else None,
        f"\u0422\u0430\u0440\u0438\u0444 #{subscription.tariff_id}",
    )
    if active_subscription_count > 1:
        return f"{base} (+{active_subscription_count - 1})"
    if active_subscription_count == 0:
        return f"{base} (\u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0439)"
    return base


def _current_channel_label(
    subscription: Subscription | None,
    active_subscription_count: int,
) -> str:
    if subscription is None:
        return "\u2014"
    base = safe_ui_text(
        subscription.channel.title if subscription.channel is not None else None,
        f"\u041a\u0430\u043d\u0430\u043b #{subscription.channel_id}",
    )
    if active_subscription_count > 1:
        return f"{base} (+{active_subscription_count - 1})"
    if active_subscription_count == 0:
        return f"{base} (\u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0439)"
    return base


def _status_label(status: str) -> str:
    mapping = {
        "\u0430\u043a\u0442\u0438\u0432\u0435\u043d": "\u2705 \u0410\u043a\u0442\u0438\u0432\u043d\u0430",
        "\u0438\u0441\u0442\u0451\u043a": "\u23f3 \u0418\u0441\u0442\u0435\u043a\u043b\u0430",
        "\u0437\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d": "\U0001f6ab \u0417\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d",
        "\u043d\u0435 \u043f\u043e\u043a\u0443\u043f\u0430\u043b": "\u26aa \u041f\u043e\u043a\u0443\u043f\u043e\u043a \u0435\u0449\u0451 \u043d\u0435 \u0431\u044b\u043b\u043e",
        "\u0431\u0435\u0437 \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0439 \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0438": "\u26aa \u041d\u0435\u0442 \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0439 \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0438",
    }
    return mapping.get(status, status)


def _payment_status_label(status: str) -> str:
    mapping = {
        "paid": "paid",
        "pending": "pending",
        "failed": "failed",
        "expired": "expired",
    }
    return mapping.get(status, status)


def _payment_tariff_label(payment: Payment) -> str:
    if payment.tariff is not None:
        return safe_ui_text(payment.tariff.name, f"\u0422\u0430\u0440\u0438\u0444 #{payment.tariff_id}")
    if payment.tariff_id is not None:
        return f"\u0422\u0430\u0440\u0438\u0444 #{payment.tariff_id}"
    return "\u0411\u0435\u0437 \u0442\u0430\u0440\u0438\u0444\u0430"


def _payment_amount_label(payment: Payment) -> str:
    if payment.provider == STARS_PROVIDER:
        return f"{int(payment.amount)} {STARS_CURRENCY}"
    if payment.provider.startswith(CRYPTO_PAY_PROVIDER):
        amount = _format_decimal(_minor_units_to_decimal(int(payment.amount)))
        return f"{amount} {(payment.currency or 'CRYPTO').upper()}"
    return f"{int(payment.amount)} {payment.currency}"


def _format_optional_datetime(value: datetime | None, timezone: str) -> str:
    if value is None:
        return "\u2014"
    return format_datetime(value, timezone)


def _format_username(username: str | None) -> str:
    if not username:
        return "\u2014"
    return f"@{username}"


def _format_referral_payload(value: str | None) -> str:
    if value is None:
        return "\u2014"
    return f"<code>{escape(value)}</code>"


def _format_stars_total(amount: int) -> str:
    return f"{amount} {STARS_CURRENCY}"


def _format_crypto_totals(values: dict[str, Decimal]) -> str:
    if not values:
        return "0"
    return " \u2022 ".join(
        f"{_format_decimal(amount)} {currency}"
        for currency, amount in sorted(values.items())
    )


def _format_timedelta(delta: timedelta) -> str:
    total_seconds = max(int(delta.total_seconds()), 0)
    days, remainder = divmod(total_seconds, 86400)
    hours = remainder // 3600
    if days > 0:
        return f"{days} \u0434\u043d. {hours} \u0447."
    if hours > 0:
        return f"{hours} \u0447."
    return "< 1 \u0447."


def _minor_units_to_decimal(value: int) -> Decimal:
    return (Decimal(value) / MINOR_UNITS_MULTIPLIER).quantize(
        DECIMAL_QUANT,
        rounding=ROUND_HALF_UP,
    )


def _format_decimal(value: Decimal) -> str:
    normalized = value.quantize(DECIMAL_QUANT, rounding=ROUND_HALF_UP)
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return format(normalized.normalize(), "f")

