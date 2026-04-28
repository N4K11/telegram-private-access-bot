from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Tariff
from app.services.tariffs import TariffDraft


class TariffRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Tariff]:
        result = await self._session.execute(
            select(Tariff)
            .options(selectinload(Tariff.channel))
            .order_by(Tariff.archived_at.is_(None).desc(), Tariff.sort_order.asc(), Tariff.id.asc())
        )
        return list(result.scalars())

    async def list_active(self) -> list[Tariff]:
        result = await self._session.execute(
            select(Tariff)
            .options(selectinload(Tariff.channel))
            .where(Tariff.is_active.is_(True))
            .where(Tariff.archived_at.is_(None))
            .order_by(Tariff.sort_order.asc(), Tariff.id.asc())
        )
        return list(result.scalars())

    async def get_by_id(self, tariff_id: int) -> Tariff | None:
        result = await self._session.execute(
            select(Tariff)
            .options(selectinload(Tariff.channel))
            .where(Tariff.id == tariff_id)
        )
        return result.scalar_one_or_none()

    async def create(self, draft: TariffDraft) -> Tariff:
        tariff = Tariff(
            name=draft.name,
            price_stars=draft.price_stars,
            duration_days=draft.duration_days,
            channel_id=draft.channel_id,
            sort_order=draft.sort_order,
            is_active=True,
        )
        self._session.add(tariff)
        await self._session.flush()
        return tariff

    async def set_active(self, tariff: Tariff, *, is_active: bool) -> Tariff:
        tariff.is_active = is_active
        return tariff

    async def archive(self, tariff: Tariff, *, archived_at) -> Tariff:
        tariff.archived_at = archived_at
        tariff.is_active = False
        return tariff