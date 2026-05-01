from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin import admin_section_keyboard
from app.config import Settings
from app.db.repositories.users import UserRepository
from app.services.admin_roles import PERMISSION_PROMOS
from app.services.audit import write_audit_log
from app.services.promo_service import (
    PromoCodeError,
    create_promo_code,
    disable_promo_code,
    effective_promo_per_user_limit,
    effective_promo_valid_until,
    get_promo_code,
    get_promo_stats,
    list_promo_codes,
    parse_promo_draft,
)
from app.utils.datetime import format_datetime
from app.utils.encoding import safe_ui_text

router = Router(name="admin_promos")
router.message.filter(AdminFilter(PERMISSION_PROMOS))


@router.message(Command("admin_promo_create"))
async def admin_promo_create(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    parts = _extract_args(message.text)
    if len(parts) < 4:
        await message.answer(_create_usage_text())
        return

    extra_options = _extract_create_options(parts[6:])

    try:
        draft = parse_promo_draft(
            code=parts[0],
            promo_type=parts[1],
            value=parts[2],
            max_uses=parts[3],
            tariff_id=parts[4] if len(parts) >= 5 else None,
            valid_days=parts[5] if len(parts) >= 6 else None,
            valid_from=extra_options.get("valid_from"),
            valid_until=extra_options.get("valid_until"),
            first_purchase_only=extra_options.get("first_purchase_only"),
            per_user_limit=extra_options.get("per_user_limit"),
            campaign_name=extra_options.get("campaign_name"),
            notes=extra_options.get("notes"),
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
                "valid_from": promo_code.valid_from.isoformat() if promo_code.valid_from else None,
                "valid_until": (
                    effective_promo_valid_until(promo_code).isoformat()
                    if effective_promo_valid_until(promo_code)
                    else None
                ),
                "first_purchase_only": promo_code.first_purchase_only,
                "per_user_limit": promo_code.per_user_limit,
                "campaign_name": promo_code.campaign_name,
                "notes": promo_code.notes,
            },
        )
        await session.commit()
    except PromoCodeError as exc:
        await session.rollback()
        await message.answer(f"{exc}\n\n{_create_usage_text()}")
        return

    await message.answer(
        "🎟 Промокод создан.\n\n" + _render_promo_summary(promo_code, settings=settings),
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


@router.message(Command("admin_promo_view"))
async def admin_promo_view(message: Message, session: AsyncSession, settings: Settings) -> None:
    parts = _extract_args(message.text)
    if len(parts) != 1:
        await message.answer("Использование: /admin_promo_view CODE")
        return

    try:
        promo_code = await get_promo_code(session, code=parts[0])
    except PromoCodeError as exc:
        await message.answer(str(exc))
        return

    await message.answer(
        "🎟 Карточка промокода\n\n" + _render_promo_summary(promo_code, settings=settings),
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

    await message.answer(
        "🎟 Статистика промокода\n\n"
        + _render_promo_summary(stats.promo_code, settings=settings)
        + "\n\n"
        + "Использования:\n"
        + f"• Всего активных/использованных: {stats.total_uses}\n"
        + f"• В ожидании: {stats.pending_count}\n"
        + f"• Использовано: {stats.consumed_count}\n"
        + f"• Отменено: {stats.cancelled_count}",
        reply_markup=admin_section_keyboard(),
    )


@router.message(Command("admin_promo_list"))
async def admin_promo_list(message: Message, session: AsyncSession, settings: Settings) -> None:
    query = _extract_query(message.text)
    promos = await list_promo_codes(session, search=query, limit=15)
    if not promos:
        text = "Промокоды не найдены." if query else "Промокодов пока нет."
        await message.answer(text, reply_markup=admin_section_keyboard())
        return

    lines = ["🎟 Промокоды"]
    if query:
        lines.append(f"Поиск: {query}")
    lines.append("")
    for promo_code in promos:
        campaign = safe_ui_text(promo_code.campaign_name, "без кампании")
        status = "активен" if promo_code.is_active else "отключён"
        lines.append(
            f"• {promo_code.code} — {promo_code.promo_type} — {campaign} — {status}"
        )
    lines.append("")
    lines.append("Для деталей: /admin_promo_view CODE")
    await message.answer("\n".join(lines), reply_markup=admin_section_keyboard())


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


def _extract_query(text: str | None) -> str | None:
    if not text:
        return None
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    query = parts[1].strip()
    return query or None


def _extract_create_options(parts: list[str]) -> dict[str, str]:
    if not parts:
        return {}

    options: dict[str, str] = {}
    index = 0
    while index < len(parts):
        chunk = parts[index]
        if "=" not in chunk:
            raise PromoCodeError("Дополнительные параметры должны быть в формате key=value.")
        key, _, raw_value = chunk.partition("=")
        normalized_key = {
            "from": "valid_from",
            "until": "valid_until",
            "first": "first_purchase_only",
            "per_user": "per_user_limit",
            "campaign": "campaign_name",
            "notes": "notes",
        }.get(key.strip().lower(), key.strip().lower())
        if normalized_key == "notes":
            tail = [raw_value, *parts[index + 1 :]]
            options[normalized_key] = " ".join(item for item in tail if item)
            break
        options[normalized_key] = raw_value
        index += 1
    return options


def _create_usage_text() -> str:
    return (
        "Использование:\n"
        "/admin_promo_create CODE TYPE VALUE LIMIT [TARIFF_ID|-] [VALID_DAYS|-] "
        "[from=ISO] [until=ISO] [first=0|1] [per_user=N] [campaign=NAME] [notes=TEXT]"
    )


def _render_promo_summary(promo_code, *, settings: Settings) -> str:
    scope = "любой тариф"
    if promo_code.tariff is not None:
        scope = safe_ui_text(promo_code.tariff.name, f"Тариф #{promo_code.tariff.id}")
    valid_from = (
        format_datetime(promo_code.valid_from, settings.timezone)
        if promo_code.valid_from is not None
        else "сразу"
    )
    valid_until_dt = effective_promo_valid_until(promo_code)
    valid_until = (
        format_datetime(valid_until_dt, settings.timezone)
        if valid_until_dt is not None
        else "без срока"
    )
    campaign = safe_ui_text(promo_code.campaign_name, "—")
    notes = safe_ui_text(promo_code.notes, "—")
    status = "активен" if promo_code.is_active else "отключён"
    first_purchase_only = "да" if promo_code.first_purchase_only else "нет"
    return (
        f"Код: {promo_code.code}\n"
        f"Статус: {status}\n"
        f"Тип: {promo_code.promo_type}\n"
        f"Значение: {promo_code.value}\n"
        f"Глобальный лимит: {promo_code.max_uses}\n"
        f"Лимит на пользователя: {effective_promo_per_user_limit(promo_code)}\n"
        f"Только до первой оплаты: {first_purchase_only}\n"
        f"Тариф: {scope}\n"
        f"Кампания: {campaign}\n"
        f"Активен с: {valid_from}\n"
        f"Активен до: {valid_until}\n"
        f"Заметки: {notes}"
    )


