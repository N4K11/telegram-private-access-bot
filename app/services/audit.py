from __future__ import annotations

import json
from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.audit_logs import AuditLogRepository


async def write_audit_log(
    session: AsyncSession,
    *,
    action: str,
    actor_user_id: int | None = None,
    target_user_id: int | None = None,
    payload: Mapping[str, object] | None = None,
) -> None:
    serialized_payload = None
    if payload:
        serialized_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    await AuditLogRepository(session).create(
        action=action,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        payload=serialized_payload,
    )