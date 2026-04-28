from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        action: str,
        actor_user_id: int | None,
        target_user_id: int | None,
        payload: str | None,
    ) -> AuditLog:
        record = AuditLog(
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            action=action,
            payload=payload,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def list_for_target_user(self, user_id: int, *, limit: int = 10) -> list[AuditLog]:
        result = await self._session.execute(
            select(AuditLog)
            .where(AuditLog.target_user_id == user_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        )
        return list(result.scalars())