from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BroadcastDelivery, User


@dataclass(slots=True)
class BroadcastDeliveryTarget:
    delivery: BroadcastDelivery
    telegram_id: int


class BroadcastDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_create(
        self,
        *,
        campaign_id: int,
        user_ids: list[int],
    ) -> list[BroadcastDelivery]:
        records = [
            BroadcastDelivery(campaign_id=campaign_id, user_id=user_id, status="pending")
            for user_id in user_ids
        ]
        self._session.add_all(records)
        await self._session.flush()
        return records

    async def list_pending_batch(
        self,
        campaign_id: int,
        *,
        limit: int = 50,
    ) -> list[BroadcastDeliveryTarget]:
        result = await self._session.execute(
            select(BroadcastDelivery, User.telegram_id)
            .join(User, User.id == BroadcastDelivery.user_id)
            .where(BroadcastDelivery.campaign_id == campaign_id)
            .where(BroadcastDelivery.status == "pending")
            .order_by(BroadcastDelivery.id.asc())
            .limit(limit)
        )
        return [
            BroadcastDeliveryTarget(delivery=delivery, telegram_id=telegram_id)
            for delivery, telegram_id in result.all()
        ]

    async def count_pending(self, campaign_id: int) -> int:
        value = (
            await self._session.execute(
                select(func.count(BroadcastDelivery.id))
                .where(BroadcastDelivery.campaign_id == campaign_id)
                .where(BroadcastDelivery.status == "pending")
            )
        ).scalar_one()
        return int(value or 0)

    async def count_by_status(self, campaign_id: int) -> dict[str, int]:
        result = await self._session.execute(
            select(BroadcastDelivery.status, func.count(BroadcastDelivery.id))
            .where(BroadcastDelivery.campaign_id == campaign_id)
            .group_by(BroadcastDelivery.status)
        )
        return {status: int(count) for status, count in result.all()}

    async def list_recent_failures(
        self,
        campaign_id: int,
        *,
        limit: int = 5,
    ) -> list[tuple[BroadcastDelivery, int]]:
        result = await self._session.execute(
            select(BroadcastDelivery, User.telegram_id)
            .join(User, User.id == BroadcastDelivery.user_id)
            .where(BroadcastDelivery.campaign_id == campaign_id)
            .where(BroadcastDelivery.status.in_(("failed", "blocked")))
            .order_by(BroadcastDelivery.id.desc())
            .limit(limit)
        )
        return list(result.all())

    async def mark_sent(
        self,
        delivery: BroadcastDelivery,
        *,
        sent_at: datetime,
    ) -> BroadcastDelivery:
        delivery.status = "sent"
        delivery.sent_at = sent_at
        delivery.error_message = None
        return delivery

    async def mark_failed(
        self,
        delivery: BroadcastDelivery,
        *,
        error_message: str,
    ) -> BroadcastDelivery:
        delivery.status = "failed"
        delivery.error_message = error_message[:1000]
        return delivery

    async def mark_blocked(
        self,
        delivery: BroadcastDelivery,
        *,
        error_message: str,
    ) -> BroadcastDelivery:
        delivery.status = "blocked"
        delivery.error_message = error_message[:1000]
        return delivery