from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.methods import TelegramMethod
from aiogram.types import Update
from aiohttp import web

from app.config import Settings
from app.healthcheck import run_healthcheck
from app.runtime_state import snapshot_runtime_state
from app.services.payments.crypto_pay import (
    CryptoPayError,
    process_crypto_pay_webhook_update,
    verify_crypto_pay_webhook_signature,
)

from .app_keys import (
    BOT_APP_KEY,
    DISPATCHER_APP_KEY,
    SESSION_FACTORY_APP_KEY,
    SETTINGS_APP_KEY,
)

logger = logging.getLogger(__name__)


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _resolve_runtime_objects(request: web.Request) -> tuple[Bot, Dispatcher, Settings]:
    bot = request.app[BOT_APP_KEY]
    dispatcher = request.app[DISPATCHER_APP_KEY]
    settings = request.app[SETTINGS_APP_KEY]
    return bot, dispatcher, settings


async def telegram_webhook(request: web.Request) -> web.Response:
    bot, dispatcher, settings = _resolve_runtime_objects(request)
    expected_secret = (
        settings.webhook_secret_token.get_secret_value()
        if settings.webhook_secret_token is not None
        else ""
    )
    actual_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not expected_secret or not secrets.compare_digest(actual_secret, expected_secret):
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

    payload = await request.json(loads=bot.session.json_loads)
    update = Update.model_validate(payload, context={"bot": bot})
    result = await dispatcher.feed_update(bot, update)
    if isinstance(result, TelegramMethod):
        await dispatcher.silent_call_request(bot=bot, result=result)
    return web.json_response({"ok": True}, dumps=bot.session.json_dumps)


async def crypto_pay_webhook(request: web.Request) -> web.Response:
    _, _, settings = _resolve_runtime_objects(request)
    session_factory = request.app.get(SESSION_FACTORY_APP_KEY)
    if session_factory is None:
        return web.json_response({"ok": False, "error": "session_factory_missing"}, status=503)

    token = (
        settings.crypto_pay_token.get_secret_value()
        if settings.crypto_pay_token is not None
        else ""
    )
    if not settings.crypto_pay_enabled or not token:
        return web.json_response({"ok": False, "error": "crypto_pay_disabled"}, status=404)

    body = await request.read()
    signature = request.headers.get("crypto-pay-api-signature", "")
    if not verify_crypto_pay_webhook_signature(token, body, signature):
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

    try:
        async with session_factory() as session:
            result = await process_crypto_pay_webhook_update(
                session,
                settings,
                update_payload=payload,
            )
            await session.commit()
    except CryptoPayError as exc:
        logger.warning("Crypto Pay webhook rejected: %s", exc)
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    except Exception:
        logger.exception("Crypto Pay webhook processing failed")
        return web.json_response({"ok": False, "error": "internal_error"}, status=500)

    return web.json_response({"ok": True, "handled": result is not None})


async def healthz(request: web.Request) -> web.Response:
    _, _, settings = _resolve_runtime_objects(request)
    runtime = snapshot_runtime_state()
    return web.json_response(
        {
            "status": "ok",
            "mode": "webhook" if settings.use_webhook else "polling",
            "started_at": _isoformat(runtime.started_at),
            "last_update_at": _isoformat(runtime.last_update_at),
        }
    )


async def readyz(request: web.Request) -> web.Response:
    _, _, settings = _resolve_runtime_objects(request)
    try:
        await run_healthcheck(settings)
    except Exception as exc:
        logger.warning("Readiness probe failed: %s: %s", exc.__class__.__name__, exc)
        return web.json_response(
            {
                "status": "error",
                "detail": f"{exc.__class__.__name__}: {exc}",
            },
            status=503,
        )
    return web.json_response({"status": "ok"})
