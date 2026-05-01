from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from urllib.parse import urlencode

import pytest

from app.services.web_auth import (
    WebAppAuthError,
    build_webapp_secret_key,
    validate_telegram_webapp_init_data,
)

BOT_TOKEN = "123456789:token"


def _build_init_data(
    *,
    user_value: dict[str, object] | str,
    auth_timestamp: int | None = None,
    extra: dict[str, str] | None = None,
    bot_token: str = BOT_TOKEN,
) -> str:
    resolved_timestamp = auth_timestamp or int(
        datetime(2024, 5, 1, 12, 0, tzinfo=UTC).timestamp()
    )
    fields: dict[str, str] = {
        "auth_date": str(resolved_timestamp),
        "query_id": "AAEAAAE",
        "user": (
            user_value
            if isinstance(user_value, str)
            else json.dumps(
                user_value,
                separators=(",", ":"),
                ensure_ascii=False,
            )
        ),
    }
    if extra:
        fields.update(extra)
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    signature = hmac.new(
        build_webapp_secret_key(bot_token),
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    fields["hash"] = signature
    return urlencode(fields)


def test_valid_init_data_returns_identity() -> None:
    init_data = _build_init_data(
        user_value={
            "id": 42,
            "username": "ruslan",
            "first_name": "Ruslan",
            "last_name": "Test",
            "language_code": "ru",
        }
    )

    identity = validate_telegram_webapp_init_data(
        init_data,
        bot_token=BOT_TOKEN,
        max_age_seconds=3600,
        now=datetime(2024, 5, 1, 12, 30, tzinfo=UTC),
    )

    assert identity.telegram_id == 42
    assert identity.username == "ruslan"
    assert identity.first_name == "Ruslan"
    assert identity.language_code == "ru"


def test_invalid_hash_is_rejected_without_secret_leakage() -> None:
    init_data = _build_init_data(user_value={"id": 42, "first_name": "Ruslan"})
    broken = init_data.replace("hash=", "hash=broken", 1)

    with pytest.raises(WebAppAuthError, match="invalid_signature") as exc_info:
        validate_telegram_webapp_init_data(
            broken,
            bot_token=BOT_TOKEN,
            max_age_seconds=3600,
            now=datetime(2024, 5, 1, 12, 30, tzinfo=UTC),
        )

    assert BOT_TOKEN not in str(exc_info.value)


def test_expired_auth_is_rejected() -> None:
    init_data = _build_init_data(
        user_value={"id": 42, "first_name": "Ruslan"},
        auth_timestamp=int(datetime(2024, 5, 1, 10, 0, tzinfo=UTC).timestamp()),
    )

    with pytest.raises(WebAppAuthError, match="auth_expired"):
        validate_telegram_webapp_init_data(
            init_data,
            bot_token=BOT_TOKEN,
            max_age_seconds=60,
            now=datetime(2024, 5, 1, 13, 30, tzinfo=UTC),
        )


def test_invalid_user_payload_is_rejected() -> None:
    init_data = _build_init_data(user_value="not-json")

    with pytest.raises(WebAppAuthError, match="invalid_user"):
        validate_telegram_webapp_init_data(
            init_data,
            bot_token=BOT_TOKEN,
            max_age_seconds=3600,
            now=datetime(2024, 5, 1, 12, 30, tzinfo=UTC),
        )


def test_missing_init_data_is_rejected() -> None:
    with pytest.raises(WebAppAuthError, match="missing_init_data"):
        validate_telegram_webapp_init_data(
            "",
            bot_token=BOT_TOKEN,
            max_age_seconds=3600,
        )
