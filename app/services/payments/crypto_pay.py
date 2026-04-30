# ruff: noqa: E501
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import CryptoInvoice, Payment, Subscription, Tariff
from app.db.repositories.crypto_invoices import CryptoInvoiceRepository
from app.db.repositories.payments import PaymentRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.tariffs import TariffRepository
from app.services.audit import write_audit_log
from app.services.referral_service import (
    consume_pending_referral_reward_days,
    get_pending_referral_reward_days,
    grant_referral_reward_for_first_payment,
)
from app.services.subscriptions import activate_or_extend_subscription
from app.utils.datetime import ensure_aware_utc, utcnow
from app.utils.encoding import safe_ui_text

logger = logging.getLogger(__name__)

CRYPTO_PAY_PROVIDER = "crypto_pay"
CRYPTO_PAY_TESTNET_BASE_URL = "https://testnet-pay.crypt.bot/api/"
CRYPTO_PAY_MAINNET_BASE_URL = "https://pay.crypt.bot/api/"
CRYPTO_PAY_INVOICE_CHARGE_PREFIX = "crypto:invoice:"
DEFAULT_CRYPTO_INVOICE_TTL_SECONDS = 3600
MINOR_UNITS_MULTIPLIER = Decimal("100")


class CryptoPayError(ValueError):
    """Raised when Crypto Pay processing fails."""


class CryptoPayDisabledError(CryptoPayError):
    """Raised when optional Crypto Pay payments are disabled."""


@dataclass(slots=True)
class CryptoPayInvoice:
    invoice_id: str
    asset: str
    amount: Decimal
    invoice_url: str | None
    status: str
    payload: str | None
    fiat_currency: str | None
    expires_at: datetime | None
    paid_at: datetime | None
    raw_payload: dict[str, Any]


@dataclass(slots=True)
class CryptoInvoiceCreationResult:
    invoice: CryptoInvoice
    remote_invoice: CryptoPayInvoice
    is_reused: bool


@dataclass(slots=True)
class CryptoInvoiceSyncResult:
    invoice: CryptoInvoice
    payment: Payment | None
    subscription: Subscription | None
    is_duplicate: bool
    is_paid: bool
    is_extension: bool


@dataclass(slots=True)
class CryptoReconciliationResult:
    processed_count: int
    paid_count: int
    expired_count: int
    active_invoice_count: int


class CryptoPayClientProtocol(Protocol):
    async def create_invoice(self, **kwargs) -> CryptoPayInvoice: ...

    async def get_invoice(self, invoice_id: str) -> CryptoPayInvoice | None: ...


class CryptoPayHTTPClient:
    def __init__(self, *, token: str, testnet: bool = True, timeout: float = 10.0) -> None:
        self._token = token
        self._timeout = timeout
        self._base_url = CRYPTO_PAY_TESTNET_BASE_URL if testnet else CRYPTO_PAY_MAINNET_BASE_URL

    @classmethod
    def from_settings(cls, settings: Settings) -> CryptoPayHTTPClient:
        if not settings.crypto_pay_enabled:
            raise CryptoPayDisabledError("\u041e\u043f\u043b\u0430\u0442\u0430 \u0447\u0435\u0440\u0435\u0437 Crypto Pay \u043e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u0430.")
        if settings.crypto_pay_token is None or not settings.crypto_pay_token.get_secret_value().strip():
            raise CryptoPayError("\u041d\u0435 \u0437\u0430\u0434\u0430\u043d \u0442\u043e\u043a\u0435\u043d Crypto Pay.")
        return cls(
            token=settings.crypto_pay_token.get_secret_value(),
            testnet=settings.crypto_pay_testnet,
        )

    async def create_invoice(self, **kwargs) -> CryptoPayInvoice:
        payload = {key: value for key, value in kwargs.items() if value is not None}
        data = await self._request("createInvoice", payload)
        return _invoice_from_api_payload(data)

    async def get_invoice(self, invoice_id: str) -> CryptoPayInvoice | None:
        data = await self._request("getInvoices", {"invoice_ids": invoice_id, "count": 1})
        items = data if isinstance(data, list) else data.get("items") or data.get("invoices") or []
        if not items:
            return None
        return _invoice_from_api_payload(items[0])

    async def _request(self, method: str, payload: dict[str, Any]) -> Any:
        return await asyncio.to_thread(self._request_sync, method, payload)

    def _request_sync(self, method: str, payload: dict[str, Any]) -> Any:
        url = self._base_url + method
        encoded = urlencode({key: _stringify_payload_value(value) for key, value in payload.items()}).encode("utf-8")
        request = Request(
            url,
            data=encoded,
            headers={
                "Crypto-Pay-API-Token": self._token,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise CryptoPayError(f"Crypto Pay HTTP error {exc.code}: {detail}") from exc
        except URLError as exc:
            raise CryptoPayError(f"Crypto Pay connection failed: {exc.reason}") from exc

        payload_data = json.loads(body)
        if not payload_data.get("ok"):
            raise CryptoPayError(payload_data.get("error", "Crypto Pay request failed."))
        return payload_data.get("result")


def build_crypto_invoice_payload(user_id: int, tariff_id: int, *, at_time: datetime) -> str:
    return f"crypto:tariff:{tariff_id}:user:{user_id}:ts:{int(at_time.timestamp())}"


def verify_crypto_pay_webhook_signature(
    token: str,
    body: str | bytes,
    signature: str | None,
) -> bool:
    if not signature:
        return False
    body_bytes = body if isinstance(body, bytes) else body.encode("utf-8")
    secret = hashlib.sha256(token.encode("utf-8")).digest()
    digest = hmac.new(secret, body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


async def create_crypto_invoice(
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: int,
    tariff: Tariff,
    client: CryptoPayClientProtocol | None = None,
    now: datetime | None = None,
) -> CryptoInvoiceCreationResult:
    if not settings.crypto_pay_enabled:
        raise CryptoPayDisabledError("\u041e\u043f\u043b\u0430\u0442\u0430 \u0447\u0435\u0440\u0435\u0437 Crypto Pay \u043e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u0430.")
    if tariff.price_crypto is None or tariff.price_crypto <= 0:
        raise CryptoPayError("\u0414\u043b\u044f \u044d\u0442\u043e\u0433\u043e \u0442\u0430\u0440\u0438\u0444\u0430 \u043d\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043d\u0430 \u0446\u0435\u043d\u0430 \u0432 Crypto Pay.")

    current_time = ensure_aware_utc(now or utcnow())
    repository = CryptoInvoiceRepository(session)
    reusable = await repository.get_reusable_active_for_user_tariff(
        user_id,
        tariff.id,
        at_time=current_time,
    )
    if reusable is not None:
        remote = CryptoPayInvoice(
            invoice_id=reusable.external_id,
            asset=reusable.asset,
            amount=Decimal(reusable.amount),
            invoice_url=reusable.invoice_url,
            status=reusable.status,
            payload=reusable.external_id,
            fiat_currency=reusable.fiat_currency,
            expires_at=reusable.expires_at,
            paid_at=reusable.paid_at,
            raw_payload=_load_raw_payload(reusable.raw_payload),
        )
        return CryptoInvoiceCreationResult(invoice=reusable, remote_invoice=remote, is_reused=True)

    crypto_client = client or CryptoPayHTTPClient.from_settings(settings)
    asset = _resolve_crypto_asset(settings)
    remote_invoice = await crypto_client.create_invoice(
        asset=asset,
        amount=str(Decimal(tariff.price_crypto)),
        description=_build_crypto_invoice_description(tariff),
        payload=build_crypto_invoice_payload(user_id, tariff.id, at_time=current_time),
        expires_in=DEFAULT_CRYPTO_INVOICE_TTL_SECONDS,
        allow_comments=False,
        allow_anonymous=False,
    )
    invoice = await repository.create(
        user_id=user_id,
        tariff_id=tariff.id,
        external_id=remote_invoice.invoice_id,
        asset=remote_invoice.asset,
        amount=remote_invoice.amount,
        fiat_currency=remote_invoice.fiat_currency,
        invoice_url=remote_invoice.invoice_url,
        status=remote_invoice.status,
        expires_at=remote_invoice.expires_at,
        raw_payload=json.dumps(remote_invoice.raw_payload, ensure_ascii=False, sort_keys=True),
    )
    return CryptoInvoiceCreationResult(
        invoice=invoice,
        remote_invoice=remote_invoice,
        is_reused=False,
    )


async def sync_crypto_invoice(
    session: AsyncSession,
    settings: Settings,
    *,
    invoice: CryptoInvoice,
    tariff: Tariff,
    client: CryptoPayClientProtocol | None = None,
    remote_invoice: CryptoPayInvoice | None = None,
    now: datetime | None = None,
) -> CryptoInvoiceSyncResult:
    current_time = ensure_aware_utc(now or utcnow())
    crypto_client = client or CryptoPayHTTPClient.from_settings(settings)
    remote = remote_invoice or await crypto_client.get_invoice(invoice.external_id)
    if remote is None:
        raise CryptoPayError(f"Crypto invoice {invoice.external_id} was not found in Crypto Pay.")

    invoice.asset = remote.asset
    invoice.amount = remote.amount
    invoice.fiat_currency = remote.fiat_currency
    invoice.invoice_url = remote.invoice_url
    invoice.status = remote.status
    invoice.expires_at = remote.expires_at
    invoice.paid_at = remote.paid_at if remote.status == "paid" else invoice.paid_at
    invoice.raw_payload = json.dumps(remote.raw_payload, ensure_ascii=False, sort_keys=True)

    if remote.status == "expired":
        await write_audit_log(
            session,
            action="invoice_expired_crypto",
            target_user_id=invoice.user_id,
            payload={
                "crypto_invoice_id": invoice.id,
                "external_id": invoice.external_id,
            },
        )
        return CryptoInvoiceSyncResult(
            invoice=invoice,
            payment=None,
            subscription=None,
            is_duplicate=False,
            is_paid=False,
            is_extension=False,
        )

    if remote.status != "paid":
        return CryptoInvoiceSyncResult(
            invoice=invoice,
            payment=None,
            subscription=None,
            is_duplicate=False,
            is_paid=False,
            is_extension=False,
        )

    payment_repository = PaymentRepository(session)
    charge_id = f"{CRYPTO_PAY_INVOICE_CHARGE_PREFIX}{invoice.external_id}"
    existing_payment = await payment_repository.get_by_telegram_charge_id(charge_id)
    if existing_payment is not None:
        subscription = await SubscriptionRepository(session).get_latest_for_user_channel(
            invoice.user_id,
            tariff.channel_id,
        )
        return CryptoInvoiceSyncResult(
            invoice=invoice,
            payment=existing_payment,
            subscription=subscription,
            is_duplicate=True,
            is_paid=True,
            is_extension=False,
        )

    paid_at = remote.paid_at or current_time
    referral_bonus_days = await get_pending_referral_reward_days(session, user_id=invoice.user_id)
    duration_override = tariff.duration_days + referral_bonus_days if referral_bonus_days > 0 else None
    subscription_change = await activate_or_extend_subscription(
        session,
        user_id=invoice.user_id,
        tariff=tariff,
        paid_at=paid_at,
        source="crypto_pay",
        duration_days_override=duration_override,
    )
    payment = await payment_repository.create_paid(
        user_id=invoice.user_id,
        tariff_id=invoice.tariff_id,
        channel_id=tariff.channel_id,
        amount=_decimal_to_minor_units(remote.amount),
        currency=remote.asset,
        provider=CRYPTO_PAY_PROVIDER,
        telegram_payment_charge_id=charge_id,
        provider_payment_charge_id=invoice.external_id,
        invoice_payload=remote.payload or invoice.external_id,
        raw_payload=json.dumps(remote.raw_payload, ensure_ascii=False, sort_keys=True),
        paid_at=paid_at,
    )
    if referral_bonus_days > 0:
        await consume_pending_referral_reward_days(
            session,
            user_id=invoice.user_id,
            payment=payment,
            consumed_days=referral_bonus_days,
            consumed_at=paid_at,
        )
    await grant_referral_reward_for_first_payment(
        session,
        referred_user_id=invoice.user_id,
        payment=payment,
        reward_days=settings.referral_reward_days,
        paid_at=paid_at,
    )
    invoice.paid_at = paid_at
    invoice.status = "paid"
    await write_audit_log(
        session,
        action="payment_paid_crypto",
        target_user_id=invoice.user_id,
        payload={
            "crypto_invoice_id": invoice.id,
            "external_id": invoice.external_id,
            "tariff_id": invoice.tariff_id,
            "asset": remote.asset,
            "amount": str(remote.amount),
        },
    )
    return CryptoInvoiceSyncResult(
        invoice=invoice,
        payment=payment,
        subscription=subscription_change.subscription,
        is_duplicate=False,
        is_paid=True,
        is_extension=subscription_change.is_extension,
    )


async def reconcile_active_crypto_invoices(
    session: AsyncSession,
    settings: Settings,
    *,
    client: CryptoPayClientProtocol | None = None,
    now: datetime | None = None,
    limit: int = 50,
) -> CryptoReconciliationResult:
    if not settings.crypto_pay_enabled:
        return CryptoReconciliationResult(0, 0, 0, 0)

    current_time = ensure_aware_utc(now or utcnow())
    repository = CryptoInvoiceRepository(session)
    invoices = await repository.list_for_reconciliation(at_time=current_time, limit=limit)
    if not invoices:
        return CryptoReconciliationResult(0, 0, 0, 0)

    processed = 0
    paid = 0
    expired = 0
    client_instance = client or CryptoPayHTTPClient.from_settings(settings)

    for invoice in invoices:
        tariff = await TariffRepository(session).get_by_id(invoice.tariff_id)
        if tariff is None:
            continue
        result = await sync_crypto_invoice(
            session,
            settings,
            invoice=invoice,
            tariff=tariff,
            client=client_instance,
            now=current_time,
        )
        processed += 1
        if result.is_paid and not result.is_duplicate:
            paid += 1
        if result.invoice.status == "expired":
            expired += 1

    if processed:
        await session.commit()

    return CryptoReconciliationResult(
        processed_count=processed,
        paid_count=paid,
        expired_count=expired,
        active_invoice_count=sum(1 for invoice in invoices if invoice.status == "active"),
    )


async def process_crypto_pay_webhook_update(
    session: AsyncSession,
    settings: Settings,
    *,
    update_payload: dict[str, Any],
    client: CryptoPayClientProtocol | None = None,
    now: datetime | None = None,
) -> CryptoInvoiceSyncResult | None:
    if update_payload.get("update_type") != "invoice_paid":
        return None

    invoice_payload = update_payload.get("payload")
    if not isinstance(invoice_payload, dict):
        raise CryptoPayError("Crypto Pay webhook payload is invalid.")

    remote_invoice = _invoice_from_api_payload(invoice_payload)
    local_invoice = await CryptoInvoiceRepository(session).get_by_external_id(remote_invoice.invoice_id)
    if local_invoice is None:
        raise CryptoPayError(f"Unknown crypto invoice: {remote_invoice.invoice_id}")

    tariff = await TariffRepository(session).get_by_id(local_invoice.tariff_id)
    if tariff is None:
        raise CryptoPayError(f"Tariff {local_invoice.tariff_id} not found for crypto invoice.")

    return await sync_crypto_invoice(
        session,
        settings,
        invoice=local_invoice,
        tariff=tariff,
        client=client,
        remote_invoice=remote_invoice,
        now=now,
    )


def _build_crypto_invoice_description(tariff: Tariff) -> str:
    channel_title = safe_ui_text(
        tariff.channel.title if tariff.channel is not None else None,
        "\u043f\u0440\u0438\u0432\u0430\u0442\u043d\u044b\u0439 \u043a\u0430\u043d\u0430\u043b",
    )
    return (
        f"\u0414\u043e\u0441\u0442\u0443\u043f \u043d\u0430 {tariff.duration_days} \u0434\u043d\u0435\u0439 \u0432 {channel_title}. "
        "\u041f\u043e\u0441\u043b\u0435 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u044f \u043e\u043f\u043b\u0430\u0442\u044b \u0432 Crypto Pay \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0430 \u0430\u043a\u0442\u0438\u0432\u0438\u0440\u0443\u0435\u0442\u0441\u044f \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438."
    )[:1024]


def _resolve_crypto_asset(settings: Settings) -> str:
    if settings.crypto_pay_accepted_assets:
        return settings.crypto_pay_accepted_assets[0].upper()
    return "USDT"


def _invoice_from_api_payload(data: dict[str, Any]) -> CryptoPayInvoice:
    invoice_url = (
        data.get("bot_invoice_url")
        or data.get("mini_app_invoice_url")
        or data.get("web_app_invoice_url")
        or data.get("pay_url")
    )
    return CryptoPayInvoice(
        invoice_id=str(data.get("invoice_id")),
        asset=str(data.get("asset") or _coerce_paid_asset(data)),
        amount=Decimal(str(data.get("amount") or data.get("paid_amount") or "0")),
        invoice_url=invoice_url,
        status=str(data.get("status") or "active"),
        payload=_string_or_none(data.get("payload")),
        fiat_currency=_string_or_none(data.get("fiat")),
        expires_at=_parse_api_datetime(data.get("expiration_date")),
        paid_at=_parse_api_datetime(data.get("paid_at")),
        raw_payload=dict(data),
    )


def _coerce_paid_asset(data: dict[str, Any]) -> str:
    return str(data.get("paid_asset") or data.get("accepted_assets") or "USDT").split(",", maxsplit=1)[0]


def _parse_api_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return ensure_aware_utc(datetime.fromisoformat(normalized))


def _decimal_to_minor_units(value: Decimal) -> int:
    scaled = (value * MINOR_UNITS_MULTIPLIER).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(scaled)


def _load_raw_payload(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _stringify_payload_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)