# ruff: noqa: E501
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import (
    AuditLog,
    Channel,
    InviteLink,
    Payment,
    PromoCode,
    PromoRedemption,
    Subscription,
    Tariff,
    User,
)
from app.db.session import create_async_engine, create_session_factory
from app.services.analytics import build_analytics_snapshot


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


async def test_analytics_snapshot_includes_source_promo_and_referral_breakdowns(
    session: AsyncSession,
) -> None:
    now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    referrer = User(telegram_id=1001, first_name="Referrer", referral_code="REF1001")
    referred = User(
        telegram_id=1002,
        first_name="Referred",
        referred_by_user_id=1,
        referred_at=now,
        referral_reward_granted_at=now,
    )
    promo_user = User(telegram_id=1003, first_name="Promo")
    session.add_all([referrer, referred, promo_user])
    await session.flush()
    referred.referred_by_user_id = referrer.id
    referrer.pending_referral_reward_days = 7

    channel = Channel(
        telegram_chat_id=-1001234567890,
        title="Main channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add(channel)
    await session.flush()

    tariff = Tariff(
        name="VIP 30",
        price_stars=250,
        duration_days=30,
        sort_order=10,
        is_active=True,
        channel_id=channel.id,
    )
    session.add(tariff)
    await session.flush()

    referred_payment = Payment(
        user_id=referred.id,
        tariff_id=tariff.id,
        channel_id=channel.id,
        amount=250,
        currency="XTR",
        provider="telegram_stars",
        telegram_payment_charge_id="charge-referred",
        provider_payment_charge_id="provider-referred",
        invoice_payload="stars:tariff:1",
        paid_at=now,
        status="paid",
    )
    promo_payment = Payment(
        user_id=promo_user.id,
        tariff_id=tariff.id,
        channel_id=channel.id,
        amount=200,
        currency="XTR",
        provider="telegram_stars",
        telegram_payment_charge_id="charge-promo",
        provider_payment_charge_id="provider-promo",
        invoice_payload="stars:tariff:2",
        paid_at=now,
        status="paid",
    )
    session.add_all([referred_payment, promo_payment])
    await session.flush()

    promo_code = PromoCode(
        code="SPRING20",
        promo_type="discount_percent",
        value=20,
        max_uses=100,
        tariff_id=tariff.id,
        campaign_name="Spring Launch",
        is_active=True,
    )
    session.add(promo_code)
    await session.flush()

    session.add(
        PromoRedemption(
            promo_code_id=promo_code.id,
            user_id=promo_user.id,
            payment_id=promo_payment.id,
            applied_tariff_id=tariff.id,
            amount_before=250,
            amount_after=200,
            status="consumed",
            used_at=now,
        )
    )

    def payload(source: str, *, user_id: int) -> str:
        return json.dumps(
            {
                "source": source,
                "tariff_id": tariff.id,
                "channel_id": channel.id,
                "user_id": user_id,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    session.add_all(
        [
            AuditLog(action="buy_screen_viewed", target_user_id=referred.id, payload=payload("main_menu", user_id=referred.id)),
            AuditLog(action="product_selected", target_user_id=referred.id, payload=payload("main_menu", user_id=referred.id)),
            AuditLog(action="offer_clicked", target_user_id=referred.id, payload=payload("main_menu", user_id=referred.id)),
            AuditLog(action="invoice_created_stars", target_user_id=referred.id, payload=payload("main_menu", user_id=referred.id)),
            AuditLog(action="payment_paid_stars", target_user_id=referred.id, payload=payload("main_menu", user_id=referred.id)),
            AuditLog(action="invite_issued", target_user_id=referred.id, payload=payload("main_menu", user_id=referred.id)),
            AuditLog(action="buy_screen_viewed", target_user_id=promo_user.id, payload=payload("onboarding", user_id=promo_user.id)),
            AuditLog(action="product_selected", target_user_id=promo_user.id, payload=payload("onboarding", user_id=promo_user.id)),
            AuditLog(action="offer_clicked", target_user_id=promo_user.id, payload=payload("onboarding", user_id=promo_user.id)),
            AuditLog(action="invoice_created_stars", target_user_id=promo_user.id, payload=payload("onboarding", user_id=promo_user.id)),
            AuditLog(action="payment_paid_stars", target_user_id=promo_user.id, payload=payload("onboarding", user_id=promo_user.id)),
            AuditLog(
                action="referral_reward_granted",
                actor_user_id=referred.id,
                target_user_id=referrer.id,
                payload=json.dumps(
                    {
                        "referred_user_id": referred.id,
                        "payment_id": referred_payment.id,
                        "reward_days": 7,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ),
        ]
    )
    await session.commit()

    snapshot = await build_analytics_snapshot(session, now=now)

    source_funnel = {item.source: item for item in snapshot.source_funnel}
    product_funnel = {item.channel_id: item for item in snapshot.product_funnel}
    assert snapshot.conversion_offer_clicked == 2
    assert source_funnel["main_menu"].paid_users == 1
    assert source_funnel["main_menu"].offer_clicked_users == 1
    assert source_funnel["onboarding"].invoice_created_users == 1
    assert source_funnel["onboarding"].offer_clicked_users == 1
    assert source_funnel["onboarding"].label == "Onboarding"
    assert product_funnel[channel.id].offer_clicked_users == 2
    source_acquisition = {item.source: item for item in snapshot.source_acquisition}
    assert source_acquisition["main_menu"].acquired_users == 1
    assert source_acquisition["main_menu"].paid_users == 1
    assert source_acquisition["main_menu"].payment_count == 1
    assert source_acquisition["main_menu"].invite_issued_users == 1
    assert source_acquisition["main_menu"].first_paid_revenue_total == 250
    assert source_acquisition["main_menu"].lifetime_revenue_total == 250
    assert source_acquisition["onboarding"].paid_conversion_percent == 100
    assert source_acquisition["onboarding"].repeat_purchase_users == 0
    assert source_acquisition["onboarding"].lifetime_revenue_total == 200

    assert snapshot.promo_attribution.total_payment_count == 1
    assert snapshot.promo_attribution.total_paid_users == 1
    assert snapshot.promo_attribution.gross_revenue_total == 250
    assert snapshot.promo_attribution.revenue_total == 200
    assert snapshot.promo_attribution.discount_total == 50
    assert snapshot.promo_attribution.discount_share_percent == 20
    assert snapshot.promo_attribution.campaigns[0].label == "Spring Launch"
    assert snapshot.promo_attribution.campaigns[0].gross_revenue_total == 250
    assert snapshot.promo_attribution.campaigns[0].discount_total == 50
    assert snapshot.promo_attribution.campaigns[0].repeat_purchase_users == 0
    assert snapshot.promo_attribution.campaigns[0].lifetime_revenue_total == 200

    assert snapshot.referral_attribution.total_referred_users == 1
    assert snapshot.referral_attribution.paid_referred_users == 1
    assert snapshot.referral_attribution.rewarded_referrals_count == 1
    assert snapshot.referral_attribution.pending_reward_days_total == 7
    assert snapshot.referral_attribution.reward_days_issued_total == 7
    assert snapshot.referral_attribution.first_paid_revenue_total == 250
    assert snapshot.referral_attribution.lifetime_referred_revenue_total == 250
    assert snapshot.referral_attribution.suspicious_event_count == 0
    assert snapshot.referral_attribution.top_referrers
    assert snapshot.referral_attribution.top_referrers[0].telegram_id == 1001
    assert snapshot.referral_attribution.top_referrers[0].pending_reward_days == 7
    assert snapshot.referral_attribution.top_referrers[0].reward_days_issued == 7
    assert snapshot.referral_attribution.top_referrers[0].first_paid_revenue_total == 250
    assert snapshot.referral_attribution.top_referrers[0].lifetime_revenue_total == 250
    assert snapshot.referral_attribution.top_referrers[0].repeat_purchase_referred_users == 0



async def test_analytics_snapshot_includes_retention_segments_and_repeat_rate(
    session: AsyncSession,
) -> None:
    now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    users = [
        User(telegram_id=2001, first_name="Fresh"),
        User(telegram_id=2002, first_name="Repeat"),
        User(telegram_id=2003, first_name="Inactive"),
        User(telegram_id=2004, first_name="Trial"),
    ]
    session.add_all(users)
    await session.flush()

    channel = Channel(
        telegram_chat_id=-1002234567890,
        title="CRM channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add(channel)
    await session.flush()

    main_tariff = Tariff(
        name="Main 30",
        price_stars=300,
        duration_days=30,
        sort_order=10,
        is_active=True,
        channel_id=channel.id,
    )
    trial_tariff = Tariff(
        name="Trial 3",
        price_stars=1,
        duration_days=3,
        sort_order=20,
        is_active=True,
        channel_id=channel.id,
        is_trial=True,
    )
    session.add_all([main_tariff, trial_tariff])
    await session.flush()

    fresh_subscription = Subscription(
        user_id=users[0].id,
        tariff_id=main_tariff.id,
        channel_id=channel.id,
        status="active",
        source="purchase",
        started_at=now - timedelta(hours=1),
        expires_at=now + timedelta(days=29),
    )
    repeat_subscription = Subscription(
        user_id=users[1].id,
        tariff_id=main_tariff.id,
        channel_id=channel.id,
        status="expired",
        source="purchase",
        started_at=now - timedelta(days=35),
        expires_at=now - timedelta(days=1),
        revoked_at=now - timedelta(days=1),
    )
    inactive_subscription = Subscription(
        user_id=users[2].id,
        tariff_id=main_tariff.id,
        channel_id=channel.id,
        status="expired",
        source="purchase",
        started_at=now - timedelta(days=40),
        expires_at=now - timedelta(days=10),
        revoked_at=now - timedelta(days=10),
    )
    trial_subscription = Subscription(
        user_id=users[3].id,
        tariff_id=trial_tariff.id,
        channel_id=channel.id,
        status="expired",
        source="purchase",
        started_at=now - timedelta(days=4),
        expires_at=now - timedelta(days=2),
        revoked_at=now - timedelta(days=2),
    )
    session.add_all([
        fresh_subscription,
        repeat_subscription,
        inactive_subscription,
        trial_subscription,
    ])
    await session.flush()

    session.add(
        InviteLink(
            user_id=users[0].id,
            channel_id=channel.id,
            subscription_id=fresh_subscription.id,
            invite_link="https://t.me/+fresh",
            expire_at=now + timedelta(days=1),
            is_revoked=False,
        )
    )

    session.add_all([
        Payment(
            user_id=users[0].id,
            tariff_id=main_tariff.id,
            channel_id=channel.id,
            amount=300,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="crm-fresh-1",
            provider_payment_charge_id="crm-fresh-1",
            invoice_payload="stars:crm:1",
            paid_at=now - timedelta(hours=2),
            status="paid",
        ),
        Payment(
            user_id=users[1].id,
            tariff_id=main_tariff.id,
            channel_id=channel.id,
            amount=300,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="crm-repeat-1",
            provider_payment_charge_id="crm-repeat-1",
            invoice_payload="stars:crm:2",
            paid_at=now - timedelta(days=25),
            status="paid",
        ),
        Payment(
            user_id=users[1].id,
            tariff_id=main_tariff.id,
            channel_id=channel.id,
            amount=300,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="crm-repeat-2",
            provider_payment_charge_id="crm-repeat-2",
            invoice_payload="stars:crm:3",
            paid_at=now - timedelta(days=3),
            status="paid",
        ),
        Payment(
            user_id=users[2].id,
            tariff_id=main_tariff.id,
            channel_id=channel.id,
            amount=300,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="crm-inactive-1",
            provider_payment_charge_id="crm-inactive-1",
            invoice_payload="stars:crm:4",
            paid_at=now - timedelta(days=20),
            status="paid",
        ),
        Payment(
            user_id=users[3].id,
            tariff_id=trial_tariff.id,
            channel_id=channel.id,
            amount=1,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="crm-trial-1",
            provider_payment_charge_id="crm-trial-1",
            invoice_payload="stars:crm:5",
            paid_at=now - timedelta(days=3),
            status="paid",
        ),
    ])
    await session.commit()

    snapshot = await build_analytics_snapshot(session, now=now)
    segment_map = {item.segment: item for item in snapshot.retention_segments}

    assert snapshot.paid_users_total == 4
    assert snapshot.repeat_purchase_users == 1
    assert snapshot.repeat_purchase_rate_percent == 25
    assert segment_map["first_payment_follow_up"].candidate_count == 1
    assert segment_map["never_joined_after_payment"].candidate_count == 1
    assert segment_map["expired_recently"].candidate_count == 1
    assert segment_map["inactive_paid"].candidate_count == 1
    assert segment_map["lost_after_trial"].candidate_count == 1


async def test_analytics_snapshot_includes_lifecycle_queues(
    session: AsyncSession,
) -> None:
    now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    users = [
        User(telegram_id=3001, first_name="Renew 3d"),
        User(telegram_id=3002, first_name="Renew 1d"),
        User(telegram_id=3003, first_name="Grace"),
        User(telegram_id=3004, first_name="Win Back"),
    ]
    session.add_all(users)
    await session.flush()

    channel = Channel(
        telegram_chat_id=-1003234567890,
        title="Lifecycle channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add(channel)
    await session.flush()

    tariff = Tariff(
        name="Lifecycle 30",
        price_stars=199,
        duration_days=30,
        sort_order=10,
        is_active=True,
        channel_id=channel.id,
    )
    session.add(tariff)
    await session.flush()

    session.add_all([
        Subscription(
            user_id=users[0].id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            status="active",
            source="purchase",
            started_at=now - timedelta(days=28),
            expires_at=now + timedelta(days=2),
        ),
        Subscription(
            user_id=users[1].id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            status="active",
            source="purchase",
            started_at=now - timedelta(days=29),
            expires_at=now + timedelta(hours=12),
        ),
        Subscription(
            user_id=users[2].id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            status="active",
            source="purchase",
            started_at=now - timedelta(days=31),
            expires_at=now - timedelta(hours=1),
            expired_notice_sent_at=now - timedelta(minutes=30),
            grace_revoke_after=now + timedelta(hours=5),
        ),
        Subscription(
            user_id=users[3].id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            status="expired",
            source="purchase",
            started_at=now - timedelta(days=35),
            expires_at=now - timedelta(days=2),
            revoked_at=now - timedelta(days=2),
        ),
    ])

    session.add_all([
        Payment(
            user_id=users[0].id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            amount=199,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="life-1",
            provider_payment_charge_id="life-1",
            invoice_payload="stars:life:1",
            paid_at=now - timedelta(days=28),
            status="paid",
        ),
        Payment(
            user_id=users[1].id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            amount=199,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="life-2",
            provider_payment_charge_id="life-2",
            invoice_payload="stars:life:2",
            paid_at=now - timedelta(days=29),
            status="paid",
        ),
        Payment(
            user_id=users[2].id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            amount=199,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="life-3",
            provider_payment_charge_id="life-3",
            invoice_payload="stars:life:3",
            paid_at=now - timedelta(days=31),
            status="paid",
        ),
        Payment(
            user_id=users[3].id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            amount=199,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="life-4",
            provider_payment_charge_id="life-4",
            invoice_payload="stars:life:4",
            paid_at=now - timedelta(days=35),
            status="paid",
        ),
    ])
    await session.commit()

    snapshot = await build_analytics_snapshot(session, now=now)

    assert snapshot.lifecycle_queues.renewal_due_3d_users == 1
    assert snapshot.lifecycle_queues.renewal_due_1d_users == 1
    assert snapshot.lifecycle_queues.grace_period_users == 1
    assert snapshot.lifecycle_queues.win_back_ready_users == 1



async def test_analytics_snapshot_includes_lifecycle_campaign_attribution(
    session: AsyncSession,
) -> None:
    now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    users = [
        User(telegram_id=3951, first_name="Attr A"),
        User(telegram_id=3952, first_name="Attr B"),
    ]
    session.add_all(users)
    await session.flush()

    channel = Channel(
        telegram_chat_id=-1004234567890,
        title="Attribution channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add(channel)
    await session.flush()

    tariff = Tariff(
        name="Attribution 30",
        price_stars=250,
        duration_days=30,
        sort_order=10,
        is_active=True,
        channel_id=channel.id,
    )
    session.add(tariff)
    await session.flush()

    subscriptions = [
        Subscription(
            user_id=users[0].id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            status="active",
            source="purchase",
            started_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=29),
        ),
        Subscription(
            user_id=users[1].id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            status="active",
            source="purchase",
            started_at=now - timedelta(days=2),
            expires_at=now + timedelta(days=28),
        ),
    ]
    session.add_all(subscriptions)
    await session.flush()

    session.add_all([
        AuditLog(
            action="retention_win_back_sent",
            target_user_id=users[0].id,
            created_at=now - timedelta(days=3),
            payload=json.dumps(
                {
                    "offer_strategy": "win_back_limited",
                    "campaign_variant": "win_back_recent",
                    "limited_primary": True,
                    "bundle_primary": False,
                    "bundle_count": 0,
                    "cross_sell_count": 1,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        AuditLog(
            action="subscription_warning_3d_sent",
            target_user_id=users[1].id,
            created_at=now - timedelta(days=2),
            payload=json.dumps(
                {
                    "offer_strategy": "renewal_bundle",
                    "campaign_variant": "renewal_3d",
                    "limited_primary": False,
                    "bundle_primary": False,
                    "bundle_count": 1,
                    "cross_sell_count": 0,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
    ])
    await session.flush()

    session.add_all([
        Payment(
            user_id=users[0].id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            amount=250,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="attr-pay-1",
            provider_payment_charge_id="attr-pay-1",
            invoice_payload="stars:attr:1",
            paid_at=now - timedelta(days=1),
            status="paid",
        ),
        Payment(
            user_id=users[1].id,
            tariff_id=tariff.id,
            channel_id=channel.id,
            amount=500,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="attr-pay-2",
            provider_payment_charge_id="attr-pay-2",
            invoice_payload="stars:attr:2",
            paid_at=now - timedelta(hours=12),
            status="paid",
        ),
    ])
    await session.flush()

    session.add_all([
        InviteLink(
            user_id=users[0].id,
            channel_id=channel.id,
            subscription_id=subscriptions[0].id,
            invite_link="https://t.me/+attr-a",
            expire_at=now + timedelta(days=1),
            is_revoked=False,
            created_at=now - timedelta(hours=20),
        ),
        InviteLink(
            user_id=users[1].id,
            channel_id=channel.id,
            subscription_id=subscriptions[1].id,
            invite_link="https://t.me/+attr-b",
            expire_at=now + timedelta(days=1),
            is_revoked=False,
            created_at=now - timedelta(hours=10),
        ),
    ])
    await session.commit()

    snapshot = await build_analytics_snapshot(session, now=now)

    attribution = snapshot.lifecycle_campaign_attribution
    assert attribution.total_sent_count == 2
    assert attribution.total_paid_users == 2
    assert attribution.total_payment_count == 2
    assert attribution.total_invite_issued_users == 2
    assert attribution.revenue_total == 750
    variant_map = {item.variant: item for item in attribution.variants}
    assert variant_map["win_back_limited"].paid_users == 1
    assert variant_map["win_back_limited"].invite_issued_users == 1
    assert variant_map["win_back_limited"].revenue_total == 250
    assert variant_map["win_back_limited"].paid_conversion_percent == 100
    assert variant_map["renewal_bundle"].paid_users == 1
    assert variant_map["renewal_bundle"].invite_issued_users == 1
    assert variant_map["renewal_bundle"].revenue_total == 500
    assert variant_map["renewal_bundle"].bundle_extra_touch_count == 1
    family_map = {item.family: item for item in attribution.families}
    assert family_map["win_back"].paid_users == 1
    assert family_map["win_back"].invite_issued_users == 1
    assert family_map["win_back"].revenue_total == 250
    assert family_map["win_back"].top_variant == "win_back_limited"
    assert family_map["renewal"].paid_users == 1
    assert family_map["renewal"].invite_issued_users == 1
    assert family_map["renewal"].revenue_total == 500
    assert family_map["renewal"].bundle_extra_touch_count == 1
    assert family_map["renewal"].top_variant == "renewal_bundle"
    rule_map = {item.rule_key: item for item in attribution.rules}
    assert rule_map["win_back_wave"].family == "win_back"
    assert rule_map["win_back_wave"].paid_users == 1
    assert rule_map["win_back_wave"].invite_issued_users == 1
    assert rule_map["win_back_wave"].revenue_total == 250
    assert rule_map["win_back_wave"].top_variant == "win_back_limited"
    assert rule_map["renewal_wave"].family == "renewal"
    assert rule_map["renewal_wave"].paid_users == 1
    assert rule_map["renewal_wave"].invite_issued_users == 1
    assert rule_map["renewal_wave"].revenue_total == 500
    assert rule_map["renewal_wave"].bundle_extra_touch_count == 1
    assert rule_map["renewal_wave"].top_variant == "renewal_bundle"
    wave_map = {item.wave_mode: item for item in attribution.waves}
    assert wave_map["limited_wave"].paid_users == 1
    assert wave_map["limited_wave"].invite_issued_users == 1
    assert wave_map["limited_wave"].revenue_total == 250
    assert wave_map["limited_wave"].top_rule_key == "win_back_wave"
    assert wave_map["recommended_bundle_wave"].paid_users == 1
    assert wave_map["recommended_bundle_wave"].invite_issued_users == 1
    assert wave_map["recommended_bundle_wave"].revenue_total == 500
    assert wave_map["recommended_bundle_wave"].bundle_extra_touch_count == 1
    assert wave_map["recommended_bundle_wave"].top_rule_key == "renewal_wave"
    highlight_map = {
        (item.scope, item.metric): item
        for item in attribution.highlights
    }
    assert highlight_map[("rules", "top_revenue")].entity_key == "renewal_wave"
    assert highlight_map[("rules", "top_revenue")].revenue_total == 500
    assert highlight_map[("waves", "top_paid_conversion")].entity_key == "recommended_bundle_wave"
    assert highlight_map[("families", "top_revenue")].entity_key == "renewal"
    assert highlight_map[("variants", "top_revenue")].entity_key == "renewal_bundle"


async def test_analytics_snapshot_includes_lifecycle_offer_mix(
    session: AsyncSession,
) -> None:
    now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    users = [
        User(telegram_id=3901, first_name="Lifecycle A"),
        User(telegram_id=3902, first_name="Lifecycle B"),
    ]
    session.add_all(users)
    await session.flush()

    session.add_all([
        AuditLog(
            action="retention_win_back_sent",
            target_user_id=users[0].id,
            created_at=now - timedelta(days=2),
            payload=json.dumps(
                {
                    "offer_strategy": "win_back_limited",
                    "campaign_variant": "win_back_recent",
                    "limited_primary": True,
                    "bundle_primary": False,
                    "bundle_count": 0,
                    "cross_sell_count": 0,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        AuditLog(
            action="retention_inactive_paid_sent",
            target_user_id=users[0].id,
            created_at=now - timedelta(days=1),
            payload=json.dumps(
                {
                    "offer_strategy": "reactivation_bundle",
                    "campaign_variant": "reactivation",
                    "limited_primary": False,
                    "bundle_primary": False,
                    "bundle_count": 1,
                    "cross_sell_count": 0,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        AuditLog(
            action="subscription_warning_3d_sent",
            target_user_id=users[1].id,
            created_at=now - timedelta(hours=12),
            payload=json.dumps(
                {
                    "offer_strategy": "renewal_bundle",
                    "campaign_variant": "renewal_3d",
                    "limited_primary": False,
                    "bundle_primary": False,
                    "bundle_count": 1,
                    "cross_sell_count": 0,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        AuditLog(
            action="subscription_expired_notice_sent",
            target_user_id=users[1].id,
            created_at=now - timedelta(hours=6),
            payload=json.dumps(
                {
                    "offer_strategy": "expired_grace",
                    "campaign_variant": "grace_recovery",
                    "limited_primary": False,
                    "bundle_primary": False,
                    "bundle_count": 0,
                    "cross_sell_count": 1,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
    ])
    await session.commit()

    snapshot = await build_analytics_snapshot(session, now=now)

    mix = snapshot.lifecycle_offer_mix
    assert mix.total_sent_count == 4
    assert mix.limited_primary_count == 1
    assert mix.bundle_primary_count == 0
    assert mix.bundle_extra_touch_count == 2
    assert mix.cross_sell_touch_count == 1
    variant_map = {item.variant: item for item in mix.variants}
    assert variant_map["win_back_limited"].sent_count == 1
    assert variant_map["reactivation_bundle"].sent_count == 1
    assert variant_map["renewal_bundle"].sent_count == 1
    assert variant_map["expired_grace"].sent_count == 1


async def test_analytics_snapshot_includes_pricing_intelligence_and_offer_performance(
    session: AsyncSession,
) -> None:
    now = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
    users = [
        User(telegram_id=3001, first_name="Alpha"),
        User(telegram_id=3002, first_name="Beta"),
    ]
    session.add_all(users)
    await session.flush()

    main_channel = Channel(
        telegram_chat_id=-1003234567890,
        title="Main channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    vip_channel = Channel(
        telegram_chat_id=-1003234567001,
        title="VIP channel",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add_all([main_channel, vip_channel])
    await session.flush()

    main_tariff = Tariff(
        name="Main 30",
        price_stars=250,
        duration_days=30,
        sort_order=10,
        is_active=True,
        is_default_offer=True,
        channel_id=main_channel.id,
        offer_group="Base",
    )
    vip_tariff = Tariff(
        name="VIP 90",
        price_stars=500,
        duration_days=90,
        sort_order=20,
        is_active=True,
        is_featured=True,
        channel_id=vip_channel.id,
        offer_group="VIP",
        offer_expires_at=now + timedelta(days=2),
    )
    session.add_all([main_tariff, vip_tariff])
    await session.flush()

    session.add_all([
        Payment(
            user_id=users[0].id,
            tariff_id=main_tariff.id,
            channel_id=main_channel.id,
            amount=250,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="pricing-main-1",
            provider_payment_charge_id="pricing-main-1",
            invoice_payload="stars:pricing:1",
            paid_at=now - timedelta(days=3),
            status="paid",
        ),
        Payment(
            user_id=users[1].id,
            tariff_id=main_tariff.id,
            channel_id=main_channel.id,
            amount=300,
            currency="XTR",
            provider="telegram_stars",
            telegram_payment_charge_id="pricing-main-2",
            provider_payment_charge_id="pricing-main-2",
            invoice_payload="stars:pricing:2",
            paid_at=now - timedelta(days=2),
            status="paid",
        ),
        Payment(
            user_id=users[0].id,
            tariff_id=vip_tariff.id,
            channel_id=vip_channel.id,
            amount=500,
            currency="USDT",
            provider="crypto_pay",
            telegram_payment_charge_id="pricing-vip-1",
            provider_payment_charge_id="pricing-vip-1",
            invoice_payload="crypto:pricing:3",
            paid_at=now - timedelta(days=1),
            status="paid",
        ),
    ])

    def payload(*, tariff_id: int, channel_id: int, source: str, user_id: int) -> str:
        return json.dumps(
            {
                "source": source,
                "tariff_id": tariff_id,
                "channel_id": channel_id,
                "user_id": user_id,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    session.add_all([
        AuditLog(
            action="retention_win_back_sent",
            target_user_id=users[0].id,
            created_at=now - timedelta(days=2),
            payload=json.dumps(
                {
                    "campaign_rule_key": "win_back_wave",
                    "campaign_rule_label": "Win-back wave",
                    "campaign_wave_mode": "cross_sell_wave",
                    "campaign_wave_label": "Cross-sell wave",
                    "offer_strategy": "win_back_limited",
                    "campaign_variant": "win_back_recent",
                    "primary_offer_source": "cross_sell",
                    "cross_sell_count": 1,
                    "channel_id": vip_channel.id,
                    "tariff_id": vip_tariff.id,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        AuditLog(action="tariff_detail_opened", target_user_id=users[0].id, payload=payload(tariff_id=main_tariff.id, channel_id=main_channel.id, source="main_menu", user_id=users[0].id)),
        AuditLog(action="tariff_detail_opened", target_user_id=users[1].id, payload=payload(tariff_id=main_tariff.id, channel_id=main_channel.id, source="main_menu", user_id=users[1].id)),
        AuditLog(action="offer_clicked", target_user_id=users[0].id, payload=payload(tariff_id=main_tariff.id, channel_id=main_channel.id, source="main_menu", user_id=users[0].id)),
        AuditLog(action="offer_clicked", target_user_id=users[1].id, payload=payload(tariff_id=main_tariff.id, channel_id=main_channel.id, source="main_menu", user_id=users[1].id)),
        AuditLog(action="invoice_created_stars", target_user_id=users[0].id, payload=payload(tariff_id=main_tariff.id, channel_id=main_channel.id, source="main_menu", user_id=users[0].id)),
        AuditLog(action="invoice_created_stars", target_user_id=users[1].id, payload=payload(tariff_id=main_tariff.id, channel_id=main_channel.id, source="main_menu", user_id=users[1].id)),
        AuditLog(action="tariff_detail_opened", target_user_id=users[0].id, payload=payload(tariff_id=vip_tariff.id, channel_id=vip_channel.id, source="profile", user_id=users[0].id)),
        AuditLog(action="tariff_detail_opened", target_user_id=users[1].id, payload=payload(tariff_id=vip_tariff.id, channel_id=vip_channel.id, source="profile", user_id=users[1].id)),
        AuditLog(action="offer_clicked", target_user_id=users[0].id, payload=payload(tariff_id=vip_tariff.id, channel_id=vip_channel.id, source="profile", user_id=users[0].id)),
        AuditLog(action="invoice_created_crypto", target_user_id=users[0].id, payload=payload(tariff_id=vip_tariff.id, channel_id=vip_channel.id, source="profile", user_id=users[0].id)),
    ])
    await session.commit()

    snapshot = await build_analytics_snapshot(session, now=now)

    source_acquisition = {item.source: item for item in snapshot.source_acquisition}
    assert source_acquisition["main_menu"].acquired_users == 2
    assert source_acquisition["main_menu"].paid_users == 2
    assert source_acquisition["main_menu"].payment_count == 3
    assert source_acquisition["main_menu"].lifecycle_paid_users == 1
    assert source_acquisition["main_menu"].lifecycle_paid_from_paid_percent == 50
    assert source_acquisition["main_menu"].lifecycle_payment_count == 1
    assert source_acquisition["main_menu"].lifecycle_revenue_total == 500
    assert source_acquisition["main_menu"].lifecycle_second_product_paid_users == 1
    assert source_acquisition["main_menu"].lifecycle_second_product_payment_count == 1
    assert source_acquisition["main_menu"].lifecycle_second_product_revenue_total == 500
    assert source_acquisition["main_menu"].lifecycle_second_product_attach_percent == 100
    assert source_acquisition["main_menu"].top_rule_key == "win_back_wave"
    assert source_acquisition["main_menu"].top_rule_label == "Win-back wave"
    assert source_acquisition["main_menu"].top_wave_mode == "cross_sell_wave"
    assert source_acquisition["main_menu"].top_wave_label == "Cross-sell wave"

    pricing = snapshot.pricing_intelligence
    assert pricing.average_payment_amount == 350
    assert pricing.stars_revenue_total == 550
    assert pricing.crypto_revenue_total == 500
    assert pricing.stars_revenue_share_percent == 52
    assert pricing.crypto_revenue_share_percent == 47
    assert pricing.multi_product_paid_users == 1
    assert pricing.multi_product_attach_rate_percent == 50
    assert pricing.featured_revenue_total == 500
    assert pricing.default_revenue_total == 550
    assert pricing.limited_revenue_total == 500
    assert pricing.active_limited_offer_count == 1
    assert pricing.top_revenue_offer is not None
    assert pricing.top_revenue_offer.tariff_name == "Main 30"
    assert pricing.top_conversion_offer is not None
    assert pricing.top_conversion_offer.tariff_name == "Main 30"
    assert pricing.top_product_pairs
    assert pricing.top_product_pairs[0].primary_channel_title == "Main channel"
    assert pricing.top_product_pairs[0].secondary_channel_title == "VIP channel"
    assert pricing.top_product_pairs[0].attached_paid_users == 1
    assert pricing.top_product_pairs[0].base_paid_users == 2
    assert pricing.top_product_pairs[0].attach_rate_percent == 50
    assert pricing.top_product_pairs[0].secondary_revenue_total == 500
    assert pricing.top_pair_campaigns
    assert pricing.top_pair_campaigns[0].primary_channel_title == "Main channel"
    assert pricing.top_pair_campaigns[0].secondary_channel_title == "VIP channel"
    assert pricing.top_pair_campaigns[0].rule_key == "win_back_wave"
    assert pricing.top_pair_campaigns[0].wave_mode == "cross_sell_wave"
    assert pricing.top_pair_campaigns[0].attached_paid_users == 1
    assert pricing.top_pair_campaigns[0].payment_count == 1
    assert pricing.top_pair_campaigns[0].secondary_revenue_total == 500
    roi_map = {
        item.rule_key: item
        for item in snapshot.lifecycle_campaign_attribution.roi
    }
    source_campaigns = snapshot.lifecycle_campaign_attribution.source_campaigns
    assert source_campaigns
    assert source_campaigns[0].source == "main_menu"
    assert source_campaigns[0].rule_key == "win_back_wave"
    assert source_campaigns[0].wave_mode == "cross_sell_wave"
    assert source_campaigns[0].source_acquired_users == 2
    assert source_campaigns[0].source_paid_users == 2
    assert source_campaigns[0].sent_count == 1
    assert source_campaigns[0].paid_users == 1
    assert source_campaigns[0].payment_count == 1
    assert source_campaigns[0].revenue_total == 500
    assert source_campaigns[0].paid_share_of_source_paid_percent == 50
    assert source_campaigns[0].second_product_paid_users == 1
    assert source_campaigns[0].second_product_payment_count == 1
    assert source_campaigns[0].second_product_revenue_total == 500
    assert source_campaigns[0].second_product_attach_percent == 100
    source_highlights = {
        item.metric: item
        for item in snapshot.lifecycle_campaign_attribution.source_highlights
    }
    assert source_highlights["top_paid_conversion"].source == "main_menu"
    assert source_highlights["top_paid_conversion"].rule_key == "win_back_wave"
    assert source_highlights["top_paid_conversion"].wave_mode == "cross_sell_wave"
    assert source_highlights["top_paid_conversion"].paid_conversion_percent == 100
    assert source_highlights["top_revenue"].revenue_total == 500
    assert source_highlights["top_second_product_attach"].second_product_attach_percent == 100
    source_roi = snapshot.lifecycle_campaign_attribution.source_roi
    assert source_roi
    assert source_roi[0].source == "main_menu"
    assert source_roi[0].rule_key == "win_back_wave"
    assert source_roi[0].average_revenue_per_source_paid_user == 250
    assert source_roi[0].second_product_revenue_share_percent == 100
    assert source_roi[0].second_product_upside_users == 0
    source_opportunities = snapshot.lifecycle_campaign_attribution.source_opportunities
    assert source_opportunities
    assert source_opportunities[0].source == "main_menu"
    assert source_opportunities[0].rule_key == "win_back_wave"
    assert source_opportunities[0].opportunity_score == 115
    assert source_opportunities[0].opportunity_label == "High"
    source_actions = snapshot.lifecycle_campaign_attribution.source_actions
    assert source_actions
    assert source_actions[0].source == "main_menu"
    assert source_actions[0].rule_key == "win_back_wave"
    assert source_actions[0].primary_issue_key == "restore_invite_flow"
    assert source_actions[0].primary_issue_label == "Invite delivery gap"
    assert source_actions[0].recommended_action_key == "audit_invite_delivery"
    assert source_actions[0].recommended_action_label == "Audit invite delivery"
    source_watchlist = {
        item.metric: item
        for item in snapshot.lifecycle_campaign_attribution.source_watchlist
    }
    assert source_watchlist["largest_source_paid_gap"].source == "main_menu"
    assert source_watchlist["largest_source_paid_gap"].rule_key == "win_back_wave"
    assert source_watchlist["largest_source_paid_gap"].note == "1 source-paid users not reconverted yet"
    assert roi_map["win_back_wave"].second_product_paid_users == 1
    assert roi_map["win_back_wave"].second_product_payment_count == 1
    assert roi_map["win_back_wave"].second_product_revenue_total == 500
    assert roi_map["win_back_wave"].top_secondary_channel_title == "VIP channel"
    assert roi_map["win_back_wave"].second_product_attach_from_paid_percent == 100
    assert pricing.top_offers[0].clicked_users == 2
    assert pricing.top_offers[1].is_limited_time is True
    assert pricing.top_offers[0].revenue_total == 550
