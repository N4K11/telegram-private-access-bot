from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.repositories.users import UserRepository
from app.services.audit import write_audit_log
from app.services.invites import InviteLinkError, issue_subscription_invite_link
from app.services.promo_service import (
    PROMO_TYPE_DISCOUNT_PERCENT,
    PROMO_TYPE_DISCOUNT_STARS,
    PROMO_TYPE_FIXED_PRICE,
    PromoApplyResult,
    PromoCodeError,
    apply_promo_code,
    effective_promo_valid_until,
)
from app.utils.datetime import format_datetime
from app.utils.encoding import safe_ui_text

logger = logging.getLogger(__name__)

router = Router(name="user_promos")


@router.message(Command("promo"))
async def promo_command(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    bot: Bot,
) -> None:
    if message.from_user is None:
        return

    code = _extract_command_arg(message.text)
    if not code:
        await message.answer("Использование: /promo CODE")
        return

    user_repository = UserRepository(session)
    user = await user_repository.get_by_telegram_id(message.from_user.id)
    if user is None:
        user = await user_repository.upsert_from_telegram_user(
            message.from_user,
            admin_ids=settings.admin_ids_set,
        )

    if user.is_blocked:
        await message.answer("Промокоды недоступны: пользователь заблокирован.")
        return

    try:
        result = await apply_promo_code(
            session,
            user_id=user.id,
            code=code,
            now=message.date,
        )
        await write_audit_log(
            session,
            action=(
                "promo_applied_free_days"
                if result.action == "granted_free_days"
                else "promo_applied_pending"
            ),
            actor_user_id=user.id,
            target_user_id=user.id,
            payload={
                "promo_code": result.promo_code.code,
                "promo_type": result.promo_code.promo_type,
                "value": result.promo_code.value,
                "max_uses": result.promo_code.max_uses,
                "tariff_id": result.promo_code.tariff_id,
                "redemption_id": result.redemption.id,
                "campaign_name": result.promo_code.campaign_name,
            },
        )
        await session.commit()
    except PromoCodeError as exc:
        await session.rollback()
        await message.answer(str(exc))
        return
    except Exception:
        await session.rollback()
        logger.exception("Failed to apply promo for user %s", message.from_user.id)
        await message.answer("Не удалось применить промокод из-за внутренней ошибки.")
        return

    if result.action == "pending_discount":
        await message.answer(_render_pending_discount_text(result, timezone=settings.timezone))
        return

    invite_link: str | None = None
    invite_expires_at = None
    invite_error: str | None = None
    assert result.subscription_change is not None
    try:
        invite_result = await issue_subscription_invite_link(
            session,
            bot,
            user_id=user.id,
            subscription_id=result.subscription_change.subscription.id,
            ttl_hours=settings.default_invite_link_ttl_hours,
        )
        invite_link = invite_result.invite.invite_link
        invite_expires_at = invite_result.invite.expire_at
        await session.commit()
    except InviteLinkError as exc:
        await session.rollback()
        invite_error = str(exc)
    except Exception:
        await session.rollback()
        logger.exception(
            "Failed to issue invite after free-days promo for subscription %s",
            result.subscription_change.subscription.id,
        )
        invite_error = "Не удалось сформировать ссылку доступа автоматически."

    await message.answer(
        _render_free_days_success_text(
            result,
            timezone=settings.timezone,
            invite_link=invite_link,
            invite_expires_at=invite_expires_at,
            invite_error=invite_error,
        )
    )


def _extract_command_arg(text: str | None) -> str:
    if not text:
        return ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return ""
    return parts[1].strip()


def _render_pending_discount_text(result: PromoApplyResult, *, timezone: str) -> str:
    promo_code = result.promo_code
    if promo_code.promo_type == PROMO_TYPE_DISCOUNT_PERCENT:
        discount_text = f"-{promo_code.value}%"
    elif promo_code.promo_type == PROMO_TYPE_DISCOUNT_STARS:
        discount_text = f"-{promo_code.value} Stars"
    else:
        discount_text = f"фиксированная цена {promo_code.value} Stars"

    lines = [
        f"🎟 Промокод {promo_code.code} активирован.",
        "",
        f"Скидка: {discount_text}",
    ]

    if promo_code.campaign_name:
        campaign_label = safe_ui_text(
            promo_code.campaign_name,
            promo_code.campaign_name,
        )
        lines.append(f"Кампания: {campaign_label}")

    if promo_code.tariff is not None:
        tariff_label = safe_ui_text(
            promo_code.tariff.name,
            f"Тариф #{promo_code.tariff.id}",
        )
        lines.append(f"Тариф: {tariff_label}")
        preview_price = _preview_tariff_price(
            promo_code,
            original_amount=promo_code.tariff.price_stars,
        )
        lines.append(
            f"К оплате будет: {preview_price} Stars вместо {promo_code.tariff.price_stars} Stars"
        )
    else:
        lines.append("Скидка будет показана при выборе подходящего тарифа.")

    valid_until = effective_promo_valid_until(promo_code)
    if valid_until is not None:
        lines.append(f"Активен до: {format_datetime(valid_until, timezone)}")

    lines.extend(["", "Он будет применён к следующей оплате через Telegram Stars."])
    return "\n".join(lines)


def _preview_tariff_price(promo_code, *, original_amount: int) -> int:
    if promo_code.promo_type == PROMO_TYPE_DISCOUNT_PERCENT:
        return (original_amount * (100 - promo_code.value)) // 100
    if promo_code.promo_type == PROMO_TYPE_DISCOUNT_STARS:
        return original_amount - promo_code.value
    if promo_code.promo_type == PROMO_TYPE_FIXED_PRICE:
        return promo_code.value
    return original_amount


def _render_free_days_success_text(
    result: PromoApplyResult,
    *,
    timezone: str,
    invite_link: str | None,
    invite_expires_at: datetime | None,
    invite_error: str | None,
) -> str:
    assert result.subscription_change is not None
    tariff = result.promo_code.tariff
    assert tariff is not None and tariff.channel is not None

    action = (
        "Подписка продлена."
        if result.subscription_change.is_extension
        else "Подписка активирована."
    )
    lines = [
        f"🎟 Промокод {result.promo_code.code} активирован.",
        "",
        action,
        f"Канал: {safe_ui_text(tariff.channel.title, f'Канал #{tariff.channel_id}')}",
        f"Бонус: {result.promo_code.value} дн.",
        (
            "Доступ активен до: "
            f"{format_datetime(result.subscription_change.subscription.expires_at, timezone)}"
        ),
    ]
    if invite_link is not None:
        lines.extend(["", f"Ссылка доступа: {invite_link}"])
        if invite_expires_at is not None:
            lines.append(
                f"Ссылка активна до: {format_datetime(invite_expires_at, timezone)}"
            )
    elif invite_error is not None:
        lines.extend(["", invite_error])
    return "\n".join(lines)
