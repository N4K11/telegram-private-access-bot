from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InviteLink


class InviteLinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest_active_for_subscription(
        self,
        subscription_id: int,
        *,
        at_time: datetime,
    ) -> InviteLink | None:
        result = await self._session.execute(
            select(InviteLink)
            .where(InviteLink.subscription_id == subscription_id)
            .where(InviteLink.is_revoked.is_(False))
            .where(or_(InviteLink.expire_at.is_(None), InviteLink.expire_at > at_time))
            .order_by(InviteLink.created_at.desc(), InviteLink.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: int,
        channel_id: int,
        subscription_id: int,
        invite_link: str,
        expire_at: datetime | None,
        member_limit: int = 1,
        is_revoked: bool = False,
    ) -> InviteLink:
        record = InviteLink(
            user_id=user_id,
            channel_id=channel_id,
            subscription_id=subscription_id,
            invite_link=invite_link,
            expire_at=expire_at,
            member_limit=member_limit,
            is_revoked=is_revoked,
        )
        self._session.add(record)
        await self._session.flush()
        return record