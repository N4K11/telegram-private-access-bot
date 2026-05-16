# ruff: noqa: E501
from __future__ import annotations

import re
from datetime import datetime
from html import unescape

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, PromoCode, Tariff
from app.services.web_admin_dashboard_limits import (
    ADMIN_PAGE_DEFAULT_SIZE,
    ADMIN_PAGE_MAX_SIZE,
    ADMIN_PREVIEW_LIMIT,
    clamp_admin_page_size,
)
from app.utils.datetime import ensure_aware_utc, format_datetime
from app.utils.encoding import safe_ui_text

DEFAULT_PAGE_SIZE = ADMIN_PAGE_DEFAULT_SIZE
MAX_PAGE_SIZE = ADMIN_PAGE_MAX_SIZE
PREVIEW_LIMIT = ADMIN_PREVIEW_LIMIT
LARGE_PAGE_SIZE = 5000
USER_FILTERS = ("all", "active", "expired", "never_paid", "blocked", "stars", "crypto")
PAYMENT_FILTERS = {"all": "Все", "stars": "Telegram Stars", "crypto": "Crypto Pay"}
PROMO_TYPE_LABELS = {
    "discount_percent": "Скидка, %",
    "discount_stars": "Скидка, Stars",
    "fixed_price": "Фиксированная цена",
    "free_days": "Бесплатные дни",
}
_TAG_RE = re.compile(r"<[^>]+>")


def _paginate(items, *, page: int, page_size: int):
    safe_page_size = clamp_admin_page_size(page_size, default=DEFAULT_PAGE_SIZE)
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
        return "—"
    parts = [
        part for part in (user.first_name, user.last_name) if isinstance(part, str) and part.strip()
    ]
    if parts:
        return " ".join(part.strip() for part in parts)
    if user.username:
        return f"@{user.username}"
    return f"User {user.telegram_id}"


def _payment_amount(item: Payment) -> str:
    if item.provider == "telegram_stars" or item.currency == "XTR":
        return f"{item.amount} Stars"
    return f"{item.amount} {item.currency}"


def _tariff_name(tariff: Tariff | None, tariff_id: int | None) -> str:
    if tariff is not None:
        return safe_ui_text(tariff.name, f"Тариф #{tariff.id}")
    if tariff_id is not None:
        return f"Тариф #{tariff_id}"
    return "—"


def _channel_name(item: Payment) -> str | None:
    if item.tariff is not None and item.tariff.channel is not None:
        return safe_ui_text(
            item.tariff.channel.title,
            f"Канал #{item.channel_id or '?'}",
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
        return f"+{item.value} дн."
    return str(item.value)


def _dt(value: datetime | None, timezone: str) -> str | None:
    if value is None:
        return None
    return format_datetime(ensure_aware_utc(value), timezone)


def _plain(value: str) -> str:
    return " ".join(_TAG_RE.sub("", unescape(value)).split())


async def _count(session: AsyncSession, statement) -> int:
    return int((await session.execute(statement)).scalar_one() or 0)
