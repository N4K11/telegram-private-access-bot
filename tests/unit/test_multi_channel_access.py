from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.multi_channel_access_service import summarize_product_access

MAIN_TITLE = "\u041e\u0441\u043d\u043e\u0432\u043d\u043e\u0439 \u043a\u0430\u043d\u0430\u043b"
VIP_TITLE = "VIP-\u0447\u0430\u0442"
TARIFF_30 = "30 \u0434\u043d\u0435\u0439"
TARIFF_90 = "90 \u0434\u043d\u0435\u0439"
TARIFF_365 = "365 \u0434\u043d\u0435\u0439"
FALLBACK_TITLE = "\u041f\u0440\u043e\u0434\u0443\u043a\u0442 #99"
FALLBACK_TARIFF = "\u0422\u0430\u0440\u0438\u0444 #5"


def test_summarize_product_access_groups_subscriptions_by_channel() -> None:
    subscriptions = [
        SimpleNamespace(
            id=1,
            channel_id=10,
            expires_at=datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
            tariff_id=101,
            channel=SimpleNamespace(title=MAIN_TITLE),
            tariff=SimpleNamespace(name=TARIFF_30),
        ),
        SimpleNamespace(
            id=2,
            channel_id=20,
            expires_at=datetime(2026, 5, 15, 10, 0, tzinfo=UTC),
            tariff_id=202,
            channel=SimpleNamespace(title=VIP_TITLE),
            tariff=SimpleNamespace(name=TARIFF_90),
        ),
        SimpleNamespace(
            id=3,
            channel_id=10,
            expires_at=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
            tariff_id=102,
            channel=SimpleNamespace(title=MAIN_TITLE),
            tariff=SimpleNamespace(name=TARIFF_365),
        ),
    ]

    summary = summarize_product_access(subscriptions)

    assert len(summary) == 2
    main = summary[0]
    assert main.channel_id == 10
    assert main.channel_title == MAIN_TITLE
    assert main.subscription_count == 2
    assert main.subscription_ids == (1, 3)
    assert main.tariff_names == (TARIFF_30, TARIFF_365)
    assert main.latest_expires_at == datetime(2026, 5, 12, 10, 0, tzinfo=UTC)

    vip = summary[1]
    assert vip.channel_id == 20
    assert vip.channel_title == VIP_TITLE
    assert vip.subscription_count == 1


def test_summarize_product_access_uses_safe_fallbacks() -> None:
    subscriptions = [
        SimpleNamespace(
            id=7,
            channel_id=99,
            expires_at=datetime(2026, 5, 20, 10, 0, tzinfo=UTC),
            tariff_id=5,
            channel=SimpleNamespace(title=None),
            tariff=SimpleNamespace(name=None),
        )
    ]

    summary = summarize_product_access(subscriptions)

    assert len(summary) == 1
    assert summary[0].channel_title == FALLBACK_TITLE
    assert summary[0].tariff_names == (FALLBACK_TARIFF,)