from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Channel, Payment, Subscription, Tariff, User
from app.db.repositories.audit_logs import AuditLogRepository
from app.db.repositories.payments import PaymentRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.users import UserRepository
from app.utils.datetime import ensure_aware_utc, utcnow

DEFAULT_USER_PAGE_SIZE = 6
USER_FILTER_LABELS: dict[str, str] = {
    "all": "Все",
    "active": "Активные",
    "expired": "Истекло",
    "never_paid": "Не покупали",
    "blocked": "Заблокированные",
    "stars": "Stars",
    "crypto": "Crypto",
}


@dataclass(slots=True)
class UserDirectoryEntry:
    user: User
    status: str
    latest_expires_at: datetime | None
    total_paid: int
    paid_count: int
    has_active_subscription: bool
    has_paid_stars: bool
    has_paid_crypto: bool


@dataclass(slots=True)
class UserDirectoryPage:
    items: list[UserDirectoryEntry]
    page: int
    total_pages: int
    total_items: int
    filter_key: str


@dataclass(slots=True)
class UserProfileSnapshot:
    user: User
    status: str
    latest_expires_at: datetime | None
    total_paid: int
    active_subscriptions: list[Subscription]
    recent_subscriptions: list[Subscription]
    recent_payments: list[Payment]
    audit_entries: list


async def build_user_directory(
    session: AsyncSession,
    *,
    filter_key: str = "all",
    page: int = 1,
    page_size: int = DEFAULT_USER_PAGE_SIZE,
    now: datetime | None = None,
) -> UserDirectoryPage:
    current_time = ensure_aware_utc(now or utcnow())
    users = await UserRepository(session).list_all()

    payment_rows = list(
        (
            await session.execute(
                select(
                    Payment.user_id,
                    Payment.provider,
                    Payment.amount,
                    Payment.tariff_id,
                ).where(Payment.status == "paid")
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

    total_paid_by_user: dict[int, int] = {}
    paid_count_by_user: dict[int, int] = {}
    stars_user_ids: set[int] = set()
    crypto_user_ids: set[int] = set()
    tariff_user_ids: dict[int, set[int]] = {}
    for user_id, provider, amount, tariff_id in payment_rows:
        total_paid_by_user[user_id] = total_paid_by_user.get(user_id, 0) + int(amount)
        paid_count_by_user[user_id] = paid_count_by_user.get(user_id, 0) + 1
        if provider == "telegram_stars":
            stars_user_ids.add(user_id)
        if provider.startswith("crypto"):
            crypto_user_ids.add(user_id)
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

    entries = [
        UserDirectoryEntry(
            user=user,
            status=describe_user_status(
                user,
                has_active_subscription=user.id in active_user_ids,
                latest_expires_at=latest_expires_by_user.get(user.id),
                paid_count=paid_count_by_user.get(user.id, 0),
            ),
            latest_expires_at=latest_expires_by_user.get(user.id),
            total_paid=total_paid_by_user.get(user.id, 0),
            paid_count=paid_count_by_user.get(user.id, 0),
            has_active_subscription=user.id in active_user_ids,
            has_paid_stars=user.id in stars_user_ids,
            has_paid_crypto=user.id in crypto_user_ids,
        )
        for user in users
    ]

    filtered = [
        entry
        for entry in entries
        if _matches_filter(
            entry,
            filter_key=filter_key,
            current_time=current_time,
            tariff_user_ids=tariff_user_ids,
            channel_user_ids=channel_user_ids,
        )
    ]

    total_items = len(filtered)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    normalized_page = min(max(page, 1), total_pages)
    start_index = (normalized_page - 1) * page_size
    items = filtered[start_index : start_index + page_size]

    return UserDirectoryPage(
        items=items,
        page=normalized_page,
        total_pages=total_pages,
        total_items=total_items,
        filter_key=filter_key,
    )


async def build_user_profile(
    session: AsyncSession,
    *,
    user_id: int,
    now: datetime | None = None,
    history_limit: int = 10,
) -> UserProfileSnapshot | None:
    current_time = ensure_aware_utc(now or utcnow())
    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        return None

    payment_repository = PaymentRepository(session)
    subscription_repository = SubscriptionRepository(session)
    active_subscriptions = await subscription_repository.list_current_for_user(
        user.id,
        at_time=current_time,
    )
    recent_subscriptions = await subscription_repository.list_history_for_user(
        user.id,
        limit=history_limit,
    )
    recent_payments = await payment_repository.list_paid_for_user(
        user.id,
        limit=history_limit,
    )
    audit_entries = await AuditLogRepository(session).list_for_target_user(
        user.id,
        limit=history_limit,
    )
    total_paid = await payment_repository.sum_paid_for_user(user.id)

    latest_expires_at = recent_subscriptions[0].expires_at if recent_subscriptions else None
    latest_expires_at = (
        ensure_aware_utc(latest_expires_at) if latest_expires_at is not None else None
    )
    status = describe_user_status(
        user,
        has_active_subscription=bool(active_subscriptions),
        latest_expires_at=latest_expires_at,
        paid_count=len(recent_payments),
    )

    return UserProfileSnapshot(
        user=user,
        status=status,
        latest_expires_at=latest_expires_at,
        total_paid=total_paid,
        active_subscriptions=active_subscriptions,
        recent_subscriptions=recent_subscriptions,
        recent_payments=recent_payments,
        audit_entries=audit_entries,
    )


async def list_active_tariffs(session: AsyncSession) -> list[Tariff]:
    result = await session.execute(
        select(Tariff)
        .options()
        .where(Tariff.is_active.is_(True))
        .where(Tariff.archived_at.is_(None))
        .order_by(Tariff.sort_order.asc(), Tariff.id.asc())
    )
    return list(result.scalars())


async def list_active_channels(session: AsyncSession) -> list[Channel]:
    result = await session.execute(
        select(Channel)
        .where(Channel.is_active.is_(True))
        .order_by(Channel.title.asc(), Channel.id.asc())
    )
    return list(result.scalars())


def describe_user_status(
    user: User,
    *,
    has_active_subscription: bool,
    latest_expires_at: datetime | None,
    paid_count: int,
) -> str:
    if user.is_blocked:
        return "заблокирован"
    if has_active_subscription:
        return "активен"
    if latest_expires_at is not None:
        return "истёк"
    if paid_count == 0:
        return "не покупал"
    return "без активной подписки"


def filter_label(filter_key: str) -> str:
    if filter_key in USER_FILTER_LABELS:
        return USER_FILTER_LABELS[filter_key]
    if filter_key.startswith("tariff-"):
        return f"Тариф #{filter_key.removeprefix('tariff-')}"
    if filter_key.startswith("channel-"):
        return f"Канал #{filter_key.removeprefix('channel-')}"
    return filter_key


def _matches_filter(
    entry: UserDirectoryEntry,
    *,
    filter_key: str,
    current_time: datetime,
    tariff_user_ids: dict[int, set[int]],
    channel_user_ids: dict[int, set[int]],
) -> bool:
    if filter_key == "all":
        return True
    if filter_key == "active":
        return entry.has_active_subscription
    if filter_key == "expired":
        return (
            not entry.has_active_subscription
            and entry.latest_expires_at is not None
            and entry.latest_expires_at <= current_time
        )
    if filter_key == "never_paid":
        return entry.paid_count == 0
    if filter_key == "blocked":
        return entry.user.is_blocked
    if filter_key == "stars":
        return entry.has_paid_stars
    if filter_key == "crypto":
        return entry.has_paid_crypto
    if filter_key.startswith("tariff-"):
        tariff_id = int(filter_key.removeprefix("tariff-"))
        return entry.user.id in tariff_user_ids.get(tariff_id, set())
    if filter_key.startswith("channel-"):
        channel_id = int(filter_key.removeprefix("channel-"))
        return entry.user.id in channel_user_ids.get(channel_id, set())
    return True
