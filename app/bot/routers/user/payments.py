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
    user_product_picker_keyboard,
    user_tariff_detail_keyboard,
    user_tariffs_keyboard,
)
from app.bot.rendering import render_section
from app.config import Settings
from app.db.models import Tariff
from app.db.repositories.payments import PaymentRepository
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
    build_stars_invoice_payload,
    parse_stars_invoice_payload,
    process_successful_stars_payment,
    send_stars_invoice,
)
from app.services.product_service import (
    ProductCatalogEntry,
    build_offer_details,
    build_product_catalog,
    get_product_entry,
    is_multi_product_catalog,
    pick_default_tariff,
)
from app.services.promo_service import (
    PromoCodeError,
    consume_discount_redemption,
    get_discount_quote_for_redemption,
    get_pending_discount_quote_for_tariff,
)
from app.services.tariffs import (
    TariffValidationError,
    effective_crypto_asset,
    effective_crypto_price,
    ensure_channel_can_host_tariff,
    ensure_tariff_purchase_allowed,
    tariff_badge_label,
    tariff_duration_label,
)
from app.services.texts import render_text
from app.utils.datetime import format_datetime
from app.utils.encoding import safe_ui_text

logger = logging.getLogger(__name__)

router = Router(name="user_payments")

DIAMOND = "\U0001f48e"
CLOCK = "\u23f3"
STARS = "\u2b50"
MEGAPHONE = "\U0001f4e3"
MEMO = "\U0001f4dd"
BITCOIN = "\u20bf"
LABEL = "\U0001f3f7"
RECYCLE = "\u267b\ufe0f"
MONEY = "\U0001f4b8"
FOLDER = "\U0001f4c1"


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
    rendered = (
        render_text(session, key, **context)
        if session is not None
        else render_text(key, **context)
    )
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


def _tariff_title(tariff: Tariff) -> str:
    badge = tariff_badge_label(tariff)
    title = _safe_tariff_name(tariff)
    if badge:
        return f"[{badge}] {title}"
    return title


def _crypto_price_label(tariff: Tariff, accepted_assets: list[str]) -> str | None:
    price = effective_crypto_price(tariff)
    if price is None:
        return None
    asset = effective_crypto_asset(tariff, accepted_assets)
    if asset is None:
        return str(price)
    return f"{price} {asset}"


def _tariff_offer_markers(tariff: Tariff, *, baseline_tariff: Tariff) -> list[str]:
    details = build_offer_details(tariff, baseline_tariff=baseline_tariff)
    markers: list[str] = []
    if details.is_featured:
        markers.append("🔥 Хит")
    if details.is_default_offer:
        markers.append("🎯 Рекомендуем")
    if details.offer_group:
        markers.append(f"🏷 {details.offer_group}")
    return markers


async def _render_tariffs_overview(
    session: AsyncSession | None,
    tariffs: list[Tariff],
    *,
    crypto_enabled: bool,
    accepted_assets: list[str],
) -> str:
    if not tariffs:
        return await _text(session, "tariffs_empty")

    baseline_tariff = pick_default_tariff(tariffs) or tariffs[0]
    lines: list[str] = []
    for index, tariff in enumerate(tariffs, start=1):
        details = build_offer_details(tariff, baseline_tariff=baseline_tariff)
        marker_line = _tariff_offer_markers(tariff, baseline_tariff=baseline_tariff)
        lines.append(f"{index}. {DIAMOND} {escape(_tariff_title(tariff))}")
        lines.append(f"   {CLOCK} Срок: {tariff_duration_label(tariff)}")
        lines.append(
            f"   {STARS} Цена: {tariff.price_stars} Stars • {details.price_per_day_label}"
        )
        lines.append(f"   {MEGAPHONE} Канал: {escape(_safe_channel_name(tariff))}")
        if marker_line:
            lines.append(f"   {LABEL} {' • '.join(marker_line)}")
        if details.savings_label:
            lines.append(f"   💰 {details.savings_label}")
        if details.offer_copy:
            lines.append(f"   {MEMO} {escape(details.offer_copy)}")
        elif tariff.description:
            lines.append(f"   {MEMO} {escape(tariff.description)}")
        crypto_label = _crypto_price_label(tariff, accepted_assets)
        if crypto_enabled and crypto_label is not None:
            lines.append(f"   {BITCOIN} Crypto Pay: {crypto_label}")
        if index != len(tariffs):
            lines.append("")

    return await _text(session, "tariffs", tariffs_block="\n".join(lines))


async def _render_buy_section_text(
    session: AsyncSession | None,
    tariffs: list[Tariff],
) -> str:
    if not tariffs:
        return await _text(session, "tariffs_empty")
    baseline_tariff = pick_default_tariff(tariffs) or tariffs[0]
    featured_tariff = next(
        (tariff for tariff in tariffs if getattr(tariff, "is_featured", False)),
        baseline_tariff,
    )
    featured_details = build_offer_details(featured_tariff, baseline_tariff=baseline_tariff)
    lines = [await _text(session, "user_tariffs"), "", "Рекомендуемый оффер:"]
    lines.append(f"• {_compact_offer_line(featured_tariff, baseline_tariff=baseline_tariff)}")
    if featured_details.offer_copy:
        lines.append(f"• {escape(featured_details.offer_copy)}")

    alternatives = [tariff for tariff in tariffs if tariff.id != featured_tariff.id]
    if alternatives:
        lines.extend(["", "Ещё варианты:"])
        preview_limit = 3
        for tariff in alternatives[:preview_limit]:
            lines.append(f"• {_compact_offer_line(tariff, baseline_tariff=baseline_tariff)}")
        remaining = len(alternatives) - min(len(alternatives), preview_limit)
        if remaining > 0:
            lines.append(f"• и ещё {remaining} офферов в списке ниже")
        lines.extend(["", "Можно оплатить сразу быстрым оффером или выбрать любой другой тариф ниже."])
    return "\n".join(lines)


def _compact_offer_line(tariff: Tariff, *, baseline_tariff: Tariff) -> str:
    details = build_offer_details(tariff, baseline_tariff=baseline_tariff)
    parts = [
        f"{escape(_tariff_title(tariff))} — {tariff.price_stars} Stars",
        details.price_per_day_label,
    ]
    if details.savings_label:
        parts.append(details.savings_label)
    return " • ".join(parts)


async def _render_tariff_detail(
    session: AsyncSession | None,
    tariff: Tariff,
    *,
    crypto_enabled: bool,
    accepted_assets: list[str],
) -> str:
    product_tariffs = [tariff]
    if tariff.channel is not None and getattr(tariff.channel, "tariffs", None):
        product_tariffs = list(tariff.channel.tariffs)
    baseline_tariff = pick_default_tariff(product_tariffs) or tariff
    details = build_offer_details(tariff, baseline_tariff=baseline_tariff)

    extra_blocks: list[str] = []
    crypto_label = _crypto_price_label(tariff, accepted_assets)
    if crypto_enabled and crypto_label is not None:
        extra_blocks.append(f"{BITCOIN} Crypto Pay: {crypto_label}")
    markers = _tariff_offer_markers(tariff, baseline_tariff=baseline_tariff)
    if markers:
        extra_blocks.append(f"{LABEL} {' • '.join(markers)}")
    extra_blocks.append(f"💹 {details.price_per_day_label}")
    if details.savings_label:
        extra_blocks.append(f"💰 {details.savings_label}")
    if details.offer_copy:
        extra_blocks.append(f"{MEMO} {escape(details.offer_copy)}")
    elif tariff.description:
        extra_blocks.append(f"{MEMO} {escape(tariff.description)}")

    crypto_block = ""
    if extra_blocks:
        crypto_block = "\n" + "\n".join(extra_blocks)

    return await _text(
        session,
        "tariff_detail",
        tariff_name=_tariff_title(tariff),
        duration_days=tariff_duration_label(tariff),
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
    action = "Доступ продлён." if is_extension else "Доступ активирован."
    invite_block = ""

    if invite_link is not None:
        invite_lines = ["", "", f"Персональная ссылка: {invite_link}"]
        if invite_expires_at is not None:
            invite_lines.append(
                f"Ссылка активна до: {format_datetime(invite_expires_at, timezone)}"
            )
        invite_block = "\n".join(invite_lines)
    elif invite_error is not None:
        invite_block = "\n\n" + invite_error

    expires_label = "Навсегда" if tariff.is_lifetime else format_datetime(expires_at, timezone)
    return await _text(
        session,
        "payment_success",
        action=action,
        tariff_name=_tariff_title(tariff),
        channel_name=_safe_channel_name(tariff),
        expires_at=expires_label,
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


async def _load_active_product_catalog(session: AsyncSession) -> list[ProductCatalogEntry]:
    tariffs = await TariffRepository(session).list_active()
    return build_product_catalog(tariffs)


def _prepend_product_heading(text: str, product: ProductCatalogEntry) -> str:
    heading = f"{FOLDER} Продукт: {escape(product.channel_title)}"
    details: list[str] = []
    if product.price_range_label:
        details.append(f"от {product.price_range_label}")
    if product.bundle_names:
        details.append(f"пакеты: {', '.join(product.bundle_names)}")
    if details:
        heading = f"{heading}\n<i>{escape(' • '.join(details))}</i>"
    return f"{heading}\n\n{text}"


async def _track_funnel_event(
    session: AsyncSession,
    *,
    event_name: str,
    telegram_user_id: int | None,
    tariff: Tariff | None = None,
    channel_id: int | None = None,
    extra_payload: dict[str, object] | None = None,
) -> None:
    if telegram_user_id is None:
        return
    repository = UserRepository(session)
    user = await repository.get_by_telegram_id(telegram_user_id)
    if user is None:
        return
    resolved_channel_id = channel_id or (tariff.channel_id if tariff is not None else None)
    payload: dict[str, object] = {}
    if tariff is not None:
        payload.update(
            {
                "tariff_id": tariff.id,
                "channel_id": tariff.channel_id,
                "price_stars": tariff.price_stars,
            }
        )
    elif resolved_channel_id is not None:
        payload["channel_id"] = resolved_channel_id
    if extra_payload:
        payload.update(extra_payload)
    await write_audit_log(
        session,
        action=event_name,
        target_user_id=user.id,
        payload=payload or None,
    )
    await session.commit()


async def _render_product_picker_text(
    session: AsyncSession | None,
    products: list[ProductCatalogEntry],
    *,
    mode: str,
) -> str:
    if not products:
        return await _text(session, "tariffs_empty")

    lines: list[str] = []
    for index, product in enumerate(products, start=1):
        prefix: list[str] = []
        if product.featured_tariff_id is not None:
            prefix.append("🔥")
        if product.default_tariff_id is not None:
            prefix.append("🎯")
        if product.bundle_names:
            prefix.append("📚")
        marker = f"{' '.join(prefix)} " if prefix else ""
        heading = f"{FOLDER} Продукт: {escape(product.channel_title)}"
        if mode == "buy":
            lines.append(f"{index}. {heading} — {marker}{product.price_range_label}")
        else:
            tariff_label = "тариф" if product.tariff_count == 1 else ("тарифа" if product.tariff_count < 5 else "тарифов")
            lines.append(f"{index}. {heading} — {marker}{product.tariff_count} {tariff_label}")

        baseline_tariff = pick_default_tariff(product.tariffs) or product.tariffs[0]
        lead_tariff = next(
            (tariff for tariff in product.tariffs if getattr(tariff, "is_featured", False)),
            baseline_tariff,
        )
        lines.append(f"   • {_compact_offer_line(lead_tariff, baseline_tariff=baseline_tariff)}")
        if product.bundle_names:
            lines.append(f"   • пакеты: {', '.join(product.bundle_names)}")

    key = "product_buy_picker" if mode == "buy" else "product_tariffs_picker"
    return await _text(session, key, products_block="\n".join(lines))


async def _product_back_callback(
    session: AsyncSession,
    tariff: Tariff,
    *,
    mode: str,
) -> str:
    catalog = await _load_active_product_catalog(session)
    if is_multi_product_catalog(catalog):
        if mode == "buy":
            return f"menu:user:buy:product:{tariff.channel_id}"
        return f"menu:user:tariffs:product:{tariff.channel_id}"
    return "menu:user:buy" if mode == "buy" else "menu:user:tariffs"


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
    lines = []
    if is_reused:
        lines.append(f"{RECYCLE} Использую уже созданный счёт Crypto Pay.")
    else:
        lines.append(f"{MONEY} Счёт Crypto Pay создан.")
    lines.extend(
        [
            "",
            f"Тариф: {escape(_tariff_title(tariff))}",
            f"Актив: {asset}",
            f"Сумма: {amount}",
            f"Канал: {escape(_safe_channel_name(tariff))}",
        ]
    )
    if expires_at is not None:
        lines.append(f"Оплатить до: {format_datetime(expires_at, timezone)}")
    if invoice_url:
        lines.extend(["", "Открой кнопку ниже и заверши оплату в Crypto Pay."])
    lines.extend(["", "После подтверждения платежа доступ активируется автоматически."])
    return "\n".join(lines)


async def render_buy_entrypoint(
    target: Message | CallbackQuery,
    session: AsyncSession,
    settings: Settings | None = None,
    *,
    channel_id: int | None = None,
) -> bool:
    catalog = await _load_active_product_catalog(session)
    product = get_product_entry(catalog, channel_id) if channel_id is not None else None
    if channel_id is not None and product is not None:
        text = await _render_buy_section_text(session, product.tariffs)
        await render_section(
            target,
            text=_prepend_product_heading(text, product),
            reply_markup=user_tariffs_keyboard(
                product.tariffs,
                mode="buy",
                back_callback="menu:user:buy",
            ),
            banner_path=get_banner_path("buy"),
        )
        return True

    if is_multi_product_catalog(catalog):
        await render_section(
            target,
            text=await _render_product_picker_text(session, catalog, mode="buy"),
            reply_markup=user_product_picker_keyboard(catalog, mode="buy"),
            banner_path=get_banner_path("buy"),
        )
        return channel_id is None

    tariffs = catalog[0].tariffs if catalog else []
    await render_section(
        target,
        text=await _render_buy_section_text(session, tariffs),
        reply_markup=user_tariffs_keyboard(tariffs, mode="buy"),
        banner_path=get_banner_path("buy"),
    )
    return channel_id is None or bool(catalog)


async def render_tariffs_entrypoint(
    target: Message | CallbackQuery,
    session: AsyncSession,
    settings: Settings | None = None,
    *,
    channel_id: int | None = None,
) -> bool:
    catalog = await _load_active_product_catalog(session)
    product = get_product_entry(catalog, channel_id) if channel_id is not None else None
    crypto_enabled = bool(settings.crypto_pay_enabled) if settings is not None else False
    accepted_assets = settings.crypto_pay_accepted_assets if settings is not None else []
    if channel_id is not None and product is not None:
        text = await _render_tariffs_overview(
            session,
            product.tariffs,
            crypto_enabled=crypto_enabled,
            accepted_assets=accepted_assets,
        )
        await render_section(
            target,
            text=_prepend_product_heading(text, product),
            reply_markup=user_tariffs_keyboard(
                product.tariffs,
                mode="browse",
                back_callback="menu:user:tariffs",
            ),
            banner_path=get_banner_path("tariffs"),
        )
        return True

    if is_multi_product_catalog(catalog):
        await render_section(
            target,
            text=await _render_product_picker_text(session, catalog, mode="browse"),
            reply_markup=user_product_picker_keyboard(catalog, mode="browse"),
            banner_path=get_banner_path("tariffs"),
        )
        return channel_id is None

    tariffs = catalog[0].tariffs if catalog else []
    await render_section(
        target,
        text=await _render_tariffs_overview(
            session,
            tariffs,
            crypto_enabled=crypto_enabled,
            accepted_assets=accepted_assets,
        ),
        reply_markup=user_tariffs_keyboard(tariffs, mode="browse"),
        banner_path=get_banner_path("tariffs"),
    )
    return channel_id is None or bool(catalog)


async def track_buy_entrypoint_view(
    session: AsyncSession,
    *,
    telegram_user_id: int | None,
    channel_id: int | None = None,
) -> None:
    catalog = await _load_active_product_catalog(session)
    product = get_product_entry(catalog, channel_id) if channel_id is not None else None
    await _track_funnel_event(
        session,
        event_name="buy_screen_viewed",
        telegram_user_id=telegram_user_id,
        channel_id=(
            product.channel_id
            if product is not None
            else (catalog[0].channel_id if len(catalog) == 1 else None)
        ),
        extra_payload={
            "product_count": len(catalog),
            "tariff_count": sum(len(entry.tariffs) for entry in catalog),
            "multi_product": is_multi_product_catalog(catalog),
            "source": "start_deep_link",
        },
    )
    if product is not None:
        await _track_funnel_event(
            session,
            event_name="product_selected",
            telegram_user_id=telegram_user_id,
            channel_id=product.channel_id,
            extra_payload={
                "product_title": product.channel_title,
                "tariff_count": len(product.tariffs),
                "source": "start_deep_link",
            },
        )


@router.message(Command("paysupport"))
async def paysupport_command(
    message: Message,
    session: AsyncSession | None = None,
) -> None:
    await message.answer(await _text(session, "payment_support"))


@router.callback_query(F.data == "menu:user:buy")
async def buy_section(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    catalog = await _load_active_product_catalog(session)
    await _track_funnel_event(
        session,
        event_name="buy_screen_viewed",
        telegram_user_id=callback.from_user.id if callback.from_user is not None else None,
        channel_id=catalog[0].channel_id if len(catalog) == 1 else None,
        extra_payload={
            "product_count": len(catalog),
            "tariff_count": sum(len(product.tariffs) for product in catalog),
            "multi_product": is_multi_product_catalog(catalog),
        },
    )
    await render_buy_entrypoint(callback, session, settings)


@router.callback_query(F.data.startswith("menu:user:buy:product:"))
async def buy_product_section(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    channel_id = _callback_entity_id(callback.data)
    if channel_id is None:
        await callback.answer()
        return
    catalog = await _load_active_product_catalog(session)
    product = get_product_entry(catalog, channel_id)
    if product is None:
        await callback.answer("Продукт недоступен.", show_alert=True)
        return
    await _track_funnel_event(
        session,
        event_name="product_selected",
        telegram_user_id=callback.from_user.id if callback.from_user is not None else None,
        channel_id=product.channel_id,
        extra_payload={
            "product_title": product.channel_title,
            "tariff_count": len(product.tariffs),
        },
    )
    await render_buy_entrypoint(
        callback,
        session,
        settings,
        channel_id=product.channel_id,
    )


@router.callback_query(F.data == "menu:user:tariffs")
async def tariffs_section(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    await render_tariffs_entrypoint(callback, session, settings)


@router.callback_query(F.data.startswith("menu:user:tariffs:product:"))
async def tariffs_product_section(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    channel_id = _callback_entity_id(callback.data)
    if channel_id is None:
        await callback.answer()
        return
    catalog = await _load_active_product_catalog(session)
    product = get_product_entry(catalog, channel_id)
    if product is None:
        await callback.answer("Продукт недоступен.", show_alert=True)
        return
    await render_tariffs_entrypoint(
        callback,
        session,
        settings,
        channel_id=product.channel_id,
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

    await _track_funnel_event(
        session,
        event_name="tariff_detail_opened",
        telegram_user_id=callback.from_user.id if callback.from_user is not None else None,
        tariff=tariff,
        extra_payload={"mode": "browse"},
    )
    await render_section(
        callback,
        text=await _render_tariff_detail(
            session,
            tariff,
            crypto_enabled=settings.crypto_pay_enabled,
            accepted_assets=settings.crypto_pay_accepted_assets,
        ),
        reply_markup=user_tariff_detail_keyboard(
            tariff.id,
            include_crypto=(
                settings.crypto_pay_enabled and effective_crypto_price(tariff) is not None
            ),
            back_callback=await _product_back_callback(session, tariff, mode="browse"),
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
            admin_ids=settings.admin_ids_set if settings is not None else set(),
        )
    if user.is_blocked:
        await callback.answer(
            "Покупка недоступна: доступ ограничен администратором.",
            show_alert=True,
        )
        return

    tariff = await _load_active_tariff(session, tariff_id)
    if tariff is None:
        await callback.answer("Тариф недоступен.", show_alert=True)
        return

    try:
        await ensure_tariff_purchase_allowed(
            session,
            user_id=user.id,
            tariff=tariff,
        )
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
                "channel_id": tariff.channel_id,
                "asset": result.remote_invoice.asset,
                "amount": str(result.remote_invoice.amount),
                "external_id": result.invoice.external_id,
                "is_reused": result.is_reused,
            },
        )
        await session.commit()
    except (TariffValidationError, CryptoPayDisabledError, CryptoPayError) as exc:
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
        reply_markup=user_crypto_invoice_keyboard(
            result.remote_invoice.invoice_url,
            back_callback=await _product_back_callback(session, tariff, mode="buy"),
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("menu:user:buy:stars:"))
@router.callback_query(F.data.startswith("menu:user:buy:"))
async def buy_tariff(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings | None = None,
) -> None:
    if callback.data is not None and (":crypto:" in callback.data or ":product:" in callback.data):
        await callback.answer()
        return

    tariff_id = _callback_entity_id(callback.data)
    if tariff_id is None or callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    user_repository = UserRepository(session)
    user = await user_repository.get_by_telegram_id(callback.from_user.id)
    if user is None:
        user = await user_repository.upsert_from_telegram_user(
            callback.from_user,
            admin_ids=settings.admin_ids_set if settings is not None else set(),
        )
    if user.is_blocked:
        await callback.answer(
            "Покупка недоступна: доступ ограничен администратором.",
            show_alert=True,
        )
        return

    tariff = await _load_active_tariff(session, tariff_id)
    if tariff is None:
        await callback.answer("Тариф недоступен.", show_alert=True)
        return

    try:
        await ensure_tariff_purchase_allowed(
            session,
            user_id=user.id,
            tariff=tariff,
        )
    except TariffValidationError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    promo_quote = await get_pending_discount_quote_for_tariff(
        session,
        user_id=user.id,
        tariff=tariff,
    )

    invoice_payload = build_stars_invoice_payload(
        tariff.id,
        promo_redemption_id=promo_quote.redemption.id if promo_quote is not None else None,
    )
    invoice_amount = promo_quote.final_amount if promo_quote is not None else tariff.price_stars

    try:
        await send_stars_invoice(
            callback.message,
            tariff,
            amount=invoice_amount,
            payload=invoice_payload,
        )
    except Exception:
        logger.exception("Failed to send Stars invoice for tariff %s", tariff_id)
        await callback.answer("Не удалось выставить счёт на оплату.", show_alert=True)
        return

    try:
        payload = {
            "tariff_id": tariff.id,
            "channel_id": tariff.channel_id,
            "amount": invoice_amount,
        }
        if promo_quote is not None:
            payload.update(
                {
                    "promo_code": promo_quote.promo_code.code,
                    "full_amount": promo_quote.original_amount,
                    "discount_amount": promo_quote.savings_amount,
                }
            )
        await write_audit_log(
            session,
            action="invoice_created_stars",
            target_user_id=user.id,
            payload=payload,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        logger.exception(
            "Failed to write invoice_created_stars audit log for user %s",
            user.id,
        )

    if promo_quote is not None:
        await callback.answer(
            f"Счёт выставлен со скидкой {promo_quote.description} по коду {promo_quote.promo_code.code}."
        )
        return
    await callback.answer("Счёт выставлен.")


@router.pre_checkout_query()
async def pre_checkout_handler(query: PreCheckoutQuery, session: AsyncSession) -> None:
    user_repository = UserRepository(session)
    user = await user_repository.get_by_telegram_id(query.from_user.id)
    if user is None:
        user = await user_repository.upsert_from_telegram_user(query.from_user, admin_ids=set())
    if user.is_blocked:
        await query.answer(
            ok=False,
            error_message="Покупка недоступна: доступ ограничен администратором.",
        )
        return

    try:
        payload = parse_stars_invoice_payload(query.invoice_payload)
        tariff = await _load_active_tariff(session, payload.tariff_id)
        if tariff is None:
            raise StarsInvoiceError("Тариф недоступен.")
        await ensure_tariff_purchase_allowed(session, user_id=user.id, tariff=tariff)
        if query.currency != STARS_CURRENCY:
            raise StarsInvoiceError("Поддерживается только оплата в Telegram Stars.")

        if payload.promo_redemption_id is not None:
            quote = await get_discount_quote_for_redemption(
                session,
                redemption_id=payload.promo_redemption_id,
                user_id=user.id,
                tariff=tariff,
            )
            if query.total_amount != quote.final_amount:
                raise StarsInvoiceError(
                    "Сумма счёта изменилась. Закрой окно и открой оплату заново."
                )
        elif query.total_amount != tariff.price_stars:
            raise StarsInvoiceError(
                "Сумма счёта изменилась. Закрой окно и открой оплату заново."
            )
    except (PromoCodeError, StarsInvoiceError, TariffValidationError) as exc:
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
            admin_ids=settings.admin_ids_set if settings is not None else set(),
        )

    existing_payment = await PaymentRepository(session).get_by_telegram_charge_id(
        message.successful_payment.telegram_payment_charge_id
    )
    if existing_payment is not None:
        await message.answer("Платёж уже обработан.")
        return

    previous_paid_count = await PaymentRepository(session).count_paid_for_user(user.id)
    promo_quote = None
    try:
        payload = parse_stars_invoice_payload(message.successful_payment.invoice_payload)
        tariff = await _load_active_tariff(session, payload.tariff_id)
        if tariff is None:
            raise StarsInvoiceError("Тариф больше недоступен.")
        await ensure_tariff_purchase_allowed(
            session,
            user_id=user.id,
            tariff=tariff,
            now=message.date,
        )

        if payload.promo_redemption_id is not None:
            promo_quote = await get_discount_quote_for_redemption(
                session,
                redemption_id=payload.promo_redemption_id,
                user_id=user.id,
                tariff=tariff,
                now=message.date,
            )

        result = await process_successful_stars_payment(
            session,
            user_id=user.id,
            tariff=tariff,
            successful_payment=message.successful_payment,
            expected_amount=promo_quote.final_amount if promo_quote is not None else tariff.price_stars,
            paid_at=message.date,
            referral_reward_days=settings.referral_reward_days,
        )
        if promo_quote is not None and result.payment is not None:
            await consume_discount_redemption(
                session,
                quote=promo_quote,
                payment=result.payment,
                used_at=message.date,
            )
        if not result.is_duplicate:
            payload_dict = {
                "tariff_id": tariff.id,
                "channel_id": tariff.channel_id,
                "amount": message.successful_payment.total_amount,
                "telegram_payment_charge_id": message.successful_payment.telegram_payment_charge_id,
                "is_extension": result.is_extension,
            }
            if promo_quote is not None:
                payload_dict.update(
                    {
                        "promo_code": promo_quote.promo_code.code,
                        "discount_amount": promo_quote.savings_amount,
                        "full_amount": promo_quote.original_amount,
                    }
                )
            await write_audit_log(
                session,
                action="payment_paid_stars",
                target_user_id=user.id,
                payload=payload_dict,
            )
            if previous_paid_count > 0:
                await write_audit_log(
                    session,
                    action="repeat_purchase_paid",
                    target_user_id=user.id,
                    payload={
                        "tariff_id": tariff.id,
                        "channel_id": tariff.channel_id,
                        "payment_id": result.payment.id if result.payment is not None else None,
                    },
                )
        await session.commit()
    except (PromoCodeError, StarsInvoiceError, TariffValidationError) as exc:
        await session.rollback()
        await message.answer(await _text(session, "payment_failed", reason=str(exc)))
        await message.answer(await _text(session, "payment_support"))
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
                reason="техническая ошибка при обработке платежа",
            )
        )
        await message.answer(await _text(session, "payment_support"))
        return

    if result.is_duplicate:
        await message.answer("Платёж уже обработан.")
        return

    if result.subscription is None:
        await message.answer(
            await _text(
                session,
                "payment_failed",
                reason="оплата прошла, но подписка ещё не активировалась автоматически",
            )
        )
        await message.answer(await _text(session, "payment_support"))
        return

    invite_link: str | None = None
    invite_expires_at: datetime | None = None
    invite_error: str | None = None
    invite_reused = False
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
        invite_reused = grant.is_reused
        await write_audit_log(
            session,
            action="invite_issued",
            target_user_id=user.id,
            payload={
                "tariff_id": tariff.id,
                "channel_id": tariff.channel_id,
                "subscription_id": result.subscription.id,
                "invite_link_id": grant.invite.id,
                "is_reused": grant.is_reused,
            },
        )
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
        invite_error = "Не удалось автоматически выдать ссылку доступа."

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
    if invite_link is not None and invite_reused:
        await message.answer("Ссылка уже была активна, поэтому я отправил действующий инвайт повторно.")
