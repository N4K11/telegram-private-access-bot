# ruff: noqa: E501
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.routers.admin.crypto import (
    admin_crypto_dashboard,
    admin_crypto_diag,
    admin_crypto_invoices,
)
from app.config import Settings
from app.db.base import Base
from app.db.models import Channel, CryptoInvoice, Payment, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.runtime_state import record_crypto_reconcile_run, reset_runtime_state


class DummyUser:
    def __init__(self, user_id: int = 755815181, first_name: str = "Admin") -> None:
        self.id = user_id
        self.first_name = first_name
        self.username = "admin"
        self.last_name = None
        self.language_code = "ru"


class DummyMessage:
    def __init__(self, text: str | None = None) -> None:
        self.text = text
        self.from_user = DummyUser()
        self.answer_calls: list[tuple[str, object | None]] = []
        self.edit_calls: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edit_calls.append((text, reply_markup))


class DummyCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = DummyMessage()
        self.from_user = DummyUser()
        self.answer_count = 0

    async def answer(self, *args, **kwargs) -> None:
        self.answer_count += 1


@pytest.fixture(autouse=True)
def runtime_state_fixture() -> AsyncIterator[None]:
    reset_runtime_state()
    yield
    reset_runtime_state()


@pytest.fixture
async def session() -> AsyncIterator[tuple[AsyncSession, int]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        user = User(telegram_id=42, first_name="Anna", is_admin=False, role="user")
        db_session.add(user)
        await db_session.flush()

        channel = Channel(
            telegram_chat_id=-1001234567890,
            title="пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ",
            invite_users_permission=True,
            ban_users_permission=True,
            is_active=True,
        )
        db_session.add(channel)
        await db_session.flush()

        tariff = Tariff(
            name="VIP 30",
            price_stars=250,
            price_crypto=Decimal("1.25"),
            duration_days=30,
            sort_order=10,
            is_active=True,
            channel_id=channel.id,
        )
        db_session.add(tariff)
        await db_session.flush()

        invoice = CryptoInvoice(
            user_id=user.id,
            tariff_id=tariff.id,
            external_id="cp-paid-missing",
            asset="TON",
            amount=Decimal("1.25"),
            status="paid",
            paid_at=datetime(2026, 5, 1, 11, 10, tzinfo=UTC),
        )
        db_session.add(invoice)
        await db_session.flush()

        paid_invoice = CryptoInvoice(
            user_id=user.id,
            tariff_id=tariff.id,
            external_id="cp-paid-ok",
            asset="TON",
            amount=Decimal("1.25"),
            status="paid",
            paid_at=datetime(2026, 5, 1, 11, 0, tzinfo=UTC),
        )
        db_session.add(paid_invoice)
        await db_session.flush()

        db_session.add(
            Payment(
                user_id=user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                amount=125,
                currency="TON",
                provider="crypto_pay",
                telegram_payment_charge_id="crypto:invoice:cp-paid-ok",
                provider_payment_charge_id="cp-paid-ok",
                invoice_payload="payload:cp-paid-ok",
                paid_at=datetime(2026, 5, 1, 11, 0, tzinfo=UTC),
                status="paid",
            )
        )
        await db_session.commit()
        yield db_session, invoice.id

    await engine.dispose()


async def test_admin_crypto_invoices_command_renders_summary(
    session: tuple[AsyncSession, int],
) -> None:
    db_session, _ = session
    record_crypto_reconcile_run(
        processed_count=2,
        paid_count=1,
        expired_count=0,
        active_invoice_count=0,
        at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "crypto_pay_enabled": True,
            "crypto_pay_webhook_path": "/crypto-pay/webhook",
            "timezone": "UTC",
        }
    )
    message = DummyMessage("/admin_crypto_invoices")

    await admin_crypto_invoices(message, db_session, settings)

    assert message.answer_calls
    text, markup = message.answer_calls[0]
    assert "Crypto Pay" in text
    assert "\u041e\u043f\u043b\u0430\u0447\u0435\u043d\u044b, \u043d\u043e \u043d\u0435 \u0430\u043a\u0442\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u043d\u044b: 1" in text
    assert "processed=2" in text
    assert markup is not None


async def test_admin_crypto_dashboard_callback_renders_summary(
    session: tuple[AsyncSession, int],
) -> None:
    db_session, _ = session
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "crypto_pay_enabled": True,
            "crypto_pay_webhook_path": "/crypto-pay/webhook",
            "timezone": "UTC",
        }
    )
    callback = DummyCallback("menu:admin:payments:crypto")

    await admin_crypto_dashboard(callback, db_session, settings)

    assert callback.message.edit_calls
    text, _ = callback.message.edit_calls[0]
    assert "Crypto Pay" in text
    assert "\u041e\u043f\u043b\u0430\u0447\u0435\u043d\u044b, \u043d\u043e \u043d\u0435 \u0430\u043a\u0442\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u043d\u044b: 1" in text
    assert callback.answer_count == 1


async def test_admin_crypto_diag_command_renders_invoice_diagnostic(
    session: tuple[AsyncSession, int],
) -> None:
    db_session, invoice_id = session
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "timezone": "UTC",
        }
    )
    message = DummyMessage(f"/admin_crypto_diag {invoice_id}")

    await admin_crypto_diag(message, db_session, settings)

    assert message.answer_calls
    text, _ = message.answer_calls[0]
    assert "\u0414\u0438\u0430\u0433\u043d\u043e\u0441\u0442\u0438\u043a\u0430 crypto-\u0438\u043d\u0432\u043e\u0439\u0441\u0430" in text
    assert f"<code>{invoice_id}</code>" in text
    assert "\u043f\u043b\u0430\u0442\u0451\u0436 \u043d\u0435 \u043f\u0440\u0438\u0432\u044f\u0437\u0430\u043d" in text

