from __future__ import annotations

import pytest

from app.db.models import Channel, Tariff
from app.services.payments.stars import (
    STARS_CURRENCY,
    StarsInvoiceError,
    build_stars_invoice_payload,
    parse_stars_invoice_payload,
    refund_stars_payment,
    send_stars_invoice,
)


class DummyMessage:
    def __init__(self) -> None:
        self.invoice_calls: list[dict[str, object]] = []

    async def answer_invoice(self, **kwargs):
        self.invoice_calls.append(kwargs)
        return kwargs


class DummyBot:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def refund_star_payment(self, **kwargs):
        self.calls.append(kwargs)
        return True


def _make_tariff() -> Tariff:
    channel = Channel(
        id=7,
        telegram_chat_id=-1001234567890,
        title="Основной канал",
        is_active=True,
        invite_users_permission=True,
        ban_users_permission=True,
    )
    return Tariff(
        id=11,
        name="VIP 30",
        price_stars=250,
        duration_days=30,
        channel_id=channel.id,
        channel=channel,
        is_active=True,
    )


def test_stars_payload_round_trip() -> None:
    payload = build_stars_invoice_payload(11)

    parsed = parse_stars_invoice_payload(payload)

    assert payload == "stars:tariff:11"
    assert parsed.tariff_id == 11


def test_stars_payload_rejects_invalid_value() -> None:
    with pytest.raises(StarsInvoiceError):
        parse_stars_invoice_payload("bad:payload")


async def test_send_stars_invoice_uses_xtr_and_empty_provider_token() -> None:
    message = DummyMessage()
    tariff = _make_tariff()

    await send_stars_invoice(message, tariff)

    assert len(message.invoice_calls) == 1
    invoice = message.invoice_calls[0]
    assert invoice["currency"] == STARS_CURRENCY
    assert invoice["provider_token"] == ""
    assert invoice["payload"] == "stars:tariff:11"
    assert len(invoice["prices"]) == 1
    assert invoice["prices"][0].amount == 250


async def test_refund_stars_payment_calls_bot_method() -> None:
    bot = DummyBot()

    result = await refund_stars_payment(
        bot,
        user_id=42,
        telegram_payment_charge_id="tg-charge-1",
    )

    assert result is True
    assert bot.calls == [
        {"user_id": 42, "telegram_payment_charge_id": "tg-charge-1"}
    ]