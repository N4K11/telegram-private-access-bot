from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BroadcastCampaign


class BroadcastCampaignRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_recent(self, *, limit: int = 10) -> list[BroadcastCampaign]:
        result = await self._session.execute(
            select(BroadcastCampaign)
            .order_by(BroadcastCampaign.id.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def get_by_id(self, campaign_id: int) -> BroadcastCampaign | None:
        return await self._session.get(BroadcastCampaign, campaign_id)

    async def get_current_sending(self) -> BroadcastCampaign | None:
        result = await self._session.execute(
            select(BroadcastCampaign)
            .where(BroadcastCampaign.status == "sending")
            .order_by(BroadcastCampaign.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_next_queued(self) -> BroadcastCampaign | None:
        result = await self._session.execute(
            select(BroadcastCampaign)
            .where(BroadcastCampaign.status == "queued")
            .order_by(BroadcastCampaign.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        created_by_user_id: int | None,
        filter_name: str,
        content: str,
        total_targets: int,
        status: str = "queued",
    ) -> BroadcastCampaign:
        campaign = BroadcastCampaign(
            created_by_user_id=created_by_user_id,
            filter_name=filter_name,
            content=content,
            status=status,
            total_targets=total_targets,
            sent_count=0,
            failed_count=0,
        )
        self._session.add(campaign)
        await self._session.flush()
        return campaign

    async def mark_sending(
        self,
        campaign: BroadcastCampaign,
        *,
        started_at: datetime,
    ) -> BroadcastCampaign:
        campaign.status = "sending"
        if campaign.started_at is None:
            campaign.started_at = started_at
        return campaign

    async def mark_completed(
        self,
        campaign: BroadcastCampaign,
        *,
        finished_at: datetime,
    ) -> BroadcastCampaign:
        campaign.status = "completed"
        campaign.finished_at = finished_at
        if campaign.started_at is None:
            campaign.started_at = finished_at
        return campaign