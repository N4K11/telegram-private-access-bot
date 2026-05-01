from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings

BOT_APP_KEY: web.AppKey[Bot] = web.AppKey("bot", Bot)
DISPATCHER_APP_KEY: web.AppKey[Dispatcher] = web.AppKey("dispatcher", Dispatcher)
SETTINGS_APP_KEY: web.AppKey[Settings] = web.AppKey("settings", Settings)
SESSION_FACTORY_APP_KEY: web.AppKey[async_sessionmaker[AsyncSession]] = web.AppKey(
    "session_factory",
    async_sessionmaker,
)
