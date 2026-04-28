from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CryptoInvoice


class CryptoInvoiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: int,
        tariff_id: int,
        external_id: str,
        asset: str,
        amount: Decimal,
        fiat_currency: str | None,
        invoice_url: str | None,
        status: str,
        expires_at: datetime | None,
        raw_payload: str | None,
    ) -> CryptoInvoice:
        invoice = CryptoInvoice(
            user_id=user_id,
            tariff_id=tariff_id,
            external_id=external_id,
            asset=asset,
            amount=amount,
            fiat_currency=fiat_currency,
            invoice_url=invoice_url,
            status=status,
            expires_at=expires_at,
            raw_payload=raw_payload,
        )
        self._session.add(invoice)
        await self._session.flush()
        return invoice

    async def get_by_external_id(self, external_id: str) -> CryptoInvoice | None:
        result = await self._session.execute(
            select(CryptoInvoice).where(CryptoInvoice.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def get_reusable_active_for_user_tariff(
        self,
        user_id: int,
        tariff_id: int,
        *,
        at_time: datetime,
    ) -> CryptoInvoice | None:
        result = await self._session.execute(
            select(CryptoInvoice)
            .where(CryptoInvoice.user_id == user_id)
            .where(CryptoInvoice.tariff_id == tariff_id)
            .where(CryptoInvoice.status == "active")
            .where(
                CryptoInvoice.expires_at.is_(None)
                | (CryptoInvoice.expires_at > at_time)
            )
            .order_by(CryptoInvoice.created_at.desc(), CryptoInvoice.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_reconciliation(
        self,
        *,
        at_time: datetime,
        limit: int = 50,
    ) -> list[CryptoInvoice]:
        result = await self._session.execute(
            select(CryptoInvoice)
            .where(CryptoInvoice.status == "active")
            .where(
                CryptoInvoice.expires_at.is_(None)
                | (CryptoInvoice.expires_at >= at_time)
            )
            .order_by(CryptoInvoice.created_at.asc(), CryptoInvoice.id.asc())
            .limit(limit)
        )
        return list(result.scalars())