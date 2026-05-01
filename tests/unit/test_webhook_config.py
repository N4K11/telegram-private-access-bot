from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.config import RuntimeConfigurationError, Settings
from app.webhook.server import delete_telegram_webhook, set_telegram_webhook


def _webhook_settings(**overrides: object) -> Settings:
    payload: dict[str, object] = {
        "bot_token": "123456789:token",
        "admin_ids": [1],
        "use_webhook": True,
        "public_webhook_url": "https://example.com/base/",
        "webhook_secret_token": "secret-token",
    }
    payload.update(overrides)
    return Settings.model_validate(payload)


def test_webhook_runtime_requires_public_webhook_url() -> None:
    settings = _webhook_settings(public_webhook_url=None)

    with pytest.raises(RuntimeConfigurationError, match="PUBLIC_WEBHOOK_URL"):
        settings.require_runtime_ready()


def test_webhook_runtime_requires_secret_token() -> None:
    settings = _webhook_settings(webhook_secret_token=None)

    with pytest.raises(RuntimeConfigurationError, match="WEBHOOK_SECRET_TOKEN"):
        settings.require_runtime_ready()


def test_webhook_path_normalizes_and_builds_resolved_url() -> None:
    settings = _webhook_settings(webhook_path="telegram/webhook")

    assert settings.webhook_path == "/telegram/webhook"
    assert settings.webhook_url == "https://example.com/base/telegram/webhook"


async def test_set_telegram_webhook_uses_resolved_runtime_settings() -> None:
    settings = _webhook_settings(webhook_path="telegram/webhook")
    bot = SimpleNamespace(set_webhook=AsyncMock())
    dispatcher = SimpleNamespace(resolve_used_update_types=Mock(return_value=["message"]))

    await set_telegram_webhook(bot=bot, dispatcher=dispatcher, settings=settings)

    bot.set_webhook.assert_awaited_once_with(
        url="https://example.com/base/telegram/webhook",
        allowed_updates=["message"],
        secret_token="secret-token",
        drop_pending_updates=False,
    )


async def test_delete_telegram_webhook_honors_shutdown_flag() -> None:
    disabled = _webhook_settings(delete_webhook_on_shutdown=False)
    enabled = _webhook_settings(delete_webhook_on_shutdown=True)
    bot = SimpleNamespace(delete_webhook=AsyncMock())

    await delete_telegram_webhook(bot=bot, settings=disabled)
    bot.delete_webhook.assert_not_awaited()

    await delete_telegram_webhook(bot=bot, settings=enabled)
    bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=False)
