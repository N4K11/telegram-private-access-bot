from __future__ import annotations

from datetime import datetime

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db.models import Channel, Payment, Tariff
from app.services.audit import write_audit_log
from app.services.channel_diagnostics import build_channel_diagnostics_report
from app.services.observability import sanitize_observability_text
from app.services.users import build_user_directory, filter_label
from app.services.web_admin_dashboard_common import (
    DEFAULT_PAGE_SIZE,
    LARGE_PAGE_SIZE,
    PAYMENT_FILTERS,
    USER_FILTERS,
    _channel_name,
    _display_name,
    _dt,
    _paginate,
    _payment_amount,
    _payment_search_blob,
    _plain,
    _tariff_name,
    _user_search_blob,
)
from app.utils.datetime import format_datetime, utcnow


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
            selectinload(Payment.user),
            selectinload(Payment.tariff).selectinload(Tariff.channel),
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
