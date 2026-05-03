from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.services.web_admin_dashboard as web_admin_dashboard
from app.config import Settings
from app.db.base import Base
from app.db.models import (
    AuditLog,
    BroadcastCampaign,
    Channel,
    CryptoInvoice,
    Payment,
    PromoCode,
    PromoRedemption,
    Subscription,
    SupportMessage,
    SupportTicket,
    Tariff,
    User,
)
from app.db.session import create_async_engine, create_session_factory
from app.runtime_state import record_critical_error, reset_runtime_state
from app.services.channel_diagnostics import (
    ChannelDiagnosticResult,
    ChannelDiagnosticsReport,
    DiagnosticCheck,
)
from app.services.web_auth import build_webapp_secret_key
from app.webhook.server import build_webhook_app

BOT_TOKEN = "123456789:token"


def _build_init_data(
    user: dict[str, object],
    *,
    bot_token: str = BOT_TOKEN,
    auth_timestamp: int | None = None,
) -> str:
    fields = {
        "auth_date": str(auth_timestamp or int(datetime.now(UTC).timestamp())),
        "query_id": "AAEAAAE",
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    signature = hmac.new(
        build_webapp_secret_key(bot_token),
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    fields["hash"] = signature
    return urlencode(fields)


@pytest_asyncio.fixture
async def webapp_runtime(
    workspace_tmp_path: Path,
) -> AsyncIterator[tuple[TestClient, Settings, async_sessionmaker[AsyncSession]]]:
    reset_runtime_state()
    database_path = workspace_tmp_path / "webapp-runtime.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        user = User(
            telegram_id=42,
            username="ruslan",
            first_name="Ruslan",
            role="user",
            is_admin=False,
            referral_code="REF42",
        )
        other_user = User(
            telegram_id=77,
            username="guest",
            first_name="Guest",
            role="user",
            is_admin=False,
            referral_code="REF77",
        )
        blocked_user = User(
            telegram_id=88,
            username="blocked",
            first_name="Blocked",
            role="user",
            is_admin=False,
            is_blocked=True,
            referral_code="REF88",
        )
        session.add_all([user, other_user, blocked_user])
        await session.flush()

        channel = Channel(
            telegram_chat_id=-1001234567890,
            title="Private channel",
            invite_users_permission=True,
            ban_users_permission=True,
            is_active=True,
        )
        vip_channel = Channel(
            telegram_chat_id=-1001234567001,
            title="VIP chat",
            invite_users_permission=True,
            ban_users_permission=True,
            is_active=True,
        )
        session.add_all([channel, vip_channel])
        await session.flush()

        tariff = Tariff(
            name="VIP 30",
            description="Main paid plan",
            price_stars=250,
            duration_days=30,
            sort_order=10,
            is_active=True,
            channel_id=channel.id,
            offer_copy="Р›СѓС‡С€РёР№ СЃС‚Р°СЂС‚ РґР»СЏ РѕСЃРЅРѕРІРЅРѕРіРѕ РєР°РЅР°Р»Р°",
            offer_group="Base",
            is_default_offer=True,
        )
        vip_tariff = Tariff(
            name="VIP Club",
            description="Extra access tier",
            price_stars=700,
            duration_days=90,
            sort_order=20,
            is_active=True,
            channel_id=vip_channel.id,
            offer_copy="РњР°РєСЃРёРјСѓРј РІС‹РіРѕРґС‹ РґР»СЏ VIP",
            offer_group="VIP",
            is_featured=True,
        )
        session.add_all([tariff, vip_tariff])
        await session.flush()

        session.add_all(
            [
                Subscription(
                    user_id=user.id,
                    tariff_id=tariff.id,
                    channel_id=channel.id,
                    status="active",
                    source="purchase",
                    started_at=datetime(2026, 4, 1, 10, 0, tzinfo=UTC),
                    expires_at=datetime(2026, 5, 20, 10, 0, tzinfo=UTC),
                ),
                Subscription(
                    user_id=user.id,
                    tariff_id=vip_tariff.id,
                    channel_id=vip_channel.id,
                    status="active",
                    source="purchase",
                    started_at=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
                    expires_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
                ),
            ]
        )
        session.add_all(
            [
                Payment(
                    user_id=user.id,
                    tariff_id=tariff.id,
                    channel_id=channel.id,
                    amount=250,
                    currency="XTR",
                    provider="telegram_stars",
                    telegram_payment_charge_id="tg-charge-1",
                    provider_payment_charge_id="provider-charge-1",
                    invoice_payload="stars:tariff:1",
                    raw_payload="{}",
                    paid_at=datetime(2026, 4, 1, 10, 0, tzinfo=UTC),
                    status="paid",
                ),
                Payment(
                    user_id=other_user.id,
                    tariff_id=tariff.id,
                    channel_id=channel.id,
                    amount=999,
                    currency="XTR",
                    provider="telegram_stars",
                    telegram_payment_charge_id="tg-charge-2",
                    provider_payment_charge_id="provider-charge-2",
                    invoice_payload="stars:tariff:2",
                    raw_payload="{}",
                    paid_at=datetime(2026, 4, 2, 9, 0, tzinfo=UTC),
                    status="paid",
                ),
                Payment(
                    user_id=blocked_user.id,
                    tariff_id=tariff.id,
                    channel_id=channel.id,
                    amount=500,
                    currency="USDT",
                    provider="crypto_pay",
                    telegram_payment_charge_id="tg-charge-3",
                    provider_payment_charge_id="crypto-charge-3",
                    invoice_payload="crypto:tariff:3",
                    raw_payload='{"secret":"value"}',
                    paid_at=datetime(2026, 4, 5, 11, 0, tzinfo=UTC),
                    status="paid",
                ),
            ]
        )

        promo_42 = PromoCode(
            code="WELCOME42",
            promo_type="discount_percent",
            value=20,
            max_uses=100,
            tariff_id=tariff.id,
            valid_until=datetime(2026, 5, 30, 0, 0, tzinfo=UTC),
            is_active=True,
        )
        promo_77 = PromoCode(
            code="OTHER77",
            promo_type="discount_stars",
            value=15,
            max_uses=100,
            tariff_id=tariff.id,
            valid_until=datetime(2026, 5, 30, 0, 0, tzinfo=UTC),
            is_active=True,
        )
        session.add_all([promo_42, promo_77])
        await session.flush()

        session.add_all(
            [
                PromoRedemption(promo_code_id=promo_42.id, user_id=user.id, status="pending"),
                PromoRedemption(promo_code_id=promo_77.id, user_id=other_user.id, status="pending"),
            ]
        )

        open_ticket = SupportTicket(
            user_id=user.id,
            category="payment",
            status="open",
            created_at=datetime(2026, 4, 3, 8, 0, tzinfo=UTC),
            updated_at=datetime(2026, 4, 3, 9, 0, tzinfo=UTC),
            last_user_message_at=datetime(2026, 4, 3, 9, 0, tzinfo=UTC),
        )
        closed_ticket = SupportTicket(
            user_id=user.id,
            category="access",
            status="closed",
            created_at=datetime(2026, 4, 1, 8, 0, tzinfo=UTC),
            updated_at=datetime(2026, 4, 1, 11, 0, tzinfo=UTC),
            last_user_message_at=datetime(2026, 4, 1, 10, 0, tzinfo=UTC),
            closed_at=datetime(2026, 4, 1, 11, 0, tzinfo=UTC),
            closed_by_user_id=user.id,
        )
        other_ticket = SupportTicket(
            user_id=other_user.id,
            category="technical",
            status="open",
            created_at=datetime(2026, 4, 4, 8, 0, tzinfo=UTC),
            updated_at=datetime(2026, 4, 4, 8, 30, tzinfo=UTC),
            last_user_message_at=datetime(2026, 4, 4, 8, 30, tzinfo=UTC),
        )
        session.add_all([open_ticket, closed_ticket, other_ticket])
        await session.flush()

        session.add_all(
            [
                SupportMessage(
                    ticket_id=open_ticket.id,
                    sender_user_id=user.id,
                    body="Payment is not visible",
                    is_admin=False,
                    created_at=datetime(2026, 4, 3, 9, 0, tzinfo=UTC),
                ),
                SupportMessage(
                    ticket_id=closed_ticket.id,
                    sender_user_id=user.id,
                    body="Access restored",
                    is_admin=False,
                    created_at=datetime(2026, 4, 1, 10, 0, tzinfo=UTC),
                ),
                SupportMessage(
                    ticket_id=other_ticket.id,
                    sender_user_id=other_user.id,
                    body="Issue for another user",
                    is_admin=False,
                    created_at=datetime(2026, 4, 4, 8, 30, tzinfo=UTC),
                ),
            ]
        )

        session.add(
            BroadcastCampaign(
                created_by_user_id=user.id,
                filter_name="active",
                content="Retention campaign",
                status="sent",
                total_targets=24,
                sent_count=22,
                failed_count=2,
                started_at=datetime(2026, 4, 6, 10, 0, tzinfo=UTC),
                finished_at=datetime(2026, 4, 6, 10, 15, tzinfo=UTC),
            )
        )
        session.add(
            CryptoInvoice(
                user_id=blocked_user.id,
                tariff_id=tariff.id,
                external_id="invoice-1",
                asset="USDT",
                amount=Decimal("5.00"),
                fiat_currency="USD",
                invoice_url="https://example.com/invoice/1",
                status="pending",
                expires_at=datetime(2026, 4, 7, 12, 0, tzinfo=UTC),
                raw_payload='{"token":"secret"}',
            )
        )
        await session.commit()

    record_critical_error(
        "worker_cycle_failed",
        "Synthetic failure for dashboard preview",
        source="tests",
        at=datetime(2026, 4, 8, 8, 0, tzinfo=UTC),
    )

    settings = Settings.model_validate(
        {
            "bot_token": BOT_TOKEN,
            "admin_ids": [1],
            "database_url": f"sqlite+aiosqlite:///{database_path.as_posix()}",
            "backup_directory": str(workspace_tmp_path / "backups"),
            "use_webhook": True,
            "public_webhook_url": "https://example.com",
            "bot_public_username": "privatair_bot",
            "webhook_secret_token": "telegram-secret",
            "webhook_path": "/telegram/webhook",
            "mini_app_path": "/cabinet",
            "mini_app_auth_max_age_seconds": 3600,
        }
    )
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    app = build_webhook_app(
        bot=bot,
        dispatcher=Dispatcher(),
        settings=settings,
        session_factory=session_factory,
    )
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        yield client, settings, session_factory
    finally:
        await client.close()
        await bot.session.close()
        await engine.dispose()
        reset_runtime_state()


async def test_mini_app_page_is_served(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    response = await client.get(settings.mini_app_path)
    assert response.status == 200
    text = await response.text()
    assert "Telegram Mini App" in text
    assert "Кабинет доступа" in text


async def test_auth_endpoint_accepts_valid_init_data(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    init_data = _build_init_data({"id": 42, "first_name": "Ruslan", "username": "ruslan"})
    response = await client.post(
        f"{settings.mini_app_path}/api/auth", json={"init_data": init_data}
    )
    assert response.status == 200
    payload = await response.json()
    assert payload["ok"] is True
    assert payload["user"]["telegram_id"] == 42
    assert payload["user"]["is_admin"] is False


async def test_auth_endpoint_rejects_invalid_init_data(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    response = await client.post(
        f"{settings.mini_app_path}/api/auth", json={"init_data": "broken-init-data"}
    )
    assert response.status == 401
    assert await response.json() == {"ok": False, "error": "unauthorized"}


async def test_bootstrap_returns_own_data(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    init_data = _build_init_data({"id": 42, "first_name": "Ruslan", "username": "ruslan"})
    response = await client.get(
        f"{settings.mini_app_path}/api/bootstrap", headers={"X-Telegram-Init-Data": init_data}
    )
    assert response.status == 200
    payload = await response.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["viewer"]["telegram_id"] == 42
    assert data["profile"]["has_active_subscription"] is True
    assert {item["title"] for item in data["products"]} == {"Private channel", "VIP chat"}
    assert len(data["recent_payments"]) == 1
    assert data["recent_payments"][0]["amount"] == 250
    assert data["recent_payments"][0]["tariff_name"] == "VIP 30"
    assert {item["channel_id"] for item in data["active_products"]} == {1, 2}
    products = {item["title"]: item for item in data["products"]}
    assert products["Private channel"]["default_tariff_id"] is not None
    assert products["Private channel"]["bundle_names"] == ["Base"]
    assert products["VIP chat"]["featured_tariff_id"] is not None
    assert products["VIP chat"]["bundle_names"] == ["VIP"]
    assert [item["code"] for item in data["pending_promos"]] == ["WELCOME42"]
    assert data["support"]["open_ticket"]["category"] == "payment"
    assert data["support"]["open_count"] == 1
    assert data["support"]["closed_count"] == 1
    assert {ticket["category"] for ticket in data["support"]["recent_tickets"]} == {
        "payment",
        "access",
    }
    assert data["actions"]["renew_link"] == "https://t.me/privatair_bot"
    assert data["actions"]["support_link"] == "https://t.me/privatair_bot"
    assert data["referrals"]["referral_link"] == "https://t.me/privatair_bot?start=ref_REF42"


async def test_bootstrap_rejects_invalid_init_data(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    response = await client.get(
        f"{settings.mini_app_path}/api/bootstrap",
        headers={"X-Telegram-Init-Data": "broken-init-data"},
    )
    assert response.status == 401
    assert await response.json() == {"ok": False, "error": "unauthorized"}


async def test_user_cannot_access_another_users_profile(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    init_data = _build_init_data({"id": 42, "first_name": "Ruslan", "username": "ruslan"})
    response = await client.get(
        f"{settings.mini_app_path}/api/users/77/profile",
        headers={"X-Telegram-Init-Data": init_data},
    )
    assert response.status == 403
    assert await response.json() == {"ok": False, "error": "forbidden"}


async def test_cabinet_read_only_endpoints_reject_post(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    init_data = _build_init_data({"id": 42, "first_name": "Ruslan", "username": "ruslan"})
    response = await client.post(
        f"{settings.mini_app_path}/api/bootstrap", headers={"X-Telegram-Init-Data": init_data}
    )
    assert response.status == 405


async def test_admin_summary_is_protected_and_available_for_admin(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    regular_init_data = _build_init_data({"id": 42, "first_name": "Ruslan", "username": "ruslan"})
    regular_response = await client.get(
        f"{settings.mini_app_path}/api/admin/summary",
        headers={"X-Telegram-Init-Data": regular_init_data},
    )
    assert regular_response.status == 403
    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})
    admin_response = await client.get(
        f"{settings.mini_app_path}/api/admin/summary",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert admin_response.status == 200
    payload = await admin_response.json()
    assert payload["ok"] is True
    assert payload["data"]["total_users"] >= 3
    assert "revenue_total" in payload["data"]


async def test_admin_dashboard_is_protected_and_available(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    regular_init_data = _build_init_data({"id": 42, "first_name": "Ruslan", "username": "ruslan"})
    regular_response = await client.get(
        f"{settings.mini_app_path}/api/admin/dashboard",
        headers={"X-Telegram-Init-Data": regular_init_data},
    )
    assert regular_response.status == 403
    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})
    admin_response = await client.get(
        f"{settings.mini_app_path}/api/admin/dashboard",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert admin_response.status == 200
    payload = await admin_response.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["summary"]["total_users"] >= 3
    assert data["users_preview"]["items"]
    assert data["payments_preview"]["items"]
    assert data["crypto_invoices"]["pending_count"] == 1
    assert data["promos"]["active_count"] == 2
    assert data["channels"]["active_count"] == 2
    assert data["support"]["awaiting_admin_count"] >= 1
    assert data["summary"]["conversion_buy_viewed"] >= 0
    assert data["summary"]["conversion_invite_issued"] >= 0
    assert data["summary"]["product_funnel"]
    assert data["anomalies"]


async def test_admin_users_filters_and_search_work(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})
    blocked_response = await client.get(
        f"{settings.mini_app_path}/api/admin/users?filter=blocked",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert blocked_response.status == 200
    blocked_payload = await blocked_response.json()
    assert blocked_payload["data"]["total_items"] == 1
    assert blocked_payload["data"]["items"][0]["telegram_id"] == 88

    search_response = await client.get(
        f"{settings.mini_app_path}/api/admin/users?query=guest",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert search_response.status == 200
    search_payload = await search_response.json()
    assert search_payload["data"]["total_items"] == 1
    assert search_payload["data"]["items"][0]["telegram_id"] == 77


async def test_admin_payments_filters_protect_sensitive_data(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})
    response = await client.get(
        f"{settings.mini_app_path}/api/admin/payments?provider=crypto",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert response.status == 200
    payload = await response.json()
    assert payload["data"]["total_items"] == 1
    item = payload["data"]["items"][0]
    assert item["provider"] == "crypto_pay"
    assert item["user_display_name"] == "Blocked"
    assert "provider_payment_charge_id" not in item
    assert "telegram_payment_charge_id" not in item
    assert "invoice_payload" not in item
    assert "raw_payload" not in item


async def test_admin_channel_check_action_writes_audit_log(
    monkeypatch: pytest.MonkeyPatch, webapp_runtime
) -> None:
    client, settings, session_factory = webapp_runtime
    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})

    async def fake_report(bot, channels):
        return ChannelDiagnosticsReport(
            bot_username="privatair_bot",
            get_me_error=None,
            results=(
                ChannelDiagnosticResult(
                    channel_id=channels[0].id,
                    title=channels[0].title,
                    telegram_chat_id=channels[0].telegram_chat_id,
                    username=channels[0].username,
                    is_active=True,
                    checks=(
                        DiagnosticCheck(
                            label="Бот администратор",
                            ok=True,
                            details="ok",
                        ),
                    ),
                    recommendations=("Всё готово",),
                ),
            ),
        )

    monkeypatch.setattr(web_admin_dashboard, "build_channel_diagnostics_report", fake_report)
    response = await client.post(
        f"{settings.mini_app_path}/api/admin/actions/channel-check",
        headers={"X-Telegram-Init-Data": admin_init_data, "Content-Type": "application/json"},
        json={},
    )
    assert response.status == 200
    payload = await response.json()
    assert payload["ok"] is True
    assert payload["data"]["checked_channels"] == 1

    async with session_factory() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.action == "webapp_admin_channel_check")
        )
        records = list(result.scalars())
    assert len(records) == 1
    assert records[0].actor_user_id is not None
