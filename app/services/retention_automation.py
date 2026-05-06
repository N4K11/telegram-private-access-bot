from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db.models import AuditLog, Channel, InviteLink, Payment, Subscription, Tariff, User
from app.services.audit import write_audit_log
from app.services.lifecycle_campaign_rules import (
    get_retention_campaign_rule,
    select_lifecycle_campaign_offers,
)
from app.services.offer_engine import build_offer_engine_snapshot, get_product_offer_lane
from app.services.offer_messaging import (
    append_offer_block,
    build_recommendations_from_tariffs,
    merge_unique_offers,
)
from app.services.product_service import build_product_catalog
from app.services.texts import render_text
from app.utils.datetime import ensure_aware_utc, format_datetime, utcnow
from app.utils.encoding import safe_ui_text

SEGMENT_FIRST_PAYMENT_FOLLOW_UP = "first_payment_follow_up"
SEGMENT_PENDING_JOIN = "never_joined_after_payment"
SEGMENT_EXPIRED_RECENTLY = "expired_recently"
SEGMENT_INACTIVE_PAID = "inactive_paid"
SEGMENT_LOST_AFTER_TRIAL = "lost_after_trial"

SEGMENT_ORDER = (
    SEGMENT_FIRST_PAYMENT_FOLLOW_UP,
    SEGMENT_PENDING_JOIN,
    SEGMENT_EXPIRED_RECENTLY,
    SEGMENT_INACTIVE_PAID,
    SEGMENT_LOST_AFTER_TRIAL,
)

SEGMENT_LABELS = {
    SEGMENT_FIRST_PAYMENT_FOLLOW_UP: "Первая оплата: follow-up",
    SEGMENT_PENDING_JOIN: "Оплатили, но не вошли",
    SEGMENT_EXPIRED_RECENTLY: "Недавно истекли",
    SEGMENT_INACTIVE_PAID: "Неактивные платящие",
    SEGMENT_LOST_AFTER_TRIAL: "Потеряны после trial",
}

SEGMENT_ACTIONS = {
    SEGMENT_FIRST_PAYMENT_FOLLOW_UP: "retention_first_payment_follow_up_sent",
    SEGMENT_PENDING_JOIN: "retention_pending_join_sent",
    SEGMENT_EXPIRED_RECENTLY: "retention_win_back_sent",
    SEGMENT_INACTIVE_PAID: "retention_inactive_paid_sent",
    SEGMENT_LOST_AFTER_TRIAL: "retention_lost_after_trial_sent",
}

SEGMENT_TEMPLATE_KEYS = {
    SEGMENT_FIRST_PAYMENT_FOLLOW_UP: "retention_first_payment_follow_up",
    SEGMENT_PENDING_JOIN: "retention_pending_join",
    SEGMENT_EXPIRED_RECENTLY: "retention_win_back",
    SEGMENT_INACTIVE_PAID: "retention_inactive_paid",
    SEGMENT_LOST_AFTER_TRIAL: "retention_lost_after_trial",
}

SEGMENT_DEDUPE_WINDOWS = {
    SEGMENT_FIRST_PAYMENT_FOLLOW_UP: timedelta(days=3),
    SEGMENT_PENDING_JOIN: timedelta(hours=24),
    SEGMENT_EXPIRED_RECENTLY: timedelta(days=7),
    SEGMENT_INACTIVE_PAID: timedelta(days=14),
    SEGMENT_LOST_AFTER_TRIAL: timedelta(days=14),
}

FIRST_PAYMENT_LOOKBACK = timedelta(hours=24)
PENDING_JOIN_LOOKBACK = timedelta(hours=48)
RECENT_EXPIRED_MIN_AGE = timedelta(hours=6)
RECENT_EXPIRED_MAX_AGE = timedelta(days=7)
INACTIVE_PAID_MIN_AGE = timedelta(days=7)
INACTIVE_PAID_MAX_AGE = timedelta(days=30)
LOST_AFTER_TRIAL_MAX_AGE = timedelta(days=14)


@dataclass(slots=True)
class RetentionCandidate:
    segment: str
    user_id: int
    telegram_id: int
    channel_id: int | None = None
    channel_name: str | None = None
    expires_at: datetime | None = None
    latest_paid_at: datetime | None = None
    days_since_expired: int | None = None


@dataclass(slots=True)
class RetentionCycleResult:
    sent_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    segment_sent_counts: dict[str, int] = field(default_factory=dict)
    segment_candidate_counts: dict[str, int] = field(default_factory=dict)

    @property
    def processed_count(self) -> int:
        return self.sent_count + self.failed_count + self.skipped_count

    @property
    def has_work(self) -> bool:
        return self.sent_count > 0


@dataclass(slots=True)
class RetentionOfferPlan:
    primary_offer: Any | None
    cross_sell_offers: tuple[Any, ...] = ()
    bundle_offers: tuple[Any, ...] = ()
    heading: str = ""
    extra_offer_limit: int = 0
    campaign_variant: str | None = None
    offer_strategy: str | None = None
    primary_source: str | None = None
    campaign_rule_key: str | None = None
    campaign_rule_label: str | None = None
    campaign_family: str | None = None
    campaign_wave_mode: str | None = None
    campaign_wave_label: str | None = None
    extras_label: str | None = None


@dataclass(slots=True)
class RetentionSegmentSnapshot:
    segment: str
    label: str
    candidate_count: int
    recent_sent_count: int
    dedupe_window_hours: int


def retention_segment_label(segment: str) -> str:
    return SEGMENT_LABELS.get(segment, segment)


async def process_retention_messages(
    session: AsyncSession,
    bot: Bot | Any,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> RetentionCycleResult:
    processed_at = ensure_aware_utc(now or utcnow())
    candidates, candidate_counts = await _collect_candidates(session, processed_at)
    result = RetentionCycleResult(segment_candidate_counts=candidate_counts)
    active_tariffs = list(
        (
            await session.execute(
                select(Tariff)
                .options(selectinload(Tariff.channel))
                .where(Tariff.is_active.is_(True))
            )
        ).scalars()
    )

    for candidate in candidates:
        offer_context = _build_candidate_offer_context(active_tariffs, candidate, now=processed_at)
        offer_plan = _build_candidate_offer_plan(candidate, offer_context)
        try:
            text = await render_text(
                session,
                SEGMENT_TEMPLATE_KEYS[candidate.segment],
                **_build_message_context(candidate, settings=settings),
            )
            text = _append_candidate_offer_block(
                text,
                settings=settings,
                offer_plan=offer_plan,
            )
            await bot.send_message(candidate.telegram_id, text)
        except Exception:
            result.failed_count += 1
            continue

        audit_payload = {
            "segment": candidate.segment,
            "channel_id": candidate.channel_id,
            "channel_name": candidate.channel_name,
            "expires_at": candidate.expires_at.isoformat()
            if candidate.expires_at is not None
            else None,
            "latest_paid_at": candidate.latest_paid_at.isoformat()
            if candidate.latest_paid_at is not None
            else None,
            "days_since_expired": candidate.days_since_expired,
        }
        if offer_plan is not None and offer_plan.campaign_variant is not None:
            audit_payload["campaign_variant"] = offer_plan.campaign_variant
        if offer_plan is not None and offer_plan.offer_strategy is not None:
            audit_payload["offer_strategy"] = offer_plan.offer_strategy
        if offer_plan is not None:
            audit_payload["cross_sell_count"] = len(offer_plan.cross_sell_offers)
            audit_payload["bundle_count"] = len(offer_plan.bundle_offers)
            audit_payload["limited_primary"] = offer_plan.primary_source == "limited"
            audit_payload["bundle_primary"] = offer_plan.primary_source == "bundle"
            audit_payload["primary_offer_source"] = offer_plan.primary_source
            audit_payload["campaign_rule_key"] = offer_plan.campaign_rule_key
            audit_payload["campaign_rule_label"] = offer_plan.campaign_rule_label
            audit_payload["campaign_family"] = offer_plan.campaign_family
            audit_payload["campaign_wave_mode"] = offer_plan.campaign_wave_mode
            audit_payload["campaign_wave_label"] = offer_plan.campaign_wave_label
        if offer_plan is not None and offer_plan.primary_offer is not None:
            audit_payload.update(
                {
                    "recommended_tariff_id": offer_plan.primary_offer.tariff_id,
                    "recommended_channel_id": offer_plan.primary_offer.channel_id,
                    "recommended_reason_code": offer_plan.primary_offer.reason_code,
                    "recommended_reason_label": offer_plan.primary_offer.reason_label,
                }
            )
        await write_audit_log(
            session,
            action=SEGMENT_ACTIONS[candidate.segment],
            target_user_id=candidate.user_id,
            payload=audit_payload,
        )
        result.sent_count += 1
        result.segment_sent_counts[candidate.segment] = (
            result.segment_sent_counts.get(candidate.segment, 0) + 1
        )

    if result.sent_count:
        await session.commit()
    return result


async def build_retention_segment_snapshots(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> tuple[RetentionSegmentSnapshot, ...]:
    snapshot_time = ensure_aware_utc(now or utcnow())
    _candidates, candidate_counts = await _collect_candidates(session, snapshot_time)
    recent_sent_counts = await _load_recent_segment_sent_counts(session, snapshot_time)
    return tuple(
        RetentionSegmentSnapshot(
            segment=segment,
            label=retention_segment_label(segment),
            candidate_count=candidate_counts.get(segment, 0),
            recent_sent_count=recent_sent_counts.get(segment, 0),
            dedupe_window_hours=int(SEGMENT_DEDUPE_WINDOWS[segment].total_seconds() // 3600),
        )
        for segment in SEGMENT_ORDER
    )


async def _load_recent_segment_sent_counts(
    session: AsyncSession,
    now: datetime,
) -> dict[str, int]:
    rows = list(
        (
            await session.execute(
                select(AuditLog.target_user_id, AuditLog.action, AuditLog.created_at)
                .where(AuditLog.action.in_(tuple(SEGMENT_ACTIONS.values())))
                .where(AuditLog.target_user_id.is_not(None))
            )
        ).all()
    )
    sent_by_segment: dict[str, set[int]] = defaultdict(set)
    action_to_segment = {action: segment for segment, action in SEGMENT_ACTIONS.items()}
    for user_id, action, created_at in rows:
        segment = action_to_segment.get(str(action))
        if segment is None or user_id is None:
            continue
        if ensure_aware_utc(created_at) < now - SEGMENT_DEDUPE_WINDOWS[segment]:
            continue
        sent_by_segment[segment].add(int(user_id))
    return {segment: len(user_ids) for segment, user_ids in sent_by_segment.items()}


async def _collect_candidates(
    session: AsyncSession,
    now: datetime,
) -> tuple[list[RetentionCandidate], dict[str, int]]:
    users = list((await session.execute(select(User).order_by(User.id.asc()))).scalars())
    tariffs = list((await session.execute(select(Tariff))).scalars())
    tariff_map = {int(tariff.id): tariff for tariff in tariffs}
    channel_titles = {
        int(channel_id): safe_ui_text(title, f"Канал #{channel_id}")
        for channel_id, title in (await session.execute(select(Channel.id, Channel.title))).all()
    }

    payment_rows = list(
        (
            await session.execute(
                select(
                    Payment.user_id,
                    Payment.tariff_id,
                    Payment.channel_id,
                    Payment.paid_at,
                    Payment.id,
                )
                .where(Payment.status == "paid")
                .where(Payment.paid_at.is_not(None))
                .order_by(Payment.user_id.asc(), Payment.paid_at.desc(), Payment.id.desc())
            )
        ).all()
    )
    payments_by_user: dict[
        int,
        list[tuple[int | None, int | None, datetime, int]],
    ] = defaultdict(list)
    for user_id, tariff_id, channel_id, paid_at, payment_id in payment_rows:
        if paid_at is None:
            continue
        payments_by_user[int(user_id)].append(
            (
                int(tariff_id) if tariff_id is not None else None,
                int(channel_id) if channel_id is not None else None,
                ensure_aware_utc(paid_at),
                int(payment_id),
            )
        )

    subscription_rows = list(
        (
            await session.execute(
                select(
                    Subscription.user_id,
                    Subscription.tariff_id,
                    Subscription.channel_id,
                    Subscription.status,
                    Subscription.revoked_at,
                    Subscription.expires_at,
                    Subscription.id,
                )
                .order_by(
                    Subscription.user_id.asc(),
                    Subscription.expires_at.desc(),
                    Subscription.id.desc(),
                )
            )
        ).all()
    )
    active_subscription_by_user: dict[int, tuple[int | None, int, datetime]] = {}
    latest_subscription_by_user: dict[int, tuple[int | None, int, datetime]] = {}
    for (
        user_id,
        tariff_id,
        channel_id,
        status,
        revoked_at,
        expires_at,
        _subscription_id,
    ) in subscription_rows:
        aware_expires_at = ensure_aware_utc(expires_at)
        user_key = int(user_id)
        latest_subscription_by_user.setdefault(
            user_key,
            (
                int(tariff_id) if tariff_id is not None else None,
                int(channel_id),
                aware_expires_at,
            ),
        )
        if (
            status == "active"
            and revoked_at is None
            and aware_expires_at > now
            and user_key not in active_subscription_by_user
        ):
            active_subscription_by_user[user_key] = (
                int(tariff_id) if tariff_id is not None else None,
                int(channel_id),
                aware_expires_at,
            )

    invite_rows = list(
        (
            await session.execute(
                select(
                    InviteLink.user_id,
                    InviteLink.channel_id,
                    InviteLink.expire_at,
                    InviteLink.is_revoked,
                )
            )
        ).all()
    )
    valid_invites_by_user: dict[int, set[int]] = defaultdict(set)
    for user_id, channel_id, expire_at, is_revoked in invite_rows:
        if is_revoked:
            continue
        if expire_at is not None and ensure_aware_utc(expire_at) <= now:
            continue
        valid_invites_by_user[int(user_id)].add(int(channel_id))

    audit_rows = list(
        (
            await session.execute(
                select(AuditLog.target_user_id, AuditLog.action, AuditLog.created_at)
                .where(AuditLog.action.in_(tuple(SEGMENT_ACTIONS.values())))
            )
        ).all()
    )
    latest_retention_audit: dict[int, dict[str, datetime]] = defaultdict(dict)
    for user_id, action, created_at in audit_rows:
        if user_id is None:
            continue
        latest_retention_audit[int(user_id)][str(action)] = ensure_aware_utc(created_at)

    candidates: list[RetentionCandidate] = []
    candidate_counts: dict[str, int] = defaultdict(int)

    for user in users:
        if user.is_blocked or user.is_admin or user.role != "user":
            continue

        user_id = int(user.id)
        user_payments = payments_by_user.get(user_id, [])
        paid_count = len(user_payments)
        latest_paid = user_payments[0] if user_payments else None
        active_subscription = active_subscription_by_user.get(user_id)
        latest_subscription = latest_subscription_by_user.get(user_id)
        retention_audit = latest_retention_audit.get(user_id, {})

        if latest_paid is not None and paid_count == 1:
            latest_paid_at = latest_paid[2]
            if latest_paid_at >= now - FIRST_PAYMENT_LOOKBACK and not _is_deduped(
                retention_audit,
                SEGMENT_FIRST_PAYMENT_FOLLOW_UP,
                now,
            ):
                candidates.append(
                    _build_candidate(
                        user=user,
                        segment=SEGMENT_FIRST_PAYMENT_FOLLOW_UP,
                        channel_id=latest_paid[1],
                        channel_titles=channel_titles,
                        expires_at=(
                            active_subscription[2]
                            if active_subscription is not None
                            else None
                        ),
                        latest_paid_at=latest_paid_at,
                    )
                )
                candidate_counts[SEGMENT_FIRST_PAYMENT_FOLLOW_UP] += 1

        if active_subscription is not None and latest_paid is not None:
            latest_paid_at = latest_paid[2]
            if (
                latest_paid_at >= now - PENDING_JOIN_LOOKBACK
                and active_subscription[1] in valid_invites_by_user.get(user_id, set())
                and not _is_deduped(retention_audit, SEGMENT_PENDING_JOIN, now)
            ):
                candidates.append(
                    _build_candidate(
                        user=user,
                        segment=SEGMENT_PENDING_JOIN,
                        channel_id=active_subscription[1],
                        channel_titles=channel_titles,
                        expires_at=active_subscription[2],
                        latest_paid_at=latest_paid_at,
                    )
                )
                candidate_counts[SEGMENT_PENDING_JOIN] += 1

        if active_subscription is not None or latest_subscription is None:
            continue

        latest_tariff_id, latest_channel_id, latest_expires_at = latest_subscription
        expired_delta = now - latest_expires_at
        if expired_delta < RECENT_EXPIRED_MIN_AGE:
            continue

        days_since_expired = max(int(expired_delta.total_seconds() // 86400), 0)
        latest_tariff = (
            tariff_map.get(latest_tariff_id)
            if latest_tariff_id is not None
            else None
        )
        latest_paid_at = latest_paid[2] if latest_paid is not None else None
        is_trial_loss = bool(latest_tariff and latest_tariff.is_trial)

        if is_trial_loss and expired_delta <= LOST_AFTER_TRIAL_MAX_AGE:
            if not _is_deduped(
                retention_audit,
                SEGMENT_LOST_AFTER_TRIAL,
                now,
            ):
                candidates.append(
                    _build_candidate(
                        user=user,
                        segment=SEGMENT_LOST_AFTER_TRIAL,
                        channel_id=latest_channel_id,
                        channel_titles=channel_titles,
                        expires_at=latest_expires_at,
                        latest_paid_at=latest_paid_at,
                        days_since_expired=days_since_expired,
                    )
                )
                candidate_counts[SEGMENT_LOST_AFTER_TRIAL] += 1
            continue

        if expired_delta <= RECENT_EXPIRED_MAX_AGE and not _is_deduped(
            retention_audit,
            SEGMENT_EXPIRED_RECENTLY,
            now,
        ):
            candidates.append(
                _build_candidate(
                    user=user,
                    segment=SEGMENT_EXPIRED_RECENTLY,
                    channel_id=latest_channel_id,
                    channel_titles=channel_titles,
                    expires_at=latest_expires_at,
                    latest_paid_at=latest_paid_at,
                    days_since_expired=days_since_expired,
                )
            )
            candidate_counts[SEGMENT_EXPIRED_RECENTLY] += 1
            continue

        if (
            paid_count > 0
            and expired_delta >= INACTIVE_PAID_MIN_AGE
            and expired_delta <= INACTIVE_PAID_MAX_AGE
            and not _is_deduped(retention_audit, SEGMENT_INACTIVE_PAID, now)
        ):
            candidates.append(
                _build_candidate(
                    user=user,
                    segment=SEGMENT_INACTIVE_PAID,
                    channel_id=latest_channel_id,
                    channel_titles=channel_titles,
                    expires_at=latest_expires_at,
                    latest_paid_at=latest_paid_at,
                    days_since_expired=days_since_expired,
                )
            )
            candidate_counts[SEGMENT_INACTIVE_PAID] += 1

    candidates.sort(key=lambda item: (item.telegram_id, item.segment))
    return candidates, dict(candidate_counts)


def _is_deduped(audit_state: dict[str, datetime], segment: str, now: datetime) -> bool:
    sent_at = audit_state.get(SEGMENT_ACTIONS[segment])
    if sent_at is None:
        return False
    return sent_at >= now - SEGMENT_DEDUPE_WINDOWS[segment]


def _build_candidate(
    *,
    user: User,
    segment: str,
    channel_id: int | None,
    channel_titles: dict[int, str],
    expires_at: datetime | None,
    latest_paid_at: datetime | None,
    days_since_expired: int | None = None,
) -> RetentionCandidate:
    return RetentionCandidate(
        segment=segment,
        user_id=int(user.id),
        telegram_id=int(user.telegram_id),
        channel_id=channel_id,
        channel_name=channel_titles.get(channel_id) if channel_id is not None else None,
        expires_at=expires_at,
        latest_paid_at=latest_paid_at,
        days_since_expired=days_since_expired,
    )


def _build_message_context(
    candidate: RetentionCandidate,
    *,
    settings: Settings,
) -> dict[str, object]:
    buy_payload = (
        f"buy_{candidate.channel_id}"
        if candidate.channel_id is not None
        else "buy"
    )
    tariffs_payload = (
        f"tariffs_{candidate.channel_id}" if candidate.channel_id is not None else "tariffs"
    )
    buy_link = (
        settings.bot_start_link(buy_payload)
        or settings.bot_start_link("buy")
        or ""
    )
    tariffs_link = (
        settings.bot_start_link(tariffs_payload)
        or settings.bot_start_link("tariffs")
        or ""
    )
    link_link = settings.bot_start_link("link") or ""
    support_link = settings.bot_start_link("help") or ""
    return {
        "channel_name": safe_ui_text(candidate.channel_name, "каналу"),
        "expires_at": format_datetime(candidate.expires_at, settings.timezone)
        if candidate.expires_at is not None
        else "—",
        "days_since_expired": candidate.days_since_expired or 0,
        "buy_link": buy_link,
        "tariffs_link": tariffs_link,
        "link_link": link_link,
        "support_link": support_link,
        "latest_paid_at": format_datetime(candidate.latest_paid_at, settings.timezone)
        if candidate.latest_paid_at is not None
        else "—",
    }



@dataclass(slots=True)
class RetentionOfferContext:
    recommendations: Any | None
    offer_engine: Any | None


def _build_candidate_offer_context(
    tariffs: list[Tariff],
    candidate: RetentionCandidate,
    *,
    now: datetime,
) -> RetentionOfferContext:
    primary_channel_id = candidate.channel_id
    if primary_channel_id is None:
        return RetentionOfferContext(recommendations=None, offer_engine=None)
    active_channel_ids: tuple[int, ...] = ()
    if candidate.segment in (SEGMENT_FIRST_PAYMENT_FOLLOW_UP, SEGMENT_PENDING_JOIN):
        active_channel_ids = (primary_channel_id,)
    recommendations = build_recommendations_from_tariffs(
        tariffs,
        primary_channel_id=primary_channel_id,
        active_channel_ids=active_channel_ids,
    )
    offer_engine = build_offer_engine_snapshot(
        build_product_catalog(tariffs),
        primary_channel_id=primary_channel_id,
        now=now,
    )
    return RetentionOfferContext(
        recommendations=recommendations,
        offer_engine=offer_engine,
    )


def _pick_limited_offer(
    snapshot,
    *,
    preferred_channel_id: int | None = None,
    exclude_channel_ids: tuple[int, ...] = (),
):
    if snapshot is None:
        return None
    excluded = {int(item) for item in exclude_channel_ids}
    if preferred_channel_id is not None and preferred_channel_id not in excluded:
        lane = get_product_offer_lane(snapshot, preferred_channel_id)
        if lane is not None and lane.limited_offer is not None:
            return lane.limited_offer
    for offer in snapshot.limited_offers:
        if int(offer.channel_id) in excluded:
            continue
        return offer
    return None


def _pick_bundle_offer(
    snapshot,
    *,
    preferred_channel_id: int | None = None,
    exclude_channel_ids: tuple[int, ...] = (),
):
    if snapshot is None:
        return None
    excluded = {int(item) for item in exclude_channel_ids}
    if preferred_channel_id is not None and preferred_channel_id not in excluded:
        lane = get_product_offer_lane(snapshot, preferred_channel_id)
        if lane is not None and lane.bundle_offer is not None:
            return lane.bundle_offer
    for offer in snapshot.bundle_offers:
        if int(offer.channel_id) in excluded:
            continue
        return offer
    return None


def _filter_cross_sell_offers(
    recommendations,
    *,
    exclude_tariff_ids: tuple[int, ...] = (),
    exclude_channel_ids: tuple[int, ...] = (),
) -> tuple[Any, ...]:
    if recommendations is None:
        return ()
    excluded_tariffs = {int(item) for item in exclude_tariff_ids}
    excluded_channels = {int(item) for item in exclude_channel_ids}
    result: list[Any] = []
    for offer in recommendations.cross_sell_offers:
        if int(offer.tariff_id) in excluded_tariffs:
            continue
        if int(offer.channel_id) in excluded_channels:
            continue
        result.append(offer)
    return tuple(result)


def _build_candidate_offer_plan(
    candidate: RetentionCandidate,
    context: RetentionOfferContext,
) -> RetentionOfferPlan | None:
    recommendations = context.recommendations
    offer_engine = context.offer_engine
    if recommendations is None:
        return None
    if candidate.segment in (SEGMENT_FIRST_PAYMENT_FOLLOW_UP, SEGMENT_PENDING_JOIN):
        return None

    rule = get_retention_campaign_rule(candidate.segment)
    if rule is None:
        return None

    excluded_current_channel = (candidate.channel_id,) if candidate.channel_id is not None else ()
    if candidate.segment == SEGMENT_LOST_AFTER_TRIAL:
        recommended_offer = None
        limited_offer = _pick_limited_offer(
            offer_engine,
            exclude_channel_ids=excluded_current_channel,
        )
        bundle_offer = _pick_bundle_offer(
            offer_engine,
            exclude_channel_ids=excluded_current_channel,
        )
        cross_sell_pool = _filter_cross_sell_offers(
            recommendations,
            exclude_channel_ids=excluded_current_channel,
        )
    elif candidate.segment in (SEGMENT_EXPIRED_RECENTLY, SEGMENT_INACTIVE_PAID):
        recommended_offer = recommendations.primary_offer
        limited_offer = _pick_limited_offer(
            offer_engine,
            preferred_channel_id=candidate.channel_id,
        )
        bundle_offer = _pick_bundle_offer(
            offer_engine,
            preferred_channel_id=candidate.channel_id,
        )
        cross_sell_pool = _filter_cross_sell_offers(
            recommendations,
            exclude_tariff_ids=(
                (recommended_offer.tariff_id,) if recommended_offer is not None else ()
            ),
            exclude_channel_ids=(
                (recommended_offer.channel_id,) if recommended_offer is not None else ()
            ),
        )
    else:
        return None

    selection = select_lifecycle_campaign_offers(
        rule,
        recommended_offer=recommended_offer,
        limited_offer=limited_offer,
        bundle_offer=bundle_offer,
        cross_sell_offers=cross_sell_pool,
    )
    if selection.primary_offer is None:
        return None
    cross_sell_offers = tuple(
        offer
        for offer in selection.cross_sell_offers
        if int(offer.channel_id) != int(selection.primary_offer.channel_id)
    )
    return RetentionOfferPlan(
        primary_offer=selection.primary_offer,
        cross_sell_offers=cross_sell_offers,
        bundle_offers=selection.bundle_offers,
        heading=selection.heading,
        extra_offer_limit=len(selection.bundle_offers) + len(cross_sell_offers),
        campaign_variant=selection.campaign_variant,
        offer_strategy=selection.offer_strategy,
        primary_source=selection.primary_source,
        campaign_rule_key=selection.campaign_rule_key,
        campaign_rule_label=selection.campaign_rule_label,
        campaign_family=selection.campaign_family,
        campaign_wave_mode=selection.campaign_wave_mode,
        campaign_wave_label=selection.campaign_wave_label,
        extras_label=selection.extras_label,
    )


def _append_candidate_offer_block(
    text: str,
    *,
    settings: Settings,
    offer_plan: RetentionOfferPlan | None,
) -> str:
    if offer_plan is None or offer_plan.primary_offer is None:
        return text
    extras = merge_unique_offers(
        offer_plan.bundle_offers,
        offer_plan.cross_sell_offers,
        exclude_tariff_ids=(offer_plan.primary_offer.tariff_id,),
    )
    return append_offer_block(
        text,
        settings=settings,
        primary_offer=offer_plan.primary_offer,
        heading=offer_plan.heading,
        cross_sell_offers=extras,
        cross_sell_limit=offer_plan.extra_offer_limit,
        extras_label=offer_plan.extras_label,
    )
