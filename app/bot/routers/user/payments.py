# ruff: noqa: E501
from __future__ import annotations

import inspect
import logging
from datetime import datetime
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.assets import get_banner_path
from app.bot.keyboards.user import (
    user_crypto_invoice_keyboard,
    user_tariff_detail_keyboard,
    user_tariffs_keyboard,
)
from app.bot.rendering import render_section
from app.config import Settings
from app.db.models import Tariff
from app.db.repositories.tariffs import TariffRepository
from app.db.repositories.users import UserRepository
from app.services.audit import write_audit_log
from app.services.invites import InviteLinkError, issue_subscription_invite_link
from app.services.payments.crypto_pay import (
    CryptoPayDisabledError,
    CryptoPayError,
    create_crypto_invoice,
)
from app.services.payments.stars import (
    STARS_CURRENCY,
    StarsInvoiceError,
    parse_stars_invoice_payload,
    process_successful_stars_payment,
    send_stars_invoice,
)
from app.services.tariffs import TariffValidationError, ensure_channel_can_host_tariff
from app.services.texts import render_text
from app.utils.datetime import format_datetime
from app.utils.encoding import safe_ui_text

logger = logging.getLogger(__name__)

router = Router(name="user_payments")


def _callback_entity_id(data: str | None) -> int | None:
    if data is None:
        return None
    try:
        return int(data.rsplit(":", 1)[-1])
    except ValueError:
        return None


async def _text(
    session: AsyncSession | None,
    key: str,
    **context: object,
) -> str:
    rendered = render_text(session, key, **context) if session is not None else render_text(key, **context)
    if inspect.isawaitable(rendered):
        return await rendered
    return rendered


def _safe_tariff_name(tariff: Tariff) -> str:
    return safe_ui_text(tariff.name, f"Тариф #{tariff.id}")


def _safe_channel_name(tariff: Tariff) -> str:
    return safe_ui_text(
        tariff.channel.title if tariff.channel is not None else None,
        f"Канал #{tariff.channel_id}",
    )


async def _render_tariffs_overview(
    session: AsyncSession | None,
    tariffs: list[Tariff],
    *,
    crypto_enabled: bool,
) -> str:
    if not tariffs:
        return await _text(session, "tariffs_empty")

    lines: list[str] = []
    for index, tariff in enumerate(tariffs, start=1):
        lines.append(f"{index}. 💎 {escape(_safe_tariff_name(tariff))}")
        lines.append(f"   ⏳ Срок: {tariff.duration_days} дней")
        lines.append(f"   ⭐ Цена: {tariff.price_stars} Stars")
        lines.append(f"   📣 Канал: {escape(_safe_channel_name(tariff))}")
        if crypto_enabled and tariff.price_crypto is not None:
            lines.append(f"   ₿ Crypto Pay: {tariff.price_crypto}")
        if index != len(tariffs):
            lines.append("")

    return await _text(session, "tariffs", tariffs_block="\n".join(lines))


async def _render_buy_section_text(
    session: AsyncSession | None,
    tariffs: list[Tariff],
) -> str:
    if not tariffs:
        return await _text(session, "tariffs_empty")
    return await _text(session, "user_tariffs")


async def _render_tariff_detail(
    session: AsyncSession | None,
    tariff: Tariff,
    *,
    crypto_enabled: bool,
) -> str:
    crypto_block = ""
    if crypto_enabled and tariff.price_crypto is not None:
        crypto_block = f"\n₿ Crypto Pay: {tariff.price_crypto}"

    return await _text(
        session,
        "tariff_detail",
        tariff_name=_safe_tariff_name(tariff),
        duration_days=tariff.duration_days,
        price_stars=tariff.price_stars,
        channel_name=_safe_channel_name(tariff),
        crypto_block=crypto_block,
    )


async def _render_payment_success_text(
    session: AsyncSession,
    tariff: Tariff,
    *,
    expires_at: datetime,
    timezone: str,
    is_extension: bool,
    invite_link: str | None = None,
    invite_expires_at: datetime | None = None,
    invite_error: str | None = None,
) -> str:
    action = "Подписка продлена." if is_extension else "Подписка активирована."
    invite_block = ""

    if invite_link is not None:
        invite_lines = ["", "", f"Ссылка доступа: {invite_link}"]
        if invite_expires_at is not None:
            invite_lines.append(
                f"Ссылка активна до: {format_datetime(invite_expires_at, timezone)}"
            )
        invite_block = "\n".join(invite_lines)
    elif invite_error is not None:
        invite_block = "\n\n" + invite_error

    return await _text(
        session,
        "payment_success",
        action=action,
        tariff_name=_safe_tariff_name(tariff),
        channel_name=_safe_channel_name(tariff),
        expires_at=format_datetime(expires_at, timezone),
        invite_block=invite_block,
    )


async def _load_active_tariff(session: AsyncSession, tariff_id: int) -> Tariff | None:
    tariff = await TariffRepository(session).get_by_id(tariff_id)
    if tariff is None or not tariff.is_active or tariff.archived_at is not None:
        return None
    try:
        ensure_channel_can_host_tariff(tariff.channel)
    except TariffValidationError:
        return None
    return tariff


def _render_crypto_invoice_text(
    *,
    tariff: Tariff,
    asset: str,
    amount: object,
    invoice_url: str | None,
    expires_at: datetime | None,
    timezone: str,
    is_reused: bool,
) -> str:
    tariff_name = safe_ui_text(tariff.name, f"Тариф #{tariff.id}")
    channel_name = safe_ui_text(
        tariff.channel.title if tariff.channel is not None else None,
        f"Канал #{tariff.channel_id}",
    )

    lines = []
    if is_reused:
        lines.append("♻️ Используем уже созданный счёт Crypto Pay.")
    else:
        lines.append("💸 Счёт Crypto Pay создан.")
    lines.extend(
        [
            "",
            f"Тариф: {escape(tariff_name)}",
            f"Актив: {asset}",
            f"Сумма: {amount}",
            f"Канал: {escape(channel_name)}",
        ]
    )
    if expires_at is not None:
        lines.append(f"Действителен до: {format_datetime(expires_at, timezone)}")
    if invoice_url:
        lines.extend(["", "Открой страницу оплаты и заверши платёж в Crypto Pay."])
    lines.extend(["", "После подтверждения оплаты подписка активируется автоматически."])
    return "\n".join(lines)


@router.message(Command("paysupport"))
async def paysupport_command(
    message: Message,
    session: AsyncSession | None = None,
) -> None:
    await message.answer(await _text(session, "paysupport"))


@router.callback_query(F.data == "menu:user:buy")
async def buy_section(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    tariffs = await TariffRepository(session).list_active()
    await render_section(
        callback,
        text=await _render_buy_section_text(session, tariffs),
        reply_markup=user_tariffs_keyboard(tariffs, mode="buy"),
        banner_path=get_banner_path("buy"),
    )


@router.callback_query(F.data == "menu:user:tariffs")
async def tariffs_section(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    tariffs = await TariffRepository(session).list_active()
    await render_section(
        callback,
        text=await _render_tariffs_overview(
            session,
            tariffs,
            crypto_enabled=settings.crypto_pay_enabled,
        ),
        reply_markup=user_tariffs_keyboard(tariffs, mode="browse"),
        banner_path=get_banner_path("tariffs"),
    )


@router.callback_query(F.data.startswith("menu:user:tariff:"))
async def tariff_detail(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    tariff_id = _callback_entity_id(callback.data)
    if tariff_id is None:
        await callback.answer()
        return

    tariff = await _load_active_tariff(session, tariff_id)
    if tariff is None:
        await callback.answer("Тариф недоступен.", show_alert=True)
        return

    await render_section(
        callback,
        text=await _render_tariff_detail(
            session,
            tariff,
            crypto_enabled=settings.crypto_pay_enabled,
        ),
        reply_markup=user_tariff_detail_keyboard(
            tariff.id,
            include_crypto=settings.crypto_pay_enabled and tariff.price_crypto is not None,
        ),
        banner_path=get_banner_path("buy"),
    )


@router.callback_query(F.data.startswith("menu:user:buy:crypto:"))
async def buy_crypto_tariff(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    tariff_id = _callback_entity_id(callback.data)
    if tariff_id is None or callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    user_repository = UserRepository(session)
    user = await user_repository.get_by_telegram_id(callback.from_user.id)
    if user is None:
        user = await user_repository.upsert_from_telegram_user(
            callback.from_user,
            admin_ids=settings.admin_ids_set,
        )
    if user.is_blocked:
        await callback.answer("Покупка недоступна: пользователь заблокирован.", show_alert=True)
        return

    tariff = await _load_active_tariff(session, tariff_id)
    if tariff is None:
        await callback.answer("Тариф недоступен.", show_alert=True)
        return

    try:
        result = await create_crypto_invoice(
            session,
            settings,
            user_id=user.id,
            tariff=tariff,
        )
        await write_audit_log(
            session,
            action="invoice_created_crypto",
            target_user_id=user.id,
            payload={
                "tariff_id": tariff.id,
                "asset": result.remote_invoice.asset,
                "amount": str(result.remote_invoice.amount),
                "external_id": result.invoice.external_id,
            },
        )
        await session.commit()
    except (CryptoPayDisabledError, CryptoPayError) as exc:
        await session.rollback()
        await callback.answer(str(exc), show_alert=True)
        return
    except Exception:
        await session.rollback()
        logger.exception("Failed to create Crypto Pay invoice for tariff %s", tariff_id)
        await callback.answer("Не удалось создать счёт Crypto Pay.", show_alert=True)
        return

    await callback.message.answer(
        _render_crypto_invoice_text(
            tariff=tariff,
            asset=result.remote_invoice.asset,
            amount=result.remote_invoice.amount,
            invoice_url=result.remote_invoice.invoice_url,
            expires_at=result.remote_invoice.expires_at,
            timezone=settings.timezone,
            is_reused=result.is_reused,
        ),
        reply_markup=user_crypto_invoice_keyboard(result.remote_invoice.invoice_url),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("menu:user:buy:stars:"))
@router.callback_query(F.data.startswith("menu:user:buy:"))
async def buy_tariff(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is not None and ":crypto:" in callback.data:
        await callback.answer()
        return

    tariff_id = _callback_entity_id(callback.data)
    if tariff_id is None or callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    user = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
    if user is not None and user.is_blocked:
        await callback.answer("Покупка недоступна: пользователь заблокирован.", show_alert=True)
        return

    tariff = await _load_active_tariff(session, tariff_id)
    if tariff is None:
        await callback.answer("Тариф недоступен.", show_alert=True)
        return

    try:
        await send_stars_invoice(callback.message, tariff)
    except Exception:
        logger.exception("Failed to send Stars invoice for tariff %s", tariff_id)
        await callback.answer("Не удалось отправить счёт на оплату.", show_alert=True)
        return

    if user is not None:
        try:
            await write_audit_log(
                session,
                action="invoice_created_stars",
                target_user_id=user.id,
                payload={"tariff_id": tariff.id, "amount": tariff.price_stars},
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception(
                "Failed to write invoice_created_stars audit log for user %s",
                user.id,
            )

    await callback.answer("Счёт отправлен.")


@router.pre_checkout_query()
async def pre_checkout_handler(query: PreCheckoutQuery, session: AsyncSession) -> None:
    user = await UserRepository(session).get_by_telegram_id(query.from_user.id)
    if user is not None and user.is_blocked:
        await query.answer(ok=False, error_message="Покупка недоступна: пользователь заблокирован.")
        return

    try:
        payload = parse_stars_invoice_payload(query.invoice_payload)
        tariff = await _load_active_tariff(session, payload.tariff_id)
        if tariff is None:
            raise StarsInvoiceError("Тариф недоступен.")
        if query.currency != STARS_CURRENCY:
            raise StarsInvoiceError("Поддерживаются только Telegram Stars.")
        if query.total_amount != tariff.price_stars:
            raise StarsInvoiceError("Цена изменилась. Открой тариф заново.")
    except StarsInvoiceError as exc:
        await query.answer(ok=False, error_message=str(exc))
        return

    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    bot: Bot,
) -> None:
    if message.from_user is None or message.successful_payment is None:
        return

    user_repository = UserRepository(session)
    user = await user_repository.get_by_telegram_id(message.from_user.id)
    if user is None:
        user = await user_repository.upsert_from_telegram_user(
            message.from_user,
            admin_ids=settings.admin_ids_set,
        )

    try:
        payload = parse_stars_invoice_payload(message.successful_payment.invoice_payload)
        tariff = await TariffRepository(session).get_by_id(payload.tariff_id)
        if tariff is None:
            raise StarsInvoiceError("Тариф не найден.")

        result = await process_successful_stars_payment(
            session,
            user_id=user.id,
            tariff=tariff,
            successful_payment=message.successful_payment,
            paid_at=message.date,
        )
        if not result.is_duplicate:
            await write_audit_log(
                session,
                action="payment_paid_stars",
                target_user_id=user.id,
                payload={
                    "tariff_id": tariff.id,
                    "amount": message.successful_payment.total_amount,
                    "telegram_payment_charge_id": (
                        message.successful_payment.telegram_payment_charge_id
                    ),
                },
            )
        await session.commit()
    except StarsInvoiceError as exc:
        await session.rollback()
        await message.answer(await _text(session, "payment_failed", reason=str(exc)))
        await message.answer(await _text(session, "paysupport"))
        return
    except Exception:
        await session.rollback()
        logger.exception(
            "Failed to process successful payment for user %s",
            message.from_user.id,
        )
        await message.answer(
            await _text(
                session,
                "payment_failed",
                reason="внутренняя ошибка обработки",
            )
        )
        await message.answer(await _text(session, "paysupport"))
        return

    if result.is_duplicate:
        await message.answer("Платёж уже обработан.")
        return

    if result.subscription is None:
        await message.answer(
            await _text(
                session,
                "payment_failed",
                reason="подписка не была обновлена автоматически",
            )
        )
        await message.answer(await _text(session, "paysupport"))
        return

    invite_link: str | None = None
    invite_expires_at: datetime | None = None
    invite_error: str | None = None
    try:
        grant = await issue_subscription_invite_link(
            session,
            bot,
            user_id=user.id,
            subscription_id=result.subscription.id,
            ttl_hours=settings.default_invite_link_ttl_hours,
        )
        invite_link = grant.invite.invite_link
        invite_expires_at = grant.invite.expire_at
        await session.commit()
    except InviteLinkError as exc:
        await session.rollback()
        invite_error = str(exc)
    except Exception:
        await session.rollback()
        logger.exception(
            "Unexpected invite issuance failure after payment for subscription %s",
            result.subscription.id,
        )
        invite_error = "Не удалось сформировать ссылку доступа."

    await message.answer(
        await _render_payment_success_text(
            session,
            tariff,
            expires_at=result.subscription.expires_at,
            timezone=settings.timezone,
            is_extension=result.is_extension,
            invite_link=invite_link,
            invite_expires_at=invite_expires_at,
            invite_error=invite_error,
        )
    )


