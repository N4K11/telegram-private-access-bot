from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.factory import build_dispatcher
from app.config import RuntimeConfigurationError, get_settings
from app.db.session import create_async_engine, create_session_factory
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()
    settings.require_runtime_ready()

    configure_logging(settings.log_level)

    engine = create_async_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = build_dispatcher(settings=settings, session_factory=session_factory)

    logger.info("Starting bot in %s mode.", settings.environment)
    try:
        if settings.use_webhook:
            raise NotImplementedError("Webhook mode will be added in a later stage.")
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await bot.session.close()
        await engine.dispose()


def main() -> None:
    try:
        asyncio.run(run())
    except RuntimeConfigurationError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
