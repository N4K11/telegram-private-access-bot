from __future__ import annotations

from pathlib import Path

import pytest_asyncio
from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message
from aiohttp.test_utils import TestClient, TestServer

from app.config import Settings
from app.webhook.server import build_webhook_app


@pytest_asyncio.fixture
async def webhook_runtime(workspace_tmp_path: Path):
    seen_messages: list[str] = []
    router = Router()

    @router.message()
    async def capture_message(message: Message) -> None:
        seen_messages.append(message.text or "")

    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    settings = Settings.model_validate(
        {
            "bot_token": "123456789:token",
            "admin_ids": [1],
            "database_url": "sqlite+aiosqlite:///:memory:",
            "backup_directory": str(workspace_tmp_path / "backups"),
            "use_webhook": True,
            "public_webhook_url": "https://example.com",
            "webhook_secret_token": "secret-token",
            "webhook_path": "/telegram/webhook",
        }
    )
    bot = Bot(
        token="123456789:token",
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    app = build_webhook_app(bot=bot, dispatcher=dispatcher, settings=settings)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        yield client, settings, seen_messages
    finally:
        await client.close()
        await bot.session.close()


def _message_update(text: str) -> dict[str, object]:
    return {
        "update_id": 1000,
        "message": {
            "message_id": 10,
            "date": 1,
            "chat": {"id": 42, "type": "private", "first_name": "Test"},
            "from": {"id": 42, "is_bot": False, "first_name": "Test"},
            "text": text,
        },
    }


async def test_valid_webhook_update_is_dispatched(webhook_runtime) -> None:
    client, settings, seen_messages = webhook_runtime

    response = await client.post(
        settings.webhook_path,
        json=_message_update("ping"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret-token"},
    )

    assert response.status == 200
    assert await response.json() == {"ok": True}
    assert seen_messages == ["ping"]


async def test_invalid_secret_is_rejected(webhook_runtime) -> None:
    client, settings, seen_messages = webhook_runtime

    response = await client.post(
        settings.webhook_path,
        json=_message_update("blocked"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-token"},
    )

    assert response.status == 401
    assert await response.json() == {"ok": False, "error": "unauthorized"}
    assert seen_messages == []


async def test_healthz_endpoint_is_ok(webhook_runtime) -> None:
    client, _, _ = webhook_runtime

    response = await client.get("/healthz")

    assert response.status == 200
    payload = await response.json()
    assert payload["status"] == "ok"
    assert payload["mode"] == "webhook"


async def test_readyz_endpoint_is_ok(webhook_runtime) -> None:
    client, _, _ = webhook_runtime

    response = await client.get("/readyz")

    assert response.status == 200
    assert await response.json() == {"status": "ok"}
