from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BroadcastCampaign, Payment, Subscription, User
from app.db.repositories.broadcast_campaigns import BroadcastCampaignRepository
from app.db.repositories.broadcast_deliveries import BroadcastDeliveryRepository
from app.services.users import filter_label
from app.utils.datetime import ensure_aware_utc, utcnow


class BroadcastValidationError(ValueError):
    """Raised when a broadcast cannot be prepared or queued."""


@dataclass(slots=True)
class BroadcastRecipientPreview:
    filter_name: str
    filter_label: str
    user_ids: list[int]

    @property
    def total_targets(self) -> int:
        return len(self.user_ids)


@dataclass(slots=True)
class BroadcastCampaignSnapshot:
    campaign: BroadcastCampaign
    filter_label: str
    blocked_count: int
    pending_count: int
    recent_failures: list[tuple[int, str, str | None]]

    @property
    def remaining_count(self) -> int:
        return self.pending_count


async def select_broadcast_recipients(
    session: AsyncSession,
    *,
    filter_name: str,
    now: datetime | None = None,
) -> BroadcastRecipientPreview:
    current_time = ensure_aware_utc(now or utcnow())
    users = list((await session.execute(select(User))).scalars())
    paid_rows = list(
        (
            await session.execute(
                select(Payment.user_id, Payment.tariff_id)
                .where(Payment.status == "paid")
            )
        ).all()
    )
    subscription_rows = list(
        (
            await session.execute(
                select(
                    Subscription.user_id,
                    Subscription.status,
                    Subscription.revoked_at,
                    Subscription.expires_at,
                    Subscription.channel_id,
                ).order_by(
                    Subscription.user_id.asc(),
                    Subscription.expires_at.desc(),
                    Subscription.id.desc(),
                )
            )
        ).all()
    )

    paid_user_ids: set[int] = set()
    tariff_user_ids: dict[int, set[int]] = {}
    for user_id, tariff_id in paid_rows:
        paid_user_ids.add(user_id)
        if tariff_id is not None:
            tariff_user_ids.setdefault(int(tariff_id), set()).add(user_id)

    latest_expires_by_user: dict[int, datetime] = {}
    active_user_ids: set[int] = set()
    channel_user_ids: dict[int, set[int]] = {}
    for user_id, status, revoked_at, expires_at, channel_id in subscription_rows:
        aware_expires_at = ensure_aware_utc(expires_at)
        latest_expires_by_user.setdefault(user_id, aware_expires_at)
        channel_user_ids.setdefault(int(channel_id), set()).add(user_id)
        if status == "active" and revoked_at is None and aware_expires_at > current_time:
            active_user_ids.add(user_id)

    selected_user_ids: list[int] = []
    for user in users:
        if _should_skip_broadcast_user(user):
            continue
        if _matches_broadcast_filter(
            user=user,
            filter_name=filter_name,
            current_time=current_time,
            active_user_ids=active_user_ids,
            latest_expires_by_user=latest_expires_by_user,
            paid_user_ids=paid_user_ids,
            tariff_user_ids=tariff_user_ids,
            channel_user_ids=channel_user_ids,
        ):
            selected_user_ids.append(user.id)

    return BroadcastRecipientPreview(
        filter_name=filter_name,
        filter_label=filter_label(filter_name),
        user_ids=selected_user_ids,
    )


async def queue_broadcast_campaign(
    session: AsyncSession,
    *,
    created_by_user_id: int | None,
    filter_name: str,
    content: str,
    now: datetime | None = None,
) -> BroadcastCampaign:
    normalized_content = content.strip()
    if not normalized_content:
        raise BroadcastValidationError(
            "\u0422\u0435\u043a\u0441\u0442 \u0440\u0430\u0441\u0441\u044b\u043b\u043a\u0438 "
            "\u043d\u0435 \u0434\u043e\u043b\u0436\u0435\u043d \u0431\u044b\u0442\u044c "
            "\u043f\u0443\u0441\u0442\u044b\u043c."
        )

    preview = await select_broadcast_recipients(
        session,
        filter_name=filter_name,
        now=now,
    )
    if not preview.user_ids:
        raise BroadcastValidationError(
            "\u041f\u043e \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u043e\u043c\u0443 "
            "\u0444\u0438\u043b\u044c\u0442\u0440\u0443 \u043d\u0435\u0442 "
            "\u043f\u043e\u043b\u0443\u0447\u0430\u0442\u0435\u043b\u0435\u0439."
        )

    campaign = await BroadcastCampaignRepository(session).create(
        created_by_user_id=created_by_user_id,
        filter_name=filter_name,
        content=normalized_content,
        total_targets=preview.total_targets,
        status="queued",
    )
    await BroadcastDeliveryRepository(session).bulk_create(
        campaign_id=campaign.id,
        user_ids=preview.user_ids,
    )
    return campaign


async def list_broadcast_campaign_snapshots(
    session: AsyncSession,
    *,
    limit: int = 10,
) -> list[BroadcastCampaignSnapshot]:
    repository = BroadcastCampaignRepository(session)
    campaigns = await repository.list_recent(limit=limit)
    return [await get_broadcast_campaign_snapshot(session, campaign.id) for campaign in campaigns]


async def get_broadcast_campaign_snapshot(
    session: AsyncSession,
    campaign_id: int,
) -> BroadcastCampaignSnapshot | None:
    campaign = await BroadcastCampaignRepository(session).get_by_id(campaign_id)
    if campaign is None:
        return None

    delivery_repository = BroadcastDeliveryRepository(session)
    counts = await delivery_repository.count_by_status(campaign.id)
    recent_failures = await delivery_repository.list_recent_failures(campaign.id, limit=5)
    return BroadcastCampaignSnapshot(
        campaign=campaign,
        filter_label=filter_label(campaign.filter_name),
        blocked_count=counts.get("blocked", 0),
        pending_count=counts.get("pending", 0),
        recent_failures=[
            (delivery.user_id, str(telegram_id), delivery.error_message)
            for delivery, telegram_id in recent_failures
        ],
    )


async def get_next_broadcast_campaign(session: AsyncSession) -> BroadcastCampaign | None:
    repository = BroadcastCampaignRepository(session)
    campaign = await repository.get_current_sending()
    if campaign is not None:
        return campaign
    return await repository.get_next_queued()


def _should_skip_broadcast_user(user: User) -> bool:
    return user.is_blocked or user.is_admin or user.role != "user"


def _matches_broadcast_filter(
    *,
    user: User,
    filter_name: str,
    current_time: datetime,
    active_user_ids: set[int],
    latest_expires_by_user: dict[int, datetime],
    paid_user_ids: set[int],
    tariff_user_ids: dict[int, set[int]],
    channel_user_ids: dict[int, set[int]],
) -> bool:
    if filter_name == "all":
        return True
    if filter_name == "active":
        return user.id in active_user_ids
    if filter_name == "expired":
        return (
            user.id not in active_user_ids
            and user.id in latest_expires_by_user
            and latest_expires_by_user[user.id] <= current_time
        )
    if filter_name == "never_paid":
        return user.id not in paid_user_ids
    if filter_name.startswith("tariff-"):
        tariff_id = int(filter_name.removeprefix("tariff-"))
        return user.id in tariff_user_ids.get(tariff_id, set())
    if filter_name.startswith("channel-"):
        channel_id = int(filter_name.removeprefix("channel-"))
        return user.id in channel_user_ids.get(channel_id, set())
    raise BroadcastValidationError(
        "\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439 "
        "\u0444\u0438\u043b\u044c\u0442\u0440 "
        f"\u0440\u0430\u0441\u0441\u044b\u043b\u043a\u0438: {filter_name}"
    )