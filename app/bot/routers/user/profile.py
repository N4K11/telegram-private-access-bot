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
            has_active_subscription=bool(snapshot and snapshot.has_active_subscription)
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


async def _load_profile_snapshot(
    callback: CallbackQuery,
    *,
    session: AsyncSession | None,
):
    if session is None or callback.from_user is None:
        return None
    return await build_user_profile_snapshot(
        session,
        telegram_user_id=callback.from_user.id,
        history_limit=PROFILE_HISTORY_LIMIT,
    )


def _render_profile_fallback(callback: CallbackQuery) -> str:
    username = _format_username(getattr(callback.from_user, "username", None))
    telegram_id = getattr(callback.from_user, "id", "\u2014")
    return "\n".join(
        [
            "\U0001f464 \u041c\u043e\u0439 \u043f\u0440\u043e\u0444\u0438\u043b\u044c",
            "",
            f"Telegram ID: <code>{telegram_id}</code>",
            f"Username: {username}",
            "\u0421\u0442\u0430\u0442\u0443\u0441: \u26aa \u041d\u0435\u0442 \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0439 \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0438",
            "\u0414\u0430\u043d\u043d\u044b\u0435 \u043f\u0440\u043e\u0444\u0438\u043b\u044f \u0435\u0449\u0451 \u043d\u0435 \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043d\u044b. \u041e\u0442\u043a\u0440\u043e\u0439 /start \u0438\u043b\u0438 \u043f\u043e\u0432\u0442\u043e\u0440\u0438 \u043f\u043e\u0437\u0436\u0435.",
        ]
    )


def _render_history_fallback() -> str:
    return "\n".join(
        [
            "\U0001f4dc \u0418\u0441\u0442\u043e\u0440\u0438\u044f \u043f\u043b\u0430\u0442\u0435\u0436\u0435\u0439",
            "",
            "\u041f\u043e\u043a\u0430 \u043d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445 \u043e \u043f\u043b\u0430\u0442\u0435\u0436\u0430\u0445.",
        ]
    )


def _format_username(username: str | None) -> str:
    if not username:
        return "\u2014"
    return f"@{username}"

