from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl

from app.utils.datetime import ensure_aware_utc, utcnow


class WebAppAuthError(ValueError):
    """Raised when Telegram WebApp init data is invalid."""


@dataclass(frozen=True, slots=True)
class WebAppIdentity:
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None
    auth_date: datetime
    raw_user: dict[str, object]


def build_webapp_secret_key(bot_token: str) -> bytes:
    return hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()


def validate_telegram_webapp_init_data(
    init_data: str,
    *,
    bot_token: str,
    max_age_seconds: int,
    now: datetime | None = None,
) -> WebAppIdentity:
    normalized = (init_data or "").strip()
    if not normalized:
        raise WebAppAuthError("missing_init_data")

    pairs = parse_qsl(normalized, keep_blank_values=True, strict_parsing=False)
    if not pairs:
        raise WebAppAuthError("invalid_init_data")

    fields = dict(pairs)
    provided_hash = fields.pop("hash", "").strip().lower()
    if not provided_hash:
        raise WebAppAuthError("missing_hash")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    expected_hash = hmac.new(
        build_webapp_secret_key(bot_token),
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_hash, provided_hash):
        raise WebAppAuthError("invalid_signature")

    auth_date = _parse_auth_date(fields.get("auth_date"), max_age_seconds=max_age_seconds, now=now)
    user = _parse_user(fields.get("user"))
    return WebAppIdentity(
        telegram_id=int(user["id"]),
        username=_normalize_optional_text(user.get("username")),
        first_name=_normalize_optional_text(user.get("first_name")),
        last_name=_normalize_optional_text(user.get("last_name")),
        language_code=_normalize_optional_text(user.get("language_code")),
        auth_date=auth_date,
        raw_user=user,
    )


def _parse_auth_date(
    raw_value: object,
    *,
    max_age_seconds: int,
    now: datetime | None,
) -> datetime:
    try:
        auth_timestamp = int(str(raw_value))
    except (TypeError, ValueError):
        raise WebAppAuthError("invalid_auth_date") from None

    auth_date = ensure_aware_utc(datetime.fromtimestamp(auth_timestamp, tz=UTC))
    current_time = ensure_aware_utc(now or utcnow())
    if max_age_seconds > 0 and current_time - auth_date > timedelta(seconds=max_age_seconds):
        raise WebAppAuthError("auth_expired")
    return auth_date


def _parse_user(raw_value: object) -> dict[str, object]:
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise WebAppAuthError("missing_user")
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise WebAppAuthError("invalid_user") from exc
    if not isinstance(payload, dict):
        raise WebAppAuthError("invalid_user")
    try:
        telegram_id = int(payload.get("id"))
    except (TypeError, ValueError):
        raise WebAppAuthError("invalid_user") from None
    if telegram_id <= 0:
        raise WebAppAuthError("invalid_user")
    payload["id"] = telegram_id
    return payload


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
