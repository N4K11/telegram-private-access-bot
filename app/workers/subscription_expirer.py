from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db.models import Subscription, Tariff
from app.db.repositories.subscriptions import SubscriptionRepository
from app.services.audit import write_audit_log
from app.services.lifecycle_campaign_rules import (
    get_subscription_campaign_rule,
    select_lifecycle_campaign_offers,
)
from app.services.multi_channel_access_service import ProductAccessEntry
from app.services.observability import EVENT_SUBSCRIPTION_REVOKED
from app.services.offer_engine import build_offer_engine_snapshot, get_product_offer_lane
from app.services.offer_messaging import (
    append_offer_block,
    build_recommendations_from_tariffs,
    merge_unique_offers,
)
from app.services.product_service import build_product_catalog
from app.services.texts import render_text
from app.utils.datetime import ensure_aware_utc, format_datetime, utcnow

logger = logging.getLogger(__name__)

MAX_REMOVE_RETRIES = 3
ABSENT_MEMBER_FRAGMENTS = (
    "user not participant",
    "participant_id_invalid",
    "user not found",
    "chat not found",
    "member not found",
)


@dataclass(slots=True)
class SubscriptionOfferPlan:
    primary_offer: Any | None
    cross_sell_offers: tuple[Any, ...] = ()
    bundle_offers: tuple[Any, ...] = ()
    heading: str = ""
    extra_offer_limit: int = 0
    offer_strategy: str | None = None
    primary_source: str | None = None
    campaign_rule_key: str | None = None
    campaign_rule_label: str | None = None
    campaign_family: str | None = None
    campaign_wave_mode: str | None = None
    campaign_wave_label: str | None = None
    extras_label: str | None = None


@dataclass(slots=True)
class SubscriptionExpirationProcessingResult:
    warning_3d_count: int = 0
    warning_1d_count: int = 0
    expired_notice_count: int = 0
    revoked_count: int = 0

    @property
    def processed_count(self) -> int:
        return (
            self.warning_3d_count
            + self.warning_1d_count
            + self.expired_notice_count
            + self.revoked_count
        )

    @property
    def has_work(self) -> bool:
        return self.processed_count > 0


async def remove_user_from_channel(
    bot: Bot | Any,
    *,
    channel_chat_id: int,
    telegram_user_id: int,
    now: datetime | None = None,
    sleep_func: Callable[[float], Awaitable[None]] = asyncio.sleep,
    max_attempts: int = MAX_REMOVE_RETRIES,
) -> None:
    ban_until = ensure_aware_utc(now or utcnow())

    for attempt in range(1, max_attempts + 1):
        try:
            await bot.ban_chat_member(
                chat_id=channel_chat_id,
                user_id=telegram_user_id,
                until_date=ban_until,
            )
            await bot.unban_chat_member(
                chat_id=channel_chat_id,
                user_id=telegram_user_id,
                only_if_banned=True,
            )
            return
        except TelegramRetryAfter as exc:
            if attempt >= max_attempts:
                raise
            retry_after = float(getattr(exc, "retry_after", 0) or 0)
            await sleep_func(retry_after)
        except TelegramBadRequest as exc:
            if _is_absent_member_error(exc):
                return
            raise


async def process_expired_subscriptions(
    session: AsyncSession,
    bot: Bot | Any,
    *,
    now: datetime | None = None,
    batch_limit: int = 100,
    grace_period_hours: int = 6,
    warning_3d_enabled: bool = True,
    warning_1d_enabled: bool = True,
    timezone: str = "UTC",
    settings: Settings | None = None,
) -> SubscriptionExpirationProcessingResult:
    processed_at = ensure_aware_utc(now or utcnow())
    repository = SubscriptionRepository(session)
    result = SubscriptionExpirationProcessingResult()
    has_mutations = False
    active_tariffs = list(
        (
            await session.execute(
                select(Tariff)
                .options(selectinload(Tariff.channel))
                .where(Tariff.is_active.is_(True))
            )
        ).scalars()
    )

    if warning_3d_enabled:
        subscriptions = await repository.list_due_for_warning_3d(
            at_time=processed_at,
            limit=batch_limit,
        )
        for subscription in subscriptions:
            sent = await _send_subscription_message(
                session,
                bot,
                subscription=subscription,
                text_key="subscription_warning_3d",
                timezone=timezone,
                active_tariffs=active_tariffs,
                settings=settings,
                reference_now=processed_at,
            )
            if not sent:
                continue
            subscription.warning_3d_sent_at = processed_at
            result.warning_3d_count += 1
            has_mutations = True
            await write_audit_log(
                session,
                action="subscription_warning_3d_sent",
                target_user_id=subscription.user_id,
                payload={
                    "subscription_id": subscription.id,
                    "tariff_id": subscription.tariff_id,
                    "channel_id": subscription.channel_id,
                    "expires_at": subscription.expires_at.isoformat(),
                    "campaign_variant": "renewal_3d",
                    **_build_subscription_offer_audit_payload(
                        subscription=subscription,
                        active_tariffs=active_tariffs,
                        mode="renewal",
                        reference_now=processed_at,
                    ),
                },
            )

    if warning_1d_enabled:
        subscriptions = await repository.list_due_for_warning_1d(
            at_time=processed_at,
            limit=batch_limit,
        )
        for subscription in subscriptions:
            sent = await _send_subscription_message(
                session,
                bot,
                subscription=subscription,
                text_key="subscription_warning_1d",
                timezone=timezone,
                active_tariffs=active_tariffs,
                settings=settings,
                reference_now=processed_at,
            )
            if not sent:
                continue
            subscription.warning_1d_sent_at = processed_at
            result.warning_1d_count += 1
            has_mutations = True
            await write_audit_log(
                session,
                action="subscription_warning_1d_sent",
                target_user_id=subscription.user_id,
                payload={
                    "subscription_id": subscription.id,
                    "tariff_id": subscription.tariff_id,
                    "channel_id": subscription.channel_id,
                    "expires_at": subscription.expires_at.isoformat(),
                    "campaign_variant": "renewal_1d",
                    **_build_subscription_offer_audit_payload(
                        subscription=subscription,
                        active_tariffs=active_tariffs,
                        mode="renewal",
                        reference_now=processed_at,
                    ),
                },
            )

    expired_subscriptions = await repository.list_due_for_expired_notice(
        at_time=processed_at,
        limit=batch_limit,
    )
    for subscription in expired_subscriptions:
        if subscription.grace_revoke_after is None:
            subscription.grace_revoke_after = processed_at + timedelta(hours=grace_period_hours)
            has_mutations = True

        sent = await _send_subscription_message(
            session,
            bot,
            subscription=subscription,
            text_key="subscription_expired_grace",
            timezone=timezone,
            grace_period_hours=grace_period_hours,
            active_tariffs=active_tariffs,
            settings=settings,
            reference_now=processed_at,
        )
        if not sent:
            continue
        subscription.expired_notice_sent_at = processed_at
        result.expired_notice_count += 1
        has_mutations = True
        await write_audit_log(
            session,
            action="subscription_expired_notice_sent",
            target_user_id=subscription.user_id,
            payload={
                "subscription_id": subscription.id,
                "tariff_id": subscription.tariff_id,
                "channel_id": subscription.channel_id,
                "expired_at": subscription.expires_at.isoformat(),
                "grace_revoke_after": subscription.grace_revoke_after.isoformat()
                if subscription.grace_revoke_after is not None
                else None,
                "campaign_variant": "grace_recovery",
                **_build_subscription_offer_audit_payload(
                    subscription=subscription,
                    active_tariffs=active_tariffs,
                    mode="expired_grace",
                    reference_now=processed_at,
                ),
            },
        )

    revoke_subscriptions = await repository.list_due_for_grace_revoke(
        at_time=processed_at,
        limit=batch_limit,
    )
    for subscription in revoke_subscriptions:
        channel = subscription.channel
        user = subscription.user
        if channel is None or user is None:
            logger.warning(
                "Skipping revoke for subscription %s because relations are missing.",
                subscription.id,
            )
            continue

        try:
            await remove_user_from_channel(
                bot,
                channel_chat_id=channel.telegram_chat_id,
                telegram_user_id=user.telegram_id,
                now=processed_at,
            )
        except Exception:
            logger.exception(
                "Failed to revoke access for subscription %s (user %s, channel %s)",
                subscription.id,
                subscription.user_id,
                subscription.channel_id,
            )
            continue

        subscription.status = "expired"
        subscription.revoked_at = processed_at
        result.revoked_count += 1
        has_mutations = True

        await write_audit_log(
            session,
            action="subscription_expired",
            target_user_id=subscription.user_id,
            payload={
                "subscription_id": subscription.id,
                "tariff_id": subscription.tariff_id,
                "channel_id": subscription.channel_id,
                "expired_at": subscription.expires_at.isoformat(),
                "grace_revoke_after": subscription.grace_revoke_after.isoformat()
                if subscription.grace_revoke_after is not None
                else None,
                "revoked_at": processed_at.isoformat(),
                "campaign_variant": "final_win_back",
                **_build_subscription_offer_audit_payload(
                    subscription=subscription,
                    active_tariffs=active_tariffs,
                    mode="expired_final",
                    reference_now=processed_at,
                ),
            },
        )
        logger.info(
            "Revoked subscription %s for user %s.",
            subscription.id,
            subscription.user_id,
            extra={
                "event_name": EVENT_SUBSCRIPTION_REVOKED,
                "user_id": subscription.user_id,
                "subscription_id": subscription.id,
                "tariff_id": subscription.tariff_id,
                "channel_id": subscription.channel_id,
            },
        )

        try:
            notification_text = await render_text(
                session,
                "subscription_expired",
                channel_name=channel.title,
            )
            offer_plan = _build_subscription_offer_plan(
                subscription=subscription,
                active_tariffs=active_tariffs,
                mode="expired_final",
                reference_now=processed_at,
            )
            if settings is not None and offer_plan.primary_offer is not None:
                extras = merge_unique_offers(
                    offer_plan.bundle_offers,
                    offer_plan.cross_sell_offers,
                    exclude_tariff_ids=(offer_plan.primary_offer.tariff_id,),
                )
                notification_text = append_offer_block(
                    notification_text,
                    settings=settings,
                    primary_offer=offer_plan.primary_offer,
                    heading=offer_plan.heading,
                    cross_sell_offers=extras,
                    cross_sell_limit=offer_plan.extra_offer_limit,
                    extras_label=offer_plan.extras_label,
                )
            await bot.send_message(user.telegram_id, notification_text)
        except Exception:
            logger.exception(
                "Failed to notify user %s about revoked subscription %s",
                user.telegram_id,
                subscription.id,
            )

    if has_mutations:
        await session.commit()

    return result


async def _send_subscription_message(
    session: AsyncSession,
    bot: Bot | Any,
    *,
    subscription: Subscription,
    text_key: str,
    timezone: str,
    grace_period_hours: int | None = None,
    active_tariffs: list[Tariff],
    settings: Settings | None,
    reference_now: datetime,
) -> bool:
    channel = subscription.channel
    user = subscription.user
    if channel is None or user is None:
        logger.warning(
            "Skipping %s for subscription %s because relations are missing.",
            text_key,
            subscription.id,
        )
        return False

    try:
        text = await render_text(
            session,
            text_key,
            channel_name=channel.title,
            expires_at=format_datetime(subscription.expires_at, timezone),
            expired_at=format_datetime(subscription.expires_at, timezone),
            grace_period_hours=grace_period_hours or 0,
        )
        if settings is not None:
            mode = "renewal"
            if text_key == "subscription_expired_grace":
                mode = "expired_grace"
            offer_plan = _build_subscription_offer_plan(
                subscription=subscription,
                active_tariffs=active_tariffs,
                mode=mode,
                reference_now=reference_now,
            )
            if offer_plan.primary_offer is not None:
                extras = merge_unique_offers(
                    offer_plan.bundle_offers,
                    offer_plan.cross_sell_offers,
                    exclude_tariff_ids=(offer_plan.primary_offer.tariff_id,),
                )
                text = append_offer_block(
                    text,
                    settings=settings,
                    primary_offer=offer_plan.primary_offer,
                    heading=offer_plan.heading,
                    cross_sell_offers=extras,
                    cross_sell_limit=offer_plan.extra_offer_limit,
                    extras_label=offer_plan.extras_label,
                )
        await bot.send_message(user.telegram_id, text)
        return True
    except Exception:
        logger.exception(
            "Failed to send %s to user %s for subscription %s",
            text_key,
            user.telegram_id,
            subscription.id,
        )
        return False




def _build_subscription_offer_audit_payload(
    *,
    subscription: Subscription,
    active_tariffs: list[Tariff],
    mode: str,
    reference_now: datetime | None = None,
) -> dict[str, Any]:
    offer_plan = _build_subscription_offer_plan(
        subscription=subscription,
        active_tariffs=active_tariffs,
        mode=mode,
        reference_now=reference_now,
    )
    payload: dict[str, Any] = {
        "offer_mode": mode,
        "offer_strategy": offer_plan.offer_strategy,
        "cross_sell_count": len(offer_plan.cross_sell_offers),
        "bundle_count": len(offer_plan.bundle_offers),
        "limited_primary": offer_plan.primary_source == "limited",
        "bundle_primary": offer_plan.primary_source == "bundle",
        "primary_offer_source": offer_plan.primary_source,
        "campaign_rule_key": offer_plan.campaign_rule_key,
        "campaign_rule_label": offer_plan.campaign_rule_label,
        "campaign_family": offer_plan.campaign_family,
        "campaign_wave_mode": offer_plan.campaign_wave_mode,
        "campaign_wave_label": offer_plan.campaign_wave_label,
    }
    if offer_plan.primary_offer is not None:
        payload.update(
            {
                "recommended_tariff_id": offer_plan.primary_offer.tariff_id,
                "recommended_channel_id": offer_plan.primary_offer.channel_id,
                "recommended_reason_code": offer_plan.primary_offer.reason_code,
                "recommended_reason_label": offer_plan.primary_offer.reason_label,
            }
        )
    return payload


def _build_subscription_offer_context(
    *,
    subscription: Subscription,
    active_tariffs: list[Tariff],
    mode: str,
    reference_now: datetime | None = None,
):
    if subscription.channel_id is None:
        return None, None
    active_channel_ids = (subscription.channel_id,) if mode == "renewal" else ()
    recommendations = build_recommendations_from_tariffs(
        active_tariffs,
        primary_channel_id=subscription.channel_id,
        active_channel_ids=active_channel_ids,
    )
    active_products: tuple[ProductAccessEntry, ...] = ()
    if mode == "renewal":
        channel_title = (
            getattr(getattr(subscription, "channel", None), "title", None)
            or f"????? #{subscription.channel_id}"
        )
        primary_tariff_id = (
            int(subscription.tariff_id) if subscription.tariff_id is not None else None
        )
        tariff_name = getattr(getattr(subscription, "tariff", None), "name", None)
        if tariff_name is None:
            tariff_name = (
                f"????? #{subscription.tariff_id}"
                if subscription.tariff_id is not None
                else channel_title
            )
        tariff_ids = (primary_tariff_id,) if primary_tariff_id is not None else ()
        active_products = (
            ProductAccessEntry(
                channel_id=int(subscription.channel_id),
                channel_title=channel_title,
                latest_expires_at=ensure_aware_utc(subscription.expires_at),
                subscription_count=1,
                tariff_names=(tariff_name,),
                tariff_ids=tariff_ids,
                primary_tariff_id=primary_tariff_id,
                subscription_ids=(int(subscription.id),),
            ),
        )
    offer_engine = build_offer_engine_snapshot(
        build_product_catalog(active_tariffs),
        active_products=active_products,
        primary_channel_id=subscription.channel_id,
        now=reference_now,
    )
    return recommendations, offer_engine


def _pick_limited_offer(
    snapshot,
    *,
    preferred_channel_id: int | None = None,
):
    if snapshot is None:
        return None
    if preferred_channel_id is not None:
        lane = get_product_offer_lane(snapshot, preferred_channel_id)
        if lane is not None and lane.limited_offer is not None:
            return lane.limited_offer
    return next(iter(snapshot.limited_offers), None)


def _pick_bundle_offer(
    snapshot,
    *,
    preferred_channel_id: int | None = None,
):
    if snapshot is None:
        return None
    if preferred_channel_id is not None:
        lane = get_product_offer_lane(snapshot, preferred_channel_id)
        if lane is not None and lane.bundle_offer is not None:
            return lane.bundle_offer
    return next(iter(snapshot.bundle_offers), None)


def _filter_cross_sell_offers(
    recommendations,
    *,
    exclude_tariff_ids: tuple[int, ...] = (),
) -> tuple[Any, ...]:
    if recommendations is None:
        return ()
    excluded = {int(item) for item in exclude_tariff_ids}
    result: list[Any] = []
    for offer in recommendations.cross_sell_offers:
        if int(offer.tariff_id) in excluded:
            continue
        result.append(offer)
    return tuple(result)


def _build_subscription_offer_plan(
    *,
    subscription: Subscription,
    active_tariffs: list[Tariff],
    mode: str,
    reference_now: datetime | None = None,
) -> SubscriptionOfferPlan:
    recommendations, offer_engine = _build_subscription_offer_context(
        subscription=subscription,
        active_tariffs=active_tariffs,
        mode=mode,
        reference_now=reference_now,
    )
    if recommendations is None:
        return SubscriptionOfferPlan(primary_offer=None)

    rule = get_subscription_campaign_rule(mode)
    recommended_offer = (
        recommendations.renewal_offer or recommendations.primary_offer
        if mode == "renewal"
        else recommendations.primary_offer
    )
    limited_offer = _pick_limited_offer(
        offer_engine,
        preferred_channel_id=subscription.channel_id,
    )
    bundle_offer = _pick_bundle_offer(
        offer_engine,
        preferred_channel_id=subscription.channel_id,
    )
    if bundle_offer is not None:
        same_as_current = (
            subscription.tariff_id is not None
            and int(bundle_offer.tariff_id) == int(subscription.tariff_id)
        )
        if same_as_current:
            bundle_offer = None
    cross_sell_offers: tuple[Any, ...] = ()
    if mode != "renewal":
        cross_sell_offers = _filter_cross_sell_offers(
            recommendations,
            exclude_tariff_ids=(
                (recommended_offer.tariff_id,) if recommended_offer is not None else ()
            ),
        )

    selection = select_lifecycle_campaign_offers(
        rule,
        recommended_offer=recommended_offer,
        limited_offer=limited_offer,
        bundle_offer=bundle_offer,
        cross_sell_offers=cross_sell_offers,
    )
    return SubscriptionOfferPlan(
        primary_offer=selection.primary_offer,
        cross_sell_offers=selection.cross_sell_offers,
        bundle_offers=selection.bundle_offers,
        heading=selection.heading,
        extra_offer_limit=selection.extra_offer_limit,
        offer_strategy=selection.offer_strategy,
        primary_source=selection.primary_source,
        campaign_rule_key=selection.campaign_rule_key,
        campaign_rule_label=selection.campaign_rule_label,
        campaign_family=selection.campaign_family,
        campaign_wave_mode=selection.campaign_wave_mode,
        campaign_wave_label=selection.campaign_wave_label,
        extras_label=selection.extras_label,
    )


def _is_absent_member_error(exc: TelegramBadRequest) -> bool:
    message = str(exc).lower()
    return any(fragment in message for fragment in ABSENT_MEMBER_FRAGMENTS)
