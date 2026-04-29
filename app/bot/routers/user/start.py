from __future__ import annotations

import inspect
from datetime import UTC, datetime
from html import escape

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.user import (
    user_main_menu_keyboard,
    user_profile_keyboard,
    user_purchase_prompt_keyboard,
    user_section_keyboard,
    user_subscription_keyboard,
)
from app.bot.routers.common import edit_or_answer
from app.config import Settings
from app.db.models import Subscription, User
from app.db.repositories.payments import PaymentRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.users import UserRepository
from app.services.texts import render_text
from app.utils.datetime import format_datetime
from app.utils.encoding import safe_ui_text

router = Router(name="user")


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


def _is_admin(
    telegram_user_id: int | None,
    *,
    settings: Settings | None,
    user: User | None,
) -> bool:
    if user is not None and user.is_admin:
        return True
    return (
        telegram_user_id is not None
        and settings is not None
        and telegram_user_id in settings.admin_ids_set
    )


async def _load_db_user(session: AsyncSession | None, telegram_user_id: int | None) -> User | None:
    if session is None or telegram_user_id is None:
        return None
    return await UserRepository(session).get_by_telegram_id(telegram_user_id)


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
    return await _text(
        session,
        "start",
        first_name=first_name,
        subscription_status_block=subscription_status_block,
    )


async def _render_profile_text(
    session: AsyncSession | None,
    *,
    telegram_user: TelegramUser | None,
    user: User | None,
    timezone: str,
) -> str:
    active_subscriptions = await _load_active_subscriptions(session, user)
    latest_expires_at = max(
        (subscription.expires_at for subscription in active_subscriptions), default=None
    )
    purchases_count = 0
    total_paid = 0
    if session is not None and user is not None:
        payment_repository = PaymentRepository(session)
        purchases_count = await payment_repository.count_paid_for_user(user.id)
        total_paid = await payment_repository.sum_paid_for_user(user.id)

    subscription_status = "активна" if active_subscriptions else "не активна"
    expires_at = (
        format_datetime(latest_expires_at, timezone) if latest_expires_at is not None else "—"
    )
    username_value = (
        getattr(user, "username", None)
        if user is not None
        else getattr(telegram_user, "username", None)
    )
    username = f"@{username_value}" if username_value else "—"
    telegram_id = (
        getattr(user, "telegram_id", None)
        if user is not None
        else getattr(telegram_user, "id", "—")
    )

    active_channels_lines = []
    for subscription in active_subscriptions:
        channel_name = safe_ui_text(subscription.channel.title, f"Канал #{subscription.channel_id}")
        active_channels_lines.append(
            f"• {escape(channel_name)} — до {format_datetime(subscription.expires_at, timezone)}"
        )
    active_channels_block = "\n".join(active_channels_lines) if active_channels_lines else "—"

    return await _text(
        session,
        "profile",
        telegram_id=telegram_id,
        username=username,
        subscription_status=subscription_status,
        expires_at=expires_at,
        purchase_count=purchases_count,
        total_paid=total_paid,
        active_channels_block=active_channels_block,
    )


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
            f"\u041a\u0430\u043d\u0430\u043b #{subscription.channel_id}",
        )
        expires_at = format_datetime(subscription.expires_at, timezone)
        subscription_lines.append(
            f"\u2022 {escape(channel_name)} \u2014 \u0434\u043e {expires_at}"
        )
    subscriptions_block = "\n".join(subscription_lines)
    return await _text(
        session,
        "user_invite_picker",
        subscriptions_block=subscriptions_block,
    )


@router.message(CommandStart())
async def start_handler(
    message: Message,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    user = await _load_db_user(session, message.from_user.id if message.from_user else None)
    timezone = settings.timezone if settings is not None else "UTC"
    await message.answer(
        await _render_start_text(
            session,
            telegram_user=message.from_user,
            user=user,
            timezone=timezone,
        ),
        reply_markup=user_main_menu_keyboard(
            is_admin=_is_admin(
                message.from_user.id if message.from_user else None,
                settings=settings,
                user=user,
            )
        ),
    )


@router.callback_query(F.data == "menu:user:home")
async def user_home(
    callback: CallbackQuery,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    user = await _load_db_user(session, callback.from_user.id if callback.from_user else None)
    timezone = settings.timezone if settings is not None else "UTC"
    await edit_or_answer(
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
    )


@router.callback_query(F.data == "menu:user:profile")
@router.callback_query(F.data == "menu:user:subscription")
async def profile_section(
    callback: CallbackQuery,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    user = await _load_db_user(session, callback.from_user.id if callback.from_user else None)
    timezone = settings.timezone if settings is not None else "UTC"
    active_subscriptions = await _load_active_subscriptions(session, user)
    await edit_or_answer(
        callback,
        text=await _render_profile_text(
            session,
            telegram_user=callback.from_user,
            user=user,
            timezone=timezone,
        ),
        reply_markup=user_profile_keyboard(has_active_subscription=bool(active_subscriptions)),
    )


@router.callback_query(F.data == "menu:user:help")
@router.callback_query(F.data == "menu:user:support")
async def help_section(callback: CallbackQuery, session: AsyncSession | None = None) -> None:
    await edit_or_answer(
        callback,
        text=await _text(session, "user_support"),
        reply_markup=user_section_keyboard(),
    )


@router.callback_query(F.data == "menu:user:link")
async def invite_section(
    callback: CallbackQuery,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    user = await _load_db_user(session, callback.from_user.id if callback.from_user else None)
    active_subscriptions = await _load_active_subscriptions(session, user)
    if not active_subscriptions:
        await edit_or_answer(
            callback,
            text=await _text(session, "user_invite_missing"),
            reply_markup=user_purchase_prompt_keyboard(),
        )
        return

    timezone = settings.timezone if settings is not None else "UTC"
    await edit_or_answer(
        callback,
        text=await _render_invite_picker_text(
            session,
            active_subscriptions=active_subscriptions,
            timezone=timezone,
        ),
        reply_markup=user_subscription_keyboard(active_subscriptions),
    )


@router.callback_query(F.data.startswith("menu:user:"))
async def unknown_user_section(callback: CallbackQuery) -> None:
    await callback.answer()
