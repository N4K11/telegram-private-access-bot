# ruff: noqa: E501, I001
from __future__ import annotations

import json
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.services.admin_roles import (
    PERMISSION_USERS_MANAGE,
    PERMISSION_USERS_VIEW,
    has_permission,
    resolve_telegram_role,
)
from app.bot.keyboards.admin import admin_form_keyboard
from app.bot.keyboards.admin_users import (
    admin_confirm_keyboard,
    admin_user_filter_picker_keyboard,
    admin_user_grant_tariff_keyboard,
    admin_user_history_keyboard,
    admin_user_profile_keyboard,
    admin_users_directory_keyboard,
)
from app.bot.routers.common import edit_or_answer
from app.bot.states.admin import AdminUserForm
from app.config import Settings
from app.db.models import User
from app.db.repositories.tariffs import TariffRepository
from app.db.repositories.users import UserRepository
from app.services.audit import write_audit_log
from app.services.subscriptions import activate_or_extend_subscription
from app.services.users import (
    UserDirectoryPage,
    UserProfileSnapshot,
    build_user_directory,
    build_user_profile,
    filter_label,
    list_active_channels,
    list_active_tariffs,
)
from app.utils.datetime import format_datetime, utcnow

logger = logging.getLogger(__name__)


async def _require_users_manage_access(
    target: CallbackQuery | Message,
    *,
    session: AsyncSession,
    settings: Settings,
) -> bool:
    telegram_user_id = getattr(getattr(target, "from_user", None), "id", None)
    role = await resolve_telegram_role(
        session,
        telegram_user_id=telegram_user_id,
        settings=settings,
    )
    if has_permission(role, PERMISSION_USERS_MANAGE):
        return True

    text = "Недостаточно прав для управления пользователями."
    if isinstance(target, CallbackQuery):
        await target.answer(text, show_alert=True)
    else:
        await target.answer(text)
    return False


router = Router(name="admin_users")
router.message.filter(AdminFilter(PERMISSION_USERS_VIEW))
router.callback_query.filter(AdminFilter(PERMISSION_USERS_VIEW))



def _format_user_name(user: User) -> str:
    raw_parts = [user.first_name or "", user.last_name or ""]
    parts = [part.strip() for part in raw_parts if part and part.strip()]
    if parts:
        return " ".join(parts)
    if user.username:
        return f"@{user.username}"
    return f"Пользователь #{user.id}"



def _format_username(user: User) -> str:
    return f"@{user.username}" if user.username else "—"



def _format_optional_datetime(value, timezone: str) -> str:
    if value is None:
        return "—"
    return format_datetime(value, timezone)



def _parse_list_context(data: str | None) -> tuple[str, int] | None:
    if data is None:
        return None
    parts = data.split(":")
    if len(parts) != 6 or parts[:4] != ["menu", "admin", "users", "list"]:
        return None
    try:
        return parts[4], int(parts[5])
    except ValueError:
        return None



def _parse_user_context(data: str | None, action: str) -> tuple[int, str, int] | None:
    if data is None:
        return None
    parts = data.split(":")
    if len(parts) != 7 or parts[:4] != ["menu", "admin", "users", action]:
        return None
    try:
        return int(parts[4]), parts[5], int(parts[6])
    except ValueError:
        return None



def _parse_user_tariff_context(data: str | None, action: str) -> tuple[int, int, str, int] | None:
    if data is None:
        return None
    parts = data.split(":")
    if len(parts) != 8 or parts[:4] != ["menu", "admin", "users", action]:
        return None
    try:
        return int(parts[4]), int(parts[5]), parts[6], int(parts[7])
    except ValueError:
        return None

def _render_users_directory(page_data: UserDirectoryPage, *, timezone: str) -> str:
    lines = [
        "Пользователи",
        "",
        f"Фильтр: {filter_label(page_data.filter_key)}",
        f"Найдено: {page_data.total_items} • Страница {page_data.page}/{page_data.total_pages}",
        "",
    ]
    if not page_data.items:
        lines.append("По выбранному фильтру пользователей пока нет.")
        return "\n".join(lines)

    for entry in page_data.items:
        lines.append(escape(_format_user_name(entry.user)))
        lines.append(f"Telegram ID: <code>{entry.user.telegram_id}</code>")
        lines.append(f"Username: {escape(_format_username(entry.user))}")
        lines.append(f"Статус: {escape(entry.status)}")
        lines.append(
            f"Подписка до: {_format_optional_datetime(entry.latest_expires_at, timezone)}"
        )
        lines.append(f"Потрачено: {entry.total_paid}")
        lines.append("")

    return "\n".join(lines).rstrip()



def _render_profile(snapshot: UserProfileSnapshot, *, timezone: str) -> str:
    user = snapshot.user
    lines = [
        "Профиль пользователя",
        "",
        f"Имя: {escape(_format_user_name(user))}",
        f"Telegram ID: <code>{user.telegram_id}</code>",
        f"Username: {escape(_format_username(user))}",
        f"Статус: {escape(snapshot.status)}",
        f"Блокировка: {'да' if user.is_blocked else 'нет'}",
        f"Последняя активность: {_format_optional_datetime(user.last_seen_at, timezone)}",
        f"Всего оплачено: {snapshot.total_paid}",
        (
            "Последний срок доступа: "
            f"{_format_optional_datetime(snapshot.latest_expires_at, timezone)}"
        ),
        "",
        "Активные подписки:",
    ]
    if snapshot.active_subscriptions:
        for subscription in snapshot.active_subscriptions:
            lines.append(
                "• "
                f"{escape(subscription.tariff.name)} • "
                f"{escape(subscription.channel.title)} • "
                f"до {_format_optional_datetime(subscription.expires_at, timezone)}"
            )
    else:
        lines.append("• Активных подписок нет")

    lines.extend(
        [
            "",
            f"Последних платежей: {len(snapshot.recent_payments)}",
            f"Записей истории подписок: {len(snapshot.recent_subscriptions)}",
            f"Записей аудита: {len(snapshot.audit_entries)}",
        ]
    )
    return "\n".join(lines)



def _render_payments(snapshot: UserProfileSnapshot, *, timezone: str) -> str:
    lines = [f"Платежи: {escape(_format_user_name(snapshot.user))}", ""]
    if not snapshot.recent_payments:
        lines.append("Оплаченных платежей пока нет.")
        return "\n".join(lines)

    for payment in snapshot.recent_payments:
        if payment.tariff is not None:
            tariff_name = payment.tariff.name
        else:
            tariff_name = f"Тариф #{payment.tariff_id}"
        lines.append(
            "• "
            f"{_format_optional_datetime(payment.paid_at, timezone)} • "
            f"{escape(tariff_name)} • {payment.amount} • {escape(payment.provider)}"
        )
    return "\n".join(lines)



def _render_subscriptions(snapshot: UserProfileSnapshot, *, timezone: str) -> str:
    lines = [f"История подписок: {escape(_format_user_name(snapshot.user))}", ""]
    if not snapshot.recent_subscriptions:
        lines.append("Истории подписок пока нет.")
        return "\n".join(lines)

    for subscription in snapshot.recent_subscriptions:
        lines.append(
            "• "
            f"{escape(subscription.tariff.name)} • "
            f"{escape(subscription.channel.title)} • {escape(subscription.status)}"
        )
        lines.append(f"  Старт: {_format_optional_datetime(subscription.started_at, timezone)}")
        lines.append(f"  До: {_format_optional_datetime(subscription.expires_at, timezone)}")
        lines.append(f"  Источник: {escape(subscription.source)}")
    return "\n".join(lines)



def _format_audit_payload(payload: str | None) -> str:
    if not payload:
        return ""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return payload
    if isinstance(data, dict):
        chunks = [f"{key}={value}" for key, value in sorted(data.items())]
        return ", ".join(chunks)
    return str(data)



def _render_audit(snapshot: UserProfileSnapshot, *, timezone: str) -> str:
    lines = [f"Аудит: {escape(_format_user_name(snapshot.user))}", ""]
    if not snapshot.audit_entries:
        lines.append("Аудит-записей пока нет.")
        return "\n".join(lines)

    for entry in snapshot.audit_entries:
        lines.append(
            "• "
            f"{_format_optional_datetime(entry.created_at, timezone)} • "
            f"{escape(entry.action)}"
        )
        payload = _format_audit_payload(entry.payload)
        if payload:
            lines.append(f"  {escape(payload)}")
    return "\n".join(lines)

async def _show_directory(
    target: CallbackQuery | Message,
    session: AsyncSession,
    settings: Settings,
    *,
    filter_key: str,
    page: int,
) -> None:
    page_data = await build_user_directory(
        session,
        filter_key=filter_key,
        page=page,
    )
    await edit_or_answer(
        target,
        text=_render_users_directory(page_data, timezone=settings.timezone),
        reply_markup=admin_users_directory_keyboard(page_data),
    )


async def _load_profile(
    session: AsyncSession,
    *,
    user_id: int,
) -> UserProfileSnapshot | None:
    return await build_user_profile(session, user_id=user_id)


async def _show_profile(
    target: CallbackQuery | Message,
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: int,
    filter_key: str,
    page: int,
    notice: str | None = None,
) -> bool:
    snapshot = await _load_profile(session, user_id=user_id)
    if snapshot is None:
        if isinstance(target, CallbackQuery):
            await target.answer("Пользователь не найден.", show_alert=True)
        else:
            await target.answer("Пользователь не найден.")
        return False

    text = _render_profile(snapshot, timezone=settings.timezone)
    if notice:
        text = f"{notice}\n\n{text}"

    await edit_or_answer(
        target,
        text=text,
        reply_markup=admin_user_profile_keyboard(
            user_id=snapshot.user.id,
            filter_key=filter_key,
            page=page,
            is_blocked=snapshot.user.is_blocked,
        ),
    )
    return True


async def _show_history(
    target: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: int,
    filter_key: str,
    page: int,
    renderer,
) -> None:
    snapshot = await _load_profile(session, user_id=user_id)
    if snapshot is None:
        await target.answer("Пользователь не найден.", show_alert=True)
        return

    await edit_or_answer(
        target,
        text=renderer(snapshot, timezone=settings.timezone),
        reply_markup=admin_user_history_keyboard(
            user_id=user_id,
            filter_key=filter_key,
            page=page,
        ),
    )


@router.callback_query(F.data == "menu:admin:users")
async def users_index(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext | None = None,
) -> None:
    if state is not None:
        await state.clear()
    await _show_directory(callback, session, settings, filter_key="all", page=1)


@router.callback_query(F.data.startswith("menu:admin:users:list:"))
async def users_list(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext | None = None,
) -> None:
    context = _parse_list_context(callback.data)
    if context is None:
        await callback.answer()
        return
    if state is not None:
        await state.clear()

    filter_key, page = context
    await _show_directory(callback, session, settings, filter_key=filter_key, page=page)


@router.callback_query(F.data == "menu:admin:users:pick-filter:tariff")
async def pick_tariff_filter(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext | None = None,
) -> None:
    if state is not None:
        await state.clear()

    tariffs = await list_active_tariffs(session)
    await edit_or_answer(
        callback,
        text="Выберите тариф для фильтра списка пользователей.",
        reply_markup=admin_user_filter_picker_keyboard(
            tariffs,
            kind="tariff",
            back_filter="all",
            back_page=1,
        ),
    )


@router.callback_query(F.data == "menu:admin:users:pick-filter:channel")
async def pick_channel_filter(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext | None = None,
) -> None:
    if state is not None:
        await state.clear()

    channels = await list_active_channels(session)
    await edit_or_answer(
        callback,
        text="Выберите канал для фильтра списка пользователей.",
        reply_markup=admin_user_filter_picker_keyboard(
            channels,
            kind="channel",
            back_filter="all",
            back_page=1,
        ),
    )


@router.callback_query(F.data.startswith("menu:admin:users:view:"))
async def user_profile(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext | None = None,
) -> None:
    context = _parse_user_context(callback.data, "view")
    if context is None:
        await callback.answer()
        return
    if state is not None:
        await state.clear()

    user_id, filter_key, page = context
    await _show_profile(
        callback,
        session,
        settings,
        user_id=user_id,
        filter_key=filter_key,
        page=page,
    )


@router.callback_query(F.data.startswith("menu:admin:users:payments:"))
async def user_payments_view(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    context = _parse_user_context(callback.data, "payments")
    if context is None:
        await callback.answer()
        return
    user_id, filter_key, page = context
    await _show_history(
        callback,
        session,
        settings,
        user_id=user_id,
        filter_key=filter_key,
        page=page,
        renderer=_render_payments,
    )


@router.callback_query(F.data.startswith("menu:admin:users:subscriptions:"))
async def user_subscriptions_view(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    context = _parse_user_context(callback.data, "subscriptions")
    if context is None:
        await callback.answer()
        return
    user_id, filter_key, page = context
    await _show_history(
        callback,
        session,
        settings,
        user_id=user_id,
        filter_key=filter_key,
        page=page,
        renderer=_render_subscriptions,
    )


@router.callback_query(F.data.startswith("menu:admin:users:audit:"))
async def user_audit_view(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    context = _parse_user_context(callback.data, "audit")
    if context is None:
        await callback.answer()
        return
    user_id, filter_key, page = context
    await _show_history(
        callback,
        session,
        settings,
        user_id=user_id,
        filter_key=filter_key,
        page=page,
        renderer=_render_audit,
    )


@router.callback_query(F.data.startswith("menu:admin:users:message:"))
async def start_direct_message(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    if not await _require_users_manage_access(callback, session=session, settings=settings):
        return

    context = _parse_user_context(callback.data, "message")
    if context is None:
        await callback.answer()
        return

    user_id, filter_key, page = context
    profile = await _load_profile(session, user_id=user_id)
    if profile is None:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return

    await state.clear()
    await state.set_state(AdminUserForm.waiting_for_direct_message)
    await state.update_data(target_user_id=user_id, filter_key=filter_key, page=page)
    await edit_or_answer(
        callback,
        text=(
            f"Личное сообщение пользователю {escape(_format_user_name(profile.user))}\n\n"
            "Р С›РЎвЂљР С—РЎР‚Р В°Р Р†РЎРЉРЎвЂљР Вµ РЎРѓР В»Р ВµР Т‘РЎС“РЎР‹РЎвЂ°Р С‘Р в„– РЎвЂљР ВµР С”РЎРѓРЎвЂљ Р С•Р Т‘Р Р…Р С‘Р С РЎРѓР С•Р С•Р В±РЎвЂ°Р ВµР Р…Р С‘Р ВµР С."
        ),
        reply_markup=admin_form_keyboard(
            back_callback=f"menu:admin:users:view:{user_id}:{filter_key}:{page}"
        ),
    )


@router.message(AdminUserForm.waiting_for_direct_message)
async def receive_direct_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    bot: Bot,
) -> None:
    if not await _require_users_manage_access(message, session=session, settings=settings):
        await state.clear()
        return

    if message.text is None or not message.text.strip():
        await message.answer("Р СњРЎС“Р В¶Р Р…Р С• Р С•РЎвЂљР С—РЎР‚Р В°Р Р†Р С‘РЎвЂљРЎРЉ РЎвЂљР ВµР С”РЎРѓРЎвЂљР С•Р Р†Р С•Р Вµ РЎРѓР С•Р С•Р В±РЎвЂ°Р ВµР Р…Р С‘Р Вµ Р В±Р ВµР В· Р С—РЎС“РЎРѓРЎвЂљР С•Р С–Р С• РЎРѓР С•Р Т‘Р ВµРЎР‚Р В¶Р С‘Р СР С•Р С–Р С•.")
        return

    data = await state.get_data()
    user_id = data.get("target_user_id")
    filter_key = str(data.get("filter_key", "all"))
    page = int(data.get("page", 1))
    if not isinstance(user_id, int):
        await state.clear()
        await message.answer("Контекст отправки сообщения потерян. Откройте профиль заново.")
        return

    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        await state.clear()
        await message.answer("Пользователь не найден.")
        return

    try:
        await bot.send_message(user.telegram_id, message.text)
    except Exception:
        logger.exception("Failed to send admin direct message to user %s", user.telegram_id)
        await message.answer(
            "Р СњР Вµ РЎС“Р Т‘Р В°Р В»Р С•РЎРѓРЎРЉ Р С•РЎвЂљР С—РЎР‚Р В°Р Р†Р С‘РЎвЂљРЎРЉ РЎРѓР С•Р С•Р В±РЎвЂ°Р ВµР Р…Р С‘Р Вµ Р С—Р С•Р В»РЎРЉР В·Р С•Р Р†Р В°РЎвЂљР ВµР В»РЎР‹. Р СљР С•Р В¶Р Р…Р С• Р С—Р С•Р С—РЎР‚Р С•Р В±Р С•Р Р†Р В°РЎвЂљРЎРЉ Р ВµРЎвЂ°РЎвЂ РЎР‚Р В°Р В·."
        )
        return

    actor_user_id = None
    if message.from_user is not None:
        actor = await UserRepository(session).get_by_telegram_id(message.from_user.id)
        actor_user_id = actor.id if actor is not None else None

    await write_audit_log(
        session,
        action="admin_direct_message",
        actor_user_id=actor_user_id,
        target_user_id=user.id,
        payload={"text": message.text},
    )
    await session.commit()
    await state.clear()
    await _show_profile(
        message,
        session,
        settings,
        user_id=user.id,
        filter_key=filter_key,
        page=page,
        notice="Сообщение отправлено.",
    )


@router.callback_query(F.data.startswith("menu:admin:users:grant:"))
async def start_manual_grant(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext | None = None,
) -> None:
    if not await _require_users_manage_access(callback, session=session, settings=settings):
        return

    context = _parse_user_context(callback.data, "grant")
    if context is None:
        await callback.answer()
        return
    if state is not None:
        await state.clear()

    user_id, filter_key, page = context
    profile = await _load_profile(session, user_id=user_id)
    if profile is None:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return

    tariffs = await list_active_tariffs(session)
    if not tariffs:
        await callback.answer("Нет активных тарифов для ручной выдачи.", show_alert=True)
        return

    await edit_or_answer(
        callback,
        text=(
            f"Ручная выдача подписки: {escape(_format_user_name(profile.user))}\n\n"
            "Выберите активный тариф."
        ),
        reply_markup=admin_user_grant_tariff_keyboard(
            tariffs,
            user_id=user_id,
            filter_key=filter_key,
            page=page,
        ),
    )


@router.callback_query(F.data.startswith("menu:admin:users:grant-review:"))
async def review_manual_grant(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if not await _require_users_manage_access(callback, session=session, settings=settings):
        return

    context = _parse_user_tariff_context(callback.data, "grant-review")
    if context is None:
        await callback.answer()
        return

    user_id, tariff_id, filter_key, page = context
    profile = await _load_profile(session, user_id=user_id)
    tariff = await TariffRepository(session).get_by_id(tariff_id)
    if profile is None or tariff is None:
        await callback.answer("Пользователь или тариф не найден.", show_alert=True)
        return
    if not tariff.is_active or tariff.archived_at is not None:
        await callback.answer("Тариф недоступен для ручной выдачи.", show_alert=True)
        return

    await edit_or_answer(
        callback,
        text=(
            "Подтверждение ручной выдачи\n\n"
            f"Пользователь: {escape(_format_user_name(profile.user))}\n"
            f"Тариф: {escape(tariff.name)}\n"
            f"Срок: {tariff.duration_days} дн.\n"
            f"РљР°РЅР°Р»: {escape(tariff.channel.title)}"
        ),
        reply_markup=admin_confirm_keyboard(
            confirm_callback=(
                f"menu:admin:users:grant-confirm:{user_id}:{tariff_id}:{filter_key}:{page}"
            ),
            cancel_callback=f"menu:admin:users:view:{user_id}:{filter_key}:{page}",
        ),
    )


@router.callback_query(F.data.startswith("menu:admin:users:grant-confirm:"))
async def confirm_manual_grant(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if not await _require_users_manage_access(callback, session=session, settings=settings):
        return

    context = _parse_user_tariff_context(callback.data, "grant-confirm")
    if context is None:
        await callback.answer()
        return

    user_id, tariff_id, filter_key, page = context
    user = await UserRepository(session).get_by_id(user_id)
    tariff = await TariffRepository(session).get_by_id(tariff_id)
    actor = None
    if callback.from_user is not None:
        actor = await UserRepository(session).get_by_telegram_id(callback.from_user.id)

    if user is None or tariff is None:
        await callback.answer("Пользователь или тариф не найден.", show_alert=True)
        return
    if not tariff.is_active or tariff.archived_at is not None:
        await callback.answer("Тариф недоступен для ручной выдачи.", show_alert=True)
        return

    change = await activate_or_extend_subscription(
        session,
        user_id=user.id,
        tariff=tariff,
        paid_at=utcnow(),
        source="admin_manual",
    )
    await write_audit_log(
        session,
        action="admin_subscription_granted",
        actor_user_id=actor.id if actor is not None else None,
        target_user_id=user.id,
        payload={
            "tariff_id": tariff.id,
            "channel_id": tariff.channel_id,
            "duration_days": tariff.duration_days,
            "is_extension": change.is_extension,
            "expires_at": change.subscription.expires_at.isoformat(),
        },
    )
    await session.commit()
    await _show_profile(
        callback,
        session,
        settings,
        user_id=user.id,
        filter_key=filter_key,
        page=page,
        notice="Подписка выдана вручную.",
    )


@router.callback_query(F.data.startswith("menu:admin:users:block:"))
async def review_block_toggle(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if not await _require_users_manage_access(callback, session=session, settings=settings):
        return

    context = _parse_user_context(callback.data, "block")
    if context is None:
        await callback.answer()
        return

    user_id, filter_key, page = context
    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return

    action_label = "разблокировать" if user.is_blocked else "заблокировать"
    await edit_or_answer(
        callback,
        text=(
            "Подтверждение действия\n\n"
            f"Пользователь: {escape(_format_user_name(user))}\n"
            f"Действие: {action_label}"
        ),
        reply_markup=admin_confirm_keyboard(
            confirm_callback=f"menu:admin:users:block-confirm:{user_id}:{filter_key}:{page}",
            cancel_callback=f"menu:admin:users:view:{user_id}:{filter_key}:{page}",
        ),
    )


@router.callback_query(F.data.startswith("menu:admin:users:block-confirm:"))
async def confirm_block_toggle(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if not await _require_users_manage_access(callback, session=session, settings=settings):
        return

    context = _parse_user_context(callback.data, "block-confirm")
    if context is None:
        await callback.answer()
        return

    user_id, filter_key, page = context
    repository = UserRepository(session)
    user = await repository.get_by_id(user_id)
    actor = None
    if callback.from_user is not None:
        actor = await repository.get_by_telegram_id(callback.from_user.id)

    if user is None:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return

    new_block_state = not user.is_blocked
    await repository.set_blocked(user, is_blocked=new_block_state)
    await write_audit_log(
        session,
        action="admin_user_blocked" if new_block_state else "admin_user_unblocked",
        actor_user_id=actor.id if actor is not None else None,
        target_user_id=user.id,
        payload={"is_blocked": new_block_state},
    )
    await session.commit()
    await _show_profile(
        callback,
        session,
        settings,
        user_id=user.id,
        filter_key=filter_key,
        page=page,
        notice=(
            "Пользователь заблокирован."
            if new_block_state
            else "Пользователь разблокирован."
        ),
    )





