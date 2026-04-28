from __future__ import annotations

from dataclasses import dataclass

from app.db.models import Channel


class TariffValidationError(ValueError):
    """Raised when admin input does not satisfy tariff constraints."""


@dataclass(slots=True)
class TariffDraft:
    name: str
    price_stars: int
    duration_days: int
    channel_id: int
    sort_order: int = 100


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


def validate_tariff_payload(
    *,
    name: str,
    price_stars: str,
    duration_days: str,
    channel: Channel | None,
    sort_order: str | None = None,
) -> TariffDraft:
    checked_channel = ensure_channel_can_host_tariff(channel)
    checked_name = validate_tariff_name(name)
    checked_price = parse_positive_int(price_stars, "цена")
    checked_days = parse_positive_int(duration_days, "длительность")
    checked_sort = 100 if sort_order is None else parse_positive_int(sort_order, "сортировка")

    return TariffDraft(
        name=checked_name,
        price_stars=checked_price,
        duration_days=checked_days,
        channel_id=checked_channel.id,
        sort_order=checked_sort,
    )