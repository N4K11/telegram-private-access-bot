
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BroadcastCampaign,
    InviteLink,
    Payment,
    Subscription,
    TextTemplate,
    User,
)
from app.db.repositories.broadcast_campaigns import BroadcastCampaignRepository
from app.db.repositories.broadcast_deliveries import BroadcastDeliveryRepository
from app.db.repositories.text_templates import TextTemplateRepository
from app.services.users import filter_label
from app.utils.datetime import ensure_aware_utc, utcnow

BROADCAST_TEMPLATE_PREFIX = "broadcast_template."
BROADCAST_PREVIEW_SAMPLE_LIMIT = 5
BROADCAST_EXPIRES_SOON_DELTA = timedelta(days=3)


class BroadcastValidationError(ValueError):
    """Raised when a broadcast cannot be prepared or queued."""


@dataclass(slots=True)
class BroadcastRecipientSample:
    user_id: int
    telegram_id: int
    label: str


@dataclass(slots=True)
class BroadcastRecipientPreview:
    filter_name: str
    filter_label: str
    user_ids: list[int]
    samples: list[BroadcastRecipientSample]

    @property
    def total_targets(self) -> int:
        return len(self.user_ids)


@dataclass(slots=True)
class BroadcastTemplateRecord:
    key: str
    title: str
    content: str
    updated_at: datetime | None


@dataclass(slots=True)
class BroadcastCampaignSnapshot:
    campaign: BroadcastCampaign
    filter_label: str
    blocked_count: int
    pending_count: int
    rate_limited_count: int
    recent_failures: list[tuple[int, str, str, str | None]]

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
    users = list((await session.execute(select(User).order_by(User.id.asc()))).scalars())
    paid_rows = list(
        (
            await session.execute(
                select(Payment.user_id, Payment.tariff_id).where(Payment.status == "paid")
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
    invite_rows = list(
        (
            await session.execute(
                select(InviteLink.user_id, InviteLink.expire_at, InviteLink.is_revoked)
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
    expires_soon_user_ids: set[int] = set()
    channel_user_ids: dict[int, set[int]] = {}
    for user_id, status, revoked_at, expires_at, channel_id in subscription_rows:
        aware_expires_at = ensure_aware_utc(expires_at)
        latest_expires_by_user.setdefault(user_id, aware_expires_at)
        channel_user_ids.setdefault(int(channel_id), set()).add(user_id)
        if status == "active" and revoked_at is None and aware_expires_at > current_time:
            active_user_ids.add(user_id)
            if aware_expires_at <= current_time + BROADCAST_EXPIRES_SOON_DELTA:
                expires_soon_user_ids.add(user_id)

    pending_join_user_ids: set[int] = set()
    for user_id, expire_at, is_revoked in invite_rows:
        if is_revoked:
            continue
        if expire_at is None or ensure_aware_utc(expire_at) > current_time:
            pending_join_user_ids.add(user_id)

    selected_user_ids: list[int] = []
    samples: list[BroadcastRecipientSample] = []
    for user in users:
        if _should_skip_broadcast_user(user):
            continue
        if _matches_broadcast_filter(
            user=user,
            filter_name=filter_name,
            current_time=current_time,
            active_user_ids=active_user_ids,
            expires_soon_user_ids=expires_soon_user_ids,
            pending_join_user_ids=pending_join_user_ids,
            latest_expires_by_user=latest_expires_by_user,
            paid_user_ids=paid_user_ids,
            tariff_user_ids=tariff_user_ids,
            channel_user_ids=channel_user_ids,
        ):
            selected_user_ids.append(user.id)
            if len(samples) < BROADCAST_PREVIEW_SAMPLE_LIMIT:
                samples.append(_build_sample(user))

    return BroadcastRecipientPreview(
        filter_name=filter_name,
        filter_label=filter_label(filter_name),
        user_ids=selected_user_ids,
        samples=samples,
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
        raise BroadcastValidationError("Текст рассылки не должен быть пустым.")

    preview = await select_broadcast_recipients(
        session,
        filter_name=filter_name,
        now=now,
    )
    if not preview.user_ids:
        raise BroadcastValidationError("По выбранному фильтру нет получателей.")

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
        rate_limited_count=counts.get("rate_limited", 0),
        recent_failures=[
            (delivery.user_id, str(telegram_id), delivery.status, delivery.error_message)
            for delivery, telegram_id in recent_failures
        ],
    )


async def get_next_broadcast_campaign(session: AsyncSession) -> BroadcastCampaign | None:
    repository = BroadcastCampaignRepository(session)
    campaign = await repository.get_current_sending()
    if campaign is not None:
        return campaign
    return await repository.get_next_queued()


async def list_broadcast_templates(
    session: AsyncSession,
    *,
    limit: int = 20,
) -> list[BroadcastTemplateRecord]:
    result = await session.execute(
        select(TextTemplate)
        .where(TextTemplate.key.like(f"{BROADCAST_TEMPLATE_PREFIX}%"))
        .where(TextTemplate.is_system.is_(False))
        .order_by(TextTemplate.title.asc(), TextTemplate.key.asc())
        .limit(limit)
    )
    return [_to_template_record(template) for template in result.scalars()]


async def get_broadcast_template(
    session: AsyncSession,
    *,
    key: str,
) -> BroadcastTemplateRecord | None:
    if not key.startswith(BROADCAST_TEMPLATE_PREFIX):
        return None
    template = await TextTemplateRepository(session).get_by_key(key)
    if template is None or template.is_system:
        return None
    return _to_template_record(template)


async def save_broadcast_template(
    session: AsyncSession,
    *,
    title: str,
    content: str,
    updated_by_user_id: int | None,
) -> BroadcastTemplateRecord:
    normalized_title = title.strip()
    normalized_content = content.strip()
    if not normalized_title:
        raise BroadcastValidationError("Название шаблона не должно быть пустым.")
    if not normalized_content:
        raise BroadcastValidationError("Шаблон не может быть пустым.")

    key = _build_broadcast_template_key(normalized_title)
    repository = TextTemplateRepository(session)
    template = await repository.get_by_key(key)
    if template is None:
        template = await repository.create(
            key=key,
            title=normalized_title,
            body=normalized_content,
            is_system=False,
            updated_by_user_id=updated_by_user_id,
        )
    else:
        template.title = normalized_title
        template.body = normalized_content
        template.is_system = False
        template.updated_by_user_id = updated_by_user_id
        await session.flush()
    return _to_template_record(template)


def _should_skip_broadcast_user(user: User) -> bool:
    return user.is_blocked or user.is_admin or user.role != "user"


def _matches_broadcast_filter(
    *,
    user: User,
    filter_name: str,
    current_time: datetime,
    active_user_ids: set[int],
    expires_soon_user_ids: set[int],
    pending_join_user_ids: set[int],
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
    if filter_name == "expires_soon":
        return user.id in expires_soon_user_ids
    if filter_name == "pending_join":
        return user.id in active_user_ids and user.id in pending_join_user_ids
    if filter_name.startswith("tariff-"):
        tariff_id = int(filter_name.removeprefix("tariff-"))
        return user.id in tariff_user_ids.get(tariff_id, set())
    if filter_name.startswith("channel-"):
        channel_id = int(filter_name.removeprefix("channel-"))
        return user.id in channel_user_ids.get(channel_id, set())
    raise BroadcastValidationError(f"Неизвестный фильтр рассылки: {filter_name}")


def _build_sample(user: User) -> BroadcastRecipientSample:
    if user.username:
        label = f"@{user.username} (Telegram {user.telegram_id})"
    elif user.first_name:
        label = f"{user.first_name} (Telegram {user.telegram_id})"
    else:
        label = f"Telegram {user.telegram_id}"
    return BroadcastRecipientSample(
        user_id=user.id,
        telegram_id=user.telegram_id,
        label=label,
    )


def _build_broadcast_template_key(title: str) -> str:
    slug = re.sub(r"\s+", "-", title.strip().lower())
    slug = re.sub(r"[^\w\-]+", "", slug, flags=re.UNICODE)
    slug = slug.strip("-") or "template"
    return f"{BROADCAST_TEMPLATE_PREFIX}{slug[:80]}"


def _to_template_record(template: TextTemplate) -> BroadcastTemplateRecord:
    state = getattr(template, "__dict__", {})
    updated_at = state.get("updated_at") or state.get("created_at")
    return BroadcastTemplateRecord(
        key=template.key,
        title=template.title,
        content=template.body,
        updated_at=ensure_aware_utc(updated_at) if updated_at is not None else None,
    )

