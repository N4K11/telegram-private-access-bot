from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Payment, Tariff, User
from app.db.repositories.payments import PaymentRepository
from app.db.repositories.tariffs import TariffRepository
from app.services.analytics import build_analytics_snapshot
from app.services.profile import UserProfileSnapshot, build_user_profile_snapshot
from app.services.referral_service import build_user_referral_dashboard
from app.utils.datetime import ensure_aware_utc, format_datetime
from app.utils.encoding import safe_ui_text


async def build_cabinet_bootstrap_payload(
    session: AsyncSession,
    *,
    user: User,
    settings: Settings,
) -> dict[str, object]:
    snapshot = await build_user_profile_snapshot(
        session,
        telegram_user_id=user.telegram_id,
        history_limit=10,
    )
    referral_dashboard = await build_user_referral_dashboard(
        session,
        user_id=user.id,
        bot_username=None,
    )
    tariffs = await TariffRepository(session).list_active()
    recent_payments = await PaymentRepository(session).list_recent_paid_for_user(
        user.id,
        limit=10,
    )
    return {
        "viewer": _serialize_user(user),
        "profile": _serialize_profile_snapshot(snapshot, settings=settings),
        "tariffs": [_serialize_tariff(tariff) for tariff in tariffs],
        "recent_payments": [
            _serialize_payment(payment, settings=settings)
            for payment in recent_payments
        ],
        "referrals": _serialize_referral_dashboard(referral_dashboard),
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
        history_limit=10,
    )
    if snapshot is None:
        return None
    recent_payments = await PaymentRepository(session).list_recent_paid_for_user(
        snapshot.user.id,
        limit=10,
    )
    referral_dashboard = await build_user_referral_dashboard(
        session,
        user_id=snapshot.user.id,
        bot_username=None,
    )
    return {
        "viewer": _serialize_user(snapshot.user),
        "profile": _serialize_profile_snapshot(snapshot, settings=settings),
        "recent_payments": [
            _serialize_payment(payment, settings=settings)
            for payment in recent_payments
        ],
        "referrals": _serialize_referral_dashboard(referral_dashboard),
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
        "conversion_invoice_created": snapshot.conversion_invoice_created,
        "conversion_paid": snapshot.conversion_paid,
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


def _serialize_tariff(tariff: Tariff) -> dict[str, object]:
    crypto_amount = getattr(tariff, "crypto_price_amount", None)
    if crypto_amount is None:
        crypto_amount = getattr(tariff, "price_crypto", None)
    channel_title = None
    if tariff.channel is not None:
        channel_title = safe_ui_text(
            tariff.channel.title,
            f"Channel #{tariff.channel_id}",
        )
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


def _format_optional_datetime(value, timezone: str) -> str | None:
    if value is None:
        return None
    return format_datetime(ensure_aware_utc(value), timezone)


def _isoformat(value) -> str | None:
    if value is None:
        return None
    return ensure_aware_utc(value).isoformat()


def _serialize_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")
