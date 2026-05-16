# ruff: noqa: E501
from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
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

import app.services.web_admin_dashboard_directory_sections as web_admin_dashboard_directory
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
from app.services.admin_read_model_refresh import refresh_admin_read_models
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
    fixture_now = datetime.now(UTC).replace(microsecond=0)
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
        other_user.referred_by_user_id = user.id
        other_user.referred_at = fixture_now - timedelta(days=37, hours=4)
        other_user.referral_reward_granted_at = fixture_now - timedelta(days=37, hours=3)

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
            offer_copy="?????? ????? ??? ????????? ??????",
            offer_group="Base",
            is_default_offer=True,
        )
        main_plus_tariff = Tariff(
            name="VIP 90",
            description="Longer access",
            price_stars=600,
            duration_days=90,
            sort_order=15,
            is_active=True,
            channel_id=channel.id,
            offer_copy="Longer access for core product",
            offer_group="Base",
        )
        vip_tariff = Tariff(
            name="VIP Club",
            description="Extra access tier",
            price_stars=700,
            duration_days=90,
            sort_order=20,
            is_active=True,
            channel_id=vip_channel.id,
            offer_copy="???????? ?????? ??? VIP",
            offer_group="VIP",
            offer_expires_at=fixture_now + timedelta(days=16),
            is_featured=True,
        )
        session.add_all([tariff, main_plus_tariff, vip_tariff])
        await session.flush()

        session.add_all(
            [
                Subscription(
                    user_id=user.id,
                    tariff_id=tariff.id,
                    channel_id=channel.id,
                    status="active",
                    source="purchase",
                    started_at=fixture_now - timedelta(days=38),
                    expires_at=fixture_now + timedelta(days=11),
                ),
                Subscription(
                    user_id=user.id,
                    tariff_id=vip_tariff.id,
                    channel_id=vip_channel.id,
                    status="active",
                    source="purchase",
                    started_at=fixture_now - timedelta(days=29),
                    expires_at=fixture_now + timedelta(days=23),
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
                    paid_at=fixture_now - timedelta(days=38),
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
                    paid_at=fixture_now - timedelta(days=37, hours=1),
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
                    paid_at=fixture_now - timedelta(days=34, hours=23),
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
            valid_until=fixture_now + timedelta(days=21),
            is_active=True,
        )
        promo_77 = PromoCode(
            code="OTHER77",
            promo_type="discount_stars",
            value=15,
            max_uses=100,
            tariff_id=tariff.id,
            valid_until=fixture_now + timedelta(days=21),
            is_active=True,
        )
        session.add_all([promo_42, promo_77])
        await session.flush()

        session.add_all(
            [
                PromoRedemption(promo_code_id=promo_42.id, user_id=user.id, status="pending"),
                PromoRedemption(promo_code_id=promo_77.id, user_id=other_user.id, status="pending"),
                PromoRedemption(
                    promo_code_id=promo_77.id,
                    user_id=other_user.id,
                    payment_id=2,
                    applied_tariff_id=tariff.id,
                    amount_before=999,
                    amount_after=984,
                    status="consumed",
                    used_at=fixture_now - timedelta(days=37, hours=1),
                ),
            ]
        )

        open_ticket = SupportTicket(
            user_id=user.id,
            category="payment",
            priority="high",
            status="open",
            created_at=fixture_now - timedelta(days=36, hours=4),
            updated_at=fixture_now - timedelta(days=36, hours=3),
            last_user_message_at=fixture_now - timedelta(days=36, hours=3),
        )
        closed_ticket = SupportTicket(
            user_id=user.id,
            category="access",
            priority="normal",
            status="closed",
            created_at=fixture_now - timedelta(days=2, hours=4),
            updated_at=fixture_now - timedelta(days=2, hours=1),
            last_user_message_at=fixture_now - timedelta(days=2, hours=2),
            closed_at=fixture_now - timedelta(days=2, hours=1),
            closed_by_user_id=user.id,
            close_reason="resolved",
        )
        other_ticket = SupportTicket(
            user_id=other_user.id,
            category="technical",
            priority="urgent",
            status="open",
            created_at=fixture_now - timedelta(days=35, hours=4),
            updated_at=fixture_now - timedelta(days=35, hours=3, minutes=30),
            last_user_message_at=fixture_now - timedelta(days=35, hours=3, minutes=30),
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
                    created_at=fixture_now - timedelta(days=36, hours=3),
                ),
                SupportMessage(
                    ticket_id=closed_ticket.id,
                    sender_user_id=user.id,
                    body="Access restored",
                    is_admin=False,
                    created_at=fixture_now - timedelta(days=2, hours=2),
                ),
                SupportMessage(
                    ticket_id=other_ticket.id,
                    sender_user_id=other_user.id,
                    body="Issue for another user",
                    is_admin=False,
                    created_at=fixture_now - timedelta(days=35, hours=3, minutes=30),
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
                started_at=fixture_now - timedelta(days=33),
                finished_at=fixture_now - timedelta(days=33) + timedelta(minutes=15),
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
                expires_at=fixture_now - timedelta(days=32),
                raw_payload='{"token":"secret"}',
            )
        )
        session.add_all(
            [
                AuditLog(
                    action="buy_screen_viewed",
                    target_user_id=user.id,
                    payload=json.dumps(
                        {"source": "main_menu", "channel_id": channel.id}, ensure_ascii=False
                    ),
                ),
                AuditLog(
                    action="product_selected",
                    target_user_id=user.id,
                    payload=json.dumps(
                        {"source": "main_menu", "channel_id": channel.id}, ensure_ascii=False
                    ),
                ),
                AuditLog(
                    action="offer_clicked",
                    target_user_id=user.id,
                    payload=json.dumps(
                        {"source": "main_menu", "channel_id": channel.id, "tariff_id": tariff.id},
                        ensure_ascii=False,
                    ),
                ),
                AuditLog(
                    action="invoice_created_stars",
                    target_user_id=user.id,
                    payload=json.dumps(
                        {"source": "main_menu", "channel_id": channel.id, "tariff_id": tariff.id},
                        ensure_ascii=False,
                    ),
                ),
                AuditLog(
                    action="payment_paid_stars",
                    target_user_id=user.id,
                    payload=json.dumps(
                        {"source": "main_menu", "channel_id": channel.id, "tariff_id": tariff.id},
                        ensure_ascii=False,
                    ),
                ),
                AuditLog(
                    action="invite_issued",
                    target_user_id=user.id,
                    payload=json.dumps(
                        {"source": "main_menu", "channel_id": channel.id, "tariff_id": tariff.id},
                        ensure_ascii=False,
                    ),
                ),
                AuditLog(
                    action="buy_screen_viewed",
                    target_user_id=other_user.id,
                    payload=json.dumps(
                        {"source": "start_deep_link", "channel_id": channel.id}, ensure_ascii=False
                    ),
                ),
                AuditLog(
                    action="offer_clicked",
                    target_user_id=other_user.id,
                    payload=json.dumps(
                        {
                            "source": "start_deep_link",
                            "channel_id": channel.id,
                            "tariff_id": tariff.id,
                        },
                        ensure_ascii=False,
                    ),
                ),
                AuditLog(
                    action="invoice_created_stars",
                    target_user_id=other_user.id,
                    payload=json.dumps(
                        {
                            "source": "start_deep_link",
                            "channel_id": channel.id,
                            "tariff_id": tariff.id,
                        },
                        ensure_ascii=False,
                    ),
                ),
                AuditLog(
                    action="payment_paid_stars",
                    target_user_id=other_user.id,
                    payload=json.dumps(
                        {
                            "source": "start_deep_link",
                            "channel_id": channel.id,
                            "tariff_id": tariff.id,
                            "promo_code": "OTHER77",
                        },
                        ensure_ascii=False,
                    ),
                ),
                AuditLog(
                    action="referral_reward_granted",
                    actor_user_id=other_user.id,
                    target_user_id=user.id,
                    payload=json.dumps(
                        {"referred_user_id": other_user.id, "payment_id": 2, "reward_days": 7},
                        ensure_ascii=False,
                    ),
                ),
            ]
        )
        await session.commit()

    record_critical_error(
        "worker_cycle_failed",
        "Synthetic failure for dashboard preview",
        source="tests",
        at=fixture_now - timedelta(hours=1),
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
    assert products["Private channel"]["tariff_count"] == 2
    assert (
        products["Private channel"]["recommended_tariff_id"]
        == products["Private channel"]["default_tariff_id"]
    )
    assert products["Private channel"]["bundle_names"] == ["Base"]
    assert products["VIP chat"]["featured_tariff_id"] is not None
    assert (
        products["VIP chat"]["recommended_tariff_id"] == products["VIP chat"]["featured_tariff_id"]
    )
    assert (
        products["VIP chat"]["recommended_offer"]["id"]
        == products["VIP chat"]["featured_tariff_id"]
    )
    assert products["VIP chat"]["recommended_offer"]["offer_expires_at"] is not None
    assert products["VIP chat"]["recommended_offer"]["is_limited_time"] is True
    assert products["VIP chat"]["bundle_names"] == ["VIP"]
    assert [item["code"] for item in data["pending_promos"]] == ["WELCOME42"]
    assert data["support"]["open_ticket"]["category"] == "payment"
    assert data["support"]["open_count"] == 1
    assert data["support"]["closed_count"] == 1
    assert {ticket["category"] for ticket in data["support"]["recent_tickets"]} == {
        "payment",
        "access",
    }
    assert data["profile"]["primary_channel_id"] == 1
    assert data["actions"]["buy_link"] == "https://t.me/privatair_bot?start=buy"
    assert data["actions"]["renew_link"] == "https://t.me/privatair_bot?start=buy_1"
    assert data["actions"]["tariffs_link"] == "https://t.me/privatair_bot?start=tariffs_1"
    assert data["actions"]["support_link"] == "https://t.me/privatair_bot?start=help"
    assert data["actions"]["link_link"] == "https://t.me/privatair_bot?start=link"
    assert products["Private channel"]["buy_link"] == "https://t.me/privatair_bot?start=buy_1"
    assert (
        products["Private channel"]["tariffs_link"] == "https://t.me/privatair_bot?start=tariffs_1"
    )
    assert products["VIP chat"]["buy_link"] == "https://t.me/privatair_bot?start=buy_2"
    active_products = {item["channel_id"]: item for item in data["active_products"]}
    assert active_products[1]["primary_tariff_id"] == 1
    assert active_products[1]["tariff_ids"] == [1]
    assert active_products[1]["renew_link"] == "https://t.me/privatair_bot?start=buy_1"
    assert active_products[2]["renew_link"] == "https://t.me/privatair_bot?start=buy_2"
    assert data["recommendations"]["primary_offer"]["channel_id"] == 1
    assert data["recommendations"]["renewal_offer"]["channel_id"] == 1
    assert data["recommendations"]["cross_sell_offers"] == []
    assert data["offer_engine"]["hero_offer"]["channel_id"] == 1
    assert data["offer_engine"]["upgrade_offers"][0]["tariff_name"] == "VIP 90"
    assert data["offer_engine"]["bundle_offers"][0]["offer_group"] == "Base"
    assert data["offer_engine"]["limited_offers"][0]["tariff_name"] == "VIP Club"
    assert data["offer_engine"]["inventory"]["bundle_group_count"] == 2
    assert data["offer_engine"]["inventory"]["limited_offer_count"] == 1
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
    assert payload["data"]["source"] == "live"
    assert isinstance(payload["data"]["build_duration_ms"], int)
    assert payload["data"]["build_duration_ms"] >= 0
    assert payload["data"]["staleness_seconds"] == 0
    assert isinstance(payload["data"]["query_count"], int)
    assert payload["data"]["query_count"] >= 0
    assert payload["data"]["query_budget"] == 6
    assert isinstance(payload["data"]["query_budget_ok"], bool)
    assert payload["data"]["payload_bytes"] > 0
    assert payload["data"]["payload_budget"] == 18000
    assert isinstance(payload["data"]["payload_budget_ok"], bool)
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
    assert data["source"] == "live"
    assert isinstance(data["build_duration_ms"], int)
    assert data["staleness_seconds"] == 0
    assert isinstance(data["query_count"], int)
    assert data["query_count"] >= 0
    assert data["query_budget"] == 12
    assert isinstance(data["query_budget_ok"], bool)
    assert data["payload_bytes"] > 0
    assert data["payload_budget"] == 48000
    assert isinstance(data["payload_budget_ok"], bool)
    assert data["summary"]["total_users"] >= 3
    assert data["users_preview"]["items"]
    assert data["payments_preview"]["items"]
    assert data["crypto_invoices"]["pending_count"] == 1
    assert data["promos"]["active_count"] == 2
    assert data["channels"]["active_count"] == 2
    assert data["support"]["awaiting_admin_count"] >= 1
    assert "insights" not in data["support"]
    assert data["summary"]["conversion_buy_viewed"] >= 0
    assert data["summary"]["conversion_offer_clicked"] == 2
    assert data["summary"]["offer_inventory"]["total_products"] == 2
    assert data["summary"]["offer_inventory"]["bundle_group_count"] == 2
    assert data["summary"]["pricing_intelligence"]["average_payment_amount"] == 583
    assert data["summary"]["pricing_intelligence"]["stars_revenue_total"] == 1249
    assert data["summary"]["pricing_intelligence"]["crypto_revenue_total"] == 500
    assert data["summary"]["pricing_intelligence"]["limited_revenue_total"] == 0
    assert data["summary"]["pricing_intelligence"]["active_limited_offer_count"] == 1
    assert "top_product_pairs" not in data["summary"]["pricing_intelligence"]
    assert "top_pair_campaigns" not in data["summary"]["pricing_intelligence"]
    assert "top_offers" not in data["summary"]["pricing_intelligence"]
    assert data["summary"]["pricing_intelligence"]["top_revenue_offer"]["tariff_name"] == "VIP 30"
    assert "top_conversion_offer" in data["summary"]["pricing_intelligence"]
    assert data["summary"]["conversion_invite_issued"] >= 0
    assert "product_funnel" not in data["summary"]
    assert "source_funnel" not in data["summary"]
    assert "source_acquisition" not in data["summary"]
    assert "repeat_purchase_rate_percent" in data["summary"]
    assert "lifecycle_queues" in data["summary"]
    assert data["summary"]["lifecycle_queues"]["renewal_due_3d_users"] >= 0
    assert data["summary"]["lifecycle_queues"]["win_back_ready_users"] >= 0
    assert "lifecycle_offer_mix" in data["summary"]
    assert data["summary"]["lifecycle_offer_mix"]["total_sent_count"] >= 0
    assert "variants" not in data["summary"]["lifecycle_offer_mix"]
    assert "lifecycle_campaign_attribution" in data["summary"]
    assert data["summary"]["lifecycle_campaign_attribution"]["total_sent_count"] >= 0
    assert "families" not in data["summary"]["lifecycle_campaign_attribution"]
    assert "rules" not in data["summary"]["lifecycle_campaign_attribution"]
    assert "waves" not in data["summary"]["lifecycle_campaign_attribution"]
    assert "highlights" not in data["summary"]["lifecycle_campaign_attribution"]
    assert "roi" not in data["summary"]["lifecycle_campaign_attribution"]
    assert "source_campaigns" not in data["summary"]["lifecycle_campaign_attribution"]
    assert "source_roi" not in data["summary"]["lifecycle_campaign_attribution"]
    assert "source_opportunities" not in data["summary"]["lifecycle_campaign_attribution"]
    assert "source_actions" not in data["summary"]["lifecycle_campaign_attribution"]
    assert "source_highlights" not in data["summary"]["lifecycle_campaign_attribution"]
    assert "source_watchlist" not in data["summary"]["lifecycle_campaign_attribution"]
    assert data["summary"]["promo_attribution"]["total_payment_count"] == 1
    assert data["summary"]["promo_attribution"]["gross_revenue_total"] == 999
    assert data["summary"]["promo_attribution"]["revenue_total"] == 984
    assert data["summary"]["promo_attribution"]["discount_total"] == 15
    assert "campaigns" not in data["summary"]["promo_attribution"]
    assert data["summary"]["referral_attribution"]["total_referred_users"] == 1
    assert data["summary"]["referral_attribution"]["paid_referred_users"] == 1
    assert data["summary"]["referral_attribution"]["reward_days_issued_total"] == 7
    assert data["summary"]["referral_attribution"]["first_paid_revenue_total"] == 999
    assert data["summary"]["referral_attribution"]["lifetime_referred_revenue_total"] == 999
    assert data["summary"]["referral_attribution"]["suspicious_event_count"] == 0
    assert "top_referrers" not in data["summary"]["referral_attribution"]
    assert data["anomalies"]


async def test_admin_dashboard_sections_filter_payload(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})
    response = await client.get(
        (
            f"{settings.mini_app_path}/api/admin/dashboard"
            "?sections=summary,channels,anomalies"
        ),
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert response.status == 200
    payload = await response.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["source"] == "live"
    assert data["requested_sections"] == ["summary", "channels", "anomalies"]
    assert "summary" in data
    assert "channels" in data
    assert "anomalies" in data
    assert "users_preview" not in data
    assert "payments_preview" not in data
    assert "support" not in data
    assert "promos" not in data
    assert "capabilities" in data
    assert "generated_at" in data


async def test_admin_pricing_endpoint_is_protected_and_available(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    regular_init_data = _build_init_data({"id": 42, "first_name": "Ruslan", "username": "ruslan"})
    regular_response = await client.get(
        f"{settings.mini_app_path}/api/admin/pricing",
        headers={"X-Telegram-Init-Data": regular_init_data},
    )
    assert regular_response.status == 403

    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})
    admin_response = await client.get(
        f"{settings.mini_app_path}/api/admin/pricing",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert admin_response.status == 200
    payload = await admin_response.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["source"] == "live"
    assert data["view"] == "overview"
    assert data["view_label"] == "Pricing / Offers"
    assert data["limit"] == 10
    assert data["average_payment_amount"] == 583
    assert data["top_revenue_offer"]["tariff_name"] == "VIP 30"
    assert isinstance(data["top_product_pairs"], list)
    assert isinstance(data["top_pair_campaigns"], list)
    assert isinstance(data["top_offers"], list)
    assert len(data["top_product_pairs"]) <= 10
    assert len(data["top_pair_campaigns"]) <= 10
    assert len(data["top_offers"]) <= 10


async def test_admin_read_models_endpoint_is_protected_and_available(webapp_runtime) -> None:
    client, settings, session_factory = webapp_runtime
    regular_init_data = _build_init_data({"id": 42, "first_name": "Ruslan", "username": "ruslan"})
    regular_response = await client.get(
        f"{settings.mini_app_path}/api/admin/read-models",
        headers={"X-Telegram-Init-Data": regular_init_data},
    )
    assert regular_response.status == 403

    refresh_time = datetime.now(UTC).replace(microsecond=0)
    async with session_factory() as session:
        await refresh_admin_read_models(
            session,
            settings=settings,
            now=refresh_time,
            force=True,
        )

    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})
    admin_response = await client.get(
        f"{settings.mini_app_path}/api/admin/read-models?limit=5",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert admin_response.status == 200
    payload = await admin_response.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["source"] == "snapshot"
    assert data["view"] == "overview"
    assert data["view_label"] == "Read-model diagnostics"
    assert data["limit"] == 5
    assert {item["key"] for item in data["available_views"]} == {
        "overview",
        "watchlist",
        "actions",
        "drift",
    }
    assert data["tracked_count"] >= 1
    assert data["available_count"] >= 1
    assert isinstance(data["budget_exceeded_count"], int)
    assert isinstance(data["stale_count"], int)
    assert isinstance(data["missing_count"], int)
    assert data["operator_digest_summary"]["summary_line"]
    assert data["payload_bytes"] > 0
    assert data["payload_budget"] == 28000
    assert isinstance(data["payload_budget_ok"], bool)
    assert len(data["items"]) <= 5
    assert data["items"][0]["label"]
    assert data["items"][0]["status_label"]
    assert "query_budget_ok" in data["items"][0]
    assert "payload_bytes" in data["items"][0]
    assert "payload_budget" in data["items"][0]
    assert "payload_budget_ok" in data["items"][0]

    live_response = await client.get(
        f"{settings.mini_app_path}/api/admin/read-models?limit=5&source=live",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert live_response.status == 200
    live_payload = await live_response.json()
    assert live_payload["data"]["source"] == "live"
    assert live_payload["data"]["operator_digest_summary"]["summary_line"]
    assert live_payload["data"]["query_budget"] == 3
    assert live_payload["data"]["payload_budget"] == 28000

    watchlist_response = await client.get(
        f"{settings.mini_app_path}/api/admin/read-models?view=watchlist&limit=5&source=live",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert watchlist_response.status == 200
    watchlist_payload = await watchlist_response.json()
    watchlist_data = watchlist_payload["data"]
    assert watchlist_data["source"] == "live"
    assert watchlist_data["view"] == "watchlist"
    assert watchlist_data["view_label"] == "Read-model watchlist"
    assert watchlist_data["query_budget"] == 80
    assert watchlist_data["payload_budget"] == 36000
    assert watchlist_data["operator_digest_summary"]["summary_line"]
    assert isinstance(watchlist_data["alert_item_count"], int)
    assert isinstance(watchlist_data["regression_count"], int)
    assert len(watchlist_data["items"]) <= 5
    if watchlist_data["items"]:
        watch_item = watchlist_data["items"][0]
        assert watch_item["label"]
        assert watch_item["watch_kind_label"]
        assert watch_item["source_mode_label"]

    actions_response = await client.get(
        f"{settings.mini_app_path}/api/admin/read-models?view=actions&limit=5&source=live",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert actions_response.status == 200
    actions_payload = await actions_response.json()
    actions_data = actions_payload["data"]
    assert actions_data["source"] == "live"
    assert actions_data["view"] == "actions"
    assert actions_data["view_label"] == "Read-model action digest"
    assert actions_data["query_budget"] == 80
    assert actions_data["payload_budget"] == 40000
    assert actions_data["operator_digest_summary"]["summary_line"]
    assert isinstance(actions_data["surface_count"], int)
    assert isinstance(actions_data["budget_action_count"], int)
    assert isinstance(actions_data["snapshot_action_count"], int)
    assert isinstance(actions_data["drift_action_count"], int)
    assert len(actions_data["items"]) <= 5
    if actions_data["items"]:
        action_item = actions_data["items"][0]
        assert action_item["label"]
        assert action_item["action_label"]
        assert action_item["action_category_label"]
        assert action_item["issue_summary_label"]

    drift_response = await client.get(
        f"{settings.mini_app_path}/api/admin/read-models?view=drift&limit=5&source=live",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert drift_response.status == 200
    drift_payload = await drift_response.json()
    drift_data = drift_payload["data"]
    assert drift_data["source"] == "live"
    assert drift_data["view"] == "drift"
    assert drift_data["view_label"] == "Snapshot vs live drift"
    assert drift_data["comparison_mode"] == "snapshot_vs_live"
    assert drift_data["query_budget"] == 80
    assert drift_data["payload_budget"] == 48000
    assert drift_data["operator_digest_summary"]["summary_line"]
    assert drift_data["tracked_count"] >= drift_data["compared_count"] >= 1
    assert isinstance(drift_data["regression_count"], int)
    assert isinstance(drift_data["improvement_count"], int)
    assert isinstance(drift_data["budget_regression_count"], int)
    assert isinstance(drift_data["items"], list)
    assert len(drift_data["items"]) <= 5
    drift_item = drift_data["items"][0]
    assert drift_item["label"]
    assert "snapshot_query_count" in drift_item
    assert "live_query_count" in drift_item
    assert "query_count_delta" in drift_item
    assert "payload_bytes_delta" in drift_item
    assert "build_duration_ms_delta" in drift_item
    assert "status_tone" in drift_item


async def test_admin_acquisition_endpoint_is_protected_and_available(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    regular_init_data = _build_init_data({"id": 42, "first_name": "Ruslan", "username": "ruslan"})
    regular_response = await client.get(
        f"{settings.mini_app_path}/api/admin/acquisition",
        headers={"X-Telegram-Init-Data": regular_init_data},
    )
    assert regular_response.status == 403

    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})
    admin_response = await client.get(
        f"{settings.mini_app_path}/api/admin/acquisition",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert admin_response.status == 200
    payload = await admin_response.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["source"] == "live"
    assert data["view"] == "overview"
    assert data["view_label"] == "Acquisition / Sources"
    assert data["limit"] == 10
    assert data["source_count"] >= 1
    assert data["cohort_count"] >= 1
    assert data["paid_users_total"] >= 0
    assert data["lifetime_revenue_total"] >= 0
    assert isinstance(data["source_funnel"], list)
    assert isinstance(data["source_acquisition"], list)
    assert len(data["source_funnel"]) <= 10
    assert len(data["source_acquisition"]) <= 10
    assert "lifecycle_paid_users" not in data["source_acquisition"][0]
    assert "top_rule_label" not in data["source_acquisition"][0]


async def test_admin_conversion_endpoint_is_protected_and_available(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    regular_init_data = _build_init_data({"id": 42, "first_name": "Ruslan", "username": "ruslan"})
    regular_response = await client.get(
        f"{settings.mini_app_path}/api/admin/conversion",
        headers={"X-Telegram-Init-Data": regular_init_data},
    )
    assert regular_response.status == 403

    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})
    admin_response = await client.get(
        f"{settings.mini_app_path}/api/admin/conversion",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert admin_response.status == 200
    payload = await admin_response.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["source"] == "live"
    assert data["view"] == "overview"
    assert data["view_label"] == "Conversion / Products"
    assert data["limit"] == 10
    assert data["conversion_offer_clicked"] == 2
    assert data["offer_inventory"]["total_products"] == 2
    assert data["offer_inventory"]["bundle_group_count"] == 2
    assert data["product_count"] >= 1
    assert isinstance(data["product_funnel"], list)
    assert len(data["product_funnel"]) <= 10
    assert data["product_funnel"][0]["offer_clicked_users"] >= 0


async def test_admin_promo_referral_endpoint_is_protected_and_available(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    regular_init_data = _build_init_data({"id": 42, "first_name": "Ruslan", "username": "ruslan"})
    regular_response = await client.get(
        f"{settings.mini_app_path}/api/admin/promo-referrals",
        headers={"X-Telegram-Init-Data": regular_init_data},
    )
    assert regular_response.status == 403

    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})
    admin_response = await client.get(
        f"{settings.mini_app_path}/api/admin/promo-referrals",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert admin_response.status == 200
    payload = await admin_response.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["source"] == "live"
    assert data["view"] == "overview"
    assert data["view_label"] == "Promo / Referral"
    assert data["limit"] == 10
    assert data["campaign_count"] >= 1
    assert data["top_referrer_count"] >= 1
    assert data["promo_attribution"]["gross_revenue_total"] == 999
    assert len(data["promo_attribution"]["campaigns"]) <= 10
    assert data["promo_attribution"]["campaigns"][0]["label"] == "OTHER77"
    assert data["promo_attribution"]["campaigns"][0]["discount_share_percent"] == 1
    assert data["referral_attribution"]["paid_referred_users"] == 1
    assert len(data["referral_attribution"]["top_referrers"]) <= 10
    assert data["referral_attribution"]["top_referrers"][0]["telegram_id"] == 42
    assert data["referral_attribution"]["top_referrers"][0]["reward_days_issued"] == 7


async def test_admin_detail_limit_policy_clamps_and_slices(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})

    lifecycle_response = await client.get(
        f"{settings.mini_app_path}/api/admin/lifecycle?view=rules&limit=999",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert lifecycle_response.status == 200
    lifecycle_payload = await lifecycle_response.json()
    assert lifecycle_payload["data"]["limit"] == 50
    assert len(lifecycle_payload["data"]["items"]) <= 50

    support_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=hotspots&limit=999",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert support_response.status == 200
    support_payload = await support_response.json()
    assert support_payload["data"]["limit"] == 50
    assert len(support_payload["data"]["items"]) <= 50

    pricing_response = await client.get(
        f"{settings.mini_app_path}/api/admin/pricing?limit=1",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert pricing_response.status == 200
    pricing_payload = await pricing_response.json()
    assert pricing_payload["data"]["limit"] == 1
    assert len(pricing_payload["data"]["top_product_pairs"]) <= 1
    assert len(pricing_payload["data"]["top_pair_campaigns"]) <= 1
    assert len(pricing_payload["data"]["top_offers"]) <= 1

    acquisition_response = await client.get(
        f"{settings.mini_app_path}/api/admin/acquisition?limit=1",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert acquisition_response.status == 200
    acquisition_payload = await acquisition_response.json()
    assert acquisition_payload["data"]["limit"] == 1
    assert len(acquisition_payload["data"]["source_funnel"]) <= 1
    assert len(acquisition_payload["data"]["source_acquisition"]) <= 1

    conversion_response = await client.get(
        f"{settings.mini_app_path}/api/admin/conversion?limit=1",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert conversion_response.status == 200
    conversion_payload = await conversion_response.json()
    assert conversion_payload["data"]["limit"] == 1
    assert len(conversion_payload["data"]["product_funnel"]) <= 1

    promo_response = await client.get(
        f"{settings.mini_app_path}/api/admin/promo-referrals?limit=1",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert promo_response.status == 200
    promo_payload = await promo_response.json()
    assert promo_payload["data"]["limit"] == 1
    assert len(promo_payload["data"]["promo_attribution"]["campaigns"]) <= 1
    assert len(promo_payload["data"]["referral_attribution"]["top_referrers"]) <= 1


async def test_admin_lifecycle_endpoint_is_protected_and_available(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    regular_init_data = _build_init_data({"id": 42, "first_name": "Ruslan", "username": "ruslan"})
    regular_response = await client.get(
        f"{settings.mini_app_path}/api/admin/lifecycle",
        headers={"X-Telegram-Init-Data": regular_init_data},
    )
    assert regular_response.status == 403

    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})
    admin_response = await client.get(
        f"{settings.mini_app_path}/api/admin/lifecycle?view=rules&limit=5",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert admin_response.status == 200
    payload = await admin_response.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["source"] == "live"
    assert isinstance(data["build_duration_ms"], int)
    assert data["staleness_seconds"] == 0
    assert isinstance(data["query_count"], int)
    assert data["query_count"] >= 0
    assert data["query_budget"] == 3
    assert isinstance(data["query_budget_ok"], bool)
    assert data["payload_bytes"] > 0
    assert data["payload_budget"] == 32000
    assert isinstance(data["payload_budget_ok"], bool)
    assert data["view"] == "rules"
    assert data["view_label"] == "Managed waves"
    assert data["limit"] == 5
    assert data["total_sent_count"] >= 0
    assert data["total_paid_users"] >= 0
    assert data["available_views"]
    assert {item["key"] for item in data["available_views"]} == {
        "rules",
        "roi",
        "sources",
        "source_campaigns",
        "source_roi",
        "source_opportunities",
        "source_actions",
        "source_highlights",
        "source_watchlist",
        "highlights",
        "waves",
        "families",
        "variants",
    }
    assert isinstance(data["items"], list)
    if data["items"]:
        item = data["items"][0]
        assert "rule_key" in item
        assert "label" in item
        assert "family" in item
        assert "paid_conversion_percent" in item

    roi_response = await client.get(
        f"{settings.mini_app_path}/api/admin/lifecycle?view=roi&limit=3",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert roi_response.status == 200
    roi_payload = await roi_response.json()
    assert roi_payload["data"]["view"] == "roi"
    assert roi_payload["data"]["limit"] == 3
    if roi_payload["data"]["items"]:
        assert "second_product_revenue_total" in roi_payload["data"]["items"][0]
        assert "second_product_attach_from_paid_percent" in roi_payload["data"]["items"][0]

    source_response = await client.get(
        f"{settings.mini_app_path}/api/admin/lifecycle?view=sources&limit=3",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert source_response.status == 200
    source_payload = await source_response.json()
    assert source_payload["data"]["view"] == "sources"
    assert source_payload["data"]["view_label"] == "Acquisition sources"
    assert source_payload["data"]["limit"] == 3
    if source_payload["data"]["items"]:
        item = source_payload["data"]["items"][0]
        assert "source" in item
        assert "lifecycle_paid_users" in item
        assert "lifecycle_revenue_total" in item
        assert "lifecycle_second_product_attach_percent" in item
        assert "top_rule_label" in item
        assert "top_wave_label" in item

    source_campaign_response = await client.get(
        f"{settings.mini_app_path}/api/admin/lifecycle?view=source_campaigns&limit=3",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert source_campaign_response.status == 200
    source_campaign_payload = await source_campaign_response.json()
    assert source_campaign_payload["data"]["view"] == "source_campaigns"
    assert source_campaign_payload["data"]["view_label"] == "Source x campaign"
    assert source_campaign_payload["data"]["limit"] == 3
    if source_campaign_payload["data"]["items"]:
        item = source_campaign_payload["data"]["items"][0]
        assert "source_label" in item
        assert "rule_label" in item
        assert "wave_label" in item
        assert "paid_share_of_source_paid_percent" in item
        assert "second_product_attach_percent" in item

    source_roi_response = await client.get(
        f"{settings.mini_app_path}/api/admin/lifecycle?view=source_roi&limit=3",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert source_roi_response.status == 200
    source_roi_payload = await source_roi_response.json()
    assert source_roi_payload["data"]["view"] == "source_roi"
    assert source_roi_payload["data"]["view_label"] == "Source ROI"
    assert source_roi_payload["data"]["limit"] == 3
    if source_roi_payload["data"]["items"]:
        item = source_roi_payload["data"]["items"][0]
        assert "average_revenue_per_source_paid_user" in item
        assert "second_product_revenue_share_percent" in item
        assert "second_product_upside_users" in item

    source_opportunities_response = await client.get(
        f"{settings.mini_app_path}/api/admin/lifecycle?view=source_opportunities&limit=3",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert source_opportunities_response.status == 200
    source_opportunities_payload = await source_opportunities_response.json()
    assert source_opportunities_payload["data"]["view"] == "source_opportunities"
    assert source_opportunities_payload["data"]["view_label"] == "Source opportunities"
    assert source_opportunities_payload["data"]["limit"] == 3
    if source_opportunities_payload["data"]["items"]:
        item = source_opportunities_payload["data"]["items"][0]
        assert "opportunity_score" in item
        assert "opportunity_label" in item
        assert "source_paid_gap_users" in item

    source_actions_response = await client.get(
        f"{settings.mini_app_path}/api/admin/lifecycle?view=source_actions&limit=3",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert source_actions_response.status == 200
    source_actions_payload = await source_actions_response.json()
    assert source_actions_payload["data"]["view"] == "source_actions"
    assert source_actions_payload["data"]["view_label"] == "Source actions"
    assert source_actions_payload["data"]["limit"] == 3
    if source_actions_payload["data"]["items"]:
        item = source_actions_payload["data"]["items"][0]
        assert "primary_issue_key" in item
        assert "primary_issue_label" in item
        assert "recommended_action_key" in item
        assert "recommended_action_label" in item
        assert "recommended_action_note" in item

    source_highlights_response = await client.get(
        f"{settings.mini_app_path}/api/admin/lifecycle?view=source_highlights&limit=3",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert source_highlights_response.status == 200
    source_highlights_payload = await source_highlights_response.json()
    assert source_highlights_payload["data"]["view"] == "source_highlights"
    assert source_highlights_payload["data"]["view_label"] == "Source leaders"
    assert source_highlights_payload["data"]["limit"] == 3
    if source_highlights_payload["data"]["items"]:
        item = source_highlights_payload["data"]["items"][0]
        assert "metric_label" in item
        assert "source_label" in item
        assert "rule_label" in item
        assert "wave_label" in item
        assert "second_product_attach_percent" in item

    source_watchlist_response = await client.get(
        f"{settings.mini_app_path}/api/admin/lifecycle?view=source_watchlist&limit=3",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert source_watchlist_response.status == 200
    source_watchlist_payload = await source_watchlist_response.json()
    assert source_watchlist_payload["data"]["view"] == "source_watchlist"
    assert source_watchlist_payload["data"]["view_label"] == "Source watchlist"
    assert source_watchlist_payload["data"]["limit"] == 3
    if source_watchlist_payload["data"]["items"]:
        item = source_watchlist_payload["data"]["items"][0]
        assert "metric_label" in item
        assert "source_label" in item
        assert "rule_label" in item
        assert "wave_label" in item
        assert "note" in item

    wave_response = await client.get(
        f"{settings.mini_app_path}/api/admin/lifecycle?view=waves&limit=3",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert wave_response.status == 200
    wave_payload = await wave_response.json()
    assert wave_payload["data"]["view"] == "waves"
    assert wave_payload["data"]["limit"] == 3
    if wave_payload["data"]["items"]:
        assert "wave_mode" in wave_payload["data"]["items"][0]
        assert "top_rule_label" in wave_payload["data"]["items"][0]

    highlights_response = await client.get(
        f"{settings.mini_app_path}/api/admin/lifecycle?view=highlights&limit=4",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert highlights_response.status == 200
    highlights_payload = await highlights_response.json()
    assert highlights_payload["data"]["view"] == "highlights"
    assert highlights_payload["data"]["limit"] == 4
    if highlights_payload["data"]["items"]:
        assert "metric_label" in highlights_payload["data"]["items"][0]
        assert "scope_label" in highlights_payload["data"]["items"][0]
        assert "entity_label" in highlights_payload["data"]["items"][0]

    family_response = await client.get(
        f"{settings.mini_app_path}/api/admin/lifecycle?view=families&limit=3",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert family_response.status == 200
    family_payload = await family_response.json()
    assert family_payload["data"]["view"] == "families"
    assert family_payload["data"]["limit"] == 3
    if family_payload["data"]["items"]:
        assert "family" in family_payload["data"]["items"][0]
        assert "top_variant_label" in family_payload["data"]["items"][0]


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


async def test_admin_support_endpoints_are_protected_and_available(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    regular_init_data = _build_init_data({"id": 42, "first_name": "Ruslan", "username": "ruslan"})
    regular_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support",
        headers={"X-Telegram-Init-Data": regular_init_data},
    )
    assert regular_response.status == 403

    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})
    admin_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support?status=open",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert admin_response.status == 200
    payload = await admin_response.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["status"] == "open"
    assert data["queue"] == "all"
    assert data["open_count"] == 2
    assert data["closed_count"] == 1
    assert data["awaiting_admin_count"] == 2
    assert data["queue_counts"]["all"] == 2
    assert data["queue_counts"]["awaiting_admin"] == 2
    assert data["queue_counts"]["awaiting_user"] == 0
    assert data["queue_counts"]["stale"] == 2
    assert data["close_reason_summary"]["top_close_reason"] == "resolved"
    assert data["close_reason_summary"]["top_close_reason_share_percent"] == 100.0
    assert data["close_reason_counts"][0]["share_percent"] == 100.0
    assert data["insights"]["recent_close_summary"]["window_days"] == 7
    assert data["insights"]["recent_close_summary"]["total_closed"] == 1
    assert data["insights"]["recent_close_summary"]["previous_total_closed"] == 0
    priority_counts = {item["key"]: item["count"] for item in data["insights"]["priority_counts"]}
    assert priority_counts == {"high": 1, "urgent": 1}
    waiting_counts = {item["key"]: item["count"] for item in data["insights"]["waiting_state_counts"]}
    assert waiting_counts == {"awaiting_admin": 2}
    canned_packs = {item["key"]: item for item in data["insights"]["canned_reply_packs"]}
    assert canned_packs["open:payment"]["sample_titles"]
    assert canned_packs["open:technical"]["count"] == 1
    pack_outcomes = {item["key"]: item for item in data["insights"]["canned_reply_pack_outcomes"]}
    assert pack_outcomes["open:access"]["resolved_rate_percent"] == 100.0
    assert data["insights"]["pack_outcome_summary"]["window_days"] == 30
    assert data["insights"]["trend_summary"]["strongest_reason"] == "resolved"
    assert data["insights"]["sla_hotspots"]
    assert data["insights"]["sla_hotspot_summary"]["top_kind"] in {"breach", "stale", "warning"}
    assert data["insights"]["sla_queue_summary"]["top_sla_queue_action"] == "reply_now"
    assert data["insights"]["sla_queue_summary"]["top_kind"] == "breach"
    assert data["insights"]["sla_queue_summary"]["top_escalation_lane"] == "payment_blocker"
    assert (
        data["insights"]["sla_action_queue"][0]["label"]
        == data["insights"]["action_lanes"][0]["label"]
    )
    assert data["insights"]["sla_action_queue"][0]["sample_ticket_ids"][0] == 1
    assert data["insights"]["sla_action_summary"]["top_kind"] == "breach"
    assert data["insights"]["sla_action_summary"]["top_action_key"] == "reply_now"
    assert (
        data["insights"]["sla_queue_summary"]["top_sample_ticket_ids"]
        == data["insights"]["sla_action_queue"][0]["sample_ticket_ids"]
    )
    assert data["insights"]["action_lane_summary"]["top_action_lane"] == "reply_now"
    assert data["insights"]["action_lane_summary"]["top_action_lane_count"] == 2
    assert data["insights"]["next_action_summary"]["top_next_action"] == "reply_now"
    assert data["insights"]["next_action_summary"]["top_next_action_count"] == 2
    assert (
        data["insights"]["next_action_queue"][0]["label"]
        == data["insights"]["action_lanes"][0]["label"]
    )
    assert data["insights"]["next_action_queue"][0]["top_escalation_lane"] == "payment_blocker"
    assert data["insights"]["next_action_queue"][0]["sample_ticket_ids"][0] == 1
    assert (
        data["insights"]["next_action_summary"]["top_sample_ticket_ids"]
        == data["insights"]["next_action_queue"][0]["sample_ticket_ids"]
    )
    assert data["insights"]["action_route_summary"]["top_action_route"] == "payment_blocker:reply_now"
    assert data["insights"]["action_route_summary"]["top_action_route_hotspot"] == "breach"
    assert (
        data["insights"]["action_routes"][0]["action_label"]
        == data["insights"]["next_action_queue"][0]["label"]
    )
    assert data["insights"]["action_routes"][0]["escalation_key"] == "payment_blocker"
    assert data["insights"]["action_routes"][0]["sample_ticket_ids"] == [1]
    assert data["insights"]["action_route_summary"]["top_sample_ticket_ids"] == [1]
    assert (
        data["insights"]["triage_queue_summary"]["top_triage_queue"]
        == "payment_blocker:reply_now:open:payment"
    )
    assert data["insights"]["triage_queue_summary"]["top_pack_key"] == "open:payment"
    assert data["insights"]["triage_queue"][0]["pack_key"] == "open:payment"
    assert (
        data["insights"]["triage_queue"][0]["action_label"]
        == data["insights"]["next_action_queue"][0]["label"]
    )
    assert data["insights"]["triage_queue"][0]["sample_ticket_ids"] == [1]
    assert data["insights"]["triage_queue_summary"]["top_sample_ticket_ids"] == [1]
    assert data["insights"]["triage_plan_summary"]["top_primary_reply_key"] == "payment_ack_review"
    assert data["insights"]["triage_plans"][0]["pack_key"] == "open:payment"
    assert data["insights"]["triage_plans"][0]["primary_reply_key"] == "payment_ack_review"
    assert data["insights"]["triage_plans"][0]["sample_ticket_ids"] == [1]
    assert data["insights"]["triage_plans"][0]["suggested_replies"]
    assert data["insights"]["triage_confirm_summary"]["top_primary_reply_key"] == "payment_ack_review"
    assert data["insights"]["triage_confirm"][0]["confirm_key"] == "payment_blocker:reply_now:open:payment"
    assert data["insights"]["triage_confirm"][0]["confirm_mode"] == "preview_only"
    assert data["insights"]["triage_confirm"][0]["sample_ticket_ids"] == [1]
    assert "read-only confirmation" in data["insights"]["triage_confirm"][0]["confirm_note"]
    assert (
        data["insights"]["action_lanes"][0]["label"]
        == data["insights"]["next_action_queue"][0]["label"]
    )
    assert data["insights"]["escalation_lane_summary"]["top_escalation_lane"] == "payment_blocker"
    assert data["insights"]["escalation_lane_summary"]["top_escalation_lane_count"] == 1
    assert data["insights"]["escalation_lanes"][0]["key"] == "payment_blocker"
    assert data["insights"]["escalation_trend_summary"]["top_trend_key"] == "access_blocker"
    assert data["insights"]["escalation_trend_summary"]["top_trend_delta"] == 1
    insights_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=pack_outcomes&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert insights_response.status == 200
    insights_payload = await insights_response.json()
    assert insights_payload["data"]["source"] == "live"
    assert isinstance(insights_payload["data"]["build_duration_ms"], int)
    assert insights_payload["data"]["staleness_seconds"] == 0
    assert isinstance(insights_payload["data"]["query_count"], int)
    assert insights_payload["data"]["query_count"] >= 0
    assert insights_payload["data"]["query_budget"] == 3
    assert isinstance(insights_payload["data"]["query_budget_ok"], bool)
    assert insights_payload["data"]["payload_bytes"] > 0
    assert insights_payload["data"]["payload_budget"] == 28000
    assert isinstance(insights_payload["data"]["payload_budget_ok"], bool)
    assert insights_payload["data"]["view"] == "pack_outcomes"
    assert insights_payload["data"]["limit"] == 2
    assert insights_payload["data"]["items"]
    assert "resolved_rate_percent" in insights_payload["data"]["items"][0]
    assert "escalation_trends" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }
    assert "sla_actions" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }
    assert "sla_queue" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }
    assert "next_actions" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }
    assert "action_routes" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }
    assert "triage_queue" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }
    assert "triage_plans" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }
    assert "triage_confirm" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }
    assert "triage_apply_history" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }
    assert "triage_apply_routes" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }
    assert "triage_apply_actors" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }
    assert "triage_apply_replies" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }
    assert "triage_apply_actor_replies" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }
    assert "triage_apply_route_actors" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }
    assert "triage_apply_reply_packs" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }
    assert "triage_apply_route_reply_actors" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }
    assert "triage_apply_focus" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }
    assert "triage_apply_effectiveness" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }
    assert "operator_action_trends" in {
        item["key"] for item in insights_payload["data"]["available_views"]
    }

    sla_action_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=sla_actions&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert sla_action_response.status == 200
    sla_action_payload = await sla_action_response.json()
    assert sla_action_payload["data"]["view"] == "sla_actions"
    assert sla_action_payload["data"]["sla_action_summary"]["top_action_key"] == "reply_now"
    assert "action_label" in sla_action_payload["data"]["items"][0]
    assert "escalation_label" in sla_action_payload["data"]["items"][0]
    assert "note" in sla_action_payload["data"]["items"][0]

    sla_queue_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=sla_queue&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert sla_queue_response.status == 200
    sla_queue_payload = await sla_queue_response.json()
    assert sla_queue_payload["data"]["view"] == "sla_queue"
    assert sla_queue_payload["data"]["sla_queue_summary"]["top_sla_queue_action"] == "reply_now"
    assert (
        sla_queue_payload["data"]["items"][0]["label"]
        == data["insights"]["action_lanes"][0]["label"]
    )
    assert sla_queue_payload["data"]["items"][0]["top_kind"] == "breach"
    assert sla_queue_payload["data"]["items"][0]["top_escalation_lane"] == "payment_blocker"
    assert sla_queue_payload["data"]["items"][0]["sample_ticket_ids"][0] == 1
    assert (
        sla_queue_payload["data"]["sla_queue_summary"]["top_sample_ticket_ids"]
        == sla_queue_payload["data"]["items"][0]["sample_ticket_ids"]
    )
    assert "note" in sla_queue_payload["data"]["items"][0]

    action_lane_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=action_lanes&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert action_lane_response.status == 200
    action_lane_payload = await action_lane_response.json()
    assert action_lane_payload["data"]["view"] == "action_lanes"
    assert action_lane_payload["data"]["action_lane_summary"]["top_action_lane"] == "reply_now"
    next_action_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=next_actions&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert next_action_response.status == 200
    next_action_payload = await next_action_response.json()
    assert next_action_payload["data"]["view"] == "next_actions"
    assert next_action_payload["data"]["next_action_summary"]["top_next_action"] == "reply_now"
    assert (
        next_action_payload["data"]["items"][0]["label"]
        == action_lane_payload["data"]["items"][0]["label"]
    )
    assert next_action_payload["data"]["items"][0]["top_escalation_lane"] == "payment_blocker"
    assert next_action_payload["data"]["items"][0]["sample_ticket_ids"][0] == 1
    assert (
        next_action_payload["data"]["next_action_summary"]["top_sample_ticket_ids"]
        == next_action_payload["data"]["items"][0]["sample_ticket_ids"]
    )
    assert "note" in next_action_payload["data"]["items"][0]
    assert action_lane_payload["data"]["items"][0]["key"] == "reply_now"
    assert "sla_breach_count" in action_lane_payload["data"]["items"][0]

    action_route_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=action_routes&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert action_route_response.status == 200
    action_route_payload = await action_route_response.json()
    assert action_route_payload["data"]["view"] == "action_routes"
    assert (
        action_route_payload["data"]["action_route_summary"]["top_action_route"]
        == "payment_blocker:reply_now"
    )
    assert action_route_payload["data"]["items"][0]["action_label"] == next_action_payload["data"]["items"][0]["label"]
    assert action_route_payload["data"]["items"][0]["escalation_key"] == "payment_blocker"
    assert action_route_payload["data"]["items"][0]["top_kind"] == "breach"
    assert action_route_payload["data"]["items"][0]["sample_ticket_ids"] == [1]
    assert action_route_payload["data"]["action_route_summary"]["top_sample_ticket_ids"] == [1]
    assert "note" in action_route_payload["data"]["items"][0]

    triage_queue_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=triage_queue&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert triage_queue_response.status == 200
    triage_queue_payload = await triage_queue_response.json()
    assert triage_queue_payload["data"]["view"] == "triage_queue"
    assert (
        triage_queue_payload["data"]["triage_queue_summary"]["top_triage_queue"]
        == "payment_blocker:reply_now:open:payment"
    )
    assert triage_queue_payload["data"]["items"][0]["pack_key"] == "open:payment"
    assert (
        triage_queue_payload["data"]["items"][0]["action_label"]
        == next_action_payload["data"]["items"][0]["label"]
    )
    assert triage_queue_payload["data"]["items"][0]["sample_ticket_ids"] == [1]
    assert triage_queue_payload["data"]["items"][0]["sample_titles"]
    assert "note" in triage_queue_payload["data"]["items"][0]

    triage_plan_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=triage_plans&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert triage_plan_response.status == 200
    triage_plan_payload = await triage_plan_response.json()
    assert triage_plan_payload["data"]["view"] == "triage_plans"
    assert (
        triage_plan_payload["data"]["triage_plan_summary"]["top_primary_reply_key"]
        == "payment_ack_review"
    )
    assert triage_plan_payload["data"]["items"][0]["pack_key"] == "open:payment"
    assert triage_plan_payload["data"]["items"][0]["primary_reply_key"] == "payment_ack_review"
    assert triage_plan_payload["data"]["items"][0]["sample_ticket_ids"] == [1]
    assert triage_plan_payload["data"]["items"][0]["suggested_replies"]
    assert (
        triage_plan_payload["data"]["items"][0]["route_label"]
        == triage_queue_payload["data"]["items"][0]["route_label"]
    )

    triage_confirm_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=triage_confirm&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert triage_confirm_response.status == 200
    triage_confirm_payload = await triage_confirm_response.json()
    assert triage_confirm_payload["data"]["view"] == "triage_confirm"
    assert (
        triage_confirm_payload["data"]["triage_confirm_summary"]["top_primary_reply_key"]
        == "payment_ack_review"
    )
    assert (
        triage_confirm_payload["data"]["items"][0]["confirm_key"]
        == "payment_blocker:reply_now:open:payment"
    )
    assert triage_confirm_payload["data"]["items"][0]["confirm_mode"] == "preview_only"
    assert triage_confirm_payload["data"]["items"][0]["sample_ticket_ids"] == [1]
    assert "read-only confirmation" in triage_confirm_payload["data"]["items"][0]["confirm_note"]

    escalation_lane_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=escalation_lanes&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert escalation_lane_response.status == 200
    escalation_lane_payload = await escalation_lane_response.json()
    assert escalation_lane_payload["data"]["view"] == "escalation_lanes"
    assert escalation_lane_payload["data"]["escalation_lane_summary"]["top_escalation_lane"] == "payment_blocker"
    assert escalation_lane_payload["data"]["items"][0]["key"] == "payment_blocker"
    assert "high_priority_count" in escalation_lane_payload["data"]["items"][0]

    escalation_trend_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=escalation_trends&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert escalation_trend_response.status == 200
    escalation_trend_payload = await escalation_trend_response.json()
    assert escalation_trend_payload["data"]["view"] == "escalation_trends"
    assert escalation_trend_payload["data"]["escalation_trend_summary"]["top_trend_key"] == "access_blocker"
    assert escalation_trend_payload["data"]["items"][0]["key"] == "access_blocker"
    assert escalation_trend_payload["data"]["items"][0]["current_count"] == 1
    assert "delta" in escalation_trend_payload["data"]["items"][0]

    operator_action_trend_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=operator_action_trends&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert operator_action_trend_response.status == 200
    operator_action_trend_payload = await operator_action_trend_response.json()
    assert operator_action_trend_payload["data"]["view"] == "operator_action_trends"
    assert operator_action_trend_payload["data"]["operator_action_trend_summary"]["top_operator_action_key"]
    assert "pack_label" in operator_action_trend_payload["data"]["items"][0]
    assert "close_reason_label" in operator_action_trend_payload["data"]["items"][0]
    assert "action_label" in operator_action_trend_payload["data"]["items"][0]
    assert "note" in operator_action_trend_payload["data"]["items"][0]

    fallback_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=unknown",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert fallback_response.status == 200
    fallback_payload = await fallback_response.json()
    assert fallback_payload["data"]["view"] == "hotspots"
    assert data["items"]
    assert data["items"][0]["message_count"] >= 1
    assert data["items"][0]["last_message_preview"]
    assert data["items"][0]["waiting_state"] == "awaiting_admin"
    assert data["items"][0]["action_lane_key"] == "reply_now"
    assert data["items"][0]["escalation_lane_key"] == "technical_watch"
    assert data["items"][0]["triage_pack_key"] == "open:technical"
    assert data["items"][0]["triage_pack_label"]
    assert data["items"][0]["triage_route_label"]
    assert data["items"][0]["triage_sample_titles"]
    assert data["items"][0]["is_stale"] is True


async def test_admin_snapshot_backed_endpoints_prefer_snapshots_after_refresh(
    webapp_runtime,
) -> None:
    client, settings, session_factory = webapp_runtime
    refresh_time = datetime.now(UTC).replace(microsecond=0)
    async with session_factory() as session:
        await refresh_admin_read_models(
            session,
            settings=settings,
            now=refresh_time,
            force=True,
        )

    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})
    urls = [
        f"{settings.mini_app_path}/api/admin/summary",
        f"{settings.mini_app_path}/api/admin/dashboard",
        f"{settings.mini_app_path}/api/admin/dashboard?sections=summary,channels",
        f"{settings.mini_app_path}/api/admin/conversion",
        f"{settings.mini_app_path}/api/admin/acquisition",
        f"{settings.mini_app_path}/api/admin/promo-referrals",
        f"{settings.mini_app_path}/api/admin/pricing",
        f"{settings.mini_app_path}/api/admin/read-models?limit=5",
        f"{settings.mini_app_path}/api/admin/lifecycle?view=rules&limit=5",
        f"{settings.mini_app_path}/api/admin/support/insights?view=hotspots&limit=5",
    ]
    for url in urls:
        response = await client.get(url, headers={"X-Telegram-Init-Data": admin_init_data})
        assert response.status == 200
        payload = await response.json()
        assert payload["data"]["source"] == "snapshot"
        assert isinstance(payload["data"]["build_duration_ms"], int)
        assert payload["data"]["staleness_seconds"] >= 0
        assert "generated_at" in payload["data"]


async def test_admin_snapshot_summary_includes_read_model_focus_digest_and_operator_summary(webapp_runtime) -> None:
    client, settings, session_factory = webapp_runtime
    refresh_time = datetime.now(UTC).replace(microsecond=0)
    async with session_factory() as session:
        await refresh_admin_read_models(
            session,
            settings=settings,
            now=refresh_time,
            force=True,
        )

    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})

    summary_response = await client.get(
        f"{settings.mini_app_path}/api/admin/summary",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert summary_response.status == 200
    summary_payload = await summary_response.json()
    assert summary_payload["data"]["source"] == "snapshot"
    assert "read_model_focus" in summary_payload["data"]
    assert summary_payload["data"]["read_model_focus"]["line"]
    assert summary_payload["data"]["read_model_focus"]["tracked_count"] > 0
    assert "read_model_operator_summary" in summary_payload["data"]
    assert summary_payload["data"]["read_model_operator_summary"]["summary_line"]
    assert summary_payload["data"]["read_model_operator_summary"]["focus_line"]
    assert "read_model_digest" in summary_payload["data"]
    assert summary_payload["data"]["read_model_digest"]["watch_summary_line"]
    assert summary_payload["data"]["read_model_digest"]["action_summary_line"]

    dashboard_response = await client.get(
        f"{settings.mini_app_path}/api/admin/dashboard?sections=summary",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert dashboard_response.status == 200
    dashboard_payload = await dashboard_response.json()
    assert dashboard_payload["data"]["source"] == "snapshot"
    assert "summary" in dashboard_payload["data"]
    assert "read_model_focus" in dashboard_payload["data"]["summary"]
    assert dashboard_payload["data"]["summary"]["read_model_focus"]["line"]
    assert "read_model_operator_summary" in dashboard_payload["data"]["summary"]
    assert dashboard_payload["data"]["summary"]["read_model_operator_summary"]["summary_line"]
    assert dashboard_payload["data"]["summary"]["read_model_operator_summary"]["focus_line"]
    assert "read_model_digest" in dashboard_payload["data"]["summary"]
    assert dashboard_payload["data"]["summary"]["read_model_digest"]["watch_summary_line"]
    assert dashboard_payload["data"]["summary"]["read_model_digest"]["action_summary_line"]


async def test_admin_snapshot_endpoints_allow_live_refresh_override(webapp_runtime) -> None:
    client, settings, session_factory = webapp_runtime
    refresh_time = datetime.now(UTC).replace(microsecond=0)
    async with session_factory() as session:
        await refresh_admin_read_models(
            session,
            settings=settings,
            now=refresh_time,
            force=True,
        )

    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})
    response = await client.get(
        f"{settings.mini_app_path}/api/admin/lifecycle?view=rules&limit=5&source=live",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert response.status == 200
    payload = await response.json()
    assert payload["data"]["source"] == "live"

    stale_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support?status=open&queue=stale",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert stale_response.status == 200
    stale_payload = await stale_response.json()
    assert stale_payload["data"]["queue"] == "stale"
    assert stale_payload["data"]["total_items"] == 2
    assert all(item["is_stale"] for item in stale_payload["data"]["items"])

    priority_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support?status=open&queue=priority_high",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert priority_response.status == 200
    priority_payload = await priority_response.json()
    assert priority_payload["data"]["queue"] == "priority_high"
    assert priority_payload["data"]["total_items"] == 2

    breach_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support?status=open&queue=sla_breach",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert breach_response.status == 200
    breach_payload = await breach_response.json()
    assert breach_payload["data"]["queue"] == "sla_breach"
    assert breach_payload["data"]["total_items"] == 2


async def test_admin_support_ticket_detail_includes_profile_and_payments(webapp_runtime) -> None:
    client, settings, session_factory = webapp_runtime
    regular_init_data = _build_init_data({"id": 42, "first_name": "Ruslan", "username": "ruslan"})
    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})

    async with session_factory() as session:
        ticket_result = await session.execute(
            select(SupportTicket.id).where(SupportTicket.category == "payment").limit(1)
        )
        ticket_id = ticket_result.scalar_one()

    forbidden_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/{ticket_id}",
        headers={"X-Telegram-Init-Data": regular_init_data},
    )
    assert forbidden_response.status == 403

    response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/{ticket_id}",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert response.status == 200
    payload = await response.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["ticket"]["id"] == ticket_id
    assert data["ticket"]["waiting_state"] == "awaiting_admin"
    assert data["ticket"]["action_lane_key"] == "reply_now"
    assert data["ticket"]["escalation_lane_key"] == "payment_blocker"
    assert data["ticket"]["triage_pack_key"] == "open:payment"
    assert data["ticket"]["triage_pack_label"]
    assert data["ticket"]["triage_route_label"]
    assert data["ticket"]["triage_sample_titles"]
    assert data["ticket"]["is_stale"] is True
    assert data["next_action"]["key"] == "reply_now"
    assert data["next_action"]["label"] == data["ticket"]["action_lane_label"]
    assert data["next_action"]["severity"] == "warn"
    assert "Платёжный блокер" in data["next_action"]["note"]
    assert data["profile"]["telegram_id"] == 42
    assert data["profile"]["current_tariff_label"]
    assert data["profile"]["current_channel_label"]
    assert data["payments_preview"]
    assert data["pinned_context"]["sla_bucket_label"]
    assert data["pinned_context"]["latest_payment_amount_label"]
    assert data["pinned_context"]["next_action_label"] == data["next_action"]["label"]
    assert "Платёжный блокер" in data["pinned_context"]["next_action_note"]
    assert data["pinned_context"]["triage_pack_key"] == "open:payment"
    assert data["pinned_context"]["triage_pack_label"] == data["ticket"]["triage_pack_label"]
    assert data["pinned_context"]["triage_route_label"] == data["ticket"]["triage_route_label"]
    assert data["pinned_context"]["triage_sample_titles"]
    assert data["pinned_context"]["triage_batch_count"] == 1
    assert data["pinned_context"]["triage_batch_sample_ticket_ids"] == [ticket_id]
    assert data["pinned_context"]["triage_primary_reply_title"]
    assert data["pinned_context"]["triage_batch_note"]
    assert data["triage_batch"]["key"] == "payment_blocker:reply_now:open:payment"
    assert data["triage_batch"]["count"] == 1
    assert data["triage_batch"]["primary_reply_key"] == "payment_ack_review"
    assert data["triage_batch"]["sample_ticket_ids"] == [ticket_id]
    assert data["triage_batch"]["suggested_replies"]
    assert data["operator_hints"]
    assert {item["key"] for item in data["operator_hints"]} >= {
        "reply_now",
        "payment_review",
        "high_priority_watch",
    }
    assert data["suggested_replies"]
    assert {item["key"] for item in data["suggested_replies"]} >= {
        "payment_ack_review",
        "payment_request_receipt",
    }
    assert any(item["kind"] == "resolve" for item in data["suggested_replies"])
    assert data["messages"][0]["body"] == "Payment is not visible"
    assert data["actions"]["user_query"] == "42"
    assert data["actions"]["payments_query"] == "42"
    assert data["actions"]["triage_confirm_key"] == "payment_blocker:reply_now:open:payment"


async def test_admin_support_triage_confirm_action_returns_preview_and_writes_audit_log(
    webapp_runtime,
) -> None:
    client, settings, session_factory = webapp_runtime
    regular_init_data = _build_init_data({"id": 42, "first_name": "Ruslan", "username": "ruslan"})
    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})

    forbidden_response = await client.post(
        f"{settings.mini_app_path}/api/admin/actions/support-triage-confirm",
        headers={"X-Telegram-Init-Data": regular_init_data, "Content-Type": "application/json"},
        json={"triage_key": "payment_blocker:reply_now:open:payment", "ticket_id": 1},
    )
    assert forbidden_response.status == 403

    response = await client.post(
        f"{settings.mini_app_path}/api/admin/actions/support-triage-confirm",
        headers={"X-Telegram-Init-Data": admin_init_data, "Content-Type": "application/json"},
        json={"triage_key": "payment_blocker:reply_now:open:payment", "ticket_id": 1},
    )
    assert response.status == 200
    payload = await response.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["preview_only"] is True
    assert data["key"] == "payment_blocker:reply_now:open:payment"
    assert data["confirm_mode"] == "preview_only"
    assert data["pack_key"] == "open:payment"
    assert data["route_key"] == "payment_blocker:reply_now"
    assert data["focused_ticket_id"] == 1
    assert data["primary_reply"]["key"] == "payment_ack_review"
    assert data["sample_ticket_ids"] == [1]
    assert data["sample_tickets"]
    assert data["sample_tickets"][0]["id"] == 1
    assert data["operator_steps"]
    assert data["operator_steps"][0]["key"] == "review_scope"
    assert "read-only confirmation" in data["confirm_note"]
    assert data["confirm_token"]
    assert data["confirm_token_expires_at_label"]
    assert data["apply_limit"] == 3
    assert data["apply_reply_key"] == "payment_ack_review"
    assert data["allowed_reply_keys"]
    assert "payment_ack_review" in data["allowed_reply_keys"]

    async with session_factory() as session:
        result = await session.execute(
            select(AuditLog).where(
                AuditLog.action == "webapp_admin_support_triage_confirm_preview"
            )
        )
        records = list(result.scalars())
    assert len(records) == 1
    assert records[0].actor_user_id is not None


async def test_admin_support_triage_apply_action_replies_and_notifies(
    monkeypatch: pytest.MonkeyPatch,
    webapp_runtime,
) -> None:
    client, settings, session_factory = webapp_runtime
    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})
    sent_messages: list[tuple[int, str]] = []

    async def fake_send_message(self, chat_id: int, text: str):
        sent_messages.append((chat_id, text))
        return None

    monkeypatch.setattr(Bot, "send_message", fake_send_message)

    preview_response = await client.post(
        f"{settings.mini_app_path}/api/admin/actions/support-triage-confirm",
        headers={"X-Telegram-Init-Data": admin_init_data, "Content-Type": "application/json"},
        json={"triage_key": "payment_blocker:reply_now:open:payment", "ticket_id": 1},
    )
    assert preview_response.status == 200
    preview_payload = await preview_response.json()
    confirm_token = preview_payload["data"]["confirm_token"]

    response = await client.post(
        f"{settings.mini_app_path}/api/admin/actions/support-triage-apply",
        headers={"X-Telegram-Init-Data": admin_init_data, "Content-Type": "application/json"},
        json={
            "triage_key": "payment_blocker:reply_now:open:payment",
            "confirm_token": confirm_token,
            "reply_key": "payment_ack_review",
            "ticket_id": 1,
        },
    )
    assert response.status == 200
    payload = await response.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["applied"] is True
    assert data["preview_only"] is False
    assert data["applied_count"] == 1
    assert data["applied_ticket_ids"] == [1]
    assert data["focused_ticket_id"] == 1
    assert data["route_key"] == "payment_blocker:reply_now"
    assert data["reply"]["key"] == "payment_ack_review"
    assert data["notified_count"] == 1
    assert data["notification_error_count"] == 0
    assert data["sample_tickets"]
    assert data["sample_tickets"][0]["id"] == 1

    history_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=triage_apply_history&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert history_response.status == 200
    history_payload = await history_response.json()
    assert history_payload["data"]["view"] == "triage_apply_history"
    assert "triage_apply_history" in {
        item["key"] for item in history_payload["data"]["available_views"]
    }
    assert history_payload["data"]["triage_apply_summary"]["top_reply_key"] == "payment_ack_review"
    assert history_payload["data"]["triage_apply_summary"]["top_count"] == 1
    assert history_payload["data"]["items"][0]["reply_key"] == "payment_ack_review"
    assert history_payload["data"]["items"][0]["ticket_ids"] == [1]
    assert history_payload["data"]["items"][0]["actor_label"] == "Owner"

    route_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=triage_apply_routes&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert route_response.status == 200
    route_payload = await route_response.json()
    assert route_payload["data"]["view"] == "triage_apply_routes"
    assert "triage_apply_routes" in {
        item["key"] for item in route_payload["data"]["available_views"]
    }
    assert (
        route_payload["data"]["triage_apply_route_summary"]["top_route_key"]
        == "payment_blocker:reply_now"
    )
    assert (
        route_payload["data"]["triage_apply_route_summary"]["top_reply_key"]
        == "payment_ack_review"
    )
    assert route_payload["data"]["triage_apply_route_summary"]["top_ticket_count"] == 1
    assert route_payload["data"]["items"][0]["route_key"] == "payment_blocker:reply_now"
    assert route_payload["data"]["items"][0]["pack_key"] == "open:payment"
    assert route_payload["data"]["items"][0]["reply_key"] == "payment_ack_review"
    assert route_payload["data"]["items"][0]["sample_ticket_ids"] == [1]
    assert route_payload["data"]["items"][0]["top_actor_label"] == "Owner"

    actor_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=triage_apply_actors&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert actor_response.status == 200
    actor_payload = await actor_response.json()
    assert actor_payload["data"]["view"] == "triage_apply_actors"
    assert "triage_apply_actors" in {
        item["key"] for item in actor_payload["data"]["available_views"]
    }
    assert actor_payload["data"]["triage_apply_actor_summary"]["top_actor_label"] == "Owner"
    assert (
        actor_payload["data"]["triage_apply_actor_summary"]["top_route_key"]
        == "payment_blocker:reply_now"
    )
    assert (
        actor_payload["data"]["triage_apply_actor_summary"]["top_reply_key"]
        == "payment_ack_review"
    )
    assert actor_payload["data"]["triage_apply_actor_summary"]["top_ticket_count"] == 1
    assert actor_payload["data"]["items"][0]["actor_label"] == "Owner"
    assert actor_payload["data"]["items"][0]["top_route_key"] == "payment_blocker:reply_now"
    assert actor_payload["data"]["items"][0]["top_reply_key"] == "payment_ack_review"
    assert actor_payload["data"]["items"][0]["sample_ticket_ids"] == [1]

    reply_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=triage_apply_replies&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert reply_response.status == 200
    reply_payload = await reply_response.json()
    assert reply_payload["data"]["view"] == "triage_apply_replies"
    assert "triage_apply_replies" in {
        item["key"] for item in reply_payload["data"]["available_views"]
    }
    assert (
        reply_payload["data"]["triage_apply_reply_summary"]["top_reply_key"]
        == "payment_ack_review"
    )
    assert (
        reply_payload["data"]["triage_apply_reply_summary"]["top_actor_label"]
        == "Owner"
    )
    assert (
        reply_payload["data"]["triage_apply_reply_summary"]["top_route_key"]
        == "payment_blocker:reply_now"
    )
    assert reply_payload["data"]["triage_apply_reply_summary"]["top_ticket_count"] == 1
    assert reply_payload["data"]["items"][0]["reply_key"] == "payment_ack_review"
    assert reply_payload["data"]["items"][0]["top_actor_label"] == "Owner"
    assert reply_payload["data"]["items"][0]["top_route_key"] == "payment_blocker:reply_now"
    assert reply_payload["data"]["items"][0]["sample_ticket_ids"] == [1]

    actor_reply_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=triage_apply_actor_replies&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert actor_reply_response.status == 200
    actor_reply_payload = await actor_reply_response.json()
    assert actor_reply_payload["data"]["view"] == "triage_apply_actor_replies"
    assert "triage_apply_actor_replies" in {
        item["key"] for item in actor_reply_payload["data"]["available_views"]
    }
    assert (
        actor_reply_payload["data"]["triage_apply_actor_reply_summary"]["top_actor_label"]
        == "Owner"
    )
    assert (
        actor_reply_payload["data"]["triage_apply_actor_reply_summary"]["top_reply_key"]
        == "payment_ack_review"
    )
    assert (
        actor_reply_payload["data"]["triage_apply_actor_reply_summary"]["top_route_key"]
        == "payment_blocker:reply_now"
    )
    assert actor_reply_payload["data"]["triage_apply_actor_reply_summary"]["top_ticket_count"] == 1
    assert actor_reply_payload["data"]["items"][0]["actor_label"] == "Owner"
    assert actor_reply_payload["data"]["items"][0]["reply_key"] == "payment_ack_review"
    assert actor_reply_payload["data"]["items"][0]["top_route_key"] == "payment_blocker:reply_now"
    assert actor_reply_payload["data"]["items"][0]["sample_ticket_ids"] == [1]

    route_actor_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=triage_apply_route_actors&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert route_actor_response.status == 200
    route_actor_payload = await route_actor_response.json()
    assert route_actor_payload["data"]["view"] == "triage_apply_route_actors"
    assert "triage_apply_route_actors" in {
        item["key"] for item in route_actor_payload["data"]["available_views"]
    }
    assert (
        route_actor_payload["data"]["triage_apply_route_actor_summary"]["top_route_key"]
        == "payment_blocker:reply_now"
    )
    assert (
        route_actor_payload["data"]["triage_apply_route_actor_summary"]["top_actor_label"]
        == "Owner"
    )
    assert (
        route_actor_payload["data"]["triage_apply_route_actor_summary"]["top_reply_key"]
        == "payment_ack_review"
    )
    assert route_actor_payload["data"]["triage_apply_route_actor_summary"]["top_ticket_count"] == 1
    assert route_actor_payload["data"]["items"][0]["route_key"] == "payment_blocker:reply_now"
    assert route_actor_payload["data"]["items"][0]["actor_label"] == "Owner"
    assert route_actor_payload["data"]["items"][0]["top_reply_key"] == "payment_ack_review"
    assert route_actor_payload["data"]["items"][0]["sample_ticket_ids"] == [1]

    reply_pack_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=triage_apply_reply_packs&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert reply_pack_response.status == 200
    reply_pack_payload = await reply_pack_response.json()
    assert reply_pack_payload["data"]["view"] == "triage_apply_reply_packs"
    assert "triage_apply_reply_packs" in {
        item["key"] for item in reply_pack_payload["data"]["available_views"]
    }
    assert (
        reply_pack_payload["data"]["triage_apply_reply_pack_summary"]["top_reply_key"]
        == "payment_ack_review"
    )
    assert (
        reply_pack_payload["data"]["triage_apply_reply_pack_summary"]["top_pack_key"]
        == "open:payment"
    )
    assert (
        reply_pack_payload["data"]["triage_apply_reply_pack_summary"]["top_route_key"]
        == "payment_blocker:reply_now"
    )
    assert (
        reply_pack_payload["data"]["triage_apply_reply_pack_summary"]["top_actor_label"]
        == "Owner"
    )
    assert reply_pack_payload["data"]["triage_apply_reply_pack_summary"]["top_ticket_count"] == 1
    assert reply_pack_payload["data"]["items"][0]["reply_key"] == "payment_ack_review"
    assert reply_pack_payload["data"]["items"][0]["pack_key"] == "open:payment"
    assert reply_pack_payload["data"]["items"][0]["top_route_key"] == "payment_blocker:reply_now"
    assert reply_pack_payload["data"]["items"][0]["sample_ticket_ids"] == [1]

    route_reply_actor_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=triage_apply_route_reply_actors&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert route_reply_actor_response.status == 200
    route_reply_actor_payload = await route_reply_actor_response.json()
    assert route_reply_actor_payload["data"]["view"] == "triage_apply_route_reply_actors"
    assert "triage_apply_route_reply_actors" in {
        item["key"] for item in route_reply_actor_payload["data"]["available_views"]
    }
    assert (
        route_reply_actor_payload["data"]["triage_apply_route_reply_actor_summary"]["top_route_key"]
        == "payment_blocker:reply_now"
    )
    assert (
        route_reply_actor_payload["data"]["triage_apply_route_reply_actor_summary"]["top_reply_key"]
        == "payment_ack_review"
    )
    assert (
        route_reply_actor_payload["data"]["triage_apply_route_reply_actor_summary"]["top_actor_label"]
        == "Owner"
    )
    assert (
        route_reply_actor_payload["data"]["triage_apply_route_reply_actor_summary"]["top_pack_key"]
        == "open:payment"
    )
    assert (
        route_reply_actor_payload["data"]["triage_apply_route_reply_actor_summary"]["top_ticket_count"]
        == 1
    )
    assert route_reply_actor_payload["data"]["items"][0]["route_key"] == "payment_blocker:reply_now"
    assert route_reply_actor_payload["data"]["items"][0]["reply_key"] == "payment_ack_review"
    assert route_reply_actor_payload["data"]["items"][0]["actor_label"] == "Owner"
    assert route_reply_actor_payload["data"]["items"][0]["sample_ticket_ids"] == [1]

    focus_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=triage_apply_focus&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert focus_response.status == 200
    focus_payload = await focus_response.json()
    assert focus_payload["data"]["view"] == "triage_apply_focus"
    assert "triage_apply_focus" in {
        item["key"] for item in focus_payload["data"]["available_views"]
    }
    assert (
        focus_payload["data"]["triage_apply_focus_summary"]["top_source_key"]
        == "route_reply_actor"
    )
    assert (
        focus_payload["data"]["triage_apply_focus_summary"]["top_source_label"]
        == "Route x reply x actor"
    )
    assert focus_payload["data"]["triage_apply_focus_summary"]["top_ticket_count"] == 1
    assert focus_payload["data"]["triage_apply_focus_summary"]["top_focus_score"] == 110
    assert (
        focus_payload["data"]["triage_apply_focus_summary"]["top_sample_ticket_ids"] == [1]
    )
    assert focus_payload["data"]["items"][0]["source_key"] == "route_reply_actor"
    assert focus_payload["data"]["items"][0]["apply_count"] == 1
    assert focus_payload["data"]["items"][0]["ticket_count"] == 1
    assert focus_payload["data"]["items"][0]["focus_score"] == 110
    assert focus_payload["data"]["items"][0]["sample_ticket_ids"] == [1]
    assert "проверку оплаты" in focus_payload["data"]["items"][0]["title"].lower()

    effectiveness_response = await client.get(
        f"{settings.mini_app_path}/api/admin/support/insights?view=triage_apply_effectiveness&limit=2",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )
    assert effectiveness_response.status == 200
    effectiveness_payload = await effectiveness_response.json()
    assert effectiveness_payload["data"]["view"] == "triage_apply_effectiveness"
    assert "triage_apply_effectiveness" in {
        item["key"] for item in effectiveness_payload["data"]["available_views"]
    }
    assert (
        effectiveness_payload["data"]["triage_apply_effectiveness_summary"]["top_source_key"]
        == "route_reply_actor"
    )
    assert (
        effectiveness_payload["data"]["triage_apply_effectiveness_summary"]["top_source_label"]
        == "Route x reply x actor"
    )
    assert (
        effectiveness_payload["data"]["triage_apply_effectiveness_summary"]["top_route_key"]
        == "payment_blocker:reply_now"
    )
    assert (
        effectiveness_payload["data"]["triage_apply_effectiveness_summary"]["top_reply_key"]
        == "payment_ack_review"
    )
    assert (
        effectiveness_payload["data"]["triage_apply_effectiveness_summary"]["top_actor_label"]
        == "Owner"
    )
    assert (
        effectiveness_payload["data"]["triage_apply_effectiveness_summary"]["top_pack_key"]
        == "open:payment"
    )
    assert (
        effectiveness_payload["data"]["triage_apply_effectiveness_summary"]["top_ticket_count"]
        == 1
    )
    assert (
        effectiveness_payload["data"]["triage_apply_effectiveness_summary"]["top_coverage_count"]
        == 1
    )
    assert (
        effectiveness_payload["data"]["triage_apply_effectiveness_summary"]["top_effectiveness_score"]
        == 155
    )
    assert (
        effectiveness_payload["data"]["triage_apply_effectiveness_summary"]["top_sample_ticket_ids"]
        == [1]
    )
    assert effectiveness_payload["data"]["items"][0]["source_key"] == "route_reply_actor"
    assert effectiveness_payload["data"]["items"][0]["route_key"] == "payment_blocker:reply_now"
    assert effectiveness_payload["data"]["items"][0]["reply_key"] == "payment_ack_review"
    assert effectiveness_payload["data"]["items"][0]["actor_label"] == "Owner"
    assert effectiveness_payload["data"]["items"][0]["pack_key"] == "open:payment"
    assert effectiveness_payload["data"]["items"][0]["coverage_count"] == 1
    assert effectiveness_payload["data"]["items"][0]["effectiveness_score"] == 155
    assert effectiveness_payload["data"]["items"][0]["sample_ticket_ids"] == [1]

    async with session_factory() as session:
        ticket = await session.get(SupportTicket, 1)
        assert ticket is not None
        assert ticket.last_admin_message_at is not None
        result = await session.execute(
            select(SupportMessage)
            .where(SupportMessage.ticket_id == 1, SupportMessage.is_admin.is_(True))
            .order_by(SupportMessage.id.desc())
        )
        replies = list(result.scalars())
        assert replies
        assert replies[0].body.startswith("Вижу тикет по оплате")
        audit_result = await session.execute(
            select(AuditLog).where(AuditLog.action == "webapp_admin_support_triage_apply")
        )
        audit_records = list(audit_result.scalars())
    assert len(audit_records) == 1
    assert len(sent_messages) == 1
    assert sent_messages[0][0] == 42
    assert "Ответ по обращению #1" in sent_messages[0][1]


async def test_admin_support_triage_apply_action_rejects_invalid_token(
    webapp_runtime,
) -> None:
    client, settings, _ = webapp_runtime
    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})

    response = await client.post(
        f"{settings.mini_app_path}/api/admin/actions/support-triage-apply",
        headers={"X-Telegram-Init-Data": admin_init_data, "Content-Type": "application/json"},
        json={
            "triage_key": "payment_blocker:reply_now:open:payment",
            "confirm_token": "broken.token",
            "reply_key": "payment_ack_review",
            "ticket_id": 1,
        },
    )
    assert response.status == 400
    payload = await response.json()
    assert payload["ok"] is False
    assert payload["error"] == "invalid_confirm_token"


async def test_admin_support_triage_apply_action_accepts_allowed_reply_key(
    monkeypatch: pytest.MonkeyPatch,
    webapp_runtime,
) -> None:
    client, settings, session_factory = webapp_runtime
    admin_init_data = _build_init_data({"id": 1, "first_name": "Owner", "username": "owner"})

    async def fake_send_message(self, chat_id: int, text: str):
        return None

    monkeypatch.setattr(Bot, "send_message", fake_send_message)

    preview_response = await client.post(
        f"{settings.mini_app_path}/api/admin/actions/support-triage-confirm",
        headers={"X-Telegram-Init-Data": admin_init_data, "Content-Type": "application/json"},
        json={"triage_key": "payment_blocker:reply_now:open:payment", "ticket_id": 1},
    )
    preview_payload = await preview_response.json()
    confirm_token = preview_payload["data"]["confirm_token"]

    response = await client.post(
        f"{settings.mini_app_path}/api/admin/actions/support-triage-apply",
        headers={"X-Telegram-Init-Data": admin_init_data, "Content-Type": "application/json"},
        json={
            "triage_key": "payment_blocker:reply_now:open:payment",
            "confirm_token": confirm_token,
            "reply_key": "payment_request_receipt",
            "ticket_id": 1,
        },
    )
    assert response.status == 200
    payload = await response.json()
    assert payload["data"]["reply"]["key"] == "payment_request_receipt"

    async with session_factory() as session:
        result = await session.execute(
            select(SupportMessage)
            .where(SupportMessage.ticket_id == 1, SupportMessage.is_admin.is_(True))
            .order_by(SupportMessage.id.desc())
        )
        replies = list(result.scalars())
    assert replies
    assert replies[0].body.startswith("Пришли, пожалуйста, скрин оплаты")


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
                            label="Bot administrator",
                            ok=True,
                            details="ok",
                        ),
                    ),
                    recommendations=("All good",),
                ),
            ),
        )

    monkeypatch.setattr(
        web_admin_dashboard_directory,
        "build_channel_diagnostics_report",
        fake_report,
    )
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
