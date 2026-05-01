from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Payment, Tariff


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_charge_id(self, charge_id: str) -> Payment | None:
        result = await self._session.execute(
            select(Payment)
            .options(selectinload(Payment.tariff).selectinload(Tariff.channel))
            .where(Payment.telegram_payment_charge_id == charge_id)
        )
        return result.scalar_one_or_none()

    async def get_by_provider_charge_id(
        self,
        *,
        provider: str,
        provider_payment_charge_id: str,
    ) -> Payment | None:
        result = await self._session.execute(
            select(Payment)
            .options(selectinload(Payment.tariff).selectinload(Tariff.channel))
            .where(Payment.provider == provider)
            .where(Payment.provider_payment_charge_id == provider_payment_charge_id)
        )
        return result.scalar_one_or_none()

    async def list_paid_for_user(self, user_id: int, *, limit: int = 10) -> list[Payment]:
        result = await self._session.execute(
            select(Payment)
            .options(selectinload(Payment.tariff).selectinload(Tariff.channel))
            .where(Payment.user_id == user_id)
            .where(Payment.status == "paid")
            .order_by(Payment.paid_at.desc(), Payment.id.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def list_recent_paid_for_user(self, user_id: int, *, limit: int = 5) -> list[Payment]:
        return await self.list_paid_for_user(user_id, limit=limit)

    async def count_paid_for_user(self, user_id: int) -> int:
        result = await self._session.execute(
            select(func.count(Payment.id))
            .where(Payment.user_id == user_id)
            .where(Payment.status == "paid")
        )
        value = result.scalar_one()
        return int(value or 0)

    async def sum_paid_for_user(self, user_id: int) -> int:
        result = await self._session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .where(Payment.user_id == user_id)
            .where(Payment.status == "paid")
        )
        value = result.scalar_one()
        return int(value or 0)

    async def create_paid(
        self,
        *,
        user_id: int,
        tariff_id: int,
        channel_id: int,
        amount: int,
        currency: str,
        provider: str,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: str | None,
        invoice_payload: str,
        raw_payload: str | None,
        paid_at: datetime,
    ) -> Payment:
        payment = Payment(
            user_id=user_id,
            tariff_id=tariff_id,
            channel_id=channel_id,
            amount=amount,
            currency=currency,
            provider=provider,
            telegram_payment_charge_id=telegram_payment_charge_id,
            provider_payment_charge_id=provider_payment_charge_id,
            invoice_payload=invoice_payload,
            raw_payload=raw_payload,
            paid_at=paid_at,
            status="paid",
        )
        self._session.add(payment)
        await self._session.flush()
        return payment
