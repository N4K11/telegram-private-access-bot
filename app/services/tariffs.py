from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Channel, Subscription, Tariff
from app.db.repositories.subscriptions import SubscriptionRepository
from app.utils.datetime import ensure_aware_utc, utcnow

LIFETIME_EXPIRES_AT = datetime(9999, 12, 31, 23, 59, tzinfo=UTC)
DEFAULT_TARIFF_SORT_ORDER = 100


class TariffValidationError(ValueError):
    """Raised when admin input or purchase constraints are invalid."""


@dataclass(slots=True)
class TariffDraft:
    name: str
    price_stars: int
    duration_days: int
    channel_id: int
    sort_order: int = DEFAULT_TARIFF_SORT_ORDER
    description: str | None = None
    badge: str | None = None
    offer_copy: str | None = None
    offer_group: str | None = None
    is_trial: bool = False
    is_lifetime: bool = False
    is_featured: bool = False
    is_default_offer: bool = False
    crypto_price_amount: Decimal | None = None
    crypto_asset: str | None = None


def validate_tariff_name(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        raise TariffValidationError("Название тарифа не должно быть пустым.")
    return value


def parse_positive_int(raw_value: str, field_name: str) -> int:
    try:
        value = int(raw_value.strip())
    except ValueError as exc:
        raise TariffValidationError(f"Поле «{field_name}» должно быть целым числом.") from exc

    if value <= 0:
        raise TariffValidationError(f"Поле «{field_name}» должно быть больше нуля.")
    return value


def parse_positive_decimal(raw_value: str, field_name: str) -> Decimal:
    try:
        value = Decimal(raw_value.strip())
    except InvalidOperation as exc:
        raise TariffValidationError(
            f"Поле «{field_name}» должно быть числом."
        ) from exc
    if value <= 0:
        raise TariffValidationError(f"Поле «{field_name}» должно быть больше нуля.")
    return value


def validate_optional_badge(raw_value: str) -> str | None:
    value = raw_value.strip()
    if not value:
        return None
    if len(value) > 32:
        raise TariffValidationError("Бейдж должен быть не длиннее 32 символов.")
    return value


def validate_optional_description(raw_value: str) -> str | None:
    value = raw_value.strip()
    return value or None


def validate_optional_offer_copy(raw_value: str) -> str | None:
    value = raw_value.strip()
    if not value:
        return None
    if len(value) > 160:
        raise TariffValidationError("Короткий оффер должен быть не длиннее 160 символов.")
    return value


def validate_optional_offer_group(raw_value: str) -> str | None:
    value = raw_value.strip()
    if not value:
        return None
    if len(value) > 64:
        raise TariffValidationError("Название группы офферов должно быть не длиннее 64 символов.")
    return value


def normalize_crypto_asset(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    value = raw_value.strip().upper()
    return value or None


def ensure_channel_can_host_tariff(channel: Channel | None) -> Channel:
    if channel is None:
        raise TariffValidationError("Сначала выберите существующий канал.")
    if not channel.is_active:
        raise TariffValidationError("Нельзя использовать выключенный канал для тарифа.")
    if not channel.invite_users_permission:
        raise TariffValidationError("У бота нет права приглашать пользователей в этот канал.")
    if not channel.ban_users_permission:
        raise TariffValidationError("У бота нет права удалять пользователей из этого канала.")
    return channel


def ensure_tariff_mode_flags(*, is_trial: bool, is_lifetime: bool) -> None:
    if is_trial and is_lifetime:
        raise TariffValidationError("Тариф не может быть одновременно trial и lifetime.")


def validate_tariff_payload(
    *,
    name: str,
    price_stars: str,
    duration_days: str,
    channel: Channel | None,
    sort_order: str | None = None,
    description: str | None = None,
    badge: str | None = None,
    is_trial: bool = False,
    is_lifetime: bool = False,
    crypto_price_amount: str | None = None,
    crypto_asset: str | None = None,
) -> TariffDraft:
    checked_channel = ensure_channel_can_host_tariff(channel)
    checked_name = validate_tariff_name(name)
    checked_price = parse_positive_int(price_stars, "цена")
    checked_days = parse_positive_int(duration_days, "длительность")
    checked_sort = (
        DEFAULT_TARIFF_SORT_ORDER
        if sort_order is None
        else parse_positive_int(sort_order, "сортировка")
    )
    ensure_tariff_mode_flags(is_trial=is_trial, is_lifetime=is_lifetime)

    return TariffDraft(
        name=checked_name,
        price_stars=checked_price,
        duration_days=checked_days,
        channel_id=checked_channel.id,
        sort_order=checked_sort,
        description=validate_optional_description(description or ""),
        badge=validate_optional_badge(badge or ""),
        offer_copy=None,
        offer_group=None,
        is_trial=is_trial,
        is_lifetime=is_lifetime,
        is_featured=False,
        is_default_offer=False,
        crypto_price_amount=(
            None
            if crypto_price_amount is None or not crypto_price_amount.strip()
            else parse_positive_decimal(crypto_price_amount, "цена Crypto Pay")
        ),
        crypto_asset=normalize_crypto_asset(crypto_asset),
    )


def effective_crypto_price(tariff: Tariff) -> Decimal | None:
    if tariff.crypto_price_amount is not None:
        return Decimal(tariff.crypto_price_amount)
    if tariff.price_crypto is not None:
        return Decimal(tariff.price_crypto)
    return None


def effective_crypto_asset(
    tariff: Tariff,
    accepted_assets: list[str] | None = None,
) -> str | None:
    asset = normalize_crypto_asset(tariff.crypto_asset)
    if asset is not None:
        return asset
    if accepted_assets:
        first = normalize_crypto_asset(accepted_assets[0])
        if first is not None:
            return first
    return None


def tariff_badge_label(tariff: Tariff) -> str | None:
    return validate_optional_badge(tariff.badge or "")


def tariff_duration_label(tariff: Tariff) -> str:
    if tariff.is_lifetime:
        return "Навсегда"
    suffix = " trial" if tariff.is_trial else ""
    return f"{tariff.duration_days} дн.{suffix}"


async def ensure_tariff_purchase_allowed(
    session: AsyncSession,
    *,
    user_id: int,
    tariff: Tariff,
    now: datetime | None = None,
) -> Tariff:
    if tariff.archived_at is not None or not tariff.is_active:
        raise TariffValidationError("Тариф недоступен для покупки.")
    ensure_channel_can_host_tariff(tariff.channel)
    current_time = ensure_aware_utc(now or utcnow())

    if tariff.is_trial:
        trial_usage = await session.execute(
            select(Subscription.id)
            .join(Tariff, Subscription.tariff_id == Tariff.id)
            .where(Subscription.user_id == user_id)
            .where(Tariff.is_trial.is_(True))
            .limit(1)
        )
        if trial_usage.scalar_one_or_none() is not None:
            raise TariffValidationError(
                "Пробный тариф можно использовать только один раз."
            )

    current = await SubscriptionRepository(session).get_latest_for_user_channel(
        user_id,
        tariff.channel_id,
    )
    if (
        current is not None
        and current.revoked_at is None
        and ensure_aware_utc(current.expires_at) > current_time
        and current.tariff is not None
        and current.tariff.is_lifetime
    ):
        raise TariffValidationError(
            "У вас уже есть пожизненный доступ к этому каналу."
        )
    return tariff
