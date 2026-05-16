from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db.models import (
    BroadcastCampaign,
    Channel,
    CryptoInvoice,
    PromoCode,
    PromoRedemption,
    Tariff,
)
from app.services.web_admin_dashboard_common import (
    PREVIEW_LIMIT,
    PROMO_TYPE_LABELS,
    _count,
    _dt,
    _promo_value,
    _tariff_name,
)
from app.utils.encoding import safe_ui_text


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
                "name": safe_ui_text(item.name, f"Тариф #{item.id}"),
                "duration_days": item.duration_days,
                "price_stars": item.price_stars,
                "channel_title": safe_ui_text(
                    item.channel.title if item.channel is not None else None,
                    f"Канал #{item.channel_id or '?'}",
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
                "title": safe_ui_text(item.title, f"Канал #{item.id}"),
                "telegram_chat_id": item.telegram_chat_id,
                "is_active": bool(item.is_active),
            }
            for item in result.scalars()
        ],
    }
