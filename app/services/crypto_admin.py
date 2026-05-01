# ruff: noqa: E501
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Literal

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import CryptoInvoice, Payment, Tariff, User
from app.db.repositories.crypto_invoices import CryptoInvoiceRepository
from app.db.repositories.payments import PaymentRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.tariffs import TariffRepository
from app.db.repositories.users import UserRepository
from app.runtime_state import snapshot_runtime_state
from app.services.payments.crypto_pay import CRYPTO_PAY_PROVIDER
from app.utils.datetime import format_datetime
from app.utils.encoding import safe_ui_text


class CryptoAdminDiagnosticError(ValueError):
    """Raised when the admin diagnostic reference cannot be resolved."""


@dataclass(frozen=True, slots=True)
class CryptoInvoiceStatusLine:
    invoice_id: int
    external_id: str
    user_id: int
    tariff_name: str
    status: str
    amount: str
    asset: str
    is_activated: bool


@dataclass(frozen=True, slots=True)
class CryptoReconciliationSummary:
    enabled: bool
    webhook_path: str
    active_count: int
    paid_activated_count: int
    paid_not_activated_count: int
    expired_count: int
    last_reconcile_at: datetime | None
    last_reconcile_processed_count: int | None
    last_reconcile_paid_count: int | None
    last_reconcile_expired_count: int | None
    last_reconcile_active_invoice_count: int | None
    last_reconcile_error_at: datetime | None
    last_reconcile_error: str | None
    recent_invoices: tuple[CryptoInvoiceStatusLine, ...]


@dataclass(frozen=True, slots=True)
class CryptoInvoiceDiagnostic:
    kind: Literal["invoice"]
    invoice_id: int
    external_id: str
    user_id: int
    user_telegram_id: int | None
    user_label: str
    tariff_name: str
    channel_reference: str
    status: str
    amount: str
    asset: str
    invoice_url: str | None
    expires_at: datetime | None
    paid_at: datetime | None
    is_activated: bool
    payment_id: int | None
    subscription_status: str | None
    subscription_expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class CryptoUserDiagnostic:
    kind: Literal["user"]
    user_id: int
    telegram_id: int
    user_label: str
    total_invoices: int
    active_count: int
    paid_count: int
    expired_count: int
    recent_invoices: tuple[CryptoInvoiceStatusLine, ...]


CryptoDiagnosticReport = CryptoInvoiceDiagnostic | CryptoUserDiagnostic


async def build_crypto_reconciliation_summary(
    session: AsyncSession,
    settings: Settings,
) -> CryptoReconciliationSummary:
    active_count = await _count_invoices(session, CryptoInvoice.status == "active")
    expired_count = await _count_invoices(session, CryptoInvoice.status == "expired")

    payment_exists = exists(
        select(Payment.id)
        .where(Payment.provider == CRYPTO_PAY_PROVIDER)
        .where(Payment.provider_payment_charge_id == CryptoInvoice.external_id)
    )
    paid_activated_count = await _count_invoices(
        session,
        CryptoInvoice.status == "paid",
        payment_exists,
    )
    paid_not_activated_count = await _count_invoices(
        session,
        CryptoInvoice.status == "paid",
        ~payment_exists,
    )

    recent_invoices = await _build_recent_invoice_lines(session)
    runtime = snapshot_runtime_state()
    return CryptoReconciliationSummary(
        enabled=settings.crypto_pay_enabled,
        webhook_path=settings.crypto_pay_webhook_path,
        active_count=active_count,
        paid_activated_count=paid_activated_count,
        paid_not_activated_count=paid_not_activated_count,
        expired_count=expired_count,
        last_reconcile_at=runtime.last_crypto_reconcile_at,
        last_reconcile_processed_count=runtime.last_crypto_reconcile_processed_count,
        last_reconcile_paid_count=runtime.last_crypto_reconcile_paid_count,
        last_reconcile_expired_count=runtime.last_crypto_reconcile_expired_count,
        last_reconcile_active_invoice_count=runtime.last_crypto_reconcile_active_invoice_count,
        last_reconcile_error_at=runtime.last_crypto_reconcile_error_at,
        last_reconcile_error=runtime.last_crypto_reconcile_error,
        recent_invoices=tuple(recent_invoices),
    )


async def build_crypto_diagnostic_report(
    session: AsyncSession,
    *,
    reference: str,
) -> CryptoDiagnosticReport:
    cleaned = reference.strip()
    if not cleaned:
        raise CryptoAdminDiagnosticError(
            "\u0423\u043a\u0430\u0436\u0438 user_id, invoice_id \u0438\u043b\u0438 \u0432\u043d\u0435\u0448\u043d\u0438\u0439 invoice id."
        )

    invoice_repository = CryptoInvoiceRepository(session)
    if cleaned.isdigit():
        invoice = await invoice_repository.get_by_id(int(cleaned))
        if invoice is not None:
            return await _build_invoice_diagnostic(session, invoice)

    invoice = await invoice_repository.get_by_external_id(cleaned)
    if invoice is not None:
        return await _build_invoice_diagnostic(session, invoice)

    user = await _resolve_user(session, cleaned)
    if user is not None:
        return await _build_user_diagnostic(session, user)

    raise CryptoAdminDiagnosticError(
        "\u041d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e: \u043d\u0438 invoice, \u043d\u0438 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c."
    )


def render_crypto_reconciliation_summary(
    summary: CryptoReconciliationSummary,
    *,
    timezone: str,
) -> str:
    lines = ["\U0001FA99 Crypto Pay", ""]
    lines.append(
        f"\u0421\u0442\u0430\u0442\u0443\u0441: {'\u0432\u043a\u043b\u044e\u0447\u0451\u043d' if summary.enabled else '\u0432\u044b\u043a\u043b\u044e\u0447\u0435\u043d'}"
    )
    lines.append(f"Webhook path: <code>{escape(summary.webhook_path)}</code>")
    lines.append(f"\u23F3 \u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0435 \u0438\u043d\u0432\u043e\u0439\u0441\u044b: {summary.active_count}")
    lines.append(
        f"\u2705 \u041e\u043f\u043b\u0430\u0447\u0435\u043d\u044b \u0438 \u0430\u043a\u0442\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u043d\u044b: {summary.paid_activated_count}"
    )
    lines.append(
        f"\u26A0\uFE0F \u041e\u043f\u043b\u0430\u0447\u0435\u043d\u044b, \u043d\u043e \u043d\u0435 \u0430\u043a\u0442\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u043d\u044b: {summary.paid_not_activated_count}"
    )
    lines.append(f"\u231B \u0418\u0441\u0442\u0435\u043a\u043b\u0438: {summary.expired_count}")

    if summary.last_reconcile_at is None:
        lines.append(
            "\U0001F504 \u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0439 reconcile: \u0435\u0449\u0451 \u043d\u0435 \u0437\u0430\u043f\u0443\u0441\u043a\u0430\u043b\u0441\u044f"
        )
    else:
        stats = [
            format_datetime(summary.last_reconcile_at, timezone),
            f"processed={summary.last_reconcile_processed_count or 0}",
            f"paid={summary.last_reconcile_paid_count or 0}",
            f"expired={summary.last_reconcile_expired_count or 0}",
            f"active={summary.last_reconcile_active_invoice_count or 0}",
        ]
        lines.append(
            f"\U0001F504 \u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0439 reconcile: {' \u00B7 '.join(stats)}"
        )

    if summary.last_reconcile_error:
        error_time = (
            format_datetime(summary.last_reconcile_error_at, timezone)
            if summary.last_reconcile_error_at is not None
            else "\u043d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u043e"
        )
        lines.append(
            "\u26A0\uFE0F \u041f\u043e\u0441\u043b\u0435\u0434\u043d\u044f\u044f \u043e\u0448\u0438\u0431\u043a\u0430 reconcile: "
            f"{escape(summary.last_reconcile_error)} \u00B7 {error_time}"
        )

    if summary.recent_invoices:
        lines.extend(["", "\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u0438\u043d\u0432\u043e\u0439\u0441\u044b:"])
        for item in summary.recent_invoices:
            lines.append(
                f"{_status_icon(item.status, item.is_activated)} #{item.invoice_id} "
                f"<code>{escape(item.external_id)}</code> \u00B7 {escape(item.tariff_name)} \u00B7 "
                f"{escape(item.amount)} {escape(item.asset)}"
            )

    lines.extend(
        [
            "",
            "\u041a\u043e\u043c\u0430\u043d\u0434\u044b:",
            "/admin_crypto_invoices",
            "/admin_crypto_diag <user_id|invoice_id>",
        ]
    )
    return "\n".join(lines)


def render_crypto_diagnostic_report(report: CryptoDiagnosticReport, *, timezone: str) -> str:
    if report.kind == "invoice":
        lines = ["\U0001FA99 \u0414\u0438\u0430\u0433\u043d\u043e\u0441\u0442\u0438\u043a\u0430 crypto-\u0438\u043d\u0432\u043e\u0439\u0441\u0430", ""]
        lines.append(f"\u041b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u0439 ID: <code>{report.invoice_id}</code>")
        lines.append(f"\u0412\u043d\u0435\u0448\u043d\u0438\u0439 ID: <code>{escape(report.external_id)}</code>")
        lines.append(
            "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c: "
            f"{escape(report.user_label)} \u00B7 internal=<code>{report.user_id}</code>"
        )
        if report.user_telegram_id is not None:
            lines.append(f"Telegram ID: <code>{report.user_telegram_id}</code>")
        lines.append(f"\u0422\u0430\u0440\u0438\u0444: {escape(report.tariff_name)}")
        lines.append(f"\u041a\u0430\u043d\u0430\u043b: {escape(report.channel_reference)}")
        lines.append(
            f"\u0421\u0442\u0430\u0442\u0443\u0441: {_status_icon(report.status, report.is_activated)} {escape(report.status)}"
        )
        lines.append(f"\u0421\u0443\u043c\u043c\u0430: {escape(report.amount)} {escape(report.asset)}")
        lines.append(
            "\u0410\u043a\u0442\u0438\u0432\u0430\u0446\u0438\u044f: "
            f"{'\u2705 \u043f\u043b\u0430\u0442\u0451\u0436 \u043f\u0440\u0438\u0432\u044f\u0437\u0430\u043d' if report.is_activated else '\u26A0\uFE0F \u043f\u043b\u0430\u0442\u0451\u0436 \u043d\u0435 \u043f\u0440\u0438\u0432\u044f\u0437\u0430\u043d'}"
        )
        if report.payment_id is not None:
            lines.append(f"Payment ID: <code>{report.payment_id}</code>")
        if report.subscription_status is not None:
            lines.append(f"\u041f\u043e\u0434\u043f\u0438\u0441\u043a\u0430: {escape(report.subscription_status)}")
        if report.subscription_expires_at is not None:
            lines.append(
                f"\u041f\u043e\u0434\u043f\u0438\u0441\u043a\u0430 \u0434\u043e: {format_datetime(report.subscription_expires_at, timezone)}"
            )
        if report.paid_at is not None:
            lines.append(f"\u041e\u043f\u043b\u0430\u0447\u0435\u043d: {format_datetime(report.paid_at, timezone)}")
        if report.expires_at is not None:
            lines.append(
                f"\u0418\u043d\u0432\u043e\u0439\u0441 \u0438\u0441\u0442\u0435\u043a\u0430\u0435\u0442: {format_datetime(report.expires_at, timezone)}"
            )
        if report.invoice_url:
            lines.append(f"URL: {escape(report.invoice_url)}")
        return "\n".join(lines)

    lines = ["\U0001FA99 \u0414\u0438\u0430\u0433\u043d\u043e\u0441\u0442\u0438\u043a\u0430 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f Crypto Pay", ""]
    lines.append(f"\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c: {escape(report.user_label)}")
    lines.append(f"Internal ID: <code>{report.user_id}</code>")
    lines.append(f"Telegram ID: <code>{report.telegram_id}</code>")
    lines.append(f"\u0412\u0441\u0435\u0433\u043e \u0438\u043d\u0432\u043e\u0439\u0441\u043e\u0432: {report.total_invoices}")
    lines.append(f"\u23F3 \u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0435: {report.active_count}")
    lines.append(f"\u2705 \u041e\u043f\u043b\u0430\u0447\u0435\u043d\u043d\u044b\u0435: {report.paid_count}")
    lines.append(f"\u231B \u0418\u0441\u0442\u0435\u043a\u0448\u0438\u0435: {report.expired_count}")
    if report.recent_invoices:
        lines.extend(["", "\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u0438\u043d\u0432\u043e\u0439\u0441\u044b:"])
        for item in report.recent_invoices:
            lines.append(
                f"{_status_icon(item.status, item.is_activated)} #{item.invoice_id} "
                f"<code>{escape(item.external_id)}</code> \u00B7 {escape(item.tariff_name)} \u00B7 "
                f"{escape(item.amount)} {escape(item.asset)}"
            )
    return "\n".join(lines)


async def _build_recent_invoice_lines(
    session: AsyncSession,
    *,
    limit: int = 5,
) -> list[CryptoInvoiceStatusLine]:
    repository = CryptoInvoiceRepository(session)
    invoices = await repository.list_recent(limit=limit)
    return [await _build_invoice_status_line(session, invoice) for invoice in invoices]


async def _build_user_diagnostic(session: AsyncSession, user: User) -> CryptoUserDiagnostic:
    repository = CryptoInvoiceRepository(session)
    invoices = await repository.list_for_user(user.id, limit=10)
    lines = [await _build_invoice_status_line(session, invoice) for invoice in invoices]
    return CryptoUserDiagnostic(
        kind="user",
        user_id=user.id,
        telegram_id=user.telegram_id,
        user_label=_user_label(user),
        total_invoices=len(invoices),
        active_count=sum(1 for invoice in invoices if invoice.status == "active"),
        paid_count=sum(1 for invoice in invoices if invoice.status == "paid"),
        expired_count=sum(1 for invoice in invoices if invoice.status == "expired"),
        recent_invoices=tuple(lines),
    )


async def _build_invoice_diagnostic(
    session: AsyncSession,
    invoice: CryptoInvoice,
) -> CryptoInvoiceDiagnostic:
    user = await UserRepository(session).get_by_id(invoice.user_id)
    tariff = await _load_invoice_tariff(session, invoice)
    payment = await PaymentRepository(session).get_by_provider_charge_id(
        provider=CRYPTO_PAY_PROVIDER,
        provider_payment_charge_id=invoice.external_id,
    )
    subscription = None
    if tariff is not None:
        subscription = await SubscriptionRepository(session).get_latest_for_user_channel(
            invoice.user_id,
            tariff.channel_id,
        )

    tariff_name = safe_ui_text(
        tariff.name if tariff is not None else None,
        f"\u0422\u0430\u0440\u0438\u0444 #{invoice.tariff_id}",
    )
    channel_reference = (
        safe_ui_text(
            tariff.channel.title if tariff is not None and tariff.channel is not None else None,
            f"channel_id={tariff.channel_id}",
        )
        if tariff is not None
        else "\u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d"
    )
    return CryptoInvoiceDiagnostic(
        kind="invoice",
        invoice_id=invoice.id,
        external_id=invoice.external_id,
        user_id=invoice.user_id,
        user_telegram_id=user.telegram_id if user is not None else None,
        user_label=_user_label(user),
        tariff_name=tariff_name,
        channel_reference=channel_reference,
        status=invoice.status,
        amount=str(invoice.amount),
        asset=invoice.asset,
        invoice_url=invoice.invoice_url,
        expires_at=invoice.expires_at,
        paid_at=invoice.paid_at,
        is_activated=payment is not None,
        payment_id=payment.id if payment is not None else None,
        subscription_status=subscription.status if subscription is not None else None,
        subscription_expires_at=subscription.expires_at if subscription is not None else None,
    )


async def _build_invoice_status_line(
    session: AsyncSession,
    invoice: CryptoInvoice,
) -> CryptoInvoiceStatusLine:
    tariff = await _load_invoice_tariff(session, invoice)
    payment = await PaymentRepository(session).get_by_provider_charge_id(
        provider=CRYPTO_PAY_PROVIDER,
        provider_payment_charge_id=invoice.external_id,
    )
    tariff_name = safe_ui_text(
        tariff.name if tariff is not None else None,
        f"\u0422\u0430\u0440\u0438\u0444 #{invoice.tariff_id}",
    )
    return CryptoInvoiceStatusLine(
        invoice_id=invoice.id,
        external_id=invoice.external_id,
        user_id=invoice.user_id,
        tariff_name=tariff_name,
        status=invoice.status,
        amount=str(invoice.amount),
        asset=invoice.asset,
        is_activated=payment is not None,
    )


async def _load_invoice_tariff(session: AsyncSession, invoice: CryptoInvoice) -> Tariff | None:
    if invoice.tariff_id is None:
        return None
    return await TariffRepository(session).get_by_id(invoice.tariff_id)


async def _resolve_user(session: AsyncSession, reference: str) -> User | None:
    repository = UserRepository(session)
    if reference.isdigit():
        numeric = int(reference)
        user = await repository.get_by_id(numeric)
        if user is not None:
            return user
        return await repository.get_by_telegram_id(numeric)
    return None


async def _count_invoices(session: AsyncSession, *conditions) -> int:
    result = await session.execute(select(func.count(CryptoInvoice.id)).where(*conditions))
    value = result.scalar_one()
    return int(value or 0)


def _status_icon(status: str, is_activated: bool) -> str:
    if status == "paid" and is_activated:
        return "\u2705"
    if status == "paid":
        return "\u26A0\uFE0F"
    if status == "expired":
        return "\u231B"
    if status == "active":
        return "\u23F3"
    return "\u2139\uFE0F"


def _user_label(user: User | None) -> str:
    if user is None:
        return "\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d"
    parts = [safe_ui_text(user.first_name, "\u0411\u0435\u0437 \u0438\u043c\u0435\u043d\u0438")]
    if user.username:
        parts.append(f"@{user.username.lstrip('@')}")
    return " ".join(parts)
