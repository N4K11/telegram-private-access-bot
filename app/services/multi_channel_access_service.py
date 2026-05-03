from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Subscription
from app.db.repositories.subscriptions import SubscriptionRepository
from app.utils.datetime import ensure_aware_utc, utcnow
from app.utils.encoding import safe_ui_text

TXT_PRODUCT = "\u041f\u0440\u043e\u0434\u0443\u043a\u0442"
TXT_TARIFF = "\u0422\u0430\u0440\u0438\u0444"


@dataclass(slots=True)
class ProductAccessEntry:
    channel_id: int
    channel_title: str
    latest_expires_at: datetime
    subscription_count: int
    tariff_names: tuple[str, ...]
    subscription_ids: tuple[int, ...]


async def load_active_product_access(
    session: AsyncSession,
    *,
    user_id: int,
    at_time: datetime | None = None,
) -> list[ProductAccessEntry]:
    subscriptions = await SubscriptionRepository(session).list_current_for_user(
        user_id,
        at_time=ensure_aware_utc(at_time or utcnow()),
    )
    return summarize_product_access(subscriptions)


def summarize_product_access(
    subscriptions: Sequence[Subscription],
) -> list[ProductAccessEntry]:
    grouped: OrderedDict[int, list[Subscription]] = OrderedDict()
    for subscription in subscriptions:
        grouped.setdefault(int(subscription.channel_id), []).append(subscription)

    result: list[ProductAccessEntry] = []
    for channel_id, channel_subscriptions in grouped.items():
        first = channel_subscriptions[0]
        channel = getattr(first, "channel", None)
        channel_title = safe_ui_text(
            getattr(channel, "title", None),
            f"{TXT_PRODUCT} #{channel_id}",
        )
        latest_expires_at = max(
            ensure_aware_utc(subscription.expires_at)
            for subscription in channel_subscriptions
        )
        tariff_names = tuple(
            safe_ui_text(
                getattr(getattr(subscription, "tariff", None), "name", None),
                f"{TXT_TARIFF} #{subscription.tariff_id}",
            )
            for subscription in channel_subscriptions
        )
        result.append(
            ProductAccessEntry(
                channel_id=channel_id,
                channel_title=channel_title,
                latest_expires_at=latest_expires_at,
                subscription_count=len(channel_subscriptions),
                tariff_names=tariff_names,
                subscription_ids=tuple(subscription.id for subscription in channel_subscriptions),
            )
        )
    return result