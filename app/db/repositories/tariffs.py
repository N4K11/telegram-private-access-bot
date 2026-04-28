from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tariff


class TariffRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self) -> list[Tariff]:
        result = await self._session.execute(select(Tariff).where(Tariff.is_active.is_(True)))
        return list(result.scalars())
