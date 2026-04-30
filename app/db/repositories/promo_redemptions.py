from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import PromoCode, PromoRedemption


class PromoRedemptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, redemption_id: int) -> PromoRedemption | None:
        result = await self._session.execute(
            select(PromoRedemption)
            .options(selectinload(PromoRedemption.promo_code).selectinload(PromoCode.tariff))
            .options(selectinload(PromoRedemption.tariff))
            .where(PromoRedemption.id == redemption_id)
        )
        return result.scalar_one_or_none()

    async def get_by_promo_and_user(
        self,
        promo_code_id: int,
        user_id: int,
    ) -> PromoRedemption | None:
        result = await self._session.execute(
            select(PromoRedemption)
            .options(selectinload(PromoRedemption.promo_code).selectinload(PromoCode.tariff))
            .options(selectinload(PromoRedemption.tariff))
            .where(PromoRedemption.promo_code_id == promo_code_id)
            .where(PromoRedemption.user_id == user_id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_pending_for_user(self, user_id: int) -> list[PromoRedemption]:
        result = await self._session.execute(
            select(PromoRedemption)
            .options(selectinload(PromoRedemption.promo_code).selectinload(PromoCode.tariff))
            .options(selectinload(PromoRedemption.tariff))
            .where(PromoRedemption.user_id == user_id)
            .where(PromoRedemption.status == "pending")
            .order_by(PromoRedemption.updated_at.desc(), PromoRedemption.id.desc())
        )
        return list(result.scalars())

    async def count_for_promo_by_statuses(
        self,
        promo_code_id: int,
        statuses: Sequence[str],
    ) -> int:
        result = await self._session.execute(
            select(func.count(PromoRedemption.id))
            .where(PromoRedemption.promo_code_id == promo_code_id)
            .where(PromoRedemption.status.in_(tuple(statuses)))
        )
        value = result.scalar_one()
        return int(value or 0)

    async def summarize_for_promo(self, promo_code_id: int) -> dict[str, int]:
        result = await self._session.execute(
            select(PromoRedemption.status, func.count(PromoRedemption.id))
            .where(PromoRedemption.promo_code_id == promo_code_id)
            .group_by(PromoRedemption.status)
        )
        summary = {"pending": 0, "consumed": 0, "cancelled": 0}
        for status, count in result:
            summary[str(status)] = int(count or 0)
        return summary

    async def create(
        self,
        *,
        promo_code_id: int,
        user_id: int,
        status: str,
        payment_id: int | None = None,
        applied_tariff_id: int | None = None,
        amount_before: int | None = None,
        amount_after: int | None = None,
        used_at: datetime | None = None,
    ) -> PromoRedemption:
        redemption = PromoRedemption(
            promo_code_id=promo_code_id,
            user_id=user_id,
            status=status,
            payment_id=payment_id,
            applied_tariff_id=applied_tariff_id,
            amount_before=amount_before,
            amount_after=amount_after,
            used_at=used_at,
        )
        self._session.add(redemption)
        await self._session.flush()
        await self._session.refresh(redemption, attribute_names=["promo_code", "tariff"])
        return redemption

    async def cancel_other_pending_for_user(
        self,
        *,
        user_id: int,
        exclude_redemption_id: int | None = None,
    ) -> int:
        pending = await self.list_pending_for_user(user_id)
        cancelled = 0
        for redemption in pending:
            if exclude_redemption_id is not None and redemption.id == exclude_redemption_id:
                continue
            redemption.status = "cancelled"
            cancelled += 1
        return cancelled

    async def activate_pending(self, redemption: PromoRedemption) -> PromoRedemption:
        redemption.status = "pending"
        redemption.payment_id = None
        redemption.applied_tariff_id = None
        redemption.amount_before = None
        redemption.amount_after = None
        redemption.used_at = None
        return redemption

    async def mark_consumed(
        self,
        redemption: PromoRedemption,
        *,
        payment_id: int | None,
        applied_tariff_id: int,
        amount_before: int | None,
        amount_after: int | None,
        used_at: datetime,
    ) -> PromoRedemption:
        redemption.status = "consumed"
        redemption.payment_id = payment_id
        redemption.applied_tariff_id = applied_tariff_id
        redemption.amount_before = amount_before
        redemption.amount_after = amount_after
        redemption.used_at = used_at
        return redemption
