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
from app.runtime_state import mark_started, reset_runtime_state
from app.services.texts import ensure_default_text_templates
from app.webhook.server import run_webhook_server
from app.workers.scheduler import background_workers

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()
    settings.require_runtime_ready()

    configure_logging(
        settings.log_level,
        critical_error_webhook_url=settings.critical_error_webhook_url,
    )
    reset_runtime_state()
    mark_started()
    logger.info("Bootstrapping application runtime.")

    engine = create_async_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        created_templates = await ensure_default_text_templates(session)
        if created_templates:
            await session.commit()
            logger.info("Seeded %s default text templates.", created_templates)

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = build_dispatcher(settings=settings, session_factory=session_factory)
    runtime_mode = "webhook" if settings.use_webhook else "polling"

    logger.info("Starting bot in %s (%s) mode.", settings.environment, runtime_mode)
    try:
        async with background_workers(
            bot=bot,
            session_factory=session_factory,
            settings=settings,
            broadcast_rate_limit_per_second=settings.broadcast_rate_limit_per_second,
        ):
            if settings.use_webhook:
                await run_webhook_server(
                    bot=bot,
                    dispatcher=dispatcher,
                    settings=settings,
                    session_factory=session_factory,
                )
            else:
                await dispatcher.start_polling(
                    bot,
                    allowed_updates=dispatcher.resolve_used_update_types(),
                    close_bot_session=False,
                )
    finally:
        logger.info("Shutting down bot runtime.")
        await bot.session.close()
        await engine.dispose()
        logger.info("Shutdown complete.")


def main() -> None:
    try:
        asyncio.run(run())
    except RuntimeConfigurationError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
