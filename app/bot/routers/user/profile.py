# ruff: noqa: E501
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.assets import get_banner_path
from app.bot.keyboards.user import user_payment_history_keyboard, user_profile_keyboard
from app.bot.rendering import render_section
from app.config import Settings
from app.services.profile import (
    UserProfileSnapshot,
    build_user_profile_snapshot,
    render_user_payment_history,
    render_user_profile,
)

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
    text = (
        render_user_profile(snapshot, timezone=timezone)
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


def _render_profile_fallback(callback: CallbackQuery) -> str:
    username = _format_username(getattr(callback.from_user, "username", None))
    telegram_id = getattr(callback.from_user, "id", "—")
    return "\n".join(
        [
            "👤 Мой профиль",
            "",
            f"Telegram ID: <code>{telegram_id}</code>",
            f"Username: {username}",
            "Статус: ⚪ Нет активной подписки",
            "Данные профиля ещё не загружены. Открой /start или повтори позже.",
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