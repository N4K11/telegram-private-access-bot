from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db.models import SupportMessage, SupportTicket
from app.services.support import build_admin_support_inbox
from app.services.web_admin_dashboard_support_insight_serializers import (
    _serialize_support_insights,
)
from app.services.web_admin_dashboard_support_ticket_serializers import (
    _matches_support_queue,
    _paginate,
    _serialize_support_close_reason_analytics,
    _serialize_support_ticket_list_item,
    _support_queue_counts,
    _support_search_blob,
)
from app.utils.datetime import ensure_aware_utc, utcnow

DEFAULT_PAGE_SIZE = 8
MAX_PAGE_SIZE = 20
PREVIEW_LIMIT = 4
SUPPORT_FILTERS = {
    "open": "Открытые",
    "closed": "Закрытые",
}
SUPPORT_QUEUE_FILTERS = {
    "all": "Все открытые",
    "awaiting_admin": "Ждут админа",
    "awaiting_user": "Ждут пользователя",
    "priority_high": "Высокий приоритет",
    "sla_warning": "Скоро SLA",
    "sla_breach": "SLA нарушен",
    "stale": "Просроченные >24ч",
}
SUPPORT_WAITING_STATE_LABELS = {
    "awaiting_admin": "Ждёт админа",
    "awaiting_user": "Ждёт пользователя",
    "new": "Новый",
    "closed": "Закрыт",
}


async def build_web_admin_support_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    status: str = "open",
    queue: str = "all",
    query: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    now: datetime | None = None,
) -> dict[str, object]:
    del viewer_role
    current_time = ensure_aware_utc(now or utcnow())
    stale_before = current_time - timedelta(hours=24)
    normalized_status = status if status in SUPPORT_FILTERS else "open"
    normalized_queue = (
        queue if normalized_status == "open" and queue in SUPPORT_QUEUE_FILTERS else "all"
    )
    normalized_query = (query or "").strip().casefold()
    result = await session.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.user),
            selectinload(SupportTicket.messages).selectinload(SupportMessage.sender),
        )
        .where(SupportTicket.status == normalized_status)
        .order_by(SupportTicket.updated_at.desc(), SupportTicket.id.desc())
    )
    items = list(result.scalars())
    queue_counts = (
        _support_queue_counts(
            items,
            stale_before=stale_before,
            reference_time=current_time,
        )
        if normalized_status == "open"
        else {"all": len(items)}
    )
    if normalized_status == "open" and normalized_queue != "all":
        items = [
            item
            for item in items
            if _matches_support_queue(
                item,
                queue=normalized_queue,
                stale_before=stale_before,
                reference_time=current_time,
            )
        ]
    if normalized_query:
        items = [item for item in items if normalized_query in _support_search_blob(item)]
    current_items, current_page, total_pages = _paginate(
        items,
        page=page,
        page_size=page_size,
    )
    inbox = await build_admin_support_inbox(
        session,
        status=normalized_status,
        limit=1,
        now=current_time,
    )
    close_reason_analytics = _serialize_support_close_reason_analytics(
        inbox.close_reason_counts,
    )
    support_insights = _serialize_support_insights(inbox.insights)
    return {
        "status": normalized_status,
        "status_label": SUPPORT_FILTERS[normalized_status],
        "queue": normalized_queue,
        "queue_label": SUPPORT_QUEUE_FILTERS.get(normalized_queue, "Все")
        if normalized_status == "open"
        else "Все",
        "queue_counts": queue_counts,
        "query": query or "",
        "page": current_page,
        "total_pages": total_pages,
        "total_items": len(items),
        "open_count": inbox.open_count,
        "closed_count": inbox.closed_count,
        "awaiting_admin_count": inbox.awaiting_admin_count,
        "awaiting_user_count": inbox.awaiting_user_count,
        "stale_open_count": inbox.stale_open_count,
        "high_priority_open_count": inbox.high_priority_open_count,
        "sla_warning_count": inbox.sla_warning_count,
        "sla_breach_count": inbox.sla_breach_count,
        "close_reason_counts": close_reason_analytics["items"],
        "close_reason_summary": {
            "total_closed": close_reason_analytics["total_closed"],
            "top_close_reason": close_reason_analytics["top_close_reason"],
            "top_close_reason_label": close_reason_analytics[
                "top_close_reason_label"
            ],
            "top_close_reason_count": close_reason_analytics[
                "top_close_reason_count"
            ],
            "top_close_reason_share_percent": close_reason_analytics[
                "top_close_reason_share_percent"
            ],
        },
        "insights": support_insights,
        "available_statuses": [
            {"key": key, "label": label} for key, label in SUPPORT_FILTERS.items()
        ],
        "available_queues": [
            {"key": key, "label": label}
            for key, label in (
                SUPPORT_QUEUE_FILTERS.items()
                if normalized_status == "open"
                else (("all", "Все"),)
            )
        ],
        "items": [
            _serialize_support_ticket_list_item(
                item,
                settings=settings,
                stale_before=stale_before,
                reference_time=current_time,
            )
            for item in current_items
        ],
    }


async def _support_overview(
    session: AsyncSession,
    *,
    settings: Settings,
) -> dict[str, object]:
    current_time = ensure_aware_utc(utcnow())
    stale_before = current_time - timedelta(hours=24)
    inbox = await build_admin_support_inbox(
        session,
        status="open",
        limit=PREVIEW_LIMIT,
        now=current_time,
    )
    close_reason_analytics = _serialize_support_close_reason_analytics(
        inbox.close_reason_counts,
    )
    return {
        "open_count": inbox.open_count,
        "closed_count": inbox.closed_count,
        "awaiting_admin_count": inbox.awaiting_admin_count,
        "awaiting_user_count": inbox.awaiting_user_count,
        "stale_open_count": inbox.stale_open_count,
        "high_priority_open_count": inbox.high_priority_open_count,
        "sla_warning_count": inbox.sla_warning_count,
        "sla_breach_count": inbox.sla_breach_count,
        "close_reason_counts": close_reason_analytics["items"],
        "close_reason_summary": {
            "total_closed": close_reason_analytics["total_closed"],
            "top_close_reason": close_reason_analytics["top_close_reason"],
            "top_close_reason_label": close_reason_analytics[
                "top_close_reason_label"
            ],
            "top_close_reason_count": close_reason_analytics[
                "top_close_reason_count"
            ],
            "top_close_reason_share_percent": close_reason_analytics[
                "top_close_reason_share_percent"
            ],
        },
        "recent": [
            _serialize_support_ticket_list_item(
                item,
                settings=settings,
                stale_before=stale_before,
                reference_time=current_time,
            )
            for item in inbox.tickets
        ],
    }
