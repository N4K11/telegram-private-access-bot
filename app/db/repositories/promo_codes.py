from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import PromoCode


class PromoCodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, promo_code_id: int) -> PromoCode | None:
        result = await self._session.execute(
            select(PromoCode)
            .options(selectinload(PromoCode.tariff))
            .where(PromoCode.id == promo_code_id)
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> PromoCode | None:
        result = await self._session.execute(
            select(PromoCode)
            .options(selectinload(PromoCode.tariff))
            .where(PromoCode.code == code)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        code: str,
        promo_type: str,
        value: int,
        max_uses: int,
        tariff_id: int | None,
        expires_at,
        is_active: bool,
        created_by_user_id: int | None,
    ) -> PromoCode:
        promo_code = PromoCode(
            code=code,
            promo_type=promo_type,
            value=value,
            max_uses=max_uses,
            tariff_id=tariff_id,
            expires_at=expires_at,
            is_active=is_active,
            created_by_user_id=created_by_user_id,
        )
        self._session.add(promo_code)
        await self._session.flush()
        if promo_code.tariff_id is not None:
            await self._session.refresh(promo_code, attribute_names=["tariff"])
        return promo_code

    async def set_active(self, promo_code: PromoCode, *, is_active: bool) -> PromoCode:
        promo_code.is_active = is_active
        return promo_code
