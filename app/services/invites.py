from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InviteLink, Subscription
from app.db.repositories.invite_links import InviteLinkRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.utils.datetime import ensure_aware_utc, utcnow

logger = logging.getLogger(__name__)


class InviteLinkError(ValueError):
    """Raised when an invite link cannot be issued for a subscription."""


@dataclass(slots=True)
class InviteLinkGrant:
    invite: InviteLink
    subscription: Subscription
    is_reused: bool


def _build_invite_name(subscription: Subscription) -> str:
    return f"sub-{subscription.id}-user-{subscription.user_id}"[:32]


async def issue_subscription_invite_link(
    session: AsyncSession,
    bot: Bot,
    *,
    user_id: int,
    subscription_id: int,
    ttl_hours: int,
    now: datetime | None = None,
) -> InviteLinkGrant:
    issued_at = ensure_aware_utc(now or utcnow())
    subscription_repository = SubscriptionRepository(session)
    subscription = await subscription_repository.get_active_for_user_subscription(
        user_id,
        subscription_id,
        at_time=issued_at,
    )
    if subscription is None:
        raise InviteLinkError("Активная подписка для выдачи ссылки не найдена.")

    invite_repository = InviteLinkRepository(session)
    existing = await invite_repository.get_latest_active_for_subscription(
        subscription.id,
        at_time=issued_at,
    )
    if existing is not None:
        return InviteLinkGrant(
            invite=existing,
            subscription=subscription,
            is_reused=True,
        )

    expire_at = issued_at + timedelta(hours=max(ttl_hours, 1))
    try:
        telegram_invite = await bot.create_chat_invite_link(
            chat_id=subscription.channel.telegram_chat_id,
            name=_build_invite_name(subscription),
            expire_date=expire_at,
            member_limit=1,
        )
    except Exception as exc:
        logger.exception(
            "Failed to create invite link for subscription %s in channel %s",
            subscription.id,
            subscription.channel.telegram_chat_id,
        )
        raise InviteLinkError(
            "Не удалось создать ссылку доступа. Попробуйте позже или используйте /paysupport."
        ) from exc

    invite_url = getattr(telegram_invite, "invite_link", None)
    if not isinstance(invite_url, str) or not invite_url:
        raise InviteLinkError("Telegram не вернул ссылку доступа. Используйте /paysupport.")

    invite_expire_at = getattr(telegram_invite, "expire_date", None)
    stored_expire_at = (
        ensure_aware_utc(invite_expire_at)
        if isinstance(invite_expire_at, datetime)
        else expire_at
    )
    member_limit = getattr(telegram_invite, "member_limit", None) or 1

    record = await invite_repository.create(
        user_id=user_id,
        channel_id=subscription.channel_id,
        subscription_id=subscription.id,
        invite_link=invite_url,
        expire_at=stored_expire_at,
        member_limit=member_limit,
    )
    return InviteLinkGrant(
        invite=record,
        subscription=subscription,
        is_reused=False,
    )