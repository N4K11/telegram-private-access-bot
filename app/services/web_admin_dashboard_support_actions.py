from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db.models import SupportMessage, SupportTicket
from app.services.audit import write_audit_log
from app.services.support import (
    SUPPORT_STATUS_OPEN,
    SupportTicketThread,
    add_admin_ticket_reply,
    build_admin_support_inbox,
    build_support_canned_replies_for_pack,
    support_action_lane,
    support_canned_reply_pack_key,
    support_escalation_lane,
)
from app.services.web_admin_dashboard_support_insight_serializers import (
    _serialize_support_insights,
)
from app.services.web_admin_dashboard_support_ticket_serializers import (
    _serialize_support_ticket_list_item,
)
from app.services.web_auth import build_webapp_secret_key
from app.utils.datetime import ensure_aware_utc, format_datetime, utcnow

SUPPORT_TRIAGE_APPLY_TOKEN_TTL_MINUTES = 15
SUPPORT_TRIAGE_APPLY_MAX_TICKETS = 3


def _support_triage_confirm_steps(
    *,
    route_label: str | None,
    primary_reply_title: str | None,
    sample_ticket_ids: list[int],
) -> list[dict[str, object]]:
    sample_ids = ", ".join(f"#{ticket_id}" for ticket_id in sample_ticket_ids[:3])
    return [
        {
            "key": "review_scope",
            "label": "Review batch scope",
            "note": (
                f"Check sample tickets {sample_ids}."
                if sample_ids
                else "Check sample tickets in this triage group."
            ),
        },
        {
            "key": "align_route",
            "label": "Align route",
            "note": f"Confirm the queue still fits {route_label or 'the current route'}.",
        },
        {
            "key": "send_manually",
            "label": "Send manually",
            "note": (
                f'Use "{primary_reply_title}" as the primary manual reply.'
                if primary_reply_title
                else "Use the primary canned reply manually."
            ),
        },
        {
            "key": "refresh_queue",
            "label": "Refresh queue",
            "note": "Refresh support insights after handling the batch.",
        },
    ]


def _support_triage_route_key(ticket: SupportTicket) -> str:
    return f"{support_escalation_lane(ticket)}:{support_action_lane(ticket)}"


def _support_triage_apply_signing_key(settings: Settings) -> bytes:
    if settings.bot_token is None or not settings.bot_token.get_secret_value().strip():
        raise ValueError("triage_apply_unavailable")
    return build_webapp_secret_key(settings.bot_token.get_secret_value())


def _encode_support_triage_apply_token(
    settings: Settings,
    *,
    actor_user_id: int,
    triage_key: str,
    pack_key: str,
    route_key: str,
    allowed_reply_keys: list[str],
    sample_ticket_ids: list[int],
    current_time: datetime,
) -> str:
    expires_at = current_time + timedelta(minutes=SUPPORT_TRIAGE_APPLY_TOKEN_TTL_MINUTES)
    payload = {
        "v": 1,
        "actor_user_id": actor_user_id,
        "triage_key": triage_key,
        "pack_key": pack_key,
        "route_key": route_key,
        "allowed_reply_keys": sorted(
            {key for key in allowed_reply_keys if isinstance(key, str) and key.strip()}
        ),
        "sample_ticket_ids": [
            int(ticket_id)
            for ticket_id in sample_ticket_ids[:SUPPORT_TRIAGE_APPLY_MAX_TICKETS]
            if int(ticket_id) > 0
        ],
        "issued_at": int(current_time.timestamp()),
        "expires_at": int(expires_at.timestamp()),
    }
    raw_payload = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    payload_bytes = raw_payload.encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    signature = hmac.new(
        _support_triage_apply_signing_key(settings),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    return f"{encoded_payload}.{signature}"


def _decode_support_triage_apply_token(
    settings: Settings,
    *,
    token: str,
    actor_user_id: int,
    triage_key: str,
    now: datetime,
) -> dict[str, object]:
    normalized = token.strip()
    if not normalized or "." not in normalized:
        raise ValueError("invalid_confirm_token")
    encoded_payload, provided_signature = normalized.rsplit(".", 1)
    padding = "=" * (-len(encoded_payload) % 4)
    try:
        payload_bytes = base64.urlsafe_b64decode(f"{encoded_payload}{padding}".encode("ascii"))
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("invalid_confirm_token") from None
    if not isinstance(payload, dict):
        raise ValueError("invalid_confirm_token")
    expected_signature = hmac.new(
        _support_triage_apply_signing_key(settings),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, provided_signature):
        raise ValueError("invalid_confirm_token")
    if int(payload.get("v") or 0) != 1:
        raise ValueError("invalid_confirm_token")
    if int(payload.get("actor_user_id") or 0) != actor_user_id:
        raise ValueError("invalid_confirm_token")
    if str(payload.get("triage_key") or "") != triage_key:
        raise ValueError("invalid_confirm_token")
    expires_at = int(payload.get("expires_at") or 0)
    if expires_at <= int(now.timestamp()):
        raise ValueError("confirm_token_expired")
    sample_ticket_ids = [
        int(value)
        for value in payload.get("sample_ticket_ids", [])
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
    ]
    if not sample_ticket_ids:
        raise ValueError("invalid_confirm_token")
    allowed_reply_keys = [
        str(value).strip()
        for value in payload.get("allowed_reply_keys", [])
        if isinstance(value, str) and value.strip()
    ]
    if not allowed_reply_keys:
        raise ValueError("invalid_confirm_token")
    return {
        "pack_key": str(payload.get("pack_key") or ""),
        "route_key": str(payload.get("route_key") or ""),
        "allowed_reply_keys": allowed_reply_keys,
        "sample_ticket_ids": sample_ticket_ids[:SUPPORT_TRIAGE_APPLY_MAX_TICKETS],
        "expires_at": expires_at,
    }


def _support_triage_apply_scope_ticket_ids(
    token_ticket_ids: list[int],
    *,
    ticket_id: int | None,
) -> list[int]:
    scope_ids = token_ticket_ids[:SUPPORT_TRIAGE_APPLY_MAX_TICKETS]
    if ticket_id is None:
        return scope_ids
    if ticket_id not in scope_ids:
        raise ValueError("invalid_ticket")
    return [ticket_id]


async def run_web_admin_support_triage_confirm_action(
    session: AsyncSession,
    *,
    settings: Settings,
    actor_user_id: int | None,
    triage_key: str,
    ticket_id: int | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    current_time = ensure_aware_utc(now or utcnow())
    inbox = await build_admin_support_inbox(
        session,
        status="open",
        limit=1,
        now=current_time,
    )
    support_insights = _serialize_support_insights(inbox.insights)
    triage_confirm_items = support_insights.get("triage_confirm", [])
    item = next(
        (
            candidate
            for candidate in triage_confirm_items
            if isinstance(candidate, dict) and candidate.get("confirm_key") == triage_key
        ),
        None,
    )
    if item is None:
        raise ValueError("triage_confirm_not_found")

    sample_ticket_ids = [
        int(value)
        for value in item.get("sample_ticket_ids", [])
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
    ]
    if ticket_id is not None and ticket_id > 0 and ticket_id not in sample_ticket_ids:
        sample_ticket_ids = [ticket_id, *sample_ticket_ids]
    sample_ticket_ids = sample_ticket_ids[:3]

    sample_tickets: list[SupportTicket] = []
    if sample_ticket_ids:
        ticket_result = await session.execute(
            select(SupportTicket)
            .options(
                selectinload(SupportTicket.user),
                selectinload(SupportTicket.messages).selectinload(SupportMessage.sender),
            )
            .where(SupportTicket.id.in_(sample_ticket_ids))
        )
        ticket_map = {ticket.id: ticket for ticket in ticket_result.scalars()}
        sample_tickets = [
            ticket_map[ticket_sample_id]
            for ticket_sample_id in sample_ticket_ids
            if ticket_sample_id in ticket_map
        ]

    stale_before = current_time - timedelta(hours=24)
    primary_reply = {
        "key": item.get("primary_reply_key"),
        "title": item.get("primary_reply_title"),
        "body": item.get("primary_reply_body"),
        "kind": item.get("primary_reply_kind"),
    }
    allowed_reply_keys = [
        str(reply.get("key")).strip()
        for reply in item.get("suggested_replies", [])
        if isinstance(reply, dict) and str(reply.get("key") or "").strip()
    ]
    confirm_token = (
        _encode_support_triage_apply_token(
            settings,
            actor_user_id=actor_user_id,
            triage_key=triage_key,
            pack_key=str(item.get("pack_key") or ""),
            route_key=str(item.get("route_key") or ""),
            allowed_reply_keys=allowed_reply_keys,
            sample_ticket_ids=sample_ticket_ids,
            current_time=current_time,
        )
        if actor_user_id is not None and allowed_reply_keys and sample_ticket_ids
        else None
    )
    confirm_expires_at = current_time + timedelta(minutes=SUPPORT_TRIAGE_APPLY_TOKEN_TTL_MINUTES)
    operator_steps = _support_triage_confirm_steps(
        route_label=item.get("route_label") if isinstance(item.get("route_label"), str) else None,
        primary_reply_title=(
            item.get("primary_reply_title")
            if isinstance(item.get("primary_reply_title"), str)
            else None
        ),
        sample_ticket_ids=sample_ticket_ids,
    )

    await write_audit_log(
        session,
        action="webapp_admin_support_triage_confirm_preview",
        actor_user_id=actor_user_id,
        payload={
            "triage_key": triage_key,
            "ticket_id": ticket_id,
            "count": item.get("count", 0),
            "pack_key": item.get("pack_key"),
            "route_key": item.get("route_key"),
            "primary_reply_key": item.get("primary_reply_key"),
            "sample_ticket_ids": sample_ticket_ids,
        },
    )

    return {
        "key": item.get("confirm_key"),
        "label": item.get("confirm_label"),
        "generated_at_label": format_datetime(current_time, settings.timezone),
        "confirm_mode": item.get("confirm_mode"),
        "confirm_mode_label": item.get("confirm_mode_label"),
        "confirm_scope_label": item.get("confirm_scope_label"),
        "confirm_note": item.get("confirm_note"),
        "confirm_token": confirm_token,
        "confirm_token_expires_at_label": format_datetime(confirm_expires_at, settings.timezone)
        if confirm_token is not None
        else None,
        "apply_limit": SUPPORT_TRIAGE_APPLY_MAX_TICKETS,
        "apply_reply_key": primary_reply.get("key"),
        "allowed_reply_keys": allowed_reply_keys,
        "pack_key": item.get("pack_key"),
        "pack_label": item.get("pack_label"),
        "route_key": item.get("route_key"),
        "route_label": item.get("route_label"),
        "count": item.get("count", 0),
        "share_percent": item.get("share_percent", 0.0),
        "primary_reply": primary_reply,
        "suggested_replies": item.get("suggested_replies", []),
        "sample_ticket_ids": sample_ticket_ids,
        "sample_tickets": [
            _serialize_support_ticket_list_item(
                ticket,
                settings=settings,
                stale_before=stale_before,
                reference_time=current_time,
            )
            for ticket in sample_tickets
        ],
        "focused_ticket_id": ticket_id,
        "operator_steps": operator_steps,
        "preview_only": True,
    }


async def run_web_admin_support_triage_apply_action(
    session: AsyncSession,
    *,
    settings: Settings,
    actor_user_id: int,
    triage_key: str,
    confirm_token: str,
    reply_key: str | None = None,
    ticket_id: int | None = None,
    now: datetime | None = None,
) -> tuple[dict[str, object], list[SupportTicketThread]]:
    current_time = ensure_aware_utc(now or utcnow())
    token_payload = _decode_support_triage_apply_token(
        settings,
        token=confirm_token,
        actor_user_id=actor_user_id,
        triage_key=triage_key,
        now=current_time,
    )
    inbox = await build_admin_support_inbox(
        session,
        status="open",
        limit=1,
        now=current_time,
    )
    support_insights = _serialize_support_insights(inbox.insights)
    triage_confirm_items = support_insights.get("triage_confirm", [])
    item = next(
        (
            candidate
            for candidate in triage_confirm_items
            if isinstance(candidate, dict) and candidate.get("confirm_key") == triage_key
        ),
        None,
    )
    if item is None:
        raise ValueError("triage_scope_changed")

    current_pack_key = str(item.get("pack_key") or "")
    current_route_key = str(item.get("route_key") or "")
    token_pack_key = str(token_payload.get("pack_key") or "")
    token_route_key = str(token_payload.get("route_key") or "")
    if current_pack_key != token_pack_key or current_route_key != token_route_key:
        raise ValueError("triage_scope_changed")

    scoped_ticket_ids = _support_triage_apply_scope_ticket_ids(
        list(token_payload.get("sample_ticket_ids", [])),
        ticket_id=ticket_id,
    )
    ticket_result = await session.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.user),
            selectinload(SupportTicket.messages).selectinload(SupportMessage.sender),
        )
        .where(SupportTicket.id.in_(scoped_ticket_ids))
    )
    ticket_map = {ticket.id: ticket for ticket in ticket_result.scalars()}
    scoped_tickets = [
        ticket_map[ticket_sample_id]
        for ticket_sample_id in scoped_ticket_ids
        if ticket_sample_id in ticket_map
    ]
    if len(scoped_tickets) != len(scoped_ticket_ids):
        raise ValueError("triage_scope_changed")

    for ticket in scoped_tickets:
        if ticket.status != SUPPORT_STATUS_OPEN:
            raise ValueError("triage_scope_changed")
        if support_canned_reply_pack_key(ticket) != current_pack_key:
            raise ValueError("triage_scope_changed")
        if _support_triage_route_key(ticket) != current_route_key:
            raise ValueError("triage_scope_changed")

    allowed_reply_keys = [
        str(value).strip()
        for value in token_payload.get("allowed_reply_keys", [])
        if isinstance(value, str) and value.strip()
    ]
    selected_reply_key = str(reply_key or item.get("primary_reply_key") or "").strip()
    if not selected_reply_key or selected_reply_key not in allowed_reply_keys:
        raise ValueError("invalid_reply_key")
    pack_replies = {
        reply.key: reply
        for reply in build_support_canned_replies_for_pack(current_pack_key, limit=6)
    }
    selected_reply = pack_replies.get(selected_reply_key)
    if selected_reply is None:
        raise ValueError("invalid_reply_key")

    threads: list[SupportTicketThread] = []
    for ticket in scoped_tickets:
        thread = await add_admin_ticket_reply(
            session,
            ticket_id=ticket.id,
            admin_user_id=actor_user_id,
            body=selected_reply.body,
            now=current_time,
        )
        threads.append(thread)

    await write_audit_log(
        session,
        action="webapp_admin_support_triage_apply",
        actor_user_id=actor_user_id,
        target_user_id=threads[0].ticket.user_id if len(threads) == 1 else None,
        payload={
            "triage_key": triage_key,
            "ticket_id": ticket_id,
            "ticket_ids": [thread.ticket.id for thread in threads],
            "count": len(threads),
            "pack_key": current_pack_key,
            "route_key": current_route_key,
            "reply_key": selected_reply.key,
        },
    )

    stale_before = current_time - timedelta(hours=24)
    response = {
        "key": triage_key,
        "applied": True,
        "preview_only": False,
        "applied_count": len(threads),
        "applied_ticket_ids": [thread.ticket.id for thread in threads],
        "focused_ticket_id": ticket_id,
        "pack_key": current_pack_key,
        "pack_label": item.get("pack_label"),
        "route_key": current_route_key,
        "route_label": item.get("route_label"),
        "reply": {
            "key": selected_reply.key,
            "title": selected_reply.title,
            "body": selected_reply.body,
            "kind": selected_reply.kind,
        },
        "generated_at_label": format_datetime(current_time, settings.timezone),
        "scope_label": (
            f"{len(threads)} ticket" if len(threads) == 1 else f"{len(threads)} tickets"
        ),
        "operator_note": (
            "Primary canned reply was applied to the confirmed triage scope."
            if len(threads) > 1
            else "Primary canned reply was applied to the confirmed ticket."
        ),
        "sample_tickets": [
            _serialize_support_ticket_list_item(
                thread.ticket,
                settings=settings,
                stale_before=stale_before,
                reference_time=current_time,
            )
            for thread in threads
        ],
    }
    return response, threads
