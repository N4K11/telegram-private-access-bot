from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
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

    async def get_by_id(self, audit_log_id: int) -> AuditLog | None:
        return await self._session.get(AuditLog, audit_log_id)

    async def list_for_target_user(self, user_id: int, *, limit: int = 10) -> list[AuditLog]:
        return await self.list_filtered(target_user_id=user_id, limit=limit)

    async def list_filtered(
        self,
        *,
        actor_user_id: int | None = None,
        target_user_id: int | None = None,
        action: str | None = None,
        created_since: datetime | None = None,
        limit: int | None = 20,
        offset: int = 0,
    ) -> list[AuditLog]:
        statement = self._build_filtered_statement(
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            action=action,
            created_since=created_since,
        ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())

        if offset > 0:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)

        result = await self._session.execute(statement)
        return list(result.scalars())

    async def count_filtered(
        self,
        *,
        actor_user_id: int | None = None,
        target_user_id: int | None = None,
        action: str | None = None,
        created_since: datetime | None = None,
    ) -> int:
        statement = self._build_filtered_statement(
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            action=action,
            created_since=created_since,
        ).with_only_columns(func.count(AuditLog.id))
        result = await self._session.execute(statement)
        value = result.scalar_one()
        return int(value or 0)

    async def list_distinct_actions(self, *, limit: int = 12) -> list[str]:
        result = await self._session.execute(
            select(AuditLog.action)
            .group_by(AuditLog.action)
            .order_by(func.count(AuditLog.id).desc(), AuditLog.action.asc())
            .limit(limit)
        )
        return [action for action in result.scalars() if action]

    def _build_filtered_statement(
        self,
        *,
        actor_user_id: int | None,
        target_user_id: int | None,
        action: str | None,
        created_since: datetime | None,
    ):
        statement = select(AuditLog)
        if actor_user_id is not None:
            statement = statement.where(AuditLog.actor_user_id == actor_user_id)
        if target_user_id is not None:
            statement = statement.where(AuditLog.target_user_id == target_user_id)
        if action:
            statement = statement.where(AuditLog.action == action)
        if created_since is not None:
            statement = statement.where(AuditLog.created_at >= created_since)
        return statement
