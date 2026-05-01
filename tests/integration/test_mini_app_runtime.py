from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.base import Base
from app.db.models import Channel, Payment, Subscription, Tariff, User
from app.db.session import create_async_engine, create_session_factory
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
    tmp_path: Path,
) -> AsyncIterator[tuple[TestClient, Settings, async_sessionmaker[AsyncSession]]]:
    database_path = tmp_path / "webapp-runtime.db"
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
        session.add_all([user, other_user])
        await session.flush()

        channel = Channel(
            telegram_chat_id=-1001234567890,
            title="Private channel",
            invite_users_permission=True,
            ban_users_permission=True,
            is_active=True,
        )
        session.add(channel)
        await session.flush()

        tariff = Tariff(
            name="VIP 30",
            description="Main paid plan",
            price_stars=250,
            duration_days=30,
            sort_order=10,
            is_active=True,
            channel_id=channel.id,
        )
        session.add(tariff)
        await session.flush()

        session.add(
            Subscription(
                user_id=user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                status="active",
                source="purchase",
                started_at=datetime(2026, 4, 1, 10, 0, tzinfo=UTC),
                expires_at=datetime(2026, 5, 20, 10, 0, tzinfo=UTC),
            )
        )
        session.add(
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
            )
        )
        await session.commit()

    settings = Settings.model_validate(
        {
            "bot_token": BOT_TOKEN,
            "admin_ids": [1],
            "database_url": f"sqlite+aiosqlite:///{database_path.as_posix()}",
            "backup_directory": str(tmp_path / "backups"),
            "use_webhook": True,
            "public_webhook_url": "https://example.com",
            "webhook_secret_token": "telegram-secret",
            "webhook_path": "/telegram/webhook",
            "mini_app_path": "/cabinet",
            "mini_app_auth_max_age_seconds": 3600,
        }
    )
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
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


async def test_mini_app_page_is_served(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime

    response = await client.get(settings.mini_app_path)

    assert response.status == 200
    text = await response.text()
    assert "Telegram Mini App" in text
    assert "Кабинет доступа" in text


async def test_auth_endpoint_accepts_valid_init_data(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    init_data = _build_init_data(
        {"id": 42, "first_name": "Ruslan", "username": "ruslan"}
    )

    response = await client.post(
        f"{settings.mini_app_path}/api/auth",
        json={"init_data": init_data},
    )

    assert response.status == 200
    payload = await response.json()
    assert payload["ok"] is True
    assert payload["user"]["telegram_id"] == 42
    assert payload["user"]["is_admin"] is False


async def test_bootstrap_returns_own_data(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    init_data = _build_init_data(
        {"id": 42, "first_name": "Ruslan", "username": "ruslan"}
    )

    response = await client.get(
        f"{settings.mini_app_path}/api/bootstrap",
        headers={"X-Telegram-Init-Data": init_data},
    )

    assert response.status == 200
    payload = await response.json()
    assert payload["ok"] is True
    assert payload["data"]["viewer"]["telegram_id"] == 42
    assert payload["data"]["profile"]["has_active_subscription"] is True
    assert payload["data"]["tariffs"][0]["name"] == "VIP 30"


async def test_user_cannot_access_another_users_profile(webapp_runtime) -> None:
    client, settings, _ = webapp_runtime
    init_data = _build_init_data(
        {"id": 42, "first_name": "Ruslan", "username": "ruslan"}
    )

    response = await client.get(
        f"{settings.mini_app_path}/api/users/77/profile",
        headers={"X-Telegram-Init-Data": init_data},
    )

    assert response.status == 403
    assert await response.json() == {"ok": False, "error": "forbidden"}


async def test_admin_summary_is_protected_and_available_for_admin(
    webapp_runtime,
) -> None:
    client, settings, _ = webapp_runtime
    regular_init_data = _build_init_data(
        {"id": 42, "first_name": "Ruslan", "username": "ruslan"}
    )
    regular_response = await client.get(
        f"{settings.mini_app_path}/api/admin/summary",
        headers={"X-Telegram-Init-Data": regular_init_data},
    )
    assert regular_response.status == 403

    admin_init_data = _build_init_data(
        {"id": 1, "first_name": "Owner", "username": "owner"}
    )
    admin_response = await client.get(
        f"{settings.mini_app_path}/api/admin/summary",
        headers={"X-Telegram-Init-Data": admin_init_data},
    )

    assert admin_response.status == 200
    payload = await admin_response.json()
    assert payload["ok"] is True
    assert payload["data"]["total_users"] >= 2
    assert "revenue_total" in payload["data"]
