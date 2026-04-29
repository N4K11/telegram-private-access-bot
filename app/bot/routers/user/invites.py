# ruff: noqa: E501
from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.repositories.users import UserRepository
from app.services.invites import InviteLinkError, InviteLinkGrant, issue_subscription_invite_link
from app.services.texts import render_text
from app.utils.datetime import format_datetime
from app.utils.encoding import safe_ui_text

logger = logging.getLogger(__name__)

router = Router(name="user_invites")

FRIENDLY_INVITE_ERROR = (
    "Не удалось создать ссылку доступа. "
    "Попробуйте позже или используйте /paysupport."
)


def _callback_entity_id(data: str | None) -> int | None:
    if data is None:
        return None
    try:
        return int(data.rsplit(":", 1)[-1])
    except ValueError:
        return None


async def _render_invite_text(
    session: AsyncSession,
    grant: InviteLinkGrant,
    *,
    timezone: str,
) -> str:
    action = "🔁 Действующая ссылка обновлена." if grant.is_reused else "✅ Ссылка доступа готова."
    invite_expires_block = ""
    if grant.invite.expire_at is not None:
        invite_expires_block = (
            "\n"
            f"Ссылка действует до: {format_datetime(grant.invite.expire_at, timezone)}"
        )

    channel_name = safe_ui_text(
        grant.subscription.channel.title,
        f"Канал #{grant.subscription.channel_id}",
    )
    return await render_text(
        session,
        "invite_link",
        action=action,
        channel_name=escape(channel_name),
        invite_link=grant.invite.invite_link,
        invite_expires_block=invite_expires_block,
    )


@router.callback_query(F.data.startswith("menu:user:invite:"))
async def issue_invite_link_handler(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    bot: Bot,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    subscription_id = _callback_entity_id(callback.data)
    if subscription_id is None:
        await callback.answer()
        return

    user = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.answer("Сначала открой /start.", show_alert=True)
        return
    if user.is_blocked:
        await callback.answer("Доступ ограничен администратором.", show_alert=True)
        return

    try:
        grant = await issue_subscription_invite_link(
            session,
            bot,
            user_id=user.id,
            subscription_id=subscription_id,
            ttl_hours=settings.default_invite_link_ttl_hours,
        )
        await session.commit()
    except InviteLinkError as exc:
        await session.rollback()
        await callback.answer(str(exc), show_alert=True)
        return
    except Exception:
        await session.rollback()
        logger.exception(
            "Unexpected invite issuance failure for subscription %s",
            subscription_id,
        )
        await callback.answer(FRIENDLY_INVITE_ERROR, show_alert=True)
        return

    await callback.message.answer(
        await _render_invite_text(session, grant, timezone=settings.timezone)
    )
    await callback.answer("Ссылка отправлена.")