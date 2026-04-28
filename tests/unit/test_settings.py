from __future__ import annotations

import pytest

from app.config import RuntimeConfigurationError, Settings


def test_csv_values_are_parsed() -> None:
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": "1, 2,3",
            "crypto_pay_accepted_assets": "ton, usdt",
        }
    )

    assert settings.admin_ids == [1, 2, 3]
    assert settings.crypto_pay_accepted_assets == ["TON", "USDT"]


def test_runtime_validation_requires_token_and_admins() -> None:
    settings = Settings.model_validate({})

    with pytest.raises(RuntimeConfigurationError):
        settings.require_runtime_ready()