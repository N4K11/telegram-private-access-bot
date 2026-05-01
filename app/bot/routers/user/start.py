from __future__ import annotations

import inspect
import logging
from datetime import UTC, datetime
from html import escape

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.assets import get_banner_path
from app.bot.keyboards.user import (
    user_main_menu_keyboard,
    user_purchase_prompt_keyboard,
    user_subscription_keyboard,
)
from app.bot.rendering import render_section
from app.bot.routers.user.support import render_support_home
from app.config import Settings
from app.db.models import Subscription, User
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.users import UserRepository
from app.services.admin_roles import is_admin_role, resolve_role_from_user
from app.services.referral_service import (
    bind_referrer_for_user,
    render_referral_status_message,
)
from app.services.texts import render_text
from app.utils.datetime import format_datetime
from app.utils.encoding import safe_ui_text

router = Router(name="user")
logger = logging.getLogger(__name__)


async def _text(
    session: AsyncSession | None,
    key: str,
    **context: object,
) -> str:
    rendered = (
        render_text(session, key, **context) if session is not None else render_text(key, **context)
    )
    if inspect.isawaitable(rendered):
        return await rendered
    return rendered


def _extract_start_payload(message_text: str | None) -> str | None:
    if not message_text:
        return None
    parts = message_text.strip().split(maxsplit=1)
    if not parts:
        return None
    command = parts[0].split("@", maxsplit=1)[0]
    if command != "/start" or len(parts) < 2:
        return None
    payload = parts[1].strip()
    return payload or None


def _is_admin(
    telegram_user_id: int | None,
    *,
    settings: Settings | None,
    user: User | None,
) -> bool:
    role = resolve_role_from_user(
        user,
        telegram_user_id=telegram_user_id,
        settings=settings,
    )
    return is_admin_role(role)


async def _load_db_user(session: AsyncSession | None, telegram_user_id: int | None) -> User | None:
    if session is None or telegram_user_id is None:
        return None
    return await UserRepository(session).get_by_telegram_id(telegram_user_id)


async def _ensure_db_user(
    session: AsyncSession | None,
    telegram_user: TelegramUser | None,
    settings: Settings | None,
) -> User | None:
    if session is None or telegram_user is None:
        return None

    repository = UserRepository(session)
    user = await repository.get_by_telegram_id(telegram_user.id)
    if user is not None:
        return user

    user = await repository.upsert_from_telegram_user(
        telegram_user,
        admin_ids=settings.admin_ids_set if settings is not None else set(),
    )
    await session.commit()
    return user


async def _load_active_subscriptions(
    session: AsyncSession | None,
    user: User | None,
) -> list[Subscription]:
    if session is None or user is None:
        return []
    return await SubscriptionRepository(session).list_current_for_user(
        user.id,
        at_time=datetime.now(UTC),
    )


async def _render_subscription_status_block(
    session: AsyncSession | None,
    *,
    active_subscriptions: list[Subscription],
    timezone: str,
) -> str:
    if not active_subscriptions:
        return await _text(session, "user_subscription_inactive")

    latest_expires_at = max(subscription.expires_at for subscription in active_subscriptions)
    status_block = await _text(
        session,
        "user_subscription_active",
        expires_at=format_datetime(latest_expires_at, timezone),
    )
    if len(active_subscriptions) > 1:
        status_block += f"\nАктивных каналов: {len(active_subscriptions)}"
    return status_block


async def _render_start_text(
    session: AsyncSession | None,
    *,
    telegram_user: TelegramUser | None,
    user: User | None,
    timezone: str,
    referral_message: str | None = None,
) -> str:
    first_name = safe_ui_text(
        user.first_name if user is not None else getattr(telegram_user, "first_name", None),
        "друг",
    )
    active_subscriptions = await _load_active_subscriptions(session, user)
    subscription_status_block = await _render_subscription_status_block(
        session,
        active_subscriptions=active_subscriptions,
        timezone=timezone,
    )
    text = await _text(
        session,
        "start",
        first_name=first_name,
        subscription_status_block=subscription_status_block,
    )
    if referral_message:
        text += f"\n\n{referral_message}"
    return text


async def _render_invite_picker_text(
    session: AsyncSession | None,
    *,
    active_subscriptions: list[Subscription],
    timezone: str,
) -> str:
    subscription_lines: list[str] = []
    for subscription in active_subscriptions:
        channel_name = safe_ui_text(
            subscription.channel.title,
            f"Канал #{subscription.channel_id}",
        )
        expires_at = format_datetime(subscription.expires_at, timezone)
        subscription_lines.append(
            f"• {escape(channel_name)} — до {expires_at}"
        )
    subscriptions_block = "\n".join(subscription_lines)
    return await _text(
        session,
        "user_invite_picker",
        subscriptions_block=subscriptions_block,
    )


async def _maybe_process_start_referral(
    message: Message,
    *,
    session: AsyncSession | None,
    user: User | None,
) -> str | None:
    if session is None or user is None:
        return None

    payload = _extract_start_payload(getattr(message, "text", None))
    if payload is None or not payload.lower().startswith("ref_"):
        return None

    try:
        result = await bind_referrer_for_user(
            session,
            user=user,
            raw_code=payload,
            at_time=message.date,
        )
        if result.status == "bound":
            await session.commit()
        return render_referral_status_message(result)
    except Exception:
        await session.rollback()
        logger.exception("Failed to bind referral payload for user %s", user.id)
        return "⚠️ Не удалось обработать реферальный код. Попробуй позже."


@router.message(CommandStart())
async def start_handler(
    message: Message,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    user = await _ensure_db_user(session, message.from_user, settings)
    user = user or await _load_db_user(session, message.from_user.id if message.from_user else None)
    timezone = settings.timezone if settings is not None else "UTC"
    referral_message = await _maybe_process_start_referral(message, session=session, user=user)
    await render_section(
        message,
        text=await _render_start_text(
            session,
            telegram_user=message.from_user,
            user=user,
            timezone=timezone,
            referral_message=referral_message,
        ),
        reply_markup=user_main_menu_keyboard(
            is_admin=_is_admin(
                message.from_user.id if message.from_user else None,
                settings=settings,
                user=user,
            )
        ),
        banner_path=get_banner_path("main"),
    )


@router.callback_query(F.data == "menu:user:home")
async def user_home(
    callback: CallbackQuery,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    user = await _load_db_user(session, callback.from_user.id if callback.from_user else None)
    timezone = settings.timezone if settings is not None else "UTC"
    await render_section(
        callback,
        text=await _render_start_text(
            session,
            telegram_user=callback.from_user,
            user=user,
            timezone=timezone,
        ),
        reply_markup=user_main_menu_keyboard(
            is_admin=_is_admin(
                callback.from_user.id if callback.from_user else None,
                settings=settings,
                user=user,
            )
        ),
        banner_path=get_banner_path("main"),
    )


@router.callback_query(F.data == "menu:user:help")
@router.callback_query(F.data == "menu:user:support")
async def help_section(
    callback: CallbackQuery,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    await render_support_home(callback, session=session, settings=settings)


@router.callback_query(F.data == "menu:user:link")
async def invite_section(
    callback: CallbackQuery,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    user = await _load_db_user(session, callback.from_user.id if callback.from_user else None)
    active_subscriptions = await _load_active_subscriptions(session, user)
    if not active_subscriptions:
        await render_section(
            callback,
            text=await _text(session, "user_invite_missing"),
            reply_markup=user_purchase_prompt_keyboard(),
            banner_path=get_banner_path("join"),
        )
        return

    timezone = settings.timezone if settings is not None else "UTC"
    await render_section(
        callback,
        text=await _render_invite_picker_text(
            session,
            active_subscriptions=active_subscriptions,
            timezone=timezone,
        ),
        reply_markup=user_subscription_keyboard(active_subscriptions),
        banner_path=get_banner_path("join"),
    )





