from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Subscription, Tariff


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_current_for_user(
        self,
        user_id: int,
        *,
        at_time: datetime,
    ) -> list[Subscription]:
        result = await self._session.execute(
            select(Subscription)
            .options(
                selectinload(Subscription.tariff).selectinload(Tariff.channel),
                selectinload(Subscription.channel),
                selectinload(Subscription.user),
            )
            .where(Subscription.user_id == user_id)
            .where(Subscription.status == "active")
            .where(Subscription.revoked_at.is_(None))
            .where(Subscription.expires_at > at_time)
            .order_by(Subscription.expires_at.asc(), Subscription.id.asc())
        )
        return list(result.scalars())

    async def list_expired_for_processing(
        self,
        *,
        at_time: datetime,
        limit: int = 100,
    ) -> list[Subscription]:
        result = await self._session.execute(
            select(Subscription)
            .options(
                selectinload(Subscription.user),
                selectinload(Subscription.tariff).selectinload(Tariff.channel),
                selectinload(Subscription.channel),
            )
            .where(Subscription.status == "active")
            .where(Subscription.revoked_at.is_(None))
            .where(Subscription.expires_at <= at_time)
            .order_by(Subscription.expires_at.asc(), Subscription.id.asc())
            .limit(limit)
        )
        return list(result.scalars())

    async def list_history_for_user(self, user_id: int, *, limit: int = 10) -> list[Subscription]:
        result = await self._session.execute(
            select(Subscription)
            .options(
                selectinload(Subscription.tariff).selectinload(Tariff.channel),
                selectinload(Subscription.channel),
                selectinload(Subscription.user),
            )
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.started_at.desc(), Subscription.id.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def get_active_for_user_subscription(
        self,
        user_id: int,
        subscription_id: int,
        *,
        at_time: datetime,
    ) -> Subscription | None:
        result = await self._session.execute(
            select(Subscription)
            .options(
                selectinload(Subscription.tariff).selectinload(Tariff.channel),
                selectinload(Subscription.channel),
                selectinload(Subscription.user),
            )
            .where(Subscription.id == subscription_id)
            .where(Subscription.user_id == user_id)
            .where(Subscription.status == "active")
            .where(Subscription.revoked_at.is_(None))
            .where(Subscription.expires_at > at_time)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_for_user_channel(
        self,
        user_id: int,
        channel_id: int,
    ) -> Subscription | None:
        result = await self._session.execute(
            select(Subscription)
            .options(
                selectinload(Subscription.tariff).selectinload(Tariff.channel),
                selectinload(Subscription.channel),
                selectinload(Subscription.user),
            )
            .where(Subscription.user_id == user_id)
            .where(Subscription.channel_id == channel_id)
            .order_by(Subscription.expires_at.desc(), Subscription.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: int,
        tariff_id: int,
        channel_id: int,
        started_at: datetime,
        expires_at: datetime,
        source: str = "purchase",
    ) -> Subscription:
        subscription = Subscription(
            user_id=user_id,
            tariff_id=tariff_id,
            channel_id=channel_id,
            status="active",
            source=source,
            started_at=started_at,
            expires_at=expires_at,
        )
        self._session.add(subscription)
        await self._session.flush()
        return subscription