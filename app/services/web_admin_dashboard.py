# ruff: noqa: E501
from __future__ import annotations

import re
from datetime import datetime, timedelta
from html import unescape

from aiogram import Bot
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db.models import (
    BroadcastCampaign,
    Channel,
    CryptoInvoice,
    Payment,
    PromoCode,
    PromoRedemption,
    SupportMessage,
    SupportTicket,
    Tariff,
)
from app.runtime_state import snapshot_runtime_state
from app.services.admin_roles import (
    PERMISSION_ANALYTICS,
    PERMISSION_BROADCASTS,
    PERMISSION_CHANNELS,
    PERMISSION_DIAGNOSTICS,
    PERMISSION_OBSERVABILITY,
    PERMISSION_PAYMENTS,
    PERMISSION_PROMOS,
    PERMISSION_SUPPORT,
    PERMISSION_TARIFFS,
    PERMISSION_USERS_VIEW,
    has_permission,
)
from app.services.analytics import build_analytics_snapshot
from app.services.audit import write_audit_log
from app.services.channel_diagnostics import build_channel_diagnostics_report
from app.services.observability import sanitize_observability_text
from app.services.profile import build_user_profile_snapshot
from app.services.support import (
    build_admin_support_inbox,
    support_category_label,
    support_status_label,
)
from app.services.users import build_user_directory, filter_label
from app.utils.datetime import ensure_aware_utc, format_datetime, utcnow
from app.utils.encoding import safe_ui_text

DEFAULT_PAGE_SIZE = 8
MAX_PAGE_SIZE = 20
PREVIEW_LIMIT = 4
LARGE_PAGE_SIZE = 5000
USER_FILTERS = ("all", "active", "expired", "never_paid", "blocked", "stars", "crypto")
PAYMENT_FILTERS = {"all": "\u0412\u0441\u0435", "stars": "Telegram Stars", "crypto": "Crypto Pay"}
SUPPORT_FILTERS = {"open": "\u041e\u0442\u043a\u0440\u044b\u0442\u044b\u0435", "closed": "\u0417\u0430\u043a\u0440\u044b\u0442\u044b\u0435"}
SUPPORT_QUEUE_FILTERS = {
    "all": "\u0412\u0441\u0435 \u043e\u0442\u043a\u0440\u044b\u0442\u044b\u0435",
    "awaiting_admin": "\u0416\u0434\u0443\u0442 \u0430\u0434\u043c\u0438\u043d\u0430",
    "awaiting_user": "\u0416\u0434\u0443\u0442 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f",
    "stale": "\u041f\u0440\u043e\u0441\u0440\u043e\u0447\u0435\u043d\u043d\u044b\u0435 >24\u0447",
}
SUPPORT_WAITING_STATE_LABELS = {
    "awaiting_admin": "\u0416\u0434\u0451\u0442 \u0430\u0434\u043c\u0438\u043d\u0430",
    "awaiting_user": "\u0416\u0434\u0451\u0442 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f",
    "new": "\u041d\u043e\u0432\u044b\u0439",
}
PROMO_TYPE_LABELS = {
    "discount_percent": "\u0421\u043a\u0438\u0434\u043a\u0430, %",
    "discount_stars": "\u0421\u043a\u0438\u0434\u043a\u0430, Stars",
    "fixed_price": "\u0424\u0438\u043a\u0441\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u0430\u044f \u0446\u0435\u043d\u0430",
    "free_days": "\u0411\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0435 \u0434\u043d\u0438",
}
_TAG_RE = re.compile(r"<[^>]+>")


async def build_web_admin_dashboard_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    now: datetime | None = None,
) -> dict[str, object]:
    current_time = ensure_aware_utc(now or utcnow())
    capabilities = _capabilities(viewer_role)
    payload: dict[str, object] = {
        "generated_at": current_time.isoformat(),
        "generated_at_label": format_datetime(current_time, settings.timezone),
        "capabilities": capabilities,
    }
    if capabilities["analytics"]:
        snapshot = await build_analytics_snapshot(session, now=current_time)
        payload["summary"] = {
            "total_users": snapshot.total_users,
            "active_subscriptions": snapshot.active_subscriptions,
            "expired_users": snapshot.expired_users,
            "never_paid_users": snapshot.never_paid_users,
            "blocked_users": snapshot.blocked_users,
            "revenue_today": snapshot.revenue_today,
            "revenue_7_days": snapshot.revenue_7_days,
            "revenue_30_days": snapshot.revenue_30_days,
            "revenue_total": snapshot.revenue_total,
            "stars_payments": snapshot.stars_payments,
            "crypto_payments": snapshot.crypto_payments,
            "conversion_started": snapshot.conversion_started,
            "conversion_buy_viewed": snapshot.conversion_buy_viewed,
            "conversion_product_selected": snapshot.conversion_product_selected,
            "conversion_tariff_opened": snapshot.conversion_tariff_opened,
            "conversion_invoice_created": snapshot.conversion_invoice_created,
            "conversion_paid": snapshot.conversion_paid,
            "conversion_invite_issued": snapshot.conversion_invite_issued,
            "repeat_purchase_users": snapshot.repeat_purchase_users,
            "product_funnel": [
                {
                    "channel_id": item.channel_id,
                    "channel_title": item.channel_title,
                    "buy_viewed_users": item.buy_viewed_users,
                    "product_selected_users": item.product_selected_users,
                    "tariff_opened_users": item.tariff_opened_users,
                    "invoice_created_users": item.invoice_created_users,
                    "paid_users": item.paid_users,
                    "invite_issued_users": item.invite_issued_users,
                    "repeat_purchase_users": item.repeat_purchase_users,
                    "revenue_total": item.revenue_total,
                }
                for item in snapshot.product_funnel
            ],
        }
        payload["revenue_chart"] = [
            {"label": "\u0421\u0435\u0433\u043e\u0434\u043d\u044f", "value": snapshot.revenue_today},
            {"label": "7 \u0434\u043d\u0435\u0439", "value": snapshot.revenue_7_days},
            {"label": "30 \u0434\u043d\u0435\u0439", "value": snapshot.revenue_30_days},
            {"label": "\u0412\u0441\u0435\u0433\u043e", "value": snapshot.revenue_total},
        ]
    if capabilities["users"]:
        payload["users_preview"] = await build_web_admin_users_payload(
            session,
            settings=settings,
            viewer_role=viewer_role,
            page_size=PREVIEW_LIMIT,
            now=current_time,
        )
    if capabilities["payments"]:
        payload["payments_preview"] = await build_web_admin_payments_payload(
            session,
            settings=settings,
            viewer_role=viewer_role,
            page_size=PREVIEW_LIMIT,
        )
        payload["crypto_invoices"] = await _crypto_invoice_overview(session, settings=settings)
    if capabilities["support"]:
        payload["support"] = await _support_overview(session, settings=settings)
    if capabilities["promos"]:
        payload["promos"] = await _promo_overview(session, settings=settings)
    if capabilities["tariffs"]:
        payload["tariffs"] = await _tariff_overview(session)
    if capabilities["broadcasts"]:
        payload["broadcasts"] = await _broadcast_overview(session, settings=settings)
    if capabilities["diagnostics"] or capabilities["channels"]:
        payload["channels"] = await _channel_overview(session)
    if capabilities["observability"]:
        payload["anomalies"] = [
            {
                "event_name": item.event_name,
                "source": item.source,
                "message": sanitize_observability_text(item.message),
                "occurred_at_label": format_datetime(item.occurred_at, settings.timezone),
            }
            for item in snapshot_runtime_state().recent_critical_errors[:PREVIEW_LIMIT]
        ]
    return payload


async def build_web_admin_users_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    filter_key: str = "all",
    query: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    now: datetime | None = None,
) -> dict[str, object]:
    del settings
    del viewer_role
    normalized_filter = filter_key if filter_key in USER_FILTERS else "all"
    normalized_query = (query or "").strip().casefold()
    directory = await build_user_directory(
        session,
        filter_key=normalized_filter,
        page=1,
        page_size=LARGE_PAGE_SIZE,
        now=now,
    )
    items = directory.items
    if normalized_query:
        items = [item for item in items if normalized_query in _user_search_blob(item)]
    current_items, current_page, total_pages = _paginate(items, page=page, page_size=page_size)
    return {
        "filter_key": normalized_filter,
        "filter_label": filter_label(normalized_filter),
        "query": query or "",
        "page": current_page,
        "total_pages": total_pages,
        "total_items": len(items),
        "available_filters": [{"key": key, "label": filter_label(key)} for key in USER_FILTERS],
        "items": [
            {
                "user_id": item.user.id,
                "telegram_id": item.user.telegram_id,
                "display_name": _display_name(item.user),
                "username": item.user.username,
                "role": item.user.role,
                "is_admin": bool(item.user.is_admin),
                "is_blocked": bool(item.user.is_blocked),
                "status": item.status,
                "total_paid": item.total_paid,
                "paid_count": item.paid_count,
                "last_seen_at_label": _dt(item.user.last_seen_at, "UTC"),
                "latest_expires_at_label": _dt(item.latest_expires_at, "UTC"),
            }
            for item in current_items
        ],
    }


async def build_web_admin_payments_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    provider_filter: str = "all",
    query: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, object]:
    del viewer_role
    normalized_filter = provider_filter if provider_filter in PAYMENT_FILTERS else "all"
    normalized_query = (query or "").strip().casefold()
    result = await session.execute(
        select(Payment)
        .options(
            selectinload(Payment.user), selectinload(Payment.tariff).selectinload(Tariff.channel)
        )
        .order_by(Payment.paid_at.desc(), Payment.id.desc())
    )
    items = list(result.scalars())
    if normalized_filter == "stars":
        items = [item for item in items if item.provider == "telegram_stars"]
    elif normalized_filter == "crypto":
        items = [item for item in items if item.provider.startswith("crypto")]
    if normalized_query:
        items = [item for item in items if normalized_query in _payment_search_blob(item)]
    current_items, current_page, total_pages = _paginate(items, page=page, page_size=page_size)
    return {
        "provider_filter": normalized_filter,
        "provider_filter_label": PAYMENT_FILTERS[normalized_filter],
        "query": query or "",
        "page": current_page,
        "total_pages": total_pages,
        "total_items": len(items),
        "available_filters": [
            {"key": key, "label": label} for key, label in PAYMENT_FILTERS.items()
        ],
        "items": [
            {
                "id": item.id,
                "user_id": item.user_id,
                "telegram_id": item.user.telegram_id if item.user is not None else None,
                "user_display_name": _display_name(item.user),
                "provider": item.provider,
                "provider_label": "Crypto Pay"
                if item.provider.startswith("crypto")
                else "Telegram Stars",
                "status": item.status,
                "amount": item.amount,
                "currency": item.currency,
                "amount_label": _payment_amount(item),
                "tariff_name": _tariff_name(item.tariff, item.tariff_id),
                "channel_title": _channel_name(item),
                "paid_at_label": _dt(item.paid_at, settings.timezone),
                "created_at_label": _dt(item.created_at, settings.timezone),
            }
            for item in current_items
        ],
    }


async def run_web_admin_channel_check_action(
    session: AsyncSession,
    *,
    bot: Bot,
    settings: Settings,
    actor_user_id: int | None,
) -> dict[str, object]:
    result = await session.execute(
        select(Channel).order_by(Channel.is_active.desc(), Channel.title.asc(), Channel.id.asc())
    )
    channels = list(result.scalars())
    report = await build_channel_diagnostics_report(bot, channels)
    items = [
        {
            "channel_id": item.channel_id,
            "title": item.title,
            "telegram_chat_id": item.telegram_chat_id,
            "is_active": item.is_active,
            "overall_ok": item.overall_ok,
            "checks": [
                {"label": check.label, "ok": check.ok, "details": _plain(check.details)}
                for check in item.checks
            ],
            "recommendations": [
                sanitize_observability_text(_plain(text)) for text in item.recommendations
            ],
        }
        for item in report.results
    ]
    problems = sum(1 for item in items if not item["overall_ok"])
    await write_audit_log(
        session,
        action="webapp_admin_channel_check",
        actor_user_id=actor_user_id,
        payload={
            "checked_channels": len(items),
            "problem_channels": problems,
            "overall_ok": report.overall_ok,
        },
    )
    return {
        "overall_ok": report.overall_ok,
        "checked_channels": len(items),
        "problem_channels": problems,
        "bot_username": report.bot_username,
        "get_me_error": sanitize_observability_text(report.get_me_error),
        "results": items,
        "generated_at_label": format_datetime(utcnow(), settings.timezone),
    }


async def _crypto_invoice_overview(
    session: AsyncSession, *, settings: Settings
) -> dict[str, object]:
    result = await session.execute(
        select(CryptoInvoice)
        .order_by(CryptoInvoice.created_at.desc(), CryptoInvoice.id.desc())
        .limit(PREVIEW_LIMIT)
    )
    return {
        "pending_count": await _count(
            session, select(func.count(CryptoInvoice.id)).where(CryptoInvoice.status == "pending")
        ),
        "paid_count": await _count(
            session, select(func.count(CryptoInvoice.id)).where(CryptoInvoice.status == "paid")
        ),
        "expired_count": await _count(
            session, select(func.count(CryptoInvoice.id)).where(CryptoInvoice.status == "expired")
        ),
        "recent": [
            {
                "id": item.id,
                "user_id": item.user_id,
                "asset": item.asset,
                "amount": format(item.amount, "f"),
                "status": item.status,
                "created_at_label": _dt(item.created_at, settings.timezone),
            }
            for item in result.scalars()
        ],
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
        queue
        if normalized_status == "open" and queue in SUPPORT_QUEUE_FILTERS
        else "all"
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
        _support_queue_counts(items, stale_before=stale_before)
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
            )
        ]
    if normalized_query:
        items = [item for item in items if normalized_query in _support_search_blob(item)]
    current_items, current_page, total_pages = _paginate(items, page=page, page_size=page_size)
    inbox = await build_admin_support_inbox(session, status=normalized_status, limit=1, now=current_time)
    return {
        "status": normalized_status,
        "status_label": SUPPORT_FILTERS[normalized_status],
        "queue": normalized_queue,
        "queue_label": SUPPORT_QUEUE_FILTERS.get(normalized_queue, "\u0412\u0441\u0435")
        if normalized_status == "open"
        else "\u0412\u0441\u0435",
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
        "available_statuses": [
            {"key": key, "label": label} for key, label in SUPPORT_FILTERS.items()
        ],
        "available_queues": [
            {"key": key, "label": label}
            for key, label in (
                SUPPORT_QUEUE_FILTERS.items()
                if normalized_status == "open"
                else (("all", "\u0412\u0441\u0435"),)
            )
        ],
        "items": [
            _serialize_support_ticket_list_item(
                item,
                settings=settings,
                stale_before=stale_before,
            )
            for item in current_items
        ],
    }


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
        .options(selectinload(Payment.user), selectinload(Payment.tariff).selectinload(Tariff.channel))
        .where(Payment.user_id == ticket.user_id)
        .where(Payment.status == "paid")
        .order_by(Payment.paid_at.desc(), Payment.id.desc())
        .limit(PREVIEW_LIMIT)
    )
    payments = list(payment_result.scalars())

    return {
        "ticket": _serialize_support_ticket_list_item(
            ticket,
            settings=settings,
            stale_before=stale_before,
        ),
        "messages": [
            {
                "id": item.id,
                "is_admin": bool(item.is_admin),
                "sender_label": "\u0410\u0434\u043c\u0438\u043d" if item.is_admin else _display_name(item.sender),
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
                "provider_label": "Crypto Pay" if item.provider.startswith("crypto") else "Telegram Stars",
                "tariff_name": _tariff_name(item.tariff, item.tariff_id),
                "channel_title": _channel_name(item),
                "paid_at_label": _dt(item.paid_at, settings.timezone),
            }
            for item in payments
        ],
        "actions": {
            "user_query": str(ticket.user.telegram_id),
            "payments_query": str(ticket.user.telegram_id),
            "profile_path": f"{settings.mini_app_path}/api/users/{ticket.user.telegram_id}/profile",
        },
    }


async def _support_overview(session: AsyncSession, *, settings: Settings) -> dict[str, object]:
    current_time = ensure_aware_utc(utcnow())
    stale_before = current_time - timedelta(hours=24)
    inbox = await build_admin_support_inbox(
        session,
        status="open",
        limit=PREVIEW_LIMIT,
        now=current_time,
    )
    return {
        "open_count": inbox.open_count,
        "closed_count": inbox.closed_count,
        "awaiting_admin_count": inbox.awaiting_admin_count,
        "awaiting_user_count": inbox.awaiting_user_count,
        "stale_open_count": inbox.stale_open_count,
        "recent": [
            _serialize_support_ticket_list_item(
                item,
                settings=settings,
                stale_before=stale_before,
            )
            for item in inbox.tickets
        ],
    }


async def _promo_overview(session: AsyncSession, *, settings: Settings) -> dict[str, object]:
    result = await session.execute(
        select(PromoCode)
        .options(selectinload(PromoCode.tariff))
        .order_by(PromoCode.created_at.desc(), PromoCode.id.desc())
        .limit(PREVIEW_LIMIT)
    )
    return {
        "active_count": await _count(
            session, select(func.count(PromoCode.id)).where(PromoCode.is_active.is_(True))
        ),
        "pending_redemptions": await _count(
            session,
            select(func.count(PromoRedemption.id)).where(PromoRedemption.status == "pending"),
        ),
        "recent": [
            {
                "id": item.id,
                "code": item.code,
                "promo_type": item.promo_type,
                "promo_type_label": PROMO_TYPE_LABELS.get(item.promo_type, item.promo_type),
                "value_label": _promo_value(item),
                "campaign_name": item.campaign_name,
                "tariff_name": _tariff_name(item.tariff, item.tariff_id),
                "is_active": bool(item.is_active),
                "valid_until_label": _dt(item.valid_until, settings.timezone),
            }
            for item in result.scalars()
        ],
    }


async def _tariff_overview(session: AsyncSession) -> dict[str, object]:
    result = await session.execute(
        select(Tariff)
        .options(selectinload(Tariff.channel))
        .order_by(Tariff.sort_order.asc(), Tariff.id.asc())
        .limit(PREVIEW_LIMIT)
    )
    return {
        "active_count": await _count(
            session,
            select(func.count(Tariff.id))
            .where(Tariff.is_active.is_(True))
            .where(Tariff.archived_at.is_(None)),
        ),
        "inactive_count": await _count(
            session, select(func.count(Tariff.id)).where(Tariff.is_active.is_(False))
        ),
        "items": [
            {
                "id": item.id,
                "name": safe_ui_text(item.name, f"\u0422\u0430\u0440\u0438\u0444 #{item.id}"),
                "duration_days": item.duration_days,
                "price_stars": item.price_stars,
                "channel_title": safe_ui_text(
                    item.channel.title if item.channel is not None else None,
                    f"\u041a\u0430\u043d\u0430\u043b #{item.channel_id or '?'}",
                ),
                "is_active": bool(item.is_active),
            }
            for item in result.scalars()
        ],
    }


async def _broadcast_overview(session: AsyncSession, *, settings: Settings) -> dict[str, object]:
    result = await session.execute(
        select(BroadcastCampaign)
        .order_by(BroadcastCampaign.created_at.desc(), BroadcastCampaign.id.desc())
        .limit(PREVIEW_LIMIT)
    )
    return {
        "total_count": await _count(session, select(func.count(BroadcastCampaign.id))),
        "active_count": await _count(
            session,
            select(func.count(BroadcastCampaign.id)).where(BroadcastCampaign.status == "running"),
        ),
        "recent": [
            {
                "id": item.id,
                "filter_name": item.filter_name,
                "status": item.status,
                "total_targets": item.total_targets,
                "sent_count": item.sent_count,
                "failed_count": item.failed_count,
                "finished_at_label": _dt(item.finished_at, settings.timezone),
            }
            for item in result.scalars()
        ],
    }


async def _channel_overview(session: AsyncSession) -> dict[str, object]:
    result = await session.execute(
        select(Channel)
        .order_by(Channel.is_active.desc(), Channel.title.asc(), Channel.id.asc())
        .limit(PREVIEW_LIMIT)
    )
    return {
        "total_count": await _count(session, select(func.count(Channel.id))),
        "active_count": await _count(
            session, select(func.count(Channel.id)).where(Channel.is_active.is_(True))
        ),
        "invite_warning_count": await _count(
            session,
            select(func.count(Channel.id)).where(Channel.invite_users_permission.is_(False)),
        ),
        "restrict_warning_count": await _count(
            session, select(func.count(Channel.id)).where(Channel.ban_users_permission.is_(False))
        ),
        "items": [
            {
                "id": item.id,
                "title": safe_ui_text(item.title, f"\u041a\u0430\u043d\u0430\u043b #{item.id}"),
                "telegram_chat_id": item.telegram_chat_id,
                "is_active": bool(item.is_active),
            }
            for item in result.scalars()
        ],
    }


def _capabilities(role: str) -> dict[str, bool]:
    return {
        "analytics": has_permission(role, PERMISSION_ANALYTICS),
        "users": has_permission(role, PERMISSION_USERS_VIEW),
        "payments": has_permission(role, PERMISSION_PAYMENTS),
        "support": has_permission(role, PERMISSION_SUPPORT),
        "promos": has_permission(role, PERMISSION_PROMOS),
        "tariffs": has_permission(role, PERMISSION_TARIFFS),
        "broadcasts": has_permission(role, PERMISSION_BROADCASTS),
        "diagnostics": has_permission(role, PERMISSION_DIAGNOSTICS),
        "observability": has_permission(role, PERMISSION_OBSERVABILITY),
        "channels": has_permission(role, PERMISSION_CHANNELS),
    }


def _paginate(items, *, page: int, page_size: int):
    safe_page_size = min(max(int(page_size or DEFAULT_PAGE_SIZE), 1), MAX_PAGE_SIZE)
    total_pages = max(1, (len(items) + safe_page_size - 1) // safe_page_size)
    current_page = min(max(int(page or 1), 1), total_pages)
    start = (current_page - 1) * safe_page_size
    return items[start : start + safe_page_size], current_page, total_pages


def _user_search_blob(item) -> str:
    user = item.user
    return " ".join(
        part.casefold()
        for part in (
            str(user.id),
            str(user.telegram_id),
            user.username or "",
            user.first_name or "",
            user.last_name or "",
            item.status,
        )
        if part
    )


def _payment_search_blob(item: Payment) -> str:
    return " ".join(
        part.casefold()
        for part in (
            str(item.id),
            str(item.user_id),
            str(item.user.telegram_id) if item.user is not None else "",
            item.user.username if item.user is not None and item.user.username else "",
            item.tariff.name if item.tariff is not None else "",
            item.provider,
            item.currency,
        )
        if part
    )


def _display_name(user) -> str:
    if user is None:
        return "\u2014"
    parts = [
        part for part in (user.first_name, user.last_name) if isinstance(part, str) and part.strip()
    ]
    if parts:
        return " ".join(part.strip() for part in parts)
    if user.username:
        return f"@{user.username}"
    return f"User {user.telegram_id}"



def _serialize_support_ticket_list_item(
    ticket: SupportTicket,
    *,
    settings: Settings,
    stale_before: datetime | None = None,
) -> dict[str, object]:
    waiting_state = _support_waiting_state(ticket)
    return {
        "id": ticket.id,
        "user_id": ticket.user_id,
        "telegram_id": ticket.user.telegram_id if ticket.user is not None else None,
        "user_display_name": _display_name(ticket.user),
        "category": ticket.category,
        "category_label": support_category_label(ticket.category),
        "status": ticket.status,
        "status_label": support_status_label(ticket.status),
        "waiting_state": waiting_state,
        "waiting_state_label": SUPPORT_WAITING_STATE_LABELS.get(waiting_state, waiting_state),
        "updated_at_label": _dt(ticket.updated_at, settings.timezone),
        "created_at_label": _dt(ticket.created_at, settings.timezone),
        "closed_at_label": _dt(ticket.closed_at, settings.timezone),
        "message_count": len(ticket.messages or []),
        "last_message_preview": _support_last_message_preview(ticket),
        "is_open": ticket.status == "open",
        "is_stale": _is_support_ticket_stale(ticket, stale_before=stale_before),
    }


def _serialize_support_profile_summary(snapshot, *, settings: Settings) -> dict[str, object] | None:
    if snapshot is None:
        return None
    return {
        "telegram_id": snapshot.user.telegram_id,
        "display_name": _display_name(snapshot.user),
        "status_label": snapshot.status_label,
        "latest_expires_at_label": _dt(snapshot.latest_expires_at, settings.timezone),
        "remaining_label": snapshot.remaining_label,
        "current_tariff_label": snapshot.current_tariff_label,
        "current_channel_label": snapshot.current_channel_label,
        "active_subscription_count": snapshot.active_subscription_count,
        "total_stars_amount": snapshot.total_stars_amount,
    }


def _support_search_blob(ticket: SupportTicket) -> str:
    return " ".join(
        part.casefold()
        for part in (
            str(ticket.id),
            str(ticket.user_id),
            str(ticket.user.telegram_id) if ticket.user is not None else "",
            ticket.user.username if ticket.user is not None and ticket.user.username else "",
            ticket.user.first_name if ticket.user is not None and ticket.user.first_name else "",
            ticket.user.last_name if ticket.user is not None and ticket.user.last_name else "",
            ticket.category,
            ticket.status,
        )
        if part
    )


def _support_last_message_preview(ticket: SupportTicket) -> str | None:
    if not ticket.messages:
        return None
    preview = sanitize_observability_text(_plain(ticket.messages[-1].body))
    return _truncate(preview, limit=160)


def _matches_support_queue(
    ticket: SupportTicket,
    *,
    queue: str,
    stale_before: datetime,
) -> bool:
    if queue == "all":
        return True
    if queue == "awaiting_admin":
        return _support_waiting_state(ticket) == "awaiting_admin"
    if queue == "awaiting_user":
        return _support_waiting_state(ticket) == "awaiting_user"
    if queue == "stale":
        return _is_support_ticket_stale(ticket, stale_before=stale_before)
    return True


def _support_queue_counts(
    tickets: list[SupportTicket],
    *,
    stale_before: datetime,
) -> dict[str, int]:
    return {
        "all": len(tickets),
        "awaiting_admin": sum(
            1 for ticket in tickets if _support_waiting_state(ticket) == "awaiting_admin"
        ),
        "awaiting_user": sum(
            1 for ticket in tickets if _support_waiting_state(ticket) == "awaiting_user"
        ),
        "stale": sum(
            1 for ticket in tickets if _is_support_ticket_stale(ticket, stale_before=stale_before)
        ),
    }


def _is_support_ticket_stale(
    ticket: SupportTicket,
    *,
    stale_before: datetime | None,
) -> bool:
    if stale_before is None or ticket.status != "open" or ticket.updated_at is None:
        return False
    return ensure_aware_utc(ticket.updated_at) < stale_before


def _truncate(value: str | None, *, limit: int) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)].rstrip() + "…"


def _support_waiting_state(ticket) -> str:
    if ticket.last_user_message_at and (
        ticket.last_admin_message_at is None
        or ticket.last_user_message_at > ticket.last_admin_message_at
    ):
        return "awaiting_admin"
    if ticket.last_admin_message_at is not None:
        return "awaiting_user"
    return "new"


def _payment_amount(item: Payment) -> str:
    if item.provider == "telegram_stars" or item.currency == "XTR":
        return f"{item.amount} Stars"
    return f"{item.amount} {item.currency}"


def _tariff_name(tariff: Tariff | None, tariff_id: int | None) -> str:
    if tariff is not None:
        return safe_ui_text(tariff.name, f"\u0422\u0430\u0440\u0438\u0444 #{tariff.id}")
    if tariff_id is not None:
        return f"\u0422\u0430\u0440\u0438\u0444 #{tariff_id}"
    return "\u2014"


def _channel_name(item: Payment) -> str | None:
    if item.tariff is not None and item.tariff.channel is not None:
        return safe_ui_text(
            item.tariff.channel.title,
            f"\u041a\u0430\u043d\u0430\u043b #{item.channel_id or '?'}",
        )
    return None


def _promo_value(item: PromoCode) -> str:
    if item.promo_type == "discount_percent":
        return f"-{item.value}%"
    if item.promo_type == "discount_stars":
        return f"-{item.value} Stars"
    if item.promo_type == "fixed_price":
        return f"{item.value} Stars"
    if item.promo_type == "free_days":
        return f"+{item.value} \u0434\u043d."
    return str(item.value)


def _dt(value: datetime | None, timezone: str) -> str | None:
    if value is None:
        return None
    return format_datetime(ensure_aware_utc(value), timezone)


def _plain(value: str) -> str:
    return " ".join(_TAG_RE.sub("", unescape(value)).split())


async def _count(session: AsyncSession, statement) -> int:
    return int((await session.execute(statement)).scalar_one() or 0)
