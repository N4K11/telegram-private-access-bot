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
    user_onboarding_keyboard,
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
from app.services.onboarding import (
    advance_onboarding,
    complete_onboarding,
    get_pending_onboarding_step,
    render_onboarding_text,
    skip_onboarding,
)
from app.services.referral_service import bind_referrer_for_user, render_referral_status_message
from app.services.texts import render_text
from app.utils.datetime import ensure_aware_utc, format_datetime
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


async def _load_or_ensure_user(
    session: AsyncSession | None,
    telegram_user: TelegramUser | None,
    settings: Settings | None,
) -> User | None:
    if telegram_user is None:
        return None
    user = await _load_db_user(session, telegram_user.id)
    if user is not None:
        return user
    return await _ensure_db_user(session, telegram_user, settings)


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
        status_block += (
            "\n"
            "\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0445 "
            "\u043a\u0430\u043d\u0430\u043b\u043e\u0432: "
            f"{len(active_subscriptions)}"
        )
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
        "\u0434\u0440\u0443\u0433",
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
            (
                f"\u041a\u0430\u043d\u0430\u043b #{subscription.channel_id}"
            ),
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
        return (
            "\u26a0\ufe0f \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c "
            "\u043e\u0431\u0440\u0430\u0431\u043e\u0442\u0430\u0442\u044c "
            "\u0440\u0435\u0444\u0435\u0440\u0430\u043b\u044c\u043d\u044b\u0439 "
            "\u043a\u043e\u0434. "
            "\u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439 \u043f\u043e\u0437\u0436\u0435."
        )


async def _render_home_section(
    event: Message | CallbackQuery,
    *,
    session: AsyncSession | None,
    settings: Settings | None,
    telegram_user: TelegramUser | None,
    user: User | None,
    referral_message: str | None = None,
) -> None:
    await render_section(
        event,
        text=await _render_start_text(
            session,
            telegram_user=telegram_user,
            user=user,
            timezone=settings.timezone if settings is not None else "UTC",
            referral_message=referral_message,
        ),
        reply_markup=user_main_menu_keyboard(
            is_admin=_is_admin(
                telegram_user.id if telegram_user is not None else None,
                settings=settings,
                user=user,
            )
        ),
        banner_path=get_banner_path("main"),
    )


def _resolve_event_time(event: Message | CallbackQuery | object) -> datetime:
    direct_time = getattr(event, "date", None)
    if direct_time is not None:
        return ensure_aware_utc(direct_time)
    callback_message = getattr(event, "message", None)
    if callback_message is not None and getattr(callback_message, "date", None) is not None:
        return ensure_aware_utc(callback_message.date)
    return datetime.now(UTC)


async def _maybe_render_onboarding(
    event: Message | CallbackQuery,
    *,
    session: AsyncSession | None,
    settings: Settings | None,
    user: User | None,
    referral_message: str | None = None,
) -> bool:
    if session is None or user is None:
        return False

    completed_before = user.onboarding_completed_at
    snapshot = await get_pending_onboarding_step(
        session,
        user=user,
        at_time=_resolve_event_time(event),
    )
    if completed_before != user.onboarding_completed_at:
        await session.commit()
    if snapshot is None:
        return False

    onboarding_text = render_onboarding_text(snapshot, first_name=user.first_name)
    if referral_message:
        onboarding_text += f"\n\n{referral_message}"

    await render_section(
        event,
        text=onboarding_text,
        reply_markup=user_onboarding_keyboard(is_last=snapshot.is_last),
        banner_path=get_banner_path("main"),
    )
    return True


@router.message(CommandStart())
async def start_handler(
    message: Message,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    user = await _ensure_db_user(session, message.from_user, settings)
    user = user or await _load_db_user(session, message.from_user.id if message.from_user else None)
    referral_message = await _maybe_process_start_referral(message, session=session, user=user)
    if await _maybe_render_onboarding(
        message,
        session=session,
        settings=settings,
        user=user,
        referral_message=referral_message,
    ):
        return
    await _render_home_section(
        message,
        session=session,
        settings=settings,
        telegram_user=message.from_user,
        user=user,
        referral_message=referral_message,
    )


@router.callback_query(F.data == "menu:user:home")
async def user_home(
    callback: CallbackQuery,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    user = await _load_or_ensure_user(session, callback.from_user, settings)
    if await _maybe_render_onboarding(callback, session=session, settings=settings, user=user):
        return
    await _render_home_section(
        callback,
        session=session,
        settings=settings,
        telegram_user=callback.from_user,
        user=user,
    )


@router.callback_query(F.data == "menu:user:onboarding:next")
async def onboarding_next(
    callback: CallbackQuery,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    user = await _load_or_ensure_user(session, callback.from_user, settings)
    if session is None or user is None:
        await callback.answer(
            "Onboarding "
            "\u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d.",
            show_alert=True,
        )
        return

    snapshot = await advance_onboarding(
        session,
        user=user,
        at_time=_resolve_event_time(callback),
    )
    await session.commit()
    if snapshot is not None:
        await render_section(
            callback,
            text=render_onboarding_text(snapshot, first_name=user.first_name),
            reply_markup=user_onboarding_keyboard(is_last=snapshot.is_last),
            banner_path=get_banner_path("main"),
        )
        return

    await _render_home_section(
        callback,
        session=session,
        settings=settings,
        telegram_user=callback.from_user,
        user=user,
    )


@router.callback_query(F.data == "menu:user:onboarding:skip")
async def onboarding_skip(
    callback: CallbackQuery,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    user = await _load_or_ensure_user(session, callback.from_user, settings)
    if session is None or user is None:
        await callback.answer(
            "Onboarding "
            "\u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d.",
            show_alert=True,
        )
        return

    await skip_onboarding(user=user, at_time=_resolve_event_time(callback))
    await session.commit()
    await _render_home_section(
        callback,
        session=session,
        settings=settings,
        telegram_user=callback.from_user,
        user=user,
    )


@router.callback_query(F.data == "menu:user:onboarding:finish")
async def onboarding_finish(
    callback: CallbackQuery,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
) -> None:
    user = await _load_or_ensure_user(session, callback.from_user, settings)
    if session is None or user is None:
        await callback.answer(
            "Onboarding "
            "\u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d.",
            show_alert=True,
        )
        return

    await complete_onboarding(user=user, at_time=_resolve_event_time(callback))
    await session.commit()
    await _render_home_section(
        callback,
        session=session,
        settings=settings,
        telegram_user=callback.from_user,
        user=user,
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
