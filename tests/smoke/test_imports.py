from __future__ import annotations


def test_modules_import() -> None:
    from app.bot.factory import build_dispatcher
    from app.config import Settings
    from app.db.base import Base
    from app.db.models import Channel, Payment, Subscription, Tariff, User
    from app.logging_config import configure_logging
    from app.main import main
    from app.services.web_auth import validate_telegram_webapp_init_data
    from app.webapp import register_webapp_routes
    from app.webhook.server import build_webhook_app

    assert build_dispatcher is not None
    assert build_webhook_app is not None
    assert register_webapp_routes is not None
    assert validate_telegram_webapp_init_data is not None
    assert configure_logging is not None
    assert main is not None
    assert Settings is not None
    assert Base is not None
    assert all(model is not None for model in [User, Channel, Tariff, Subscription, Payment])
