from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import setup_application
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.webapp import register_webapp_routes

from .app_keys import (
    BOT_APP_KEY,
    DISPATCHER_APP_KEY,
    SESSION_FACTORY_APP_KEY,
    SETTINGS_APP_KEY,
)
from .handlers import crypto_pay_webhook, healthz, readyz, telegram_webhook

logger = logging.getLogger(__name__)


def build_webhook_app(
    *,
    bot: Bot,
    dispatcher: Dispatcher,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> web.Application:
    app = web.Application()
    app[BOT_APP_KEY] = bot
    app[DISPATCHER_APP_KEY] = dispatcher
    app[SETTINGS_APP_KEY] = settings
    if session_factory is not None:
        app[SESSION_FACTORY_APP_KEY] = session_factory

    app.router.add_get("/healthz", healthz)
    app.router.add_get("/readyz", readyz)
    app.router.add_post(settings.webhook_path, telegram_webhook)
    app.router.add_post(settings.crypto_pay_webhook_path, crypto_pay_webhook)
    register_webapp_routes(app, settings)

    workflow_data: dict[str, Any] = {"bot": bot, "settings": settings}
    if session_factory is not None:
        workflow_data["session_factory"] = session_factory
    setup_application(app, dispatcher, **workflow_data)
    return app


async def set_telegram_webhook(*, bot: Bot, dispatcher: Dispatcher, settings: Settings) -> None:
    await bot.set_webhook(
        url=settings.webhook_url,
        allowed_updates=dispatcher.resolve_used_update_types(),
        secret_token=settings.webhook_secret_token.get_secret_value(),
        drop_pending_updates=False,
    )
    logger.info("Configured Telegram webhook at %s.", settings.webhook_url)


async def delete_telegram_webhook(*, bot: Bot, settings: Settings) -> None:
    if not settings.delete_webhook_on_shutdown:
        return
    await bot.delete_webhook(drop_pending_updates=False)
    logger.info("Deleted Telegram webhook on shutdown.")


async def run_webhook_server(
    *,
    bot: Bot,
    dispatcher: Dispatcher,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = build_webhook_app(
        bot=bot,
        dispatcher=dispatcher,
        settings=settings,
        session_factory=session_factory,
    )
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.webapp_host, port=settings.webapp_port)
    try:
        await site.start()
        await set_telegram_webhook(bot=bot, dispatcher=dispatcher, settings=settings)
        logger.info(
            "Webhook server is listening on %s:%s with path %s.",
            settings.webapp_host,
            settings.webapp_port,
            settings.webhook_path,
        )
        await asyncio.Event().wait()
    finally:
        try:
            await delete_telegram_webhook(bot=bot, settings=settings)
        finally:
            await runner.cleanup()
