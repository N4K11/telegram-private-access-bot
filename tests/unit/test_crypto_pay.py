from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.user import user_tariff_detail_keyboard
from app.config import Settings
from app.db.base import Base
from app.db.models import Channel, CryptoInvoice, Payment, Subscription, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.services.payments.crypto_pay import (
    CryptoPayDisabledError,
    CryptoPayInvoice,
    create_crypto_invoice,
    reconcile_active_crypto_invoices,
    sync_crypto_invoice,
)


class FakeCryptoClient:
    def __init__(
        self,
        *,
        create_response: CryptoPayInvoice | None = None,
        invoice_responses: dict[str, CryptoPayInvoice] | None = None,
    ) -> None:
        self.create_response = create_response
        self.invoice_responses = invoice_responses or {}
        self.create_calls: list[dict[str, object]] = []
        self.lookup_calls: list[str] = []

    async def create_invoice(self, **kwargs) -> CryptoPayInvoice:
        self.create_calls.append(kwargs)
        if self.create_response is None:
            raise AssertionError("create_response is not configured")
        return self.create_response

    async def get_invoice(self, invoice_id: str) -> CryptoPayInvoice | None:
        self.lookup_calls.append(invoice_id)
        return self.invoice_responses.get(invoice_id)


async def _create_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    session = session_factory()
    session._test_engine = engine  # type: ignore[attr-defined]
    return session


async def _close_session(session: AsyncSession) -> None:
    engine = session._test_engine  # type: ignore[attr-defined]
    await session.close()
    await engine.dispose()


async def _seed_user_channel_tariff(session: AsyncSession) -> tuple[User, Channel, Tariff]:
    user = User(telegram_id=42, first_name="Anna", is_admin=False, role="user")
    channel = Channel(
        telegram_chat_id=-1001234567890,
        title="Main channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add_all([user, channel])
    await session.flush()

    tariff = Tariff(
        name="VIP 30",
        price_stars=250,
        price_crypto=Decimal("1.25"),
        duration_days=30,
        sort_order=10,
        is_active=True,
        channel_id=channel.id,
    )
    session.add(tariff)
    await session.commit()
    return user, channel, tariff


def _settings(*, enabled: bool) -> Settings:
    return Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [42],
            "crypto_pay_enabled": enabled,
            "crypto_pay_token": "crypto-token",
            "crypto_pay_testnet": True,
            "crypto_pay_accepted_assets": ["TON", "USDT"],
        }
    )


def _remote_invoice(
    *,
    invoice_id: str,
    status: str,
    amount: str = "1.25",
    paid_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> CryptoPayInvoice:
    return CryptoPayInvoice(
        invoice_id=invoice_id,
        asset="TON",
        amount=Decimal(amount),
        invoice_url=f"https://pay.example/{invoice_id}",
        status=status,
        payload=f"payload:{invoice_id}",
        fiat_currency=None,
        expires_at=expires_at,
        paid_at=paid_at,
        raw_payload={"invoice_id": invoice_id, "status": status},
    )


def _button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


async def test_crypto_invoice_creation_rejects_when_disabled() -> None:
    session = await _create_session()
    try:
        user, _, tariff = await _seed_user_channel_tariff(session)
        disabled_settings = _settings(enabled=False)
        disabled_client = FakeCryptoClient(
            create_response=_remote_invoice(invoice_id="1", status="active")
        )

        with pytest.raises(CryptoPayDisabledError):
            await create_crypto_invoice(
                session,
                disabled_settings,
                user_id=user.id,
                tariff=tariff,
                client=disabled_client,
            )
    finally:
        await _close_session(session)


async def test_active_crypto_invoice_does_not_activate_before_payment() -> None:
    session = await _create_session()
    try:
        user, _, tariff = await _seed_user_channel_tariff(session)
        current_time = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
        remote = _remote_invoice(
            invoice_id="101",
            status="active",
            expires_at=current_time + timedelta(hours=1),
        )
        client = FakeCryptoClient(
            create_response=remote,
            invoice_responses={remote.invoice_id: remote},
        )

        created = await create_crypto_invoice(
            session,
            _settings(enabled=True),
            user_id=user.id,
            tariff=tariff,
            client=client,
            now=current_time,
        )
        await session.commit()

        result = await sync_crypto_invoice(
            session,
            _settings(enabled=True),
            invoice=created.invoice,
            tariff=tariff,
            client=client,
            now=current_time + timedelta(minutes=10),
        )
        await session.commit()

        payments = list((await session.execute(select(Payment))).scalars())
        subscriptions = list((await session.execute(select(Subscription))).scalars())

        assert result.is_paid is False
        assert payments == []
        assert subscriptions == []
        assert created.invoice.status == "active"
    finally:
        await _close_session(session)


async def test_paid_crypto_invoice_is_idempotent_and_activates_subscription() -> None:
    session = await _create_session()
    try:
        user, _, tariff = await _seed_user_channel_tariff(session)
        created_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
        active = _remote_invoice(
            invoice_id="202",
            status="active",
            expires_at=created_at + timedelta(hours=1),
        )
        paid = _remote_invoice(
            invoice_id="202",
            status="paid",
            paid_at=created_at + timedelta(minutes=5),
            expires_at=created_at + timedelta(hours=1),
        )
        client = FakeCryptoClient(
            create_response=active,
            invoice_responses={active.invoice_id: paid},
        )

        created = await create_crypto_invoice(
            session,
            _settings(enabled=True),
            user_id=user.id,
            tariff=tariff,
            client=client,
            now=created_at,
        )
        await session.commit()

        first = await sync_crypto_invoice(
            session,
            _settings(enabled=True),
            invoice=created.invoice,
            tariff=tariff,
            client=client,
            now=created_at + timedelta(minutes=5),
        )
        await session.commit()
        first_expires_at = first.subscription.expires_at if first.subscription is not None else None

        second = await sync_crypto_invoice(
            session,
            _settings(enabled=True),
            invoice=created.invoice,
            tariff=tariff,
            client=client,
            now=created_at + timedelta(minutes=6),
        )
        await session.commit()

        payments = list((await session.execute(select(Payment))).scalars())
        subscriptions = list((await session.execute(select(Subscription))).scalars())

        assert first.is_paid is True
        assert first.is_duplicate is False
        assert second.is_duplicate is True
        assert len(payments) == 1
        assert len(subscriptions) == 1
        assert second.subscription is not None
        assert second.subscription.expires_at == first_expires_at
        assert created.invoice.status == "paid"
    finally:
        await _close_session(session)


async def test_reconciliation_marks_expired_invoice() -> None:
    session = await _create_session()
    try:
        user, _, tariff = await _seed_user_channel_tariff(session)
        created_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
        active = _remote_invoice(
            invoice_id="303",
            status="active",
            expires_at=created_at + timedelta(hours=1),
        )
        expired = _remote_invoice(
            invoice_id="303",
            status="expired",
            expires_at=created_at + timedelta(hours=1),
        )
        client = FakeCryptoClient(
            create_response=active,
            invoice_responses={active.invoice_id: expired},
        )

        created = await create_crypto_invoice(
            session,
            _settings(enabled=True),
            user_id=user.id,
            tariff=tariff,
            client=client,
            now=created_at,
        )
        await session.commit()

        result = await reconcile_active_crypto_invoices(
            session,
            _settings(enabled=True),
            client=client,
            now=created_at + timedelta(minutes=30),
        )

        refreshed = await session.get(CryptoInvoice, created.invoice.id)
        payments = list((await session.execute(select(Payment))).scalars())

        assert result.processed_count == 1
        assert result.expired_count == 1
        assert refreshed is not None
        assert refreshed.status == "expired"
        assert payments == []
    finally:
        await _close_session(session)


def test_user_tariff_detail_keyboard_hides_crypto_by_default() -> None:
    default_markup = user_tariff_detail_keyboard(10)
    crypto_markup = user_tariff_detail_keyboard(10, include_crypto=True)

    assert _button_texts(default_markup) == [
        "в­ђ РћРїР»Р°С‚РёС‚СЊ Stars",
        "РќР°Р·Р°Рґ",
        "Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ",
    ]
    assert _button_texts(crypto_markup)[0:2] == [
        "в­ђ РћРїР»Р°С‚РёС‚СЊ Stars",
        "в‚ї Crypto Pay",
    ]