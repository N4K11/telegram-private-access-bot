# ruff: noqa: E501
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, User
from app.services.support_catalog import support_triage_route_label
from app.services.support_models import SupportTriageApplyHistory
from app.services.support_reply_packs import SUPPORT_CANNED_REPLY_PACKS
from app.utils.datetime import ensure_aware_utc


def _support_triage_apply_actor_label(user: User | None, *, user_id: int | None) -> str | None:
    if user is None:
        return f"User {user_id}" if user_id is not None else None
    return user.first_name or user.username or f"User {user.id}"


def _parse_support_triage_apply_payload(raw_payload: str | None) -> dict[str, object] | None:
    if not raw_payload:
        return None
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _support_triage_apply_reply_title(pack_key: str, reply_key: str) -> str | None:
    for key, title, _body, _kind in SUPPORT_CANNED_REPLY_PACKS.get(pack_key, ()):
        if key == reply_key:
            return title
    return None


def _support_triage_apply_note(
    *,
    route_key: str,
    reply_title: str | None,
    count: int,
) -> str:
    route_label = support_triage_route_label(route_key)
    reply_label = reply_title or "canned reply"
    ticket_label = "ticket" if count == 1 else "tickets"
    return f'{route_label} -> "{reply_label}" on {count} {ticket_label}.'


async def _build_support_triage_apply_history(
    session: AsyncSession,
    *,
    limit: int = 10,
) -> list[SupportTriageApplyHistory]:
    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.action == "webapp_admin_support_triage_apply")
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
    )
    records = list(result.scalars())
    if not records:
        return []

    actor_ids = {record.actor_user_id for record in records if record.actor_user_id is not None}
    users_by_id: dict[int, User] = {}
    if actor_ids:
        user_result = await session.execute(select(User).where(User.id.in_(actor_ids)))
        users_by_id = {user.id: user for user in user_result.scalars()}

    items: list[SupportTriageApplyHistory] = []
    for record in records:
        payload = _parse_support_triage_apply_payload(record.payload)
        if payload is None:
            continue
        pack_key = str(payload.get("pack_key") or "").strip()
        route_key = str(payload.get("route_key") or "").strip()
        reply_key = str(payload.get("reply_key") or "").strip()
        triage_key = str(payload.get("triage_key") or "").strip()
        if not pack_key or not route_key or not reply_key or not triage_key:
            continue
        reply_title = _support_triage_apply_reply_title(pack_key, reply_key)
        ticket_ids = tuple(
            int(value)
            for value in payload.get("ticket_ids", [])
            if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
        )
        count = int(payload.get("count") or len(ticket_ids) or 0)
        actor_user = users_by_id.get(record.actor_user_id or 0)
        items.append(
            SupportTriageApplyHistory(
                audit_log_id=record.id,
                actor_user_id=record.actor_user_id,
                actor_label=_support_triage_apply_actor_label(
                    actor_user,
                    user_id=record.actor_user_id,
                ),
                triage_key=triage_key,
                pack_key=pack_key,
                route_key=route_key,
                reply_key=reply_key,
                reply_title=reply_title,
                ticket_ids=ticket_ids,
                count=count,
                created_at=ensure_aware_utc(record.created_at),
                note=_support_triage_apply_note(
                    route_key=route_key,
                    reply_title=reply_title,
                    count=count,
                ),
            )
        )
    return items
