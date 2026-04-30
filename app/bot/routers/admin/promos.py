from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin import admin_section_keyboard
from app.config import Settings
from app.db.repositories.users import UserRepository
from app.services.audit import write_audit_log
from app.services.promo_service import (
    PromoCodeError,
    create_promo_code,
    disable_promo_code,
    get_promo_stats,
    parse_promo_draft,
)
from app.utils.datetime import format_datetime
from app.utils.encoding import safe_ui_text

router = Router(name="admin_promos")
router.message.filter(AdminFilter())


@router.message(Command("admin_promo_create"))
async def admin_promo_create(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    parts = _extract_args(message.text)
    if len(parts) < 4:
        await message.answer(
            "Использование: /admin_promo_create CODE TYPE VALUE LIMIT [TARIFF_ID|-] [VALID_DAYS|-]"
        )
        return

    try:
        draft = parse_promo_draft(
            code=parts[0],
            promo_type=parts[1],
            value=parts[2],
            max_uses=parts[3],
            tariff_id=parts[4] if len(parts) >= 5 else None,
            valid_days=parts[5] if len(parts) >= 6 else None,
        )
        actor = await _load_actor(message=message, session=session, settings=settings)
        promo_code = await create_promo_code(
            session,
            actor_user_id=actor.id if actor is not None else None,
            draft=draft,
            now=message.date,
        )
        await write_audit_log(
            session,
            action="promo_created",
            actor_user_id=actor.id if actor is not None else None,
            payload={
                "code": promo_code.code,
                "promo_type": promo_code.promo_type,
                "value": promo_code.value,
                "max_uses": promo_code.max_uses,
                "tariff_id": promo_code.tariff_id,
                "expires_at": promo_code.expires_at.isoformat() if promo_code.expires_at else None,
            },
        )
        await session.commit()
    except PromoCodeError as exc:
        await session.rollback()
        await message.answer(str(exc))
        return

    scope = "любой тариф"
    if promo_code.tariff is not None:
        scope = safe_ui_text(promo_code.tariff.name, f"Тариф #{promo_code.tariff.id}")
    expires = (
        format_datetime(promo_code.expires_at, settings.timezone)
        if promo_code.expires_at is not None
        else "без срока"
    )
    await message.answer(
        "🎟 Промокод создан.\n\n"
        f"Код: {promo_code.code}\n"
        f"Тип: {promo_code.promo_type}\n"
        f"Значение: {promo_code.value}\n"
        f"Лимит: {promo_code.max_uses}\n"
        f"Тариф: {scope}\n"
        f"Действует до: {expires}",
        reply_markup=admin_section_keyboard(),
    )


@router.message(Command("admin_promo_disable"))
async def admin_promo_disable(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    parts = _extract_args(message.text)
    if len(parts) != 1:
        await message.answer("Использование: /admin_promo_disable CODE")
        return

    try:
        actor = await _load_actor(message=message, session=session, settings=settings)
        promo_code = await disable_promo_code(session, code=parts[0])
        await write_audit_log(
            session,
            action="promo_disabled",
            actor_user_id=actor.id if actor is not None else None,
            payload={"code": promo_code.code},
        )
        await session.commit()
    except PromoCodeError as exc:
        await session.rollback()
        await message.answer(str(exc))
        return

    await message.answer(
        f"Промокод {promo_code.code} отключён.",
        reply_markup=admin_section_keyboard(),
    )


@router.message(Command("admin_promo_stats"))
async def admin_promo_stats(message: Message, session: AsyncSession, settings: Settings) -> None:
    parts = _extract_args(message.text)
    if len(parts) != 1:
        await message.answer("Использование: /admin_promo_stats CODE")
        return

    try:
        stats = await get_promo_stats(session, code=parts[0])
    except PromoCodeError as exc:
        await message.answer(str(exc))
        return

    promo_code = stats.promo_code
    scope = "любой тариф"
    if promo_code.tariff is not None:
        scope = safe_ui_text(promo_code.tariff.name, f"Тариф #{promo_code.tariff.id}")
    expires = (
        format_datetime(promo_code.expires_at, settings.timezone)
        if promo_code.expires_at is not None
        else "без срока"
    )
    status = "активен" if promo_code.is_active else "отключён"

    await message.answer(
        "🎟 Статистика промокода\n\n"
        f"Код: {promo_code.code}\n"
        f"Статус: {status}\n"
        f"Тип: {promo_code.promo_type}\n"
        f"Значение: {promo_code.value}\n"
        f"Лимит: {promo_code.max_uses}\n"
        f"Использований: {stats.total_uses}\n"
        f"В ожидании: {stats.pending_count}\n"
        f"Использовано: {stats.consumed_count}\n"
        f"Отменено: {stats.cancelled_count}\n"
        f"Тариф: {scope}\n"
        f"Действует до: {expires}",
        reply_markup=admin_section_keyboard(),
    )


async def _load_actor(
    *,
    message: Message,
    session: AsyncSession,
    settings: Settings,
):
    if message.from_user is None:
        return None
    repository = UserRepository(session)
    actor = await repository.get_by_telegram_id(message.from_user.id)
    if actor is None:
        actor = await repository.upsert_from_telegram_user(
            message.from_user,
            admin_ids=settings.admin_ids_set,
        )
    return actor



def _extract_args(text: str | None) -> list[str]:
    if not text:
        return []
    parts = text.split()
    return parts[1:]
