from __future__ import annotations

from aiogram import Dispatcher
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.middlewares.db import DbSessionMiddleware
from app.bot.middlewares.rate_limit import RateLimitMiddleware
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
    rate_limit_middleware = RateLimitMiddleware(
        window_seconds=settings.rate_limit_window_seconds,
        max_events=settings.rate_limit_max_events,
        duplicate_window_seconds=settings.anti_spam_duplicate_window_seconds,
    )

    dispatcher.message.middleware(rate_limit_middleware)
    dispatcher.callback_query.middleware(rate_limit_middleware)
    dispatcher.pre_checkout_query.middleware(rate_limit_middleware)

    dispatcher.message.middleware(db_session_middleware)
    dispatcher.callback_query.middleware(db_session_middleware)
    dispatcher.pre_checkout_query.middleware(db_session_middleware)

    dispatcher.message.middleware(user_sync_middleware)
    dispatcher.callback_query.middleware(user_sync_middleware)
    dispatcher.pre_checkout_query.middleware(user_sync_middleware)

    for router in get_routers():
        dispatcher.include_router(router)

    return dispatcher