from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, User

CONVERSION_SOURCE_START_DEEP_LINK = "start_deep_link"
CONVERSION_SOURCE_MAIN_MENU = "main_menu"
CONVERSION_SOURCE_ONBOARDING = "onboarding"
CONVERSION_SOURCE_PROFILE = "profile"
CONVERSION_SOURCE_SUPPORT = "support"
CONVERSION_SOURCE_UNKNOWN = "unknown"

KNOWN_CONVERSION_SOURCES = {
    CONVERSION_SOURCE_START_DEEP_LINK,
    CONVERSION_SOURCE_MAIN_MENU,
    CONVERSION_SOURCE_ONBOARDING,
    CONVERSION_SOURCE_PROFILE,
    CONVERSION_SOURCE_SUPPORT,
    CONVERSION_SOURCE_UNKNOWN,
}

CONVERSION_SOURCE_LABELS = {
    CONVERSION_SOURCE_START_DEEP_LINK: "Deep link /start",
    CONVERSION_SOURCE_MAIN_MENU: "Главное меню",
    CONVERSION_SOURCE_ONBOARDING: "Onboarding",
    CONVERSION_SOURCE_PROFILE: "Профиль",
    CONVERSION_SOURCE_SUPPORT: "Помощь",
    CONVERSION_SOURCE_UNKNOWN: "Неизвестно",
}

START_SOURCE_PLAIN = "plain_start"
START_SOURCE_REFERRAL = "referral_deep_link"
START_SOURCE_BUY = "start_buy_deep_link"
START_SOURCE_TARIFFS = "start_tariffs_deep_link"
START_SOURCE_HELP = "start_help_deep_link"
START_SOURCE_LINK = "start_link_deep_link"


def normalize_conversion_source(
    value: object,
    *,
    fallback: str | None = None,
) -> str | None:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in KNOWN_CONVERSION_SOURCES:
            return normalized
    return fallback


def conversion_source_label(source: str) -> str:
    normalized = normalize_conversion_source(source, fallback=CONVERSION_SOURCE_UNKNOWN)
    if normalized is None:
        return CONVERSION_SOURCE_LABELS[CONVERSION_SOURCE_UNKNOWN]
    return CONVERSION_SOURCE_LABELS.get(normalized, normalized)


def infer_menu_conversion_source(user: User | None) -> str:
    if user is not None and user.onboarding_completed_at is None:
        return CONVERSION_SOURCE_ONBOARDING
    return CONVERSION_SOURCE_MAIN_MENU


def start_navigation_source(action_name: str | None, *, is_referral: bool) -> str:
    if is_referral:
        return START_SOURCE_REFERRAL
    if action_name == "buy":
        return START_SOURCE_BUY
    if action_name == "tariffs":
        return START_SOURCE_TARIFFS
    if action_name == "help":
        return START_SOURCE_HELP
    if action_name == "link":
        return START_SOURCE_LINK
    return START_SOURCE_PLAIN


async def find_recent_conversion_source(
    session: AsyncSession,
    *,
    user_id: int,
    channel_id: int | None = None,
    tariff_id: int | None = None,
    actions: tuple[str, ...],
    fallback: str | None = None,
    limit: int = 20,
) -> str | None:
    result = await session.execute(
        select(AuditLog.action, AuditLog.payload)
        .where(AuditLog.target_user_id == user_id)
        .where(AuditLog.action.in_(actions))
        .order_by(AuditLog.id.desc())
        .limit(limit)
    )
    for action, raw_payload in result.all():
        payload = parse_audit_payload(raw_payload)
        if not _matches_entity(payload, tariff_id=tariff_id, channel_id=channel_id):
            continue
        source = normalize_conversion_source(payload.get("source"))
        if source is not None:
            return source
        if action == "profile_opened":
            return CONVERSION_SOURCE_PROFILE
        if action == "support_opened":
            return CONVERSION_SOURCE_SUPPORT
    return fallback


def parse_audit_payload(raw_payload: str | None) -> dict[str, object]:
    if not raw_payload:
        return {}
    try:
        value = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _matches_entity(
    payload: dict[str, object],
    *,
    tariff_id: int | None,
    channel_id: int | None,
) -> bool:
    payload_tariff_id = _coerce_int(payload.get("tariff_id"))
    payload_channel_id = _coerce_int(payload.get("channel_id"))
    if tariff_id is not None and payload_tariff_id is not None and payload_tariff_id != tariff_id:
        return False
    return not (
        channel_id is not None
        and payload_channel_id is not None
        and payload_channel_id != channel_id
    )


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None

