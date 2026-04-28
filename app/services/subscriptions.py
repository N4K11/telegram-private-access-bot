from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Subscription, Tariff
from app.db.repositories.subscriptions import SubscriptionRepository
from app.utils.datetime import ensure_aware_utc, utcnow


@dataclass(slots=True)
class SubscriptionChange:
    subscription: Subscription
    starts_at: datetime
    previous_expires_at: datetime | None
    is_extension: bool


async def activate_or_extend_subscription(
    session: AsyncSession,
    *,
    user_id: int,
    tariff: Tariff,
    paid_at: datetime | None = None,
    source: str = "purchase",
) -> SubscriptionChange:
    event_time = ensure_aware_utc(paid_at or utcnow())
    repository = SubscriptionRepository(session)
    current = await repository.get_latest_for_user_channel(user_id, tariff.channel_id)
    duration = timedelta(days=tariff.duration_days)

    if (
        current is not None
        and current.revoked_at is None
        and current.status == "active"
        and current.expires_at > event_time
    ):
        previous_expires_at = current.expires_at
        current.tariff_id = tariff.id
        current.channel_id = tariff.channel_id
        current.source = source
        current.expires_at = current.expires_at + duration
        return SubscriptionChange(
            subscription=current,
            starts_at=current.started_at,
            previous_expires_at=previous_expires_at,
            is_extension=True,
        )

    if current is not None and current.revoked_at is None and current.expires_at <= event_time:
        current.status = "expired"

    subscription = await repository.create(
        user_id=user_id,
        tariff_id=tariff.id,
        channel_id=tariff.channel_id,
        started_at=event_time,
        expires_at=event_time + duration,
        source=source,
    )
    return SubscriptionChange(
        subscription=subscription,
        starts_at=event_time,
        previous_expires_at=current.expires_at if current is not None else None,
        is_extension=False,
    )