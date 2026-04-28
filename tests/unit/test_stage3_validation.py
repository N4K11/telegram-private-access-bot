from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.db.models import Channel
from app.services.channels import (
    ChannelValidationError,
    extract_channel_reference,
    parse_channel_reference,
)
from app.services.tariffs import TariffValidationError, validate_tariff_payload


def test_parse_channel_reference_accepts_username_and_chat_id() -> None:
    assert parse_channel_reference("@demo_channel") == "@demo_channel"
    assert parse_channel_reference("-1001234567890") == -1001234567890



def test_extract_channel_reference_uses_forwarded_chat() -> None:
    message = SimpleNamespace(
        text=None,
        sender_chat=None,
        forward_from_chat=SimpleNamespace(id=-1009988776655),
    )

    assert extract_channel_reference(message) == -1009988776655



def test_parse_channel_reference_rejects_empty_value() -> None:
    with pytest.raises(ChannelValidationError):
        parse_channel_reference("   ")



def test_validate_tariff_payload_requires_channel_with_permissions() -> None:
    blocked_channel = Channel(
        id=10,
        telegram_chat_id=-1001,
        title="Broken",
        invite_users_permission=False,
        ban_users_permission=True,
        is_active=True,
    )

    with pytest.raises(TariffValidationError):
        validate_tariff_payload(
            name="VIP",
            price_stars="100",
            duration_days="30",
            channel=blocked_channel,
        )



def test_validate_tariff_payload_builds_draft() -> None:
    channel = Channel(
        id=7,
        telegram_chat_id=-1002,
        title="Main",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )

    draft = validate_tariff_payload(
        name="VIP 30",
        price_stars="250",
        duration_days="30",
        channel=channel,
        sort_order="5",
    )

    assert draft.name == "VIP 30"
    assert draft.price_stars == 250
    assert draft.duration_days == 30
    assert draft.channel_id == 7
    assert draft.sort_order == 5