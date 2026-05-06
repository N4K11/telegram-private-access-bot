# ruff: noqa: E501
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.assets import get_banner_path
from app.bot.keyboards.user import user_payment_history_keyboard, user_profile_keyboard
from app.bot.rendering import render_section
from app.config import Settings
from app.db.repositories.tariffs import TariffRepository
from app.services.audit import write_audit_log
from app.services.multi_channel_access_service import load_active_product_access
from app.services.offer_engine import OfferEngineSnapshot, build_offer_engine_snapshot
from app.services.product_service import RecommendedTariffOffer, build_product_catalog
from app.services.profile import (
    UserProfileSnapshot,
    build_user_profile_snapshot,
    render_user_payment_history,
    render_user_profile,
)
from app.utils.datetime import ensure_aware_utc, format_datetime

router = Router(name="user_profile")
PROFILE_HISTORY_LIMIT = 10


@router.callback_query(F.data == "menu:user:profile")
@router.callback_query(F.data == "menu:user:subscription")
async def profile_section(
    callback: CallbackQuery,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    timezone = settings.timezone if settings is not None else "UTC"
    snapshot = await _load_profile_snapshot(callback, session=session)
    offer_engine = await _load_profile_offer_engine(session=session, snapshot=snapshot)
    if session is not None and snapshot is not None:
        await write_audit_log(
            session,
            action="profile_opened",
            target_user_id=snapshot.user.id,
            payload={
                "channel_id": snapshot.primary_channel_id,
                "has_active_subscription": snapshot.has_active_subscription,
            },
        )
        await session.commit()
    text = (
        _render_profile_text(snapshot, timezone=timezone, offer_engine=offer_engine)
        if snapshot is not None
        else _render_profile_fallback(callback)
    )
    await render_section(
        callback,
        text=text,
        reply_markup=user_profile_keyboard(
            has_active_subscription=bool(snapshot and snapshot.has_active_subscription),
            buy_callback=_resolve_profile_buy_callback(snapshot),
        ),
        banner_path=get_banner_path("profile"),
    )


@router.callback_query(F.data == "menu:user:payment-history")
async def payment_history_section(
    callback: CallbackQuery,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    timezone = settings.timezone if settings is not None else "UTC"
    snapshot = await _load_profile_snapshot(callback, session=session)
    text = (
        render_user_payment_history(snapshot, timezone=timezone)
        if snapshot is not None
        else _render_history_fallback()
    )
    await render_section(
        callback,
        text=text,
        reply_markup=user_payment_history_keyboard(),
        banner_path=get_banner_path("profile"),
    )


def _resolve_profile_buy_callback(snapshot: UserProfileSnapshot | None) -> str:
    if snapshot is None or snapshot.primary_channel_id is None:
        return "menu:user:buy"
    if snapshot.active_subscription_count == 1:
        return f"menu:user:buy:product:{snapshot.primary_channel_id}"
    if not snapshot.has_active_subscription:
        return f"menu:user:buy:product:{snapshot.primary_channel_id}"
    return "menu:user:buy"


async def _load_profile_snapshot(
    callback: CallbackQuery,
    *,
    session: AsyncSession | None,
) -> UserProfileSnapshot | None:
    if session is None or callback.from_user is None:
        return None
    return await build_user_profile_snapshot(
        session,
        telegram_user_id=callback.from_user.id,
        history_limit=PROFILE_HISTORY_LIMIT,
    )


async def _load_profile_offer_engine(
    *,
    session: AsyncSession | None,
    snapshot: UserProfileSnapshot | None,
) -> OfferEngineSnapshot | None:
    if session is None or snapshot is None:
        return None
    tariffs = await TariffRepository(session).list_active()
    product_catalog = build_product_catalog(tariffs)
    active_products = await load_active_product_access(session, user_id=snapshot.user.id)
    return build_offer_engine_snapshot(
        product_catalog,
        active_products=active_products,
        primary_channel_id=snapshot.primary_channel_id,
    )


def _render_profile_text(
    snapshot: UserProfileSnapshot,
    *,
    timezone: str,
    offer_engine: OfferEngineSnapshot | None,
) -> str:
    text = render_user_profile(snapshot, timezone=timezone)
    if offer_engine is None:
        return text

    blocks: list[str] = []
    if offer_engine.limited_offers:
        blocks.append("")
        blocks.append("⏰ Ограниченные предложения:")
        for offer in offer_engine.limited_offers[:2]:
            blocks.append(_recommendation_line(offer, compact=True, timezone=timezone))
    if offer_engine.hero_offer is not None:
        blocks.extend(["", "💡 Рекомендуем сейчас:", _recommendation_line(offer_engine.hero_offer, timezone=timezone)])
    if offer_engine.upgrade_offers:
        blocks.append("⬆️ Можно усилить тариф:")
        for offer in offer_engine.upgrade_offers[:2]:
            blocks.append(_recommendation_line(offer, compact=True, timezone=timezone))
    if offer_engine.cross_sell_offers:
        blocks.append("➕ Можно докупить:")
        for offer in offer_engine.cross_sell_offers[:2]:
            blocks.append(_recommendation_line(offer, compact=True, timezone=timezone))
    if offer_engine.bundle_offers and not offer_engine.cross_sell_offers:
        blocks.append("📦 Пакеты, которые стоит посмотреть:")
        for offer in offer_engine.bundle_offers[:2]:
            blocks.append(_recommendation_line(offer, compact=True, timezone=timezone))
    if not blocks:
        return text
    return text + "\n" + "\n".join(blocks)


def _recommendation_line(
    offer: RecommendedTariffOffer,
    *,
    compact: bool = False,
    timezone: str,
) -> str:
    parts = [
        f"• {offer.reason_label}: {offer.tariff_name} — {offer.price_stars} Stars",
        offer.price_per_day_label,
    ]
    if offer.savings_label:
        parts.append(offer.savings_label)
    if offer.is_limited_time and offer.offer_expires_at is not None:
        parts.append(f"до {format_datetime(ensure_aware_utc(offer.offer_expires_at), timezone)}")
    line = " • ".join(parts)
    if compact or not offer.offer_copy:
        return line
    return f"{line}\n  {offer.offer_copy}"


def _render_profile_fallback(callback: CallbackQuery) -> str:
    username = _format_username(getattr(callback.from_user, "username", None))
    telegram_id = getattr(callback.from_user, "id", "?")
    return "\n".join(
        [
            "👤 Мой профиль",
            "",
            f"Telegram ID: <code>{telegram_id}</code>",
            f"Username: {username}",
            "Статус: профиль ещё не сформирован",
            "Нажмите /start или оплатите тариф, чтобы появились данные.",
        ]
    )


def _render_history_fallback() -> str:
    return "\n".join(
        [
            "📜 История платежей",
            "",
            "Пока нет данных о платежах.",
        ]
    )


def _format_username(username: str | None) -> str:
    if not username:
        return "—"
    return f"@{username}"
