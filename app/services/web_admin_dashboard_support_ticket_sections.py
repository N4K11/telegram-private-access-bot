from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db.models import Payment, SupportMessage, SupportTicket, Tariff
from app.services.observability import sanitize_observability_text
from app.services.profile import build_user_profile_snapshot
from app.services.support import (
    build_admin_support_inbox,
    support_action_lane,
    support_canned_reply_pack_key,
    support_escalation_lane,
)
from app.services.web_admin_dashboard_common import PREVIEW_LIMIT
from app.services.web_admin_dashboard_support_insight_serializers import (
    _serialize_support_insights,
)
from app.services.web_admin_dashboard_support_ticket_serializers import (
    _build_support_operator_hints,
    _channel_name,
    _display_name,
    _dt,
    _payment_amount,
    _plain,
    _serialize_support_canned_replies,
    _serialize_support_next_action,
    _serialize_support_profile_summary,
    _serialize_support_ticket_list_item,
    _serialize_support_ticket_pinned_context,
    _tariff_name,
)
from app.utils.datetime import ensure_aware_utc, utcnow


async def build_web_admin_support_ticket_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    ticket_id: int,
) -> dict[str, object] | None:
    del viewer_role
    current_time = ensure_aware_utc(utcnow())
    stale_before = current_time - timedelta(hours=24)
    result = await session.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.user),
            selectinload(SupportTicket.messages).selectinload(SupportMessage.sender),
        )
        .where(SupportTicket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    if ticket is None:
        return None

    profile_snapshot = await build_user_profile_snapshot(
        session,
        telegram_user_id=ticket.user.telegram_id,
        history_limit=PREVIEW_LIMIT,
    )
    payment_result = await session.execute(
        select(Payment)
        .options(
            selectinload(Payment.user),
            selectinload(Payment.tariff).selectinload(Tariff.channel),
        )
        .where(Payment.user_id == ticket.user_id)
        .where(Payment.status == "paid")
        .order_by(Payment.paid_at.desc(), Payment.id.desc())
        .limit(PREVIEW_LIMIT)
    )
    payments = list(payment_result.scalars())
    suggested_replies = _serialize_support_canned_replies(ticket)
    next_action = _serialize_support_next_action(
        ticket,
        reference_time=current_time,
    )
    triage_batch = None
    if ticket.status == "open":
        support_inbox = await build_admin_support_inbox(
            session,
            status="open",
            limit=1,
            now=current_time,
        )
        triage_batch = _serialize_support_ticket_triage_batch(
            ticket,
            support_inbox=support_inbox,
            reference_time=current_time,
        )

    pinned_context = _serialize_support_ticket_pinned_context(
        ticket,
        profile_snapshot=profile_snapshot,
        payments=payments,
        settings=settings,
        reference_time=current_time,
        triage_batch=triage_batch,
    )
    operator_hints = _build_support_operator_hints(
        ticket,
        profile_snapshot=profile_snapshot,
        payments=payments,
        reference_time=current_time,
    )

    return {
        "ticket": _serialize_support_ticket_list_item(
            ticket,
            settings=settings,
            stale_before=stale_before,
            reference_time=current_time,
        ),
        "next_action": next_action,
        "triage_batch": triage_batch,
        "pinned_context": pinned_context,
        "operator_hints": operator_hints,
        "messages": [
            {
                "id": item.id,
                "is_admin": bool(item.is_admin),
                "sender_label": "Админ" if item.is_admin else _display_name(item.sender),
                "body": sanitize_observability_text(_plain(item.body)),
                "created_at_label": _dt(item.created_at, settings.timezone),
            }
            for item in ticket.messages
        ],
        "profile": _serialize_support_profile_summary(
            profile_snapshot,
            settings=settings,
        ),
        "payments_preview": [
            {
                "id": item.id,
                "amount_label": _payment_amount(item),
                "provider_label": "Crypto Pay"
                if item.provider.startswith("crypto")
                else "Telegram Stars",
                "tariff_name": _tariff_name(item.tariff, item.tariff_id),
                "channel_title": _channel_name(item),
                "paid_at_label": _dt(item.paid_at, settings.timezone),
            }
            for item in payments
        ],
        "suggested_replies": suggested_replies,
        "actions": {
            "user_query": str(ticket.user.telegram_id),
            "payments_query": str(ticket.user.telegram_id),
            "profile_path": f"{settings.mini_app_path}/api/users/{ticket.user.telegram_id}/profile",
            "triage_confirm_key": triage_batch["key"] if triage_batch is not None else None,
        },
    }


def _serialize_support_ticket_triage_batch(
    ticket: SupportTicket,
    *,
    support_inbox,
    reference_time: datetime,
) -> dict[str, object] | None:
    support_insights = _serialize_support_insights(support_inbox.insights)
    triage_key = (
        f"{support_escalation_lane(ticket, now=reference_time)}:"
        f"{support_action_lane(ticket, now=reference_time)}:"
        f"{support_canned_reply_pack_key(ticket)}"
    )
    for item in support_insights.get("triage_plans", []):
        if item.get("key") == triage_key:
            return item
    return None
