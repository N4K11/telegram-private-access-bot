# ruff: noqa: E501
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from html import escape
from io import StringIO
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, CryptoInvoice, Payment, PromoCode, PromoRedemption, Tariff, User
from app.services.payments.crypto_pay import CRYPTO_PAY_PROVIDER, MINOR_UNITS_MULTIPLIER
from app.services.payments.stars import STARS_PROVIDER
from app.utils.datetime import ensure_aware_utc, format_datetime, utcnow
from app.utils.encoding import safe_ui_text

FinancePeriodKey = Literal["day", "week", "month", "all"]
PERIOD_DAY: FinancePeriodKey = "day"
PERIOD_WEEK: FinancePeriodKey = "week"
PERIOD_MONTH: FinancePeriodKey = "month"
PERIOD_ALL: FinancePeriodKey = "all"
FINANCE_PERIODS: tuple[FinancePeriodKey, ...] = (
    PERIOD_DAY,
    PERIOD_WEEK,
    PERIOD_MONTH,
    PERIOD_ALL,
)
PERIOD_LABELS: dict[FinancePeriodKey, str] = {
    PERIOD_DAY: "\u0434\u0435\u043d\u044c",
    PERIOD_WEEK: "7 \u0434\u043d\u0435\u0439",
    PERIOD_MONTH: "30 \u0434\u043d\u0435\u0439",
    PERIOD_ALL: "\u0432\u0441\u0451 \u0432\u0440\u0435\u043c\u044f",
}
ZERO_DECIMAL = Decimal("0")
DECIMAL_QUANT = Decimal("0.01")


@dataclass(slots=True)
class FinancePaymentRow:
    payment_id: int
    user_id: int
    tariff_id: int | None
    tariff_name: str
    provider: str
    currency: str
    amount: int
    paid_at: datetime


@dataclass(slots=True)
class FinancePeriodSnapshot:
    key: FinancePeriodKey
    label: str
    stars_revenue: int = 0
    stars_payment_count: int = 0
    stars_paying_users: int = 0
    crypto_revenue: dict[str, Decimal] = field(default_factory=dict)
    crypto_payment_count: int = 0
    crypto_paying_users: dict[str, int] = field(default_factory=dict)
    total_paying_users: int = 0


@dataclass(slots=True)
class TopTariffEntry:
    tariff_id: int | None
    tariff_name: str
    payment_count: int
    stars_revenue: int
    crypto_revenue: dict[str, Decimal]


@dataclass(slots=True)
class FinanceSnapshot:
    generated_at: datetime
    periods: dict[FinancePeriodKey, FinancePeriodSnapshot]
    unpaid_crypto_invoices: int
    expired_crypto_invoices: int
    refunds_count: int
    manual_recoveries_count: int
    promo_free_days_count: int
    referral_rewards_count: int
    stars_average_revenue_per_user: Decimal
    crypto_average_revenue_per_user: dict[str, Decimal]
    top_tariffs: list[TopTariffEntry]
    payment_rows: list[FinancePaymentRow]


async def build_finance_snapshot(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> FinanceSnapshot:
    current_time = ensure_aware_utc(now or utcnow())
    period_starts = _period_starts(current_time)
    payment_rows = await _load_paid_payment_rows(session)

    periods = {
        key: FinancePeriodSnapshot(key=key, label=PERIOD_LABELS[key])
        for key in FINANCE_PERIODS
    }
    stars_payers = {key: set() for key in FINANCE_PERIODS}
    crypto_payers = {key: defaultdict(set) for key in FINANCE_PERIODS}
    all_payers = {key: set() for key in FINANCE_PERIODS}

    for row in payment_rows:
        for key in FINANCE_PERIODS:
            cutoff = period_starts[key]
            if cutoff is not None and row.paid_at < cutoff:
                continue

            snapshot = periods[key]
            all_payers[key].add(row.user_id)
            if row.provider == STARS_PROVIDER:
                snapshot.stars_revenue += row.amount
                snapshot.stars_payment_count += 1
                stars_payers[key].add(row.user_id)
                continue

            if row.provider.startswith(CRYPTO_PAY_PROVIDER):
                snapshot.crypto_payment_count += 1
                snapshot.crypto_revenue[row.currency] = snapshot.crypto_revenue.get(
                    row.currency,
                    ZERO_DECIMAL,
                ) + _minor_units_to_decimal(row.amount)
                crypto_payers[key][row.currency].add(row.user_id)

    for key in FINANCE_PERIODS:
        periods[key].stars_paying_users = len(stars_payers[key])
        periods[key].crypto_paying_users = {
            currency: len(user_ids)
            for currency, user_ids in crypto_payers[key].items()
        }
        periods[key].total_paying_users = len(all_payers[key])

    unpaid_crypto_invoices, expired_crypto_invoices = await _load_crypto_invoice_counts(
        session,
        now=current_time,
    )
    refunds_count = await _count_refunds(session)
    manual_recoveries_count = await _count_audit_action(session, "admin_subscription_granted")
    promo_free_days_count = await _count_promo_free_days(session)
    referral_rewards_count = await _count_referral_rewards(session)

    all_period = periods[PERIOD_ALL]
    stars_average_revenue_per_user = _average_from_int(
        all_period.stars_revenue,
        all_period.stars_paying_users,
    )
    crypto_average_revenue_per_user = {
        currency: _average_from_decimal(
            amount,
            all_period.crypto_paying_users.get(currency, 0),
        )
        for currency, amount in all_period.crypto_revenue.items()
    }

    return FinanceSnapshot(
        generated_at=current_time,
        periods=periods,
        unpaid_crypto_invoices=unpaid_crypto_invoices,
        expired_crypto_invoices=expired_crypto_invoices,
        refunds_count=refunds_count,
        manual_recoveries_count=manual_recoveries_count,
        promo_free_days_count=promo_free_days_count,
        referral_rewards_count=referral_rewards_count,
        stars_average_revenue_per_user=stars_average_revenue_per_user,
        crypto_average_revenue_per_user=crypto_average_revenue_per_user,
        top_tariffs=_build_top_tariffs(payment_rows),
        payment_rows=payment_rows,
    )


def render_finance_dashboard(snapshot: FinanceSnapshot, *, timezone: str) -> str:
    lines = ["\U0001f4b0 \u0424\u0438\u043d\u0430\u043d\u0441\u043e\u0432\u0430\u044f \u043f\u0430\u043d\u0435\u043b\u044c", "", "\u2b50 Stars:"]
    for key in FINANCE_PERIODS:
        period = snapshot.periods[key]
        lines.append(
            f"\u2022 {period.label}: {period.stars_revenue} Stars ({period.stars_payment_count} \u043e\u043f\u043b\u0430\u0442)"
        )

    lines.extend(["", "\U0001fa99 Crypto Pay:"])
    for key in FINANCE_PERIODS:
        period = snapshot.periods[key]
        lines.append(
            f"\u2022 {period.label}: {_format_crypto_totals(period.crypto_revenue)} "
            f"({period.crypto_payment_count} \u043e\u043f\u043b\u0430\u0442)"
        )

    lines.extend(
        [
            "",
            "\u0421\u043e\u0441\u0442\u043e\u044f\u043d\u0438\u0435 \u0441\u0447\u0451\u0442\u043e\u0432:",
            f"\u2022 \u041d\u0435\u043e\u043f\u043b\u0430\u0447\u0435\u043d\u043d\u044b\u0435 crypto invoices: {snapshot.unpaid_crypto_invoices}",
            f"\u2022 \u0418\u0441\u0442\u0451\u043a\u0448\u0438\u0435 crypto invoices: {snapshot.expired_crypto_invoices}",
            f"\u2022 \u0412\u043e\u0437\u0432\u0440\u0430\u0442\u044b: {snapshot.refunds_count}",
            f"\u2022 \u0420\u0443\u0447\u043d\u044b\u0435 \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f: {snapshot.manual_recoveries_count}",
            f"\u2022 Promo free-days: {snapshot.promo_free_days_count}",
            f"\u2022 Referral rewards: {snapshot.referral_rewards_count}",
            "",
            "ARPPU:",
            (
                f"\u2022 Stars: {_format_decimal(snapshot.stars_average_revenue_per_user)} "
                f"Stars \u043d\u0430 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f"
            ),
            (
                "\u2022 Crypto: "
                f"{_format_crypto_totals(snapshot.crypto_average_revenue_per_user)} \u043d\u0430 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f"
            ),
            (
                f"\u2022 \u0412\u0441\u0435\u0433\u043e \u043f\u043b\u0430\u0442\u044f\u0449\u0438\u0445 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439: "
                f"{snapshot.periods[PERIOD_ALL].total_paying_users}"
            ),
            "",
            "\u0422\u043e\u043f \u0442\u0430\u0440\u0438\u0444\u043e\u0432:",
        ]
    )

    if snapshot.top_tariffs:
        for index, entry in enumerate(snapshot.top_tariffs, start=1):
            title = escape(safe_ui_text(entry.tariff_name, "\u0422\u0430\u0440\u0438\u0444 \u0431\u0435\u0437 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u044f"))
            stars_block = f"{entry.stars_revenue} Stars"
            crypto_block = _format_crypto_totals(entry.crypto_revenue)
            lines.append(
                f"{index}. {title} \u2014 {entry.payment_count} \u043e\u043f\u043b\u0430\u0442 \u2022 "
                f"{stars_block} \u2022 {crypto_block}"
            )
    else:
        lines.append("\u2022 \u041f\u043e\u043a\u0430 \u043d\u0435\u0442 \u0443\u0441\u043f\u0435\u0448\u043d\u044b\u0445 \u043e\u043f\u043b\u0430\u0442.")

    lines.extend(
        [
            "",
            f"\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u043d\u043e: {format_datetime(snapshot.generated_at, timezone)}",
        ]
    )
    return "\n".join(lines)


def build_finance_report_csv(
    snapshot: FinanceSnapshot,
    *,
    period: FinancePeriodKey,
    timezone: str,
) -> bytes:
    key = normalize_finance_period(period)
    period_snapshot = snapshot.periods[key]
    rows = _filter_payments_for_period(snapshot.payment_rows, snapshot.generated_at, key)
    top_tariffs = _build_top_tariffs(rows)

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["section", "metric", "period", "provider", "currency", "value"])
    writer.writerow(["summary", "generated_at", key, "system", timezone, snapshot.generated_at.isoformat()])
    writer.writerow(["summary", "period_label", key, "system", "text", period_snapshot.label])
    writer.writerow(["summary", "stars_revenue", key, STARS_PROVIDER, "Stars", period_snapshot.stars_revenue])
    writer.writerow(["summary", "stars_payments", key, STARS_PROVIDER, "count", period_snapshot.stars_payment_count])
    for currency, amount in sorted(period_snapshot.crypto_revenue.items()):
        writer.writerow(
            [
                "summary",
                "crypto_revenue",
                key,
                CRYPTO_PAY_PROVIDER,
                currency,
                _format_decimal(amount),
            ]
        )
    writer.writerow(
        [
            "summary",
            "crypto_payments",
            key,
            CRYPTO_PAY_PROVIDER,
            "count",
            period_snapshot.crypto_payment_count,
        ]
    )
    writer.writerow(["summary", "unpaid_crypto_invoices", key, "system", "count", snapshot.unpaid_crypto_invoices])
    writer.writerow(["summary", "expired_crypto_invoices", key, "system", "count", snapshot.expired_crypto_invoices])
    writer.writerow(["summary", "refunds_count", key, "system", "count", snapshot.refunds_count])
    writer.writerow(["summary", "manual_recoveries_count", key, "system", "count", snapshot.manual_recoveries_count])
    writer.writerow(["summary", "promo_free_days_count", key, "system", "count", snapshot.promo_free_days_count])
    writer.writerow(["summary", "referral_rewards_count", key, "system", "count", snapshot.referral_rewards_count])
    writer.writerow([])

    writer.writerow(
        [
            "payments",
            "payment_id",
            "paid_at",
            "user_id",
            "tariff_id",
            "tariff_name",
            "provider",
            "currency",
            "amount",
        ]
    )
    for row in rows:
        amount = row.amount
        if row.provider.startswith(CRYPTO_PAY_PROVIDER):
            amount = _format_decimal(_minor_units_to_decimal(row.amount))
        writer.writerow(
            [
                "payments",
                row.payment_id,
                row.paid_at.isoformat(),
                row.user_id,
                row.tariff_id or "",
                row.tariff_name,
                row.provider,
                row.currency,
                amount,
            ]
        )

    writer.writerow([])
    writer.writerow(
        [
            "top_tariffs",
            "rank",
            "tariff_id",
            "tariff_name",
            "payment_count",
            "stars_revenue",
            "crypto_revenue",
        ]
    )
    for index, entry in enumerate(top_tariffs, start=1):
        writer.writerow(
            [
                "top_tariffs",
                index,
                entry.tariff_id or "",
                entry.tariff_name,
                entry.payment_count,
                entry.stars_revenue,
                _format_crypto_totals(entry.crypto_revenue),
            ]
        )

    return buffer.getvalue().encode("utf-8")


def build_finance_report_filename(
    *,
    period: FinancePeriodKey,
    generated_at: datetime,
) -> str:
    key = normalize_finance_period(period)
    return f"finance-report-{key}-{generated_at.strftime('%Y%m%d-%H%M%S')}.csv"


def normalize_finance_period(value: str | FinancePeriodKey) -> FinancePeriodKey:
    normalized = str(value).strip().lower()
    if normalized not in FINANCE_PERIODS:
        raise ValueError(f"Unsupported finance period: {value}")
    return normalized  # type: ignore[return-value]


async def _load_paid_payment_rows(session: AsyncSession) -> list[FinancePaymentRow]:
    result = await session.execute(
        select(
            Payment.id,
            Payment.user_id,
            Payment.tariff_id,
            Tariff.name,
            Payment.provider,
            Payment.currency,
            Payment.amount,
            Payment.paid_at,
        )
        .outerjoin(Tariff, Payment.tariff_id == Tariff.id)
        .where(Payment.status == "paid")
        .where(Payment.paid_at.is_not(None))
        .order_by(Payment.paid_at.desc(), Payment.id.desc())
    )
    rows: list[FinancePaymentRow] = []
    for payment_id, user_id, tariff_id, tariff_name, provider, currency, amount, paid_at in result.all():
        if paid_at is None:
            continue
        rows.append(
            FinancePaymentRow(
                payment_id=payment_id,
                user_id=user_id,
                tariff_id=tariff_id,
                tariff_name=tariff_name or _tariff_fallback_name(tariff_id),
                provider=provider,
                currency=currency,
                amount=int(amount),
                paid_at=ensure_aware_utc(paid_at),
            )
        )
    return rows


async def _load_crypto_invoice_counts(
    session: AsyncSession,
    *,
    now: datetime,
) -> tuple[int, int]:
    rows = list((await session.execute(select(CryptoInvoice.status, CryptoInvoice.expires_at))).all())
    unpaid = 0
    expired = 0
    for status, expires_at in rows:
        normalized_status = (status or "").lower()
        aware_expires_at = ensure_aware_utc(expires_at) if expires_at is not None else None
        if normalized_status == "paid":
            continue
        if normalized_status == "expired" or (
            aware_expires_at is not None and aware_expires_at <= now
        ):
            expired += 1
            continue
        unpaid += 1
    return unpaid, expired


async def _count_refunds(session: AsyncSession) -> int:
    value = (await session.execute(select(func.count(Payment.id)).where(Payment.status == "refunded"))).scalar_one()
    return int(value or 0)


async def _count_audit_action(session: AsyncSession, action: str) -> int:
    value = (await session.execute(select(func.count(AuditLog.id)).where(AuditLog.action == action))).scalar_one()
    return int(value or 0)


async def _count_promo_free_days(session: AsyncSession) -> int:
    value = (
        await session.execute(
            select(func.count(PromoRedemption.id))
            .join(PromoCode, PromoRedemption.promo_code_id == PromoCode.id)
            .where(PromoRedemption.status == "consumed")
            .where(PromoCode.promo_type == "free_days")
        )
    ).scalar_one()
    return int(value or 0)


async def _count_referral_rewards(session: AsyncSession) -> int:
    value = (
        await session.execute(
            select(func.count(User.id)).where(User.referral_reward_granted_at.is_not(None))
        )
    ).scalar_one()
    return int(value or 0)


def _build_top_tariffs(rows: list[FinancePaymentRow]) -> list[TopTariffEntry]:
    grouped: dict[tuple[int | None, str], dict[str, object]] = {}
    for row in rows:
        key = (row.tariff_id, row.tariff_name)
        if key not in grouped:
            grouped[key] = {
                "payment_count": 0,
                "stars_revenue": 0,
                "crypto_revenue": defaultdict(Decimal),
            }
        bucket = grouped[key]
        bucket["payment_count"] = int(bucket["payment_count"]) + 1
        if row.provider == STARS_PROVIDER:
            bucket["stars_revenue"] = int(bucket["stars_revenue"]) + row.amount
        elif row.provider.startswith(CRYPTO_PAY_PROVIDER):
            crypto_revenue = bucket["crypto_revenue"]
            crypto_revenue[row.currency] += _minor_units_to_decimal(row.amount)

    entries: list[TopTariffEntry] = []
    for (tariff_id, tariff_name), bucket in grouped.items():
        crypto_revenue = {
            currency: amount
            for currency, amount in dict(bucket["crypto_revenue"]).items()
        }
        entries.append(
            TopTariffEntry(
                tariff_id=tariff_id,
                tariff_name=tariff_name,
                payment_count=int(bucket["payment_count"]),
                stars_revenue=int(bucket["stars_revenue"]),
                crypto_revenue=crypto_revenue,
            )
        )

    entries.sort(
        key=lambda item: (
            -item.payment_count,
            -item.stars_revenue,
            -sum(item.crypto_revenue.values(), ZERO_DECIMAL),
            item.tariff_name.lower(),
        )
    )
    return entries[:5]


def _period_starts(now: datetime) -> dict[FinancePeriodKey, datetime | None]:
    today_start = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        PERIOD_DAY: today_start,
        PERIOD_WEEK: now - timedelta(days=7),
        PERIOD_MONTH: now - timedelta(days=30),
        PERIOD_ALL: None,
    }


def _filter_payments_for_period(
    rows: list[FinancePaymentRow],
    now: datetime,
    period: FinancePeriodKey,
) -> list[FinancePaymentRow]:
    cutoff = _period_starts(now)[period]
    if cutoff is None:
        return list(rows)
    return [row for row in rows if row.paid_at >= cutoff]


def _minor_units_to_decimal(value: int) -> Decimal:
    return (Decimal(value) / MINOR_UNITS_MULTIPLIER).quantize(DECIMAL_QUANT, rounding=ROUND_HALF_UP)


def _average_from_int(amount: int, count: int) -> Decimal:
    if count <= 0:
        return ZERO_DECIMAL
    return (Decimal(amount) / Decimal(count)).quantize(DECIMAL_QUANT, rounding=ROUND_HALF_UP)


def _average_from_decimal(amount: Decimal, count: int) -> Decimal:
    if count <= 0:
        return ZERO_DECIMAL
    return (amount / Decimal(count)).quantize(DECIMAL_QUANT, rounding=ROUND_HALF_UP)


def _format_crypto_totals(values: dict[str, Decimal]) -> str:
    if not values:
        return "0"
    return " \u2022 ".join(
        f"{_format_decimal(amount)} {currency}"
        for currency, amount in sorted(values.items())
    )


def _format_decimal(value: Decimal) -> str:
    normalized = value.quantize(DECIMAL_QUANT, rounding=ROUND_HALF_UP)
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return format(normalized.normalize(), "f")


def _tariff_fallback_name(tariff_id: int | None) -> str:
    if tariff_id is None:
        return "\u0411\u0435\u0437 \u0442\u0430\u0440\u0438\u0444\u0430"
    return f"\u0422\u0430\u0440\u0438\u0444 #{tariff_id}"
