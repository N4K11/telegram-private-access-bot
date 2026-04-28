# ruff: noqa: E501
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.repositories.users import UserRepository
from app.services.invites import InviteLinkError, InviteLinkGrant, issue_subscription_invite_link
from app.services.texts import render_text
from app.utils.datetime import format_datetime

logger = logging.getLogger(__name__)

router = Router(name="user_invites")

FRIENDLY_INVITE_ERROR = (
    "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0437\u0434\u0430\u0442\u044c "
    "\u0441\u0441\u044b\u043b\u043a\u0443 \u0434\u043e\u0441\u0442\u0443\u043f\u0430. "
    "\u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u043f\u043e\u0437\u0436\u0435 "
    "\u0438\u043b\u0438 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439\u0442\u0435 /paysupport."
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
    action = (
        "Active invite link reused."
        if grant.is_reused
        else "Access link is ready."
    )
    invite_expires_block = ""
    if grant.invite.expire_at is not None:
        invite_expires_block = (
            "\n"
            f"Valid until: {format_datetime(grant.invite.expire_at, timezone)}"
        )

    return await render_text(
        session,
        "invite_link",
        action=action,
        channel_name=grant.subscription.channel.title,
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
        await callback.answer("Start the bot first.", show_alert=True)
        return
    if user.is_blocked:
        await callback.answer("Access is restricted.", show_alert=True)
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
    await callback.answer("Link sent.")