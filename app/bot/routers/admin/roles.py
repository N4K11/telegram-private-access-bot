from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin_roles import (
    admin_role_detail_keyboard,
    admin_role_prompt_keyboard,
    admin_roles_home_keyboard,
)
from app.bot.routers.common import edit_or_answer
from app.bot.states.admin import AdminRoleForm
from app.config import Settings
from app.db.models import User
from app.db.repositories.users import UserRepository
from app.services.admin_roles import (
    ADMIN_ROLES,
    PERMISSION_SETTINGS,
    is_owner_fallback,
    permission_labels_for_role,
    resolve_role_from_user,
    role_label,
)
from app.services.audit import write_audit_log

router = Router(name="admin_roles")
router.message.filter(AdminFilter(PERMISSION_SETTINGS))
router.callback_query.filter(AdminFilter(PERMISSION_SETTINGS))


def _display_name(user: User) -> str:
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}".strip()
    if user.first_name:
        return user.first_name
    if user.username:
        return f"@{user.username}"
    return f"User #{user.id}"


async def _list_role_users(session: AsyncSession) -> list[User]:
    users = await UserRepository(session).list_all()
    filtered = [user for user in users if user.is_admin or user.role in ADMIN_ROLES]
    return sorted(filtered, key=lambda item: (item.role != "owner", item.role, item.id))


async def _find_role_target(session: AsyncSession, raw_reference: str) -> User | None:
    repository = UserRepository(session)
    normalized = raw_reference.strip()
    if not normalized:
        return None
    if normalized.startswith("id:"):
        suffix = normalized.removeprefix("id:").strip()
        return await repository.get_by_id(int(suffix)) if suffix.isdigit() else None
    if normalized.startswith("tg:"):
        suffix = normalized.removeprefix("tg:").strip()
        return await repository.get_by_telegram_id(int(suffix)) if suffix.isdigit() else None
    if normalized.startswith("@"):
        return await repository.get_by_username(normalized)
    if normalized.isdigit():
        as_id = await repository.get_by_id(int(normalized))
        if as_id is not None:
            return as_id
        return await repository.get_by_telegram_id(int(normalized))
    return await repository.get_by_username(normalized)


async def _actor_user_id(session: AsyncSession, telegram_user_id: int | None) -> int | None:
    if telegram_user_id is None:
        return None
    actor = await UserRepository(session).get_by_telegram_id(telegram_user_id)
    return actor.id if actor is not None else None


def _can_edit_target(user: User, settings: Settings) -> bool:
    return not is_owner_fallback(telegram_user_id=user.telegram_id, settings=settings)


def _render_roles_home(users: list[User], settings: Settings) -> str:
    lines = [
        "⚙️ Настройки и роли",
        "",
        "Owner fallback из ADMIN_IDS всегда имеет полный доступ.",
        f"Fallback owner IDs: {len(settings.admin_ids_set)}",
        "",
    ]
    if not users:
        lines.append("Пока нет ни одного пользователя с админ-ролью в базе.")
        lines.append("Нажмите «Назначить или изменить роль», чтобы выбрать пользователя.")
        return "\n".join(lines)

    lines.append("Текущие роли:")
    for user in users:
        effective_role = resolve_role_from_user(
            user,
            telegram_user_id=user.telegram_id,
            settings=settings,
        )
        suffix = " • ADMIN_IDS" if _can_edit_target(user, settings) is False else ""
        lines.append(
            f"• {escape(_display_name(user))} — {role_label(effective_role)}{suffix}"
        )
    lines.extend(
        [
            "",
            (
                "Чтобы назначить роль новому пользователю, отправьте его "
                "internal ID, Telegram ID или @username."
            ),
        ]
    )
    return "\n".join(lines)


def _render_role_detail(user: User, settings: Settings, *, notice: str | None = None) -> str:
    stored_role = role_label(user.role)
    effective_role = resolve_role_from_user(
        user,
        telegram_user_id=user.telegram_id,
        settings=settings,
    )
    permission_lines = permission_labels_for_role(effective_role)
    lines = []
    if notice:
        lines.extend([notice, ""])
    lines.extend(
        [
            "👤 Роль пользователя",
            "",
            f"Имя: {escape(_display_name(user))}",
            f"User ID: <code>{user.id}</code>",
            f"Telegram ID: <code>{user.telegram_id}</code>",
            f"Username: {escape('@' + user.username) if user.username else '—'}",
            f"Роль в БД: {stored_role}",
            f"Эффективная роль: {role_label(effective_role)}",
            f"Админ-доступ: {'да' if user.is_admin else 'нет'}",
        ]
    )
    if is_owner_fallback(telegram_user_id=user.telegram_id, settings=settings):
        lines.extend(
            [
                "",
                "Этот пользователь входит в ADMIN_IDS, поэтому его роль нельзя понизить из UI.",
            ]
        )
    if permission_lines:
        lines.extend(["", "Доступы:"])
        for item in permission_lines:
            lines.append(f"• {item}")
    return "\n".join(lines)


async def _show_roles_home(
    target: Message | CallbackQuery,
    *,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext | None = None,
) -> None:
    if state is not None:
        await state.clear()
    users = await _list_role_users(session)
    await edit_or_answer(
        target,
        text=_render_roles_home(users, settings),
        reply_markup=admin_roles_home_keyboard(users),
    )


async def _show_role_detail(
    target: Message | CallbackQuery,
    *,
    session: AsyncSession,
    settings: Settings,
    user: User,
    notice: str | None = None,
) -> None:
    effective_role = resolve_role_from_user(
        user,
        telegram_user_id=user.telegram_id,
        settings=settings,
    )
    await edit_or_answer(
        target,
        text=_render_role_detail(user, settings, notice=notice),
        reply_markup=admin_role_detail_keyboard(
            user.id,
            current_role=effective_role,
            can_edit=_can_edit_target(user, settings),
        ),
    )


@router.message(Command("admin_roles"))
async def admin_roles(message: Message, session: AsyncSession, settings: Settings) -> None:
    await _show_roles_home(message, session=session, settings=settings)


@router.callback_query(F.data == "menu:admin:settings")
async def admin_settings_home(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext | None = None,
) -> None:
    await _show_roles_home(callback, session=session, settings=settings, state=state)


@router.callback_query(F.data == "menu:admin:roles:prompt")
async def admin_roles_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AdminRoleForm.waiting_for_user_reference)
    await edit_or_answer(
        callback,
        text=(
            "Отправьте internal user ID, Telegram ID, @username или username одним сообщением."
        ),
        reply_markup=admin_role_prompt_keyboard(),
    )


@router.message(AdminRoleForm.waiting_for_user_reference)
async def admin_roles_receive_reference(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    candidate = (message.text or "").strip()
    if not candidate:
        await message.answer("Нужен user ID, Telegram ID или @username.")
        return

    user = await _find_role_target(session, candidate)
    if user is None:
        await message.answer(
            "Пользователь не найден в базе. Сначала он должен хотя бы один раз написать боту.",
            reply_markup=admin_role_prompt_keyboard(),
        )
        return

    await state.clear()
    await _show_role_detail(message, session=session, settings=settings, user=user)


@router.callback_query(F.data.startswith("menu:admin:roles:view:"))
async def admin_role_view(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext | None = None,
) -> None:
    if state is not None:
        await state.clear()
    suffix = callback.data.rsplit(":", 1)[-1] if callback.data else ""
    if not suffix.isdigit():
        await callback.answer()
        return
    user = await UserRepository(session).get_by_id(int(suffix))
    if user is None:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return
    await _show_role_detail(callback, session=session, settings=settings, user=user)


@router.callback_query(F.data.startswith("menu:admin:roles:set:"))
async def admin_role_set(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if callback.data is None:
        await callback.answer()
        return

    parts = callback.data.split(":")
    if len(parts) != 6 or parts[:4] != ["menu", "admin", "roles", "set"]:
        await callback.answer()
        return
    user_id_raw, new_role = parts[4], parts[5]
    if not user_id_raw.isdigit():
        await callback.answer()
        return

    repository = UserRepository(session)
    user = await repository.get_by_id(int(user_id_raw))
    if user is None:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return

    if not _can_edit_target(user, settings):
        await callback.answer(
            "Этого owner из ADMIN_IDS нельзя изменить через UI.",
            show_alert=True,
        )
        return

    if new_role not in {"owner", "admin", "support", "analyst", "user"}:
        await callback.answer("Неизвестная роль.", show_alert=True)
        return

    old_role = user.role
    if old_role == new_role:
        await _show_role_detail(
            callback,
            session=session,
            settings=settings,
            user=user,
            notice="Роль уже установлена.",
        )
        return

    actor_user_id = await _actor_user_id(
        session,
        callback.from_user.id if callback.from_user else None,
    )
    await repository.set_role(user, role=new_role)
    await write_audit_log(
        session,
        action="admin_role_changed",
        actor_user_id=actor_user_id,
        target_user_id=user.id,
        payload={
            "old_role": old_role,
            "new_role": new_role,
            "telegram_id": user.telegram_id,
        },
    )
    await session.commit()
    await _show_role_detail(
        callback,
        session=session,
        settings=settings,
        user=user,
        notice="Роль обновлена.",
    )
