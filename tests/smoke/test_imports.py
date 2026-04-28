from __future__ import annotations


def test_modules_import() -> None:
    from app.bot.factory import build_dispatcher
    from app.config import Settings
    from app.db.base import Base
    from app.db.models import Channel, Payment, Subscription, Tariff, User
    from app.logging_config import configure_logging
    from app.main import main

    assert build_dispatcher is not None
    assert configure_logging is not None
    assert main is not None
    assert Settings is not None
    assert Base is not None
    assert all(model is not None for model in [User, Channel, Tariff, Subscription, Payment])
