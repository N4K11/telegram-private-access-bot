from __future__ import annotations

from aiogram import Dispatcher
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.middlewares.db import DbSessionMiddleware
from app.bot.middlewares.user_sync import UserSyncMiddleware
from app.bot.routers import get_routers
from app.config import Settings


def build_dispatcher(
    *, settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher["settings"] = settings
    dispatcher["session_factory"] = session_factory

    db_session_middleware = DbSessionMiddleware(session_factory)
    user_sync_middleware = UserSyncMiddleware()

    dispatcher.message.middleware(db_session_middleware)
    dispatcher.callback_query.middleware(db_session_middleware)
    dispatcher.pre_checkout_query.middleware(db_session_middleware)

    dispatcher.message.middleware(user_sync_middleware)
    dispatcher.callback_query.middleware(user_sync_middleware)

    for router in get_routers():
        dispatcher.include_router(router)

    return dispatcher
