# ruff: noqa: E501
from __future__ import annotations

import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from html import escape

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TextTemplate
from app.db.repositories.text_templates import TextTemplateRepository

logger = logging.getLogger(__name__)

SUSPICIOUS_TEXT_FRAGMENTS = ("\u0420\u045f", "\u00d0", "\u00d1", "\ufffd")


class TextTemplateValidationError(ValueError):
    """Raised when a managed text template is invalid."""


class _SafeDict(dict[str, object]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"

    def __getitem__(self, key: str) -> object:
        value = super().__getitem__(key)
        if isinstance(value, str):
            return escape(value)
        return value


@dataclass(frozen=True, slots=True)
class TextTemplateSeed:
    key: str
    title: str
    body: str
    is_system: bool = False


DEFAULT_TEXT_TEMPLATES: dict[str, TextTemplateSeed] = {
    "start": TextTemplateSeed(
        key="start",
        title="Start message",
        body=(
            "\u0417\u0434\u0440\u0430\u0432\u0441\u0442\u0432\u0443\u0439\u0442\u0435, {first_name}.\n\n"
            "Private access bot."
        ),
    ),    "user_subscription": TextTemplateSeed(
        key="user_subscription",
        title="User subscription",
        body=(
            "\u041c\u043e\u044f \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0430\n\n"
            "\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u043f\u043e\u0434\u043f\u0438\u0441\u043e\u043a \u0441\u0435\u0439\u0447\u0430\u0441 \u043d\u0435\u0442."
        ),
    ),
    "user_tariffs": TextTemplateSeed(
        key="user_tariffs",
        title="User tariffs",
        body=(
            "\u0422\u0430\u0440\u0438\u0444\u044b\n\n"
            "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043f\u043e\u0434\u0445\u043e\u0434\u044f\u0449\u0438\u0439 \u0442\u0430\u0440\u0438\u0444."
        ),
    ),
    "profile": TextTemplateSeed(
        key="profile",
        title="Profile",
        body=(
            "\u041c\u043e\u044f \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0430\n\n"
            "{subscriptions_block}{payments_block}"
        ),
    ),
    "tariffs": TextTemplateSeed(
        key="tariffs",
        title="Tariffs",
        body="\u0422\u0430\u0440\u0438\u0444\u044b\n\n{tariffs_block}",
    ),
    "payment_success": TextTemplateSeed(
        key="payment_success",
        title="Payment success",
        body=(
            "\u041e\u043f\u043b\u0430\u0442\u0430 \u043f\u0440\u043e\u0448\u043b\u0430 \u0443\u0441\u043f\u0435\u0448\u043d\u043e.\n\n"
            "{action}\n"
            "Tariff: {tariff_name}\n"
            "Channel: {channel_name}\n"
            "Expires: {expires_at}{invite_block}"
        ),
    ),
    "payment_failed": TextTemplateSeed(
        key="payment_failed",
        title="Payment failed",
        body=(
            "\u041e\u043f\u043b\u0430\u0442\u0430 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0430, \u043d\u043e \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0430 \u043d\u0435 \u0437\u0430\u0432\u0435\u0440\u0448\u0438\u043b\u0430\u0441\u044c: {reason}\n\n"
            "Use /paysupport."
        ),
    ),
    "subscription_expired": TextTemplateSeed(
        key="subscription_expired",
        title="Subscription expired",
        body=(
            "\u0414\u043e\u0441\u0442\u0443\u043f \u043a \u043a\u0430\u043d\u0430\u043b\u0443 \xab{channel_name}\xbb \u0437\u0430\u0432\u0435\u0440\u0448\u0451\u043d.\n\n"
            "\u041f\u043e\u0434\u043f\u0438\u0441\u043a\u0430 \u0438\u0441\u0442\u0435\u043a\u043b\u0430."
        ),
    ),
    "invite_link": TextTemplateSeed(
        key="invite_link",
        title="Invite link",
        body=(
            "{action}\n\n"
            "\u041a\u0430\u043d\u0430\u043b: {channel_name}\n"
            "\u0421\u0441\u044b\u043b\u043a\u0430: {invite_link}{invite_expires_block}"
        ),
    ),
    "support": TextTemplateSeed(
        key="support",
        title="Support",
        body=(
            "\u041f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430\n\n"
            "Use /paysupport or contact the admin."
        ),
    ),
    "user_support": TextTemplateSeed(
        key="user_support",
        title="User support",
        body=(
            "\u041f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430\n\n"
            "Use /paysupport or contact the admin."
        ),
    ),
    "paysupport": TextTemplateSeed(
        key="paysupport",
        title="Payment support",
        body=(
            "\u041f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430 \u043e\u043f\u043b\u0430\u0442\u044b\n\n"
            "Send the payment screenshot and tariff details to the admin."
        ),
    ),
    "admin_dashboard": TextTemplateSeed(
        key="admin_dashboard",
        title="Admin dashboard",
        body=(
            "\u041f\u0430\u043d\u0435\u043b\u044c \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u0430\n\n"
            "Manage tariffs, channels, texts and broadcasts."
        ),
    ),
    "admin_section": TextTemplateSeed(
        key="admin_section",
        title="Admin section title",
        body=(
            "\u0420\u0430\u0437\u0434\u0435\u043b \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u0430: {section}"
        ),
    ),
    "admin_menu_analytics": TextTemplateSeed(
        key="admin_menu_analytics",
        title="Admin menu analytics",
        body="\U0001f4ca \u0410\u043d\u0430\u043b\u0438\u0442\u0438\u043a\u0430",
        is_system=True,
    ),
    "admin_menu_users": TextTemplateSeed(
        key="admin_menu_users",
        title="Admin menu users",
        body="\U0001f465 \u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0438",
        is_system=True,
    ),
    "admin_menu_payments": TextTemplateSeed(
        key="admin_menu_payments",
        title="Admin menu payments",
        body="\U0001f4b3 \u041f\u043b\u0430\u0442\u0435\u0436\u0438",
        is_system=True,
    ),
    "admin_menu_tariffs": TextTemplateSeed(
        key="admin_menu_tariffs",
        title="Admin menu tariffs",
        body="\U0001f9fe \u0422\u0430\u0440\u0438\u0444\u044b",
        is_system=True,
    ),
    "admin_menu_channels": TextTemplateSeed(
        key="admin_menu_channels",
        title="Admin menu channels",
        body="\U0001f4e3 \u041a\u0430\u043d\u0430\u043b\u044b",
        is_system=True,
    ),
    "admin_menu_texts": TextTemplateSeed(
        key="admin_menu_texts",
        title="Admin menu texts",
        body="\u270d\ufe0f \u0422\u0435\u043a\u0441\u0442\u044b",
        is_system=True,
    ),
    "admin_menu_broadcasts": TextTemplateSeed(
        key="admin_menu_broadcasts",
        title="Admin menu broadcasts",
        body="\U0001f4e2 \u0420\u0430\u0441\u0441\u044b\u043b\u043a\u0430",
        is_system=True,
    ),
    "admin_menu_backups": TextTemplateSeed(
        key="admin_menu_backups",
        title="Admin menu backups",
        body="\U0001f4be \u0411\u044d\u043a\u0430\u043f\u044b",
        is_system=True,
    ),
    "admin_menu_settings": TextTemplateSeed(
        key="admin_menu_settings",
        title="Admin menu settings",
        body="\u2699\ufe0f \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438",
        is_system=True,
    ),
    "admin_menu_diagnostics": TextTemplateSeed(
        key="admin_menu_diagnostics",
        title="Admin menu diagnostics",
        body="\U0001f9ea \u0414\u0438\u0430\u0433\u043d\u043e\u0441\u0442\u0438\u043a\u0430",
        is_system=True,
    ),
    "admin_button_back": TextTemplateSeed(
        key="admin_button_back",
        title="Admin button back",
        body="\u041d\u0430\u0437\u0430\u0434",
        is_system=True,
    ),
    "admin_button_home": TextTemplateSeed(
        key="admin_button_home",
        title="Admin button home",
        body="\u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e",
        is_system=True,
    ),
}


def default_text_template(key: str) -> TextTemplateSeed | None:
    return DEFAULT_TEXT_TEMPLATES.get(key)


def default_text_body(key: str) -> str:
    template = default_text_template(key)
    return template.body if template is not None else key


def has_mojibake(value: str) -> bool:
    return any(fragment in value for fragment in SUSPICIOUS_TEXT_FRAGMENTS)


def is_default_text_body(key: str, body: str) -> bool:
    template = default_text_template(key)
    return template is not None and template.body == body


def validate_text_body(body: str) -> str:
    normalized = body.strip()
    if not normalized:
        raise TextTemplateValidationError(
            "\u0422\u0435\u043a\u0441\u0442 \u0448\u0430\u0431\u043b\u043e\u043d\u0430 \u043d\u0435 \u0434\u043e\u043b\u0436\u0435\u043d \u0431\u044b\u0442\u044c \u043f\u0443\u0441\u0442\u044b\u043c."
        )
    if has_mojibake(normalized):
        raise TextTemplateValidationError(
            "\u041f\u043e\u0445\u043e\u0436\u0435, \u0432 \u0442\u0435\u043a\u0441\u0442\u0435 \u0435\u0441\u0442\u044c \u043a\u0440\u0430\u043a\u043e\u0437\u044f\u0431\u0440\u044b."
        )

    try:
        _render_body(normalized)
    except (IndexError, ValueError) as exc:
        raise TextTemplateValidationError(
            "Invalid placeholders or braces."
        ) from exc

    return normalized


async def ensure_default_text_templates(session: AsyncSession) -> int:
    repository = TextTemplateRepository(session)
    existing = await repository.get_by_keys(tuple(DEFAULT_TEXT_TEMPLATES))
    created = 0
    for key, seed in DEFAULT_TEXT_TEMPLATES.items():
        if key in existing:
            continue
        await repository.create(
            key=seed.key,
            title=seed.title,
            body=seed.body,
            is_system=seed.is_system,
        )
        created += 1
    return created


async def list_text_templates(session: AsyncSession) -> list[TextTemplate]:
    await ensure_default_text_templates(session)
    return await TextTemplateRepository(session).list_all()


async def get_text_template_record(
    session: AsyncSession,
    key: str,
) -> TextTemplate | None:
    repository = TextTemplateRepository(session)
    template = await repository.get_by_key(key)
    if template is not None:
        return template

    seed = default_text_template(key)
    if seed is None:
        return None

    return await repository.create(
        key=seed.key,
        title=seed.title,
        body=seed.body,
        is_system=seed.is_system,
    )


async def update_text_template_body(
    session: AsyncSession,
    *,
    key: str,
    body: str,
    updated_by_user_id: int | None,
) -> TextTemplate:
    template = await get_text_template_record(session, key)
    if template is None:
        raise TextTemplateValidationError(f"Unknown template key: {key}")

    template.body = validate_text_body(body)
    template.updated_by_user_id = updated_by_user_id
    await session.flush()
    return template


async def reset_text_template_body(
    session: AsyncSession,
    *,
    key: str,
    updated_by_user_id: int | None,
) -> TextTemplate:
    template = await get_text_template_record(session, key)
    default_template = default_text_template(key)
    if template is None or default_template is None:
        raise TextTemplateValidationError(f"Unknown template key: {key}")

    template.body = default_template.body
    template.updated_by_user_id = updated_by_user_id
    await session.flush()
    return template


async def get_text_bodies(
    session: AsyncSession | None,
    keys: tuple[str, ...],
) -> dict[str, str]:
    if session is None:
        return {key: default_text_body(key) for key in keys}

    templates = await TextTemplateRepository(session).get_by_keys(keys)
    return {
        key: templates[key].body if key in templates else default_text_body(key)
        for key in keys
    }


def render_text(
    session_or_key: AsyncSession | str | None,
    key: str | None = None,
    **context: object,
) -> str | Awaitable[str]:
    if isinstance(session_or_key, AsyncSession) or key is not None:
        session = session_or_key if isinstance(session_or_key, AsyncSession) else None
        managed_key = key if key is not None else str(session_or_key)
        return _render_managed_text(session, managed_key, **context)

    fallback_key = str(session_or_key)
    fallback_body = default_text_body(fallback_key)
    return _render_with_fallback(fallback_body, fallback_body, **context)


async def _render_managed_text(
    session: AsyncSession | None,
    key: str,
    **context: object,
) -> str:
    template_body = (await get_text_bodies(session, (key,))).get(key, key)
    fallback_body = default_text_body(key)
    return _render_with_fallback(template_body, fallback_body, **context)


def _render_with_fallback(
    template_body: str,
    fallback_body: str,
    **context: object,
) -> str:
    try:
        return _render_body(template_body, **context)
    except (IndexError, ValueError):
        if template_body != fallback_body:
            logger.warning("Managed text template fallback activated.")
            try:
                return _render_body(fallback_body, **context)
            except (IndexError, ValueError):
                return fallback_body
        return fallback_body


def _render_body(body: str, **context: object) -> str:
    return body.format_map(_SafeDict(context))