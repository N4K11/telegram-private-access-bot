from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Payment, PromoCode, PromoRedemption, SupportTicket, Tariff, User
from app.db.repositories.payments import PaymentRepository
from app.db.repositories.promo_redemptions import PromoRedemptionRepository
from app.db.repositories.tariffs import TariffRepository
from app.services.analytics import build_analytics_snapshot
from app.services.multi_channel_access_service import load_active_product_access
from app.services.product_service import (
    ProductCatalogEntry,
    build_offer_details,
    build_product_catalog,
    pick_default_tariff,
)
from app.services.profile import UserProfileSnapshot, build_user_profile_snapshot
from app.services.promo_service import (
    PROMO_TYPE_DISCOUNT_PERCENT,
    PROMO_TYPE_DISCOUNT_STARS,
    PROMO_TYPE_FIXED_PRICE,
    PROMO_TYPE_FREE_DAYS,
    effective_promo_valid_until,
)
from app.services.referral_service import build_user_referral_dashboard
from app.services.support import (
    SupportUserDashboard,
    build_user_support_dashboard,
    support_category_label,
    support_status_label,
)
from app.utils.datetime import ensure_aware_utc, format_datetime
from app.utils.encoding import safe_ui_text

MAX_CABINET_PAYMENT_ITEMS = 10
MAX_CABINET_PROMO_ITEMS = 5
MAX_CABINET_SUPPORT_ITEMS = 5
PROMO_STATUS_PENDING = "pending"
PROMO_STATUS_CONSUMED = "consumed"
PROMO_STATUS_CANCELLED = "cancelled"
PROMO_STATUS_LABELS = {
    PROMO_STATUS_PENDING: "Ждёт применения",
    PROMO_STATUS_CONSUMED: "Использован",
    PROMO_STATUS_CANCELLED: "Отменён",
}


async def build_cabinet_bootstrap_payload(
    session: AsyncSession,
    *,
    user: User,
    settings: Settings,
) -> dict[str, object]:
    snapshot = await build_user_profile_snapshot(
        session,
        telegram_user_id=user.telegram_id,
        history_limit=MAX_CABINET_PAYMENT_ITEMS,
    )
    referral_dashboard = await build_user_referral_dashboard(
        session,
        user_id=user.id,
        bot_username=settings.bot_public_username,
    )
    support_dashboard = await build_user_support_dashboard(
        session,
        user_id=user.id,
        limit=MAX_CABINET_SUPPORT_ITEMS,
    )
    pending_promos = await PromoRedemptionRepository(session).list_pending_for_user(user.id)
    tariffs = await TariffRepository(session).list_active()
    product_catalog = build_product_catalog(tariffs)
    active_products = await load_active_product_access(session, user_id=user.id)
    recent_payments = await PaymentRepository(session).list_recent_paid_for_user(
        user.id,
        limit=MAX_CABINET_PAYMENT_ITEMS,
    )
    return {
        "viewer": _serialize_user(user),
        "profile": _serialize_profile_snapshot(snapshot, settings=settings),
        "products": [_serialize_product(product) for product in product_catalog],
        "active_products": [
            _serialize_active_product(product, settings=settings)
            for product in active_products
        ],
        "tariffs": [_serialize_tariff(tariff, baseline_tariff=None) for tariff in tariffs],
        "recent_payments": [
            _serialize_payment(payment, settings=settings)
            for payment in recent_payments
        ],
        "referrals": _serialize_referral_dashboard(referral_dashboard),
        "pending_promos": [
            _serialize_pending_promo(redemption, settings=settings)
            for redemption in pending_promos[:MAX_CABINET_PROMO_ITEMS]
            if redemption.promo_code is not None
        ],
        "support": _serialize_support_dashboard(support_dashboard, settings=settings),
        "actions": _serialize_cabinet_actions(settings=settings),
        "mini_app_path": settings.mini_app_path,
    }


async def build_cabinet_profile_payload(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    settings: Settings,
) -> dict[str, object] | None:
    snapshot = await build_user_profile_snapshot(
        session,
        telegram_user_id=telegram_user_id,
        history_limit=MAX_CABINET_PAYMENT_ITEMS,
    )
    if snapshot is None:
        return None
    recent_payments = await PaymentRepository(session).list_recent_paid_for_user(
        snapshot.user.id,
        limit=MAX_CABINET_PAYMENT_ITEMS,
    )
    referral_dashboard = await build_user_referral_dashboard(
        session,
        user_id=snapshot.user.id,
        bot_username=settings.bot_public_username,
    )
    support_dashboard = await build_user_support_dashboard(
        session,
        user_id=snapshot.user.id,
        limit=MAX_CABINET_SUPPORT_ITEMS,
    )
    pending_promos = await PromoRedemptionRepository(session).list_pending_for_user(
        snapshot.user.id,
    )
    tariffs = await TariffRepository(session).list_active()
    product_catalog = build_product_catalog(tariffs)
    active_products = await load_active_product_access(session, user_id=snapshot.user.id)
    return {
        "viewer": _serialize_user(snapshot.user),
        "profile": _serialize_profile_snapshot(snapshot, settings=settings),
        "products": [_serialize_product(product) for product in product_catalog],
        "active_products": [
            _serialize_active_product(product, settings=settings)
            for product in active_products
        ],
        "tariffs": [_serialize_tariff(tariff, baseline_tariff=None) for tariff in tariffs],
        "recent_payments": [
            _serialize_payment(payment, settings=settings)
            for payment in recent_payments
        ],
        "referrals": _serialize_referral_dashboard(referral_dashboard),
        "pending_promos": [
            _serialize_pending_promo(redemption, settings=settings)
            for redemption in pending_promos[:MAX_CABINET_PROMO_ITEMS]
            if redemption.promo_code is not None
        ],
        "support": _serialize_support_dashboard(support_dashboard, settings=settings),
        "actions": _serialize_cabinet_actions(settings=settings),
    }


async def build_cabinet_admin_summary_payload(
    session: AsyncSession,
    *,
    settings: Settings,
) -> dict[str, object]:
    snapshot = await build_analytics_snapshot(session)
    return {
        "timezone": settings.timezone,
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


def _serialize_user(user: User) -> dict[str, object]:
    return {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "display_name": _display_name(user),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "language_code": user.language_code,
        "role": user.role,
        "is_admin": bool(user.is_admin),
        "is_blocked": bool(user.is_blocked),
        "last_seen_at": _isoformat(user.last_seen_at),
    }


def _serialize_profile_snapshot(
    snapshot: UserProfileSnapshot | None,
    *,
    settings: Settings,
) -> dict[str, object] | None:
    if snapshot is None:
        return None
    return {
        "status": snapshot.status,
        "status_label": snapshot.status_label,
        "has_active_subscription": snapshot.has_active_subscription,
        "active_subscription_count": snapshot.active_subscription_count,
        "latest_expires_at": _isoformat(snapshot.latest_expires_at),
        "latest_expires_at_label": _format_optional_datetime(
            snapshot.latest_expires_at,
            settings.timezone,
        ),
        "remaining_label": snapshot.remaining_label,
        "current_tariff_label": snapshot.current_tariff_label,
        "current_channel_label": snapshot.current_channel_label,
        "total_stars_amount": snapshot.total_stars_amount,
        "total_crypto_amounts": {
            asset: _serialize_decimal(amount)
            for asset, amount in snapshot.total_crypto_amounts.items()
        },
        "last_payment_at": _isoformat(snapshot.last_payment_at),
        "last_payment_at_label": _format_optional_datetime(
            snapshot.last_payment_at,
            settings.timezone,
        ),
        "referral_payload": snapshot.referral_payload,
        "pending_referral_reward_days": snapshot.pending_referral_reward_days,
        "rewarded_referrals_count": snapshot.rewarded_referrals_count,
    }


def _serialize_referral_dashboard(dashboard: object) -> dict[str, object] | None:
    if dashboard is None:
        return None
    return {
        "referral_payload": dashboard.referral_payload,
        "referral_link": dashboard.referral_link,
        "invited_users_count": dashboard.invited_users_count,
        "paid_referrals_count": dashboard.paid_referrals_count,
        "earned_days": dashboard.earned_days,
        "pending_reward_days": dashboard.pending_reward_days,
    }


def _serialize_support_dashboard(
    dashboard: SupportUserDashboard,
    *,
    settings: Settings,
) -> dict[str, object]:
    return {
        "open_ticket": _serialize_support_ticket(
            dashboard.open_ticket,
            settings=settings,
        ),
        "recent_tickets": [
            _serialize_support_ticket(ticket, settings=settings)
            for ticket in dashboard.recent_tickets[:MAX_CABINET_SUPPORT_ITEMS]
        ],
        "open_count": dashboard.open_count,
        "closed_count": dashboard.closed_count,
    }


def _serialize_support_ticket(
    ticket: SupportTicket | None,
    *,
    settings: Settings,
) -> dict[str, object] | None:
    if ticket is None:
        return None
    return {
        "id": ticket.id,
        "category": ticket.category,
        "category_label": support_category_label(ticket.category),
        "status": ticket.status,
        "status_label": support_status_label(ticket.status),
        "message_count": len(ticket.messages or []),
        "updated_at": _isoformat(ticket.updated_at),
        "updated_at_label": _format_optional_datetime(ticket.updated_at, settings.timezone),
        "last_user_message_at_label": _format_optional_datetime(
            ticket.last_user_message_at,
            settings.timezone,
        ),
        "last_admin_message_at_label": _format_optional_datetime(
            ticket.last_admin_message_at,
            settings.timezone,
        ),
        "closed_at_label": _format_optional_datetime(ticket.closed_at, settings.timezone),
    }


def _serialize_pending_promo(
    redemption: PromoRedemption,
    *,
    settings: Settings,
) -> dict[str, object]:
    promo_code = redemption.promo_code
    if promo_code is None:
        raise ValueError("Pending promo redemption must include promo code")
    tariff_name = None
    if promo_code.tariff is not None:
        tariff_name = safe_ui_text(
            promo_code.tariff.name,
            f"Tariff #{promo_code.tariff_id or '?'}",
        )
    elif redemption.tariff is not None:
        tariff_name = safe_ui_text(
            redemption.tariff.name,
            f"Tariff #{redemption.applied_tariff_id or '?'}",
        )
    valid_until = effective_promo_valid_until(promo_code)
    return {
        "id": redemption.id,
        "code": promo_code.code,
        "promo_type": promo_code.promo_type,
        "status": redemption.status,
        "status_label": PROMO_STATUS_LABELS.get(redemption.status, redemption.status),
        "discount_label": _serialize_promo_value(promo_code),
        "tariff_name": tariff_name,
        "campaign_name": promo_code.campaign_name,
        "first_purchase_only": bool(promo_code.first_purchase_only),
        "valid_until": _isoformat(valid_until),
        "valid_until_label": _format_optional_datetime(valid_until, settings.timezone),
    }


def _serialize_cabinet_actions(*, settings: Settings) -> dict[str, object]:
    return {
        "bot_username": settings.bot_public_username,
        "bot_link": settings.bot_public_link,
        "renew_link": settings.bot_public_link,
        "support_link": settings.bot_public_link,
        "promo_command": "/promo CODE",
        "support_command": "/support",
        "cabinet_path": settings.mini_app_path,
    }


def _serialize_product(product: ProductCatalogEntry) -> dict[str, object]:
    default_tariff = pick_default_tariff(product.tariffs)
    return {
        "channel_id": product.channel_id,
        "title": product.channel_title,
        "username": product.channel_username,
        "tariff_count": product.tariff_count,
        "price_from_stars": product.price_from_stars,
        "price_to_stars": product.price_to_stars,
        "price_range_label": product.price_range_label,
        "featured_tariff_id": product.featured_tariff_id,
        "default_tariff_id": product.default_tariff_id,
        "bundle_names": list(product.bundle_names),
        "tariffs": [
            _serialize_tariff(tariff, baseline_tariff=default_tariff)
            for tariff in product.tariffs
        ],
    }


def _serialize_active_product(product, *, settings: Settings) -> dict[str, object]:
    return {
        "channel_id": product.channel_id,
        "title": product.channel_title,
        "latest_expires_at": _isoformat(product.latest_expires_at),
        "latest_expires_at_label": _format_optional_datetime(
            product.latest_expires_at,
            settings.timezone,
        ),
        "subscription_count": product.subscription_count,
        "tariff_names": list(product.tariff_names),
        "subscription_ids": list(product.subscription_ids),
    }


def _serialize_tariff(
    tariff: Tariff,
    *,
    baseline_tariff: Tariff | None,
) -> dict[str, object]:
    crypto_amount = getattr(tariff, "crypto_price_amount", None)
    if crypto_amount is None:
        crypto_amount = getattr(tariff, "price_crypto", None)
    channel_title = None
    if tariff.channel is not None:
        channel_title = safe_ui_text(
            tariff.channel.title,
            f"Channel #{tariff.channel_id}",
        )
    offer = build_offer_details(tariff, baseline_tariff=baseline_tariff)
    return {
        "id": tariff.id,
        "name": safe_ui_text(tariff.name, f"Tariff #{tariff.id}"),
        "description": tariff.description,
        "badge": tariff.badge,
        "duration_days": tariff.duration_days,
        "is_trial": bool(tariff.is_trial),
        "is_lifetime": bool(tariff.is_lifetime),
        "price_stars": tariff.price_stars,
        "crypto_price_amount": _serialize_decimal(crypto_amount),
        "crypto_asset": tariff.crypto_asset,
        "channel_id": tariff.channel_id,
        "channel_title": channel_title,
        "offer_copy": offer.offer_copy,
        "offer_group": offer.offer_group,
        "price_per_day_label": offer.price_per_day_label,
        "savings_label": offer.savings_label,
        "is_featured": offer.is_featured,
        "is_default_offer": offer.is_default_offer,
    }


def _serialize_payment(payment: Payment, *, settings: Settings) -> dict[str, object]:
    tariff_name = safe_ui_text(
        payment.tariff.name if payment.tariff is not None else None,
        f"Tariff #{payment.tariff_id or '?'}",
    )
    channel_title = None
    if payment.tariff is not None and payment.tariff.channel is not None:
        channel_title = safe_ui_text(
            payment.tariff.channel.title,
            f"Channel #{payment.channel_id or '?'}",
        )
    amount_label = f"{payment.amount} {payment.currency}"
    if payment.currency == "XTR":
        amount_label = f"{payment.amount} Stars"
    return {
        "id": payment.id,
        "provider": payment.provider,
        "status": payment.status,
        "amount": payment.amount,
        "currency": payment.currency,
        "amount_label": amount_label,
        "tariff_name": tariff_name,
        "channel_title": channel_title,
        "paid_at": _isoformat(payment.paid_at),
        "paid_at_label": _format_optional_datetime(
            payment.paid_at,
            settings.timezone,
        ),
    }


def _serialize_promo_value(promo_code: PromoCode) -> str:
    if promo_code.promo_type == PROMO_TYPE_DISCOUNT_PERCENT:
        return f"-{promo_code.value}%"
    if promo_code.promo_type == PROMO_TYPE_DISCOUNT_STARS:
        return f"-{promo_code.value} Stars"
    if promo_code.promo_type == PROMO_TYPE_FIXED_PRICE:
        return f"{promo_code.value} Stars"
    if promo_code.promo_type == PROMO_TYPE_FREE_DAYS:
        return f"+{promo_code.value} дн."
    return promo_code.promo_type


def _display_name(user: User) -> str:
    parts = [
        part
        for part in [user.first_name, user.last_name]
        if isinstance(part, str) and part.strip()
    ]
    if parts:
        return " ".join(parts)
    if user.username:
        return f"@{user.username}"
    return f"User {user.telegram_id}"


def _format_optional_datetime(value: datetime | None, timezone: str) -> str | None:
    if value is None:
        return None
    return format_datetime(ensure_aware_utc(value), timezone)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return ensure_aware_utc(value).isoformat()


def _serialize_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")