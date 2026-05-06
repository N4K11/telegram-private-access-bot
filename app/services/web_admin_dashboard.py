# ruff: noqa: E501
from __future__ import annotations

import re
from datetime import datetime, timedelta
from html import unescape

from aiogram import Bot
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db.models import (
    BroadcastCampaign,
    Channel,
    CryptoInvoice,
    Payment,
    PromoCode,
    PromoRedemption,
    SupportMessage,
    SupportTicket,
    Tariff,
)
from app.runtime_state import snapshot_runtime_state
from app.services.admin_roles import (
    PERMISSION_ANALYTICS,
    PERMISSION_BROADCASTS,
    PERMISSION_CHANNELS,
    PERMISSION_DIAGNOSTICS,
    PERMISSION_OBSERVABILITY,
    PERMISSION_PAYMENTS,
    PERMISSION_PROMOS,
    PERMISSION_SUPPORT,
    PERMISSION_TARIFFS,
    PERMISSION_USERS_VIEW,
    has_permission,
)
from app.services.analytics import PricingIntelligenceSnapshot, build_analytics_snapshot
from app.services.audit import write_audit_log
from app.services.channel_diagnostics import build_channel_diagnostics_report
from app.services.observability import sanitize_observability_text
from app.services.offer_engine import build_offer_engine_snapshot
from app.services.profile import build_user_profile_snapshot
from app.services.support import (
    SUPPORT_CATEGORY_ACCESS,
    SUPPORT_CATEGORY_PAYMENT,
    SUPPORT_CATEGORY_TECHNICAL,
    SUPPORT_PRIORITY_HIGH,
    SUPPORT_PRIORITY_URGENT,
    SUPPORT_SLA_BUCKET_BREACH,
    SUPPORT_SLA_BUCKET_LABELS,
    SUPPORT_SLA_BUCKET_WARNING,
    build_admin_support_inbox,
    build_support_canned_replies,
    support_action_lane,
    support_action_lane_label,
    support_canned_reply_pack_label,
    support_canned_reply_pack_titles,
    support_category_label,
    support_close_reason_label,
    support_escalation_lane,
    support_escalation_lane_label,
    support_priority_label,
    support_sla_bucket,
    support_sla_due_hours,
    support_sla_hotspot_label,
    support_status_label,
)
from app.services.users import build_user_directory, filter_label
from app.utils.datetime import ensure_aware_utc, format_datetime, utcnow
from app.utils.encoding import safe_ui_text

DEFAULT_PAGE_SIZE = 8
MAX_PAGE_SIZE = 20
PREVIEW_LIMIT = 4
LARGE_PAGE_SIZE = 5000
USER_FILTERS = ("all", "active", "expired", "never_paid", "blocked", "stars", "crypto")
PAYMENT_FILTERS = {"all": "\u0412\u0441\u0435", "stars": "Telegram Stars", "crypto": "Crypto Pay"}
SUPPORT_FILTERS = {
    "open": "\u041e\u0442\u043a\u0440\u044b\u0442\u044b\u0435",
    "closed": "\u0417\u0430\u043a\u0440\u044b\u0442\u044b\u0435",
}
SUPPORT_QUEUE_FILTERS = {
    "all": "\u0412\u0441\u0435 \u043e\u0442\u043a\u0440\u044b\u0442\u044b\u0435",
    "awaiting_admin": "\u0416\u0434\u0443\u0442 \u0430\u0434\u043c\u0438\u043d\u0430",
    "awaiting_user": "\u0416\u0434\u0443\u0442 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f",
    "priority_high": "\u0412\u044b\u0441\u043e\u043a\u0438\u0439 \u043f\u0440\u0438\u043e\u0440\u0438\u0442\u0435\u0442",
    "sla_warning": "\u0421\u043a\u043e\u0440\u043e SLA",
    "sla_breach": "SLA \u043d\u0430\u0440\u0443\u0448\u0435\u043d",
    "stale": "\u041f\u0440\u043e\u0441\u0440\u043e\u0447\u0435\u043d\u043d\u044b\u0435 >24\u0447",
}
SUPPORT_WAITING_STATE_LABELS = {
    "awaiting_admin": "\u0416\u0434\u0451\u0442 \u0430\u0434\u043c\u0438\u043d\u0430",
    "awaiting_user": "\u0416\u0434\u0451\u0442 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f",
    "new": "\u041d\u043e\u0432\u044b\u0439",
    "closed": "\u0417\u0430\u043a\u0440\u044b\u0442",
}
SUPPORT_INSIGHT_VIEWS = {
    "hotspots": "SLA hotspots",
    "sla_actions": "SLA actions",
    "pack_outcomes": "Reply-pack outcomes",
    "close_trends": "Close-reason trends",
    "action_lanes": "Action lanes",
    "escalation_lanes": "Escalation lanes",
    "escalation_actions": "Escalation actions",
    "priority_focus": "Priority handling",
    "escalation_watchlist": "Escalation watchlist",
    "escalation_trends": "Escalation trends",
    "operator_action_trends": "Operator action trends",
}

LIFECYCLE_VIEWS = {
    "rules": "Managed waves",
    "roi": "ROI",
    "sources": "Acquisition sources",
    "source_campaigns": "Source x campaign",
    "source_roi": "Source ROI",
    "source_opportunities": "Source opportunities",
    "source_actions": "Source actions",
    "source_highlights": "Source leaders",
    "source_watchlist": "Source watchlist",
    "highlights": "Highlights",
    "waves": "Wave modes",
    "families": "Touch families",
    "variants": "Campaign variants",
}
PROMO_TYPE_LABELS = {
    "discount_percent": "\u0421\u043a\u0438\u0434\u043a\u0430, %",
    "discount_stars": "\u0421\u043a\u0438\u0434\u043a\u0430, Stars",
    "fixed_price": "\u0424\u0438\u043a\u0441\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u0430\u044f \u0446\u0435\u043d\u0430",
    "free_days": "\u0411\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0435 \u0434\u043d\u0438",
}
_TAG_RE = re.compile(r"<[^>]+>")


async def build_web_admin_dashboard_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    now: datetime | None = None,
) -> dict[str, object]:
    current_time = ensure_aware_utc(now or utcnow())
    capabilities = _capabilities(viewer_role)
    payload: dict[str, object] = {
        "generated_at": current_time.isoformat(),
        "generated_at_label": format_datetime(current_time, settings.timezone),
        "capabilities": capabilities,
    }
    if capabilities["analytics"]:
        snapshot = await build_analytics_snapshot(session, now=current_time)
        active_tariffs = await session.execute(
            select(Tariff)
            .options(selectinload(Tariff.channel))
            .where(Tariff.is_active.is_(True))
            .where(Tariff.archived_at.is_(None))
            .order_by(Tariff.sort_order.asc(), Tariff.id.asc())
        )
        offer_engine = build_offer_engine_snapshot(
            _build_product_catalog_for_dashboard(active_tariffs.scalars())
        )
        payload["summary"] = {
            "total_users": snapshot.total_users,
            "active_subscriptions": snapshot.active_subscriptions,
            "expired_users": snapshot.expired_users,
            "never_paid_users": snapshot.never_paid_users,
            "blocked_users": snapshot.blocked_users,
            "revenue_today": snapshot.revenue_today,
            "revenue_7_days": snapshot.revenue_7_days,
            "revenue_30_days": snapshot.revenue_30_days,
            "revenue_total": snapshot.revenue_total,
            "stars_payments": snapshot.stars_payments,
            "crypto_payments": snapshot.crypto_payments,
            "paid_users_total": snapshot.paid_users_total,
            "conversion_started": snapshot.conversion_started,
            "conversion_buy_viewed": snapshot.conversion_buy_viewed,
            "conversion_product_selected": snapshot.conversion_product_selected,
            "conversion_tariff_opened": snapshot.conversion_tariff_opened,
            "conversion_offer_clicked": snapshot.conversion_offer_clicked,
            "conversion_invoice_created": snapshot.conversion_invoice_created,
            "conversion_paid": snapshot.conversion_paid,
            "conversion_invite_issued": snapshot.conversion_invite_issued,
            "repeat_purchase_users": snapshot.repeat_purchase_users,
            "repeat_purchase_rate_percent": snapshot.repeat_purchase_rate_percent,
            "offer_inventory": _serialize_offer_inventory_preview(offer_engine),
            "pricing_intelligence": _serialize_pricing_intelligence_preview(
                snapshot.pricing_intelligence
            ),
            "lifecycle_queues": {
                "renewal_due_3d_users": snapshot.lifecycle_queues.renewal_due_3d_users,
                "renewal_due_1d_users": snapshot.lifecycle_queues.renewal_due_1d_users,
                "grace_period_users": snapshot.lifecycle_queues.grace_period_users,
                "win_back_ready_users": snapshot.lifecycle_queues.win_back_ready_users,
            },
            "lifecycle_offer_mix": _serialize_lifecycle_offer_mix(snapshot.lifecycle_offer_mix),
            "lifecycle_campaign_attribution": _serialize_lifecycle_campaign_attribution(
                snapshot.lifecycle_campaign_attribution
            ),
            "retention_segments": [
                {
                    "segment": item.segment,
                    "label": item.label,
                    "candidate_count": item.candidate_count,
                    "recent_sent_count": item.recent_sent_count,
                    "dedupe_window_hours": item.dedupe_window_hours,
                }
                for item in snapshot.retention_segments
            ],
            "product_funnel": [
                {
                    "channel_id": item.channel_id,
                    "channel_title": item.channel_title,
                    "buy_viewed_users": item.buy_viewed_users,
                    "product_selected_users": item.product_selected_users,
                    "tariff_opened_users": item.tariff_opened_users,
                    "offer_clicked_users": item.offer_clicked_users,
                    "invoice_created_users": item.invoice_created_users,
                    "paid_users": item.paid_users,
                    "invite_issued_users": item.invite_issued_users,
                    "repeat_purchase_users": item.repeat_purchase_users,
                    "revenue_total": item.revenue_total,
                }
                for item in snapshot.product_funnel
            ],
            "source_funnel": [
                {
                    "source": item.source,
                    "label": item.label,
                    "buy_viewed_users": item.buy_viewed_users,
                    "product_selected_users": item.product_selected_users,
                    "tariff_opened_users": item.tariff_opened_users,
                    "offer_clicked_users": item.offer_clicked_users,
                    "invoice_created_users": item.invoice_created_users,
                    "paid_users": item.paid_users,
                    "invite_issued_users": item.invite_issued_users,
                }
                for item in snapshot.source_funnel
            ],
            "source_acquisition": [
                {
                    "source": item.source,
                    "label": item.label,
                    "acquired_users": item.acquired_users,
                    "paid_users": item.paid_users,
                    "payment_count": item.payment_count,
                    "invite_issued_users": item.invite_issued_users,
                    "repeat_purchase_users": item.repeat_purchase_users,
                    "first_paid_revenue_total": item.first_paid_revenue_total,
                    "lifetime_revenue_total": item.lifetime_revenue_total,
                    "lifecycle_paid_users": item.lifecycle_paid_users,
                    "lifecycle_paid_from_paid_percent": item.lifecycle_paid_from_paid_percent,
                    "lifecycle_payment_count": item.lifecycle_payment_count,
                    "lifecycle_invite_issued_users": item.lifecycle_invite_issued_users,
                    "lifecycle_revenue_total": item.lifecycle_revenue_total,
                    "lifecycle_second_product_paid_users": item.lifecycle_second_product_paid_users,
                    "lifecycle_second_product_payment_count": item.lifecycle_second_product_payment_count,
                    "lifecycle_second_product_revenue_total": item.lifecycle_second_product_revenue_total,
                    "lifecycle_second_product_attach_percent": item.lifecycle_second_product_attach_percent,
                    "top_rule_key": item.top_rule_key,
                    "top_rule_label": item.top_rule_label,
                    "top_wave_mode": item.top_wave_mode,
                    "top_wave_label": item.top_wave_label,
                    "paid_conversion_percent": item.paid_conversion_percent,
                    "repeat_purchase_rate_percent": item.repeat_purchase_rate_percent,
                }
                for item in snapshot.source_acquisition
            ],
            "promo_attribution": {
                "total_paid_users": snapshot.promo_attribution.total_paid_users,
                "total_payment_count": snapshot.promo_attribution.total_payment_count,
                "gross_revenue_total": snapshot.promo_attribution.gross_revenue_total,
                "revenue_total": snapshot.promo_attribution.revenue_total,
                "discount_total": snapshot.promo_attribution.discount_total,
                "discount_share_percent": snapshot.promo_attribution.discount_share_percent,
                "campaigns": [
                    {
                        "promo_code_id": item.promo_code_id,
                        "label": item.label,
                        "campaign_name": item.campaign_name,
                        "paid_users": item.paid_users,
                        "payment_count": item.payment_count,
                        "repeat_purchase_users": item.repeat_purchase_users,
                        "repeat_purchase_rate_percent": item.repeat_purchase_rate_percent,
                        "gross_revenue_total": item.gross_revenue_total,
                        "revenue_total": item.revenue_total,
                        "discount_total": item.discount_total,
                        "discount_share_percent": item.discount_share_percent,
                        "lifetime_revenue_total": item.lifetime_revenue_total,
                    }
                    for item in snapshot.promo_attribution.campaigns
                ],
            },
            "referral_attribution": {
                "total_referred_users": snapshot.referral_attribution.total_referred_users,
                "paid_referred_users": snapshot.referral_attribution.paid_referred_users,
                "rewarded_referrals_count": snapshot.referral_attribution.rewarded_referrals_count,
                "paid_conversion_percent": snapshot.referral_attribution.paid_conversion_percent,
                "suspicious_event_count": snapshot.referral_attribution.suspicious_event_count,
                "pending_reward_days_total": snapshot.referral_attribution.pending_reward_days_total,
                "reward_days_issued_total": snapshot.referral_attribution.reward_days_issued_total,
                "first_paid_revenue_total": snapshot.referral_attribution.first_paid_revenue_total,
                "lifetime_referred_revenue_total": snapshot.referral_attribution.lifetime_referred_revenue_total,
                "top_referrers": [
                    {
                        "user_id": item.user_id,
                        "telegram_id": item.telegram_id,
                        "display_name": item.display_name,
                        "invited_users_count": item.invited_users_count,
                        "paid_referrals_count": item.paid_referrals_count,
                        "repeat_purchase_referred_users": item.repeat_purchase_referred_users,
                        "repeat_purchase_rate_percent": item.repeat_purchase_rate_percent,
                        "pending_reward_days": item.pending_reward_days,
                        "reward_days_issued": item.reward_days_issued,
                        "first_paid_revenue_total": item.first_paid_revenue_total,
                        "lifetime_revenue_total": item.lifetime_revenue_total,
                        "conversion_percent": item.conversion_percent,
                    }
                    for item in snapshot.referral_attribution.top_referrers
                ],
            },
        }
        payload["revenue_chart"] = [
            {
                "label": "\u0421\u0435\u0433\u043e\u0434\u043d\u044f",
                "value": snapshot.revenue_today,
            },
            {"label": "7 \u0434\u043d\u0435\u0439", "value": snapshot.revenue_7_days},
            {"label": "30 \u0434\u043d\u0435\u0439", "value": snapshot.revenue_30_days},
            {"label": "\u0412\u0441\u0435\u0433\u043e", "value": snapshot.revenue_total},
        ]
    if capabilities["users"]:
        payload["users_preview"] = await build_web_admin_users_payload(
            session,
            settings=settings,
            viewer_role=viewer_role,
            page_size=PREVIEW_LIMIT,
            now=current_time,
        )
    if capabilities["payments"]:
        payload["payments_preview"] = await build_web_admin_payments_payload(
            session,
            settings=settings,
            viewer_role=viewer_role,
            page_size=PREVIEW_LIMIT,
        )
        payload["crypto_invoices"] = await _crypto_invoice_overview(session, settings=settings)
    if capabilities["support"]:
        payload["support"] = await _support_overview(session, settings=settings)
    if capabilities["promos"]:
        payload["promos"] = await _promo_overview(session, settings=settings)
    if capabilities["tariffs"]:
        payload["tariffs"] = await _tariff_overview(session)
    if capabilities["broadcasts"]:
        payload["broadcasts"] = await _broadcast_overview(session, settings=settings)
    if capabilities["diagnostics"] or capabilities["channels"]:
        payload["channels"] = await _channel_overview(session)
    if capabilities["observability"]:
        payload["anomalies"] = [
            {
                "event_name": item.event_name,
                "source": item.source,
                "message": sanitize_observability_text(item.message),
                "occurred_at_label": format_datetime(item.occurred_at, settings.timezone),
            }
            for item in snapshot_runtime_state().recent_critical_errors[:PREVIEW_LIMIT]
        ]
    return payload


async def build_web_admin_lifecycle_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    view: str = "rules",
    limit: int = 12,
    now: datetime | None = None,
) -> dict[str, object]:
    del viewer_role
    current_time = ensure_aware_utc(now or utcnow())
    normalized_view = view if view in LIFECYCLE_VIEWS else "rules"
    normalized_limit = max(1, min(limit, 25))
    snapshot = await build_analytics_snapshot(session, now=current_time)
    attribution = snapshot.lifecycle_campaign_attribution

    if normalized_view == "roi":
        items = [
            {
                "rule_key": item.rule_key,
                "label": item.label,
                "family": item.family,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "top_secondary_channel_id": item.top_secondary_channel_id,
                "top_secondary_channel_title": item.top_secondary_channel_title,
                "second_product_attach_from_paid_percent": item.second_product_attach_from_paid_percent,
                "second_product_attach_from_sent_percent": item.second_product_attach_from_sent_percent,
            }
            for item in attribution.roi[:normalized_limit]
        ]
        total_items = len(attribution.roi)
    elif normalized_view == "sources":
        source_items = sorted(
            snapshot.source_acquisition,
            key=lambda item: (
                -item.lifecycle_revenue_total,
                -item.lifecycle_second_product_revenue_total,
                -item.lifetime_revenue_total,
                -item.paid_users,
                item.label,
                item.source,
            ),
        )
        items = [
            {
                "source": item.source,
                "label": item.label,
                "acquired_users": item.acquired_users,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "repeat_purchase_users": item.repeat_purchase_users,
                "first_paid_revenue_total": item.first_paid_revenue_total,
                "lifetime_revenue_total": item.lifetime_revenue_total,
                "lifecycle_paid_users": item.lifecycle_paid_users,
                "lifecycle_paid_from_paid_percent": item.lifecycle_paid_from_paid_percent,
                "lifecycle_payment_count": item.lifecycle_payment_count,
                "lifecycle_invite_issued_users": item.lifecycle_invite_issued_users,
                "lifecycle_revenue_total": item.lifecycle_revenue_total,
                "lifecycle_second_product_paid_users": item.lifecycle_second_product_paid_users,
                "lifecycle_second_product_payment_count": item.lifecycle_second_product_payment_count,
                "lifecycle_second_product_revenue_total": item.lifecycle_second_product_revenue_total,
                "lifecycle_second_product_attach_percent": item.lifecycle_second_product_attach_percent,
                "top_rule_key": item.top_rule_key,
                "top_rule_label": item.top_rule_label,
                "top_wave_mode": item.top_wave_mode,
                "top_wave_label": item.top_wave_label,
                "paid_conversion_percent": item.paid_conversion_percent,
                "repeat_purchase_rate_percent": item.repeat_purchase_rate_percent,
            }
            for item in source_items[:normalized_limit]
        ]
        total_items = len(source_items)
    elif normalized_view == "source_campaigns":
        items = [
            {
                "source": item.source,
                "source_label": item.source_label,
                "source_acquired_users": item.source_acquired_users,
                "source_paid_users": item.source_paid_users,
                "rule_key": item.rule_key,
                "rule_label": item.rule_label,
                "wave_mode": item.wave_mode,
                "wave_label": item.wave_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "paid_conversion_percent": item.paid_conversion_percent,
                "paid_share_of_source_paid_percent": item.paid_share_of_source_paid_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
                "second_product_attach_percent": item.second_product_attach_percent,
            }
            for item in attribution.source_campaigns[:normalized_limit]
        ]
        total_items = len(attribution.source_campaigns)
    elif normalized_view == "source_roi":
        items = [
            {
                "source": item.source,
                "source_label": item.source_label,
                "source_acquired_users": item.source_acquired_users,
                "source_paid_users": item.source_paid_users,
                "rule_key": item.rule_key,
                "rule_label": item.rule_label,
                "wave_mode": item.wave_mode,
                "wave_label": item.wave_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "paid_conversion_percent": item.paid_conversion_percent,
                "paid_share_of_source_paid_percent": item.paid_share_of_source_paid_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
                "second_product_attach_percent": item.second_product_attach_percent,
                "average_revenue_per_paid_user": item.average_revenue_per_paid_user,
                "average_revenue_per_source_paid_user": item.average_revenue_per_source_paid_user,
                "second_product_revenue_share_percent": item.second_product_revenue_share_percent,
                "source_paid_gap_users": item.source_paid_gap_users,
                "invite_gap_users": item.invite_gap_users,
                "second_product_upside_users": item.second_product_upside_users,
            }
            for item in attribution.source_roi[:normalized_limit]
        ]
        total_items = len(attribution.source_roi)
    elif normalized_view == "source_opportunities":
        items = [
            {
                "source": item.source,
                "source_label": item.source_label,
                "source_acquired_users": item.source_acquired_users,
                "source_paid_users": item.source_paid_users,
                "rule_key": item.rule_key,
                "rule_label": item.rule_label,
                "wave_mode": item.wave_mode,
                "wave_label": item.wave_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "paid_conversion_percent": item.paid_conversion_percent,
                "paid_share_of_source_paid_percent": item.paid_share_of_source_paid_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
                "second_product_attach_percent": item.second_product_attach_percent,
                "average_revenue_per_paid_user": item.average_revenue_per_paid_user,
                "average_revenue_per_source_paid_user": item.average_revenue_per_source_paid_user,
                "second_product_revenue_share_percent": item.second_product_revenue_share_percent,
                "source_paid_gap_users": item.source_paid_gap_users,
                "invite_gap_users": item.invite_gap_users,
                "second_product_upside_users": item.second_product_upside_users,
                "opportunity_score": item.opportunity_score,
                "opportunity_label": item.opportunity_label,
            }
            for item in attribution.source_opportunities[:normalized_limit]
        ]
        total_items = len(attribution.source_opportunities)
    elif normalized_view == "source_actions":
        items = [
            {
                "source": item.source,
                "source_label": item.source_label,
                "source_acquired_users": item.source_acquired_users,
                "source_paid_users": item.source_paid_users,
                "rule_key": item.rule_key,
                "rule_label": item.rule_label,
                "wave_mode": item.wave_mode,
                "wave_label": item.wave_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "paid_conversion_percent": item.paid_conversion_percent,
                "paid_share_of_source_paid_percent": item.paid_share_of_source_paid_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
                "second_product_attach_percent": item.second_product_attach_percent,
                "average_revenue_per_paid_user": item.average_revenue_per_paid_user,
                "average_revenue_per_source_paid_user": item.average_revenue_per_source_paid_user,
                "second_product_revenue_share_percent": item.second_product_revenue_share_percent,
                "source_paid_gap_users": item.source_paid_gap_users,
                "invite_gap_users": item.invite_gap_users,
                "second_product_upside_users": item.second_product_upside_users,
                "opportunity_score": item.opportunity_score,
                "opportunity_label": item.opportunity_label,
                "primary_issue_key": item.primary_issue_key,
                "primary_issue_label": item.primary_issue_label,
                "recommended_action_key": item.recommended_action_key,
                "recommended_action_label": item.recommended_action_label,
                "recommended_action_note": item.recommended_action_note,
            }
            for item in attribution.source_actions[:normalized_limit]
        ]
        total_items = len(attribution.source_actions)
    elif normalized_view == "source_highlights":
        items = [
            {
                "metric": item.metric,
                "metric_label": item.metric_label,
                "source": item.source,
                "source_label": item.source_label,
                "source_acquired_users": item.source_acquired_users,
                "source_paid_users": item.source_paid_users,
                "rule_key": item.rule_key,
                "rule_label": item.rule_label,
                "wave_mode": item.wave_mode,
                "wave_label": item.wave_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "note": item.note,
                "paid_conversion_percent": item.paid_conversion_percent,
                "paid_share_of_source_paid_percent": item.paid_share_of_source_paid_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
                "second_product_attach_percent": item.second_product_attach_percent,
            }
            for item in attribution.source_highlights[:normalized_limit]
        ]
        total_items = len(attribution.source_highlights)
    elif normalized_view == "source_watchlist":
        items = [
            {
                "metric": item.metric,
                "metric_label": item.metric_label,
                "source": item.source,
                "source_label": item.source_label,
                "source_acquired_users": item.source_acquired_users,
                "source_paid_users": item.source_paid_users,
                "rule_key": item.rule_key,
                "rule_label": item.rule_label,
                "wave_mode": item.wave_mode,
                "wave_label": item.wave_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "note": item.note,
                "paid_conversion_percent": item.paid_conversion_percent,
                "paid_share_of_source_paid_percent": item.paid_share_of_source_paid_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
                "second_product_attach_percent": item.second_product_attach_percent,
            }
            for item in attribution.source_watchlist[:normalized_limit]
        ]
        total_items = len(attribution.source_watchlist)
    elif normalized_view == "highlights":
        items = [
            {
                "scope": item.scope,
                "scope_label": item.scope_label,
                "metric": item.metric,
                "metric_label": item.metric_label,
                "entity_key": item.entity_key,
                "entity_label": item.entity_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "note": item.note,
                "paid_conversion_percent": item.paid_conversion_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
            }
            for item in attribution.highlights[:normalized_limit]
        ]
        total_items = len(attribution.highlights)
    elif normalized_view == "waves":
        items = [
            {
                "wave_mode": item.wave_mode,
                "label": item.label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "limited_primary_count": item.limited_primary_count,
                "bundle_primary_count": item.bundle_primary_count,
                "bundle_extra_touch_count": item.bundle_extra_touch_count,
                "cross_sell_touch_count": item.cross_sell_touch_count,
                "top_rule_key": item.top_rule_key,
                "top_rule_label": item.top_rule_label,
                "paid_conversion_percent": item.paid_conversion_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
            }
            for item in attribution.waves[:normalized_limit]
        ]
        total_items = len(attribution.waves)
    elif normalized_view == "families":
        items = [
            {
                "family": item.family,
                "label": item.label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "limited_primary_count": item.limited_primary_count,
                "bundle_primary_count": item.bundle_primary_count,
                "bundle_extra_touch_count": item.bundle_extra_touch_count,
                "cross_sell_touch_count": item.cross_sell_touch_count,
                "top_variant": item.top_variant,
                "top_variant_label": item.top_variant_label,
                "paid_conversion_percent": item.paid_conversion_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
            }
            for item in attribution.families[:normalized_limit]
        ]
        total_items = len(attribution.families)
    elif normalized_view == "variants":
        items = [
            {
                "variant": item.variant,
                "label": item.label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "limited_primary_count": item.limited_primary_count,
                "bundle_primary_count": item.bundle_primary_count,
                "bundle_extra_touch_count": item.bundle_extra_touch_count,
                "cross_sell_touch_count": item.cross_sell_touch_count,
                "paid_conversion_percent": item.paid_conversion_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
            }
            for item in attribution.variants[:normalized_limit]
        ]
        total_items = len(attribution.variants)
    else:
        items = [
            {
                "rule_key": item.rule_key,
                "label": item.label,
                "family": item.family,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "limited_primary_count": item.limited_primary_count,
                "bundle_primary_count": item.bundle_primary_count,
                "bundle_extra_touch_count": item.bundle_extra_touch_count,
                "cross_sell_touch_count": item.cross_sell_touch_count,
                "top_variant": item.top_variant,
                "top_variant_label": item.top_variant_label,
                "paid_conversion_percent": item.paid_conversion_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
            }
            for item in attribution.rules[:normalized_limit]
        ]
        total_items = len(attribution.rules)

    return {
        "generated_at": current_time.isoformat(),
        "generated_at_label": format_datetime(current_time, settings.timezone),
        "view": normalized_view,
        "view_label": LIFECYCLE_VIEWS[normalized_view],
        "available_views": [{"key": key, "label": label} for key, label in LIFECYCLE_VIEWS.items()],
        "limit": normalized_limit,
        "total_items": total_items,
        "total_sent_count": attribution.total_sent_count,
        "total_paid_users": attribution.total_paid_users,
        "total_payment_count": attribution.total_payment_count,
        "total_invite_issued_users": attribution.total_invite_issued_users,
        "revenue_total": attribution.revenue_total,
        "repeat_purchase_rate_percent": snapshot.repeat_purchase_rate_percent,
        "renewal_due_3d_users": snapshot.lifecycle_queues.renewal_due_3d_users,
        "renewal_due_1d_users": snapshot.lifecycle_queues.renewal_due_1d_users,
        "grace_period_users": snapshot.lifecycle_queues.grace_period_users,
        "win_back_ready_users": snapshot.lifecycle_queues.win_back_ready_users,
        "items": items,
    }


async def build_web_admin_users_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    filter_key: str = "all",
    query: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    now: datetime | None = None,
) -> dict[str, object]:
    del settings
    del viewer_role
    normalized_filter = filter_key if filter_key in USER_FILTERS else "all"
    normalized_query = (query or "").strip().casefold()
    directory = await build_user_directory(
        session,
        filter_key=normalized_filter,
        page=1,
        page_size=LARGE_PAGE_SIZE,
        now=now,
    )
    items = directory.items
    if normalized_query:
        items = [item for item in items if normalized_query in _user_search_blob(item)]
    current_items, current_page, total_pages = _paginate(items, page=page, page_size=page_size)
    return {
        "filter_key": normalized_filter,
        "filter_label": filter_label(normalized_filter),
        "query": query or "",
        "page": current_page,
        "total_pages": total_pages,
        "total_items": len(items),
        "available_filters": [{"key": key, "label": filter_label(key)} for key in USER_FILTERS],
        "items": [
            {
                "user_id": item.user.id,
                "telegram_id": item.user.telegram_id,
                "display_name": _display_name(item.user),
                "username": item.user.username,
                "role": item.user.role,
                "is_admin": bool(item.user.is_admin),
                "is_blocked": bool(item.user.is_blocked),
                "status": item.status,
                "total_paid": item.total_paid,
                "paid_count": item.paid_count,
                "last_seen_at_label": _dt(item.user.last_seen_at, "UTC"),
                "latest_expires_at_label": _dt(item.latest_expires_at, "UTC"),
            }
            for item in current_items
        ],
    }


async def build_web_admin_payments_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    provider_filter: str = "all",
    query: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, object]:
    del viewer_role
    normalized_filter = provider_filter if provider_filter in PAYMENT_FILTERS else "all"
    normalized_query = (query or "").strip().casefold()
    result = await session.execute(
        select(Payment)
        .options(
            selectinload(Payment.user), selectinload(Payment.tariff).selectinload(Tariff.channel)
        )
        .order_by(Payment.paid_at.desc(), Payment.id.desc())
    )
    items = list(result.scalars())
    if normalized_filter == "stars":
        items = [item for item in items if item.provider == "telegram_stars"]
    elif normalized_filter == "crypto":
        items = [item for item in items if item.provider.startswith("crypto")]
    if normalized_query:
        items = [item for item in items if normalized_query in _payment_search_blob(item)]
    current_items, current_page, total_pages = _paginate(items, page=page, page_size=page_size)
    return {
        "provider_filter": normalized_filter,
        "provider_filter_label": PAYMENT_FILTERS[normalized_filter],
        "query": query or "",
        "page": current_page,
        "total_pages": total_pages,
        "total_items": len(items),
        "available_filters": [
            {"key": key, "label": label} for key, label in PAYMENT_FILTERS.items()
        ],
        "items": [
            {
                "id": item.id,
                "user_id": item.user_id,
                "telegram_id": item.user.telegram_id if item.user is not None else None,
                "user_display_name": _display_name(item.user),
                "provider": item.provider,
                "provider_label": "Crypto Pay"
                if item.provider.startswith("crypto")
                else "Telegram Stars",
                "status": item.status,
                "amount": item.amount,
                "currency": item.currency,
                "amount_label": _payment_amount(item),
                "tariff_name": _tariff_name(item.tariff, item.tariff_id),
                "channel_title": _channel_name(item),
                "paid_at_label": _dt(item.paid_at, settings.timezone),
                "created_at_label": _dt(item.created_at, settings.timezone),
            }
            for item in current_items
        ],
    }


async def run_web_admin_channel_check_action(
    session: AsyncSession,
    *,
    bot: Bot,
    settings: Settings,
    actor_user_id: int | None,
) -> dict[str, object]:
    result = await session.execute(
        select(Channel).order_by(Channel.is_active.desc(), Channel.title.asc(), Channel.id.asc())
    )
    channels = list(result.scalars())
    report = await build_channel_diagnostics_report(bot, channels)
    items = [
        {
            "channel_id": item.channel_id,
            "title": item.title,
            "telegram_chat_id": item.telegram_chat_id,
            "is_active": item.is_active,
            "overall_ok": item.overall_ok,
            "checks": [
                {"label": check.label, "ok": check.ok, "details": _plain(check.details)}
                for check in item.checks
            ],
            "recommendations": [
                sanitize_observability_text(_plain(text)) for text in item.recommendations
            ],
        }
        for item in report.results
    ]
    problems = sum(1 for item in items if not item["overall_ok"])
    await write_audit_log(
        session,
        action="webapp_admin_channel_check",
        actor_user_id=actor_user_id,
        payload={
            "checked_channels": len(items),
            "problem_channels": problems,
            "overall_ok": report.overall_ok,
        },
    )
    return {
        "overall_ok": report.overall_ok,
        "checked_channels": len(items),
        "problem_channels": problems,
        "bot_username": report.bot_username,
        "get_me_error": sanitize_observability_text(report.get_me_error),
        "results": items,
        "generated_at_label": format_datetime(utcnow(), settings.timezone),
    }


async def _crypto_invoice_overview(
    session: AsyncSession, *, settings: Settings
) -> dict[str, object]:
    result = await session.execute(
        select(CryptoInvoice)
        .order_by(CryptoInvoice.created_at.desc(), CryptoInvoice.id.desc())
        .limit(PREVIEW_LIMIT)
    )
    return {
        "pending_count": await _count(
            session, select(func.count(CryptoInvoice.id)).where(CryptoInvoice.status == "pending")
        ),
        "paid_count": await _count(
            session, select(func.count(CryptoInvoice.id)).where(CryptoInvoice.status == "paid")
        ),
        "expired_count": await _count(
            session, select(func.count(CryptoInvoice.id)).where(CryptoInvoice.status == "expired")
        ),
        "recent": [
            {
                "id": item.id,
                "user_id": item.user_id,
                "asset": item.asset,
                "amount": format(item.amount, "f"),
                "status": item.status,
                "created_at_label": _dt(item.created_at, settings.timezone),
            }
            for item in result.scalars()
        ],
    }


async def build_web_admin_support_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    status: str = "open",
    queue: str = "all",
    query: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    now: datetime | None = None,
) -> dict[str, object]:
    del viewer_role
    current_time = ensure_aware_utc(now or utcnow())
    stale_before = current_time - timedelta(hours=24)
    normalized_status = status if status in SUPPORT_FILTERS else "open"
    normalized_queue = (
        queue if normalized_status == "open" and queue in SUPPORT_QUEUE_FILTERS else "all"
    )
    normalized_query = (query or "").strip().casefold()
    result = await session.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.user),
            selectinload(SupportTicket.messages).selectinload(SupportMessage.sender),
        )
        .where(SupportTicket.status == normalized_status)
        .order_by(SupportTicket.updated_at.desc(), SupportTicket.id.desc())
    )
    items = list(result.scalars())
    queue_counts = (
        _support_queue_counts(items, stale_before=stale_before, reference_time=current_time)
        if normalized_status == "open"
        else {"all": len(items)}
    )
    if normalized_status == "open" and normalized_queue != "all":
        items = [
            item
            for item in items
            if _matches_support_queue(
                item,
                queue=normalized_queue,
                stale_before=stale_before,
                reference_time=current_time,
            )
        ]
    if normalized_query:
        items = [item for item in items if normalized_query in _support_search_blob(item)]
    current_items, current_page, total_pages = _paginate(items, page=page, page_size=page_size)
    inbox = await build_admin_support_inbox(
        session, status=normalized_status, limit=1, now=current_time
    )
    close_reason_analytics = _serialize_support_close_reason_analytics(
        inbox.close_reason_counts
    )
    support_insights = _serialize_support_insights(inbox.insights)
    return {
        "status": normalized_status,
        "status_label": SUPPORT_FILTERS[normalized_status],
        "queue": normalized_queue,
        "queue_label": SUPPORT_QUEUE_FILTERS.get(normalized_queue, "\u0412\u0441\u0435")
        if normalized_status == "open"
        else "\u0412\u0441\u0435",
        "queue_counts": queue_counts,
        "query": query or "",
        "page": current_page,
        "total_pages": total_pages,
        "total_items": len(items),
        "open_count": inbox.open_count,
        "closed_count": inbox.closed_count,
        "awaiting_admin_count": inbox.awaiting_admin_count,
        "awaiting_user_count": inbox.awaiting_user_count,
        "stale_open_count": inbox.stale_open_count,
        "high_priority_open_count": inbox.high_priority_open_count,
        "sla_warning_count": inbox.sla_warning_count,
        "sla_breach_count": inbox.sla_breach_count,
        "close_reason_counts": close_reason_analytics["items"],
        "close_reason_summary": {
            "total_closed": close_reason_analytics["total_closed"],
            "top_close_reason": close_reason_analytics["top_close_reason"],
            "top_close_reason_label": close_reason_analytics["top_close_reason_label"],
            "top_close_reason_count": close_reason_analytics["top_close_reason_count"],
            "top_close_reason_share_percent": close_reason_analytics[
                "top_close_reason_share_percent"
            ],
        },
        "insights": support_insights,
        "available_statuses": [
            {"key": key, "label": label} for key, label in SUPPORT_FILTERS.items()
        ],
        "available_queues": [
            {"key": key, "label": label}
            for key, label in (
                SUPPORT_QUEUE_FILTERS.items()
                if normalized_status == "open"
                else (("all", "\u0412\u0441\u0435"),)
            )
        ],
        "items": [
            _serialize_support_ticket_list_item(
                item,
                settings=settings,
                stale_before=stale_before,
                reference_time=current_time,
            )
            for item in current_items
        ],
    }



def _normalize_support_insight_view(view: str | None) -> str:
    normalized = (view or "hotspots").strip()
    return normalized if normalized in SUPPORT_INSIGHT_VIEWS else "hotspots"


def _support_insight_items_for_view(
    insights: dict[str, object], *, view: str
) -> list[dict[str, object]]:
    source_key = {
        "hotspots": "sla_hotspots",
        "sla_actions": "sla_actions",
        "pack_outcomes": "canned_reply_pack_outcomes",
        "close_trends": "close_reason_trends",
        "action_lanes": "action_lanes",
        "escalation_lanes": "escalation_lanes",
        "escalation_actions": "escalation_actions",
        "priority_focus": "priority_focus",
        "escalation_watchlist": "escalation_watchlist",
        "escalation_trends": "escalation_trends",
        "operator_action_trends": "operator_action_trends",
    }[view]
    items = insights.get(source_key, [])
    return list(items) if isinstance(items, list) else []


async def build_web_admin_support_insights_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    view: str = "hotspots",
    limit: int = DEFAULT_PAGE_SIZE,
    now: datetime | None = None,
) -> dict[str, object]:
    del settings, viewer_role
    current_time = ensure_aware_utc(now or utcnow())
    normalized_view = _normalize_support_insight_view(view)
    normalized_limit = max(1, min(limit, MAX_PAGE_SIZE))
    inbox = await build_admin_support_inbox(
        session,
        status="open",
        limit=1,
        now=current_time,
    )
    support_insights = _serialize_support_insights(inbox.insights)
    all_items = _support_insight_items_for_view(
        support_insights,
        view=normalized_view,
    )
    return {
        "view": normalized_view,
        "view_label": SUPPORT_INSIGHT_VIEWS[normalized_view],
        "available_views": [
            {"key": key, "label": label}
            for key, label in SUPPORT_INSIGHT_VIEWS.items()
        ],
        "limit": normalized_limit,
        "total_items": len(all_items),
        "open_count": inbox.open_count,
        "awaiting_admin_count": inbox.awaiting_admin_count,
        "awaiting_user_count": inbox.awaiting_user_count,
        "stale_open_count": inbox.stale_open_count,
        "high_priority_open_count": inbox.high_priority_open_count,
        "sla_warning_count": inbox.sla_warning_count,
        "sla_breach_count": inbox.sla_breach_count,
        "recent_close_summary": support_insights.get("recent_close_summary", {}),
        "trend_summary": support_insights.get("trend_summary", {}),
        "pack_outcome_summary": support_insights.get("pack_outcome_summary", {}),
        "sla_hotspot_summary": support_insights.get("sla_hotspot_summary", {}),
        "sla_action_summary": support_insights.get("sla_action_summary", {}),
        "action_lane_summary": support_insights.get("action_lane_summary", {}),
        "escalation_lane_summary": support_insights.get("escalation_lane_summary", {}),
        "escalation_action_summary": support_insights.get("escalation_action_summary", {}),
        "priority_focus_summary": support_insights.get("priority_focus_summary", {}),
        "escalation_watchlist_summary": support_insights.get("escalation_watchlist_summary", {}),
        "escalation_trend_summary": support_insights.get("escalation_trend_summary", {}),
        "operator_action_trend_summary": support_insights.get("operator_action_trend_summary", {}),
        "items": all_items[:normalized_limit],
    }

async def build_web_admin_support_ticket_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    ticket_id: int,
) -> dict[str, object] | None:
    del viewer_role
    current_time = ensure_aware_utc(utcnow())
    stale_before = current_time - timedelta(hours=24)
    result = await session.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.user),
            selectinload(SupportTicket.messages).selectinload(SupportMessage.sender),
        )
        .where(SupportTicket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    if ticket is None:
        return None

    profile_snapshot = await build_user_profile_snapshot(
        session,
        telegram_user_id=ticket.user.telegram_id,
        history_limit=PREVIEW_LIMIT,
    )
    payment_result = await session.execute(
        select(Payment)
        .options(
            selectinload(Payment.user), selectinload(Payment.tariff).selectinload(Tariff.channel)
        )
        .where(Payment.user_id == ticket.user_id)
        .where(Payment.status == "paid")
        .order_by(Payment.paid_at.desc(), Payment.id.desc())
        .limit(PREVIEW_LIMIT)
    )
    payments = list(payment_result.scalars())
    suggested_replies = _serialize_support_canned_replies(ticket)

    pinned_context = _serialize_support_ticket_pinned_context(
        ticket,
        profile_snapshot=profile_snapshot,
        payments=payments,
        settings=settings,
        reference_time=current_time,
    )
    operator_hints = _build_support_operator_hints(
        ticket,
        profile_snapshot=profile_snapshot,
        payments=payments,
        reference_time=current_time,
    )

    return {
        "ticket": _serialize_support_ticket_list_item(
            ticket,
            settings=settings,
            stale_before=stale_before,
            reference_time=current_time,
        ),
        "pinned_context": pinned_context,
        "operator_hints": operator_hints,
        "messages": [
            {
                "id": item.id,
                "is_admin": bool(item.is_admin),
                "sender_label": "\u0410\u0434\u043c\u0438\u043d"
                if item.is_admin
                else _display_name(item.sender),
                "body": sanitize_observability_text(_plain(item.body)),
                "created_at_label": _dt(item.created_at, settings.timezone),
            }
            for item in ticket.messages
        ],
        "profile": _serialize_support_profile_summary(
            profile_snapshot,
            settings=settings,
        ),
        "payments_preview": [
            {
                "id": item.id,
                "amount_label": _payment_amount(item),
                "provider_label": "Crypto Pay"
                if item.provider.startswith("crypto")
                else "Telegram Stars",
                "tariff_name": _tariff_name(item.tariff, item.tariff_id),
                "channel_title": _channel_name(item),
                "paid_at_label": _dt(item.paid_at, settings.timezone),
            }
            for item in payments
        ],
        "suggested_replies": suggested_replies,
        "actions": {
            "user_query": str(ticket.user.telegram_id),
            "payments_query": str(ticket.user.telegram_id),
            "profile_path": f"{settings.mini_app_path}/api/users/{ticket.user.telegram_id}/profile",
        },
    }


def _serialize_support_canned_replies(ticket: SupportTicket) -> list[dict[str, object]]:
    return [
        {
            "key": item.key,
            "title": item.title,
            "body": item.body,
            "kind": item.kind,
        }
        for item in build_support_canned_replies(ticket)
    ]


def _serialize_support_distribution(
    counts: dict[str, int],
    *,
    label_resolver,
    total: int | None = None,
) -> list[dict[str, object]]:
    base_total = total if total is not None else sum(counts.values())
    return [
        {
            "key": key,
            "label": label_resolver(key),
            "count": count,
            "share_percent": round((count / base_total) * 100, 1) if base_total else 0.0,
        }
        for key, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], label_resolver(item[0])),
        )
    ]


def _serialize_support_insights(insights) -> dict[str, object]:
    open_total = sum(insights.priority_counts.values())
    priority_items = _serialize_support_distribution(
        insights.priority_counts,
        label_resolver=support_priority_label,
        total=open_total,
    )
    waiting_state_items = _serialize_support_distribution(
        insights.waiting_state_counts,
        label_resolver=lambda key: SUPPORT_WAITING_STATE_LABELS.get(key, key),
        total=sum(insights.waiting_state_counts.values()),
    )
    category_items = _serialize_support_distribution(
        insights.category_counts,
        label_resolver=support_category_label,
        total=sum(insights.category_counts.values()),
    )
    pack_total = sum(insights.canned_reply_pack_counts.values())
    canned_reply_packs = [
        {
            "key": key,
            "label": support_canned_reply_pack_label(key),
            "count": count,
            "share_percent": round((count / pack_total) * 100, 1) if pack_total else 0.0,
            "sample_titles": support_canned_reply_pack_titles(key),
        }
        for key, count in sorted(
            insights.canned_reply_pack_counts.items(),
            key=lambda item: (-item[1], support_canned_reply_pack_label(item[0])),
        )
    ]
    recent_close_reasons = _serialize_support_distribution(
        insights.recent_close_reason_counts,
        label_resolver=support_close_reason_label,
        total=insights.recent_close_total,
    )
    previous_close_reasons = _serialize_support_distribution(
        insights.previous_close_reason_counts,
        label_resolver=support_close_reason_label,
        total=insights.previous_close_total,
    )
    close_reason_trends = [
        {
            "key": item.reason,
            "label": support_close_reason_label(item.reason),
            "current_count": item.current_count,
            "previous_count": item.previous_count,
            "delta": item.delta,
        }
        for item in insights.close_reason_trends
    ]
    canned_reply_pack_outcomes = [
        {
            "key": item.pack_key,
            "label": support_canned_reply_pack_label(item.pack_key),
            "ticket_count": item.ticket_count,
            "resolved_count": item.resolved_count,
            "no_response_count": item.no_response_count,
            "duplicate_count": item.duplicate_count,
            "other_count": item.other_count,
            "resolved_rate_percent": item.resolved_rate_percent,
            "no_response_rate_percent": item.no_response_rate_percent,
            "duplicate_rate_percent": item.duplicate_rate_percent,
            "sample_titles": support_canned_reply_pack_titles(item.pack_key),
        }
        for item in insights.canned_reply_pack_outcomes
    ]
    sla_hotspots = [
        {
            "kind": item.kind,
            "kind_label": support_sla_hotspot_label(item.kind),
            "category": item.category,
            "category_label": support_category_label(item.category),
            "priority": item.priority,
            "priority_label": support_priority_label(item.priority),
            "count": item.count,
            "share_percent": round((item.count / open_total) * 100, 1) if open_total else 0.0,
        }
        for item in insights.sla_hotspots
    ]
    sla_actions = [
        {
            "key": f"{item.kind}:{item.category}:{item.priority}",
            "label": f"{support_sla_hotspot_label(item.kind)} -> {support_action_lane_label(item.action_key)}",
            "kind": item.kind,
            "kind_label": support_sla_hotspot_label(item.kind),
            "category": item.category,
            "category_label": support_category_label(item.category),
            "priority": item.priority,
            "priority_label": support_priority_label(item.priority),
            "count": item.count,
            "share_percent": round((item.count / open_total) * 100, 1) if open_total else 0.0,
            "action_key": item.action_key,
            "action_label": support_action_lane_label(item.action_key),
            "escalation_key": item.escalation_key,
            "escalation_label": support_escalation_lane_label(item.escalation_key),
            "note": item.note,
        }
        for item in insights.sla_actions
    ]
    action_lanes = [
        {
            "key": item.key,
            "label": support_action_lane_label(item.key),
            "count": item.count,
            "share_percent": round((item.count / open_total) * 100, 1) if open_total else 0.0,
            "high_priority_count": item.high_priority_count,
            "stale_count": item.stale_count,
            "sla_warning_count": item.sla_warning_count,
            "sla_breach_count": item.sla_breach_count,
            "top_category": item.top_category,
            "top_category_label": support_category_label(item.top_category) if item.top_category else None,
        }
        for item in insights.action_lanes
    ]
    escalation_lanes = [
        {
            "key": item.key,
            "label": support_escalation_lane_label(item.key),
            "count": item.count,
            "share_percent": round((item.count / open_total) * 100, 1) if open_total else 0.0,
            "high_priority_count": item.high_priority_count,
            "stale_count": item.stale_count,
            "sla_breach_count": item.sla_breach_count,
            "top_category": item.top_category,
            "top_category_label": support_category_label(item.top_category) if item.top_category else None,
        }
        for item in insights.escalation_lanes
    ]
    escalation_actions = [
        {
            "key": item.key,
            "label": f"{support_escalation_lane_label(item.escalation_key)} -> {support_action_lane_label(item.action_key)}",
            "escalation_key": item.escalation_key,
            "escalation_label": support_escalation_lane_label(item.escalation_key),
            "action_key": item.action_key,
            "action_label": support_action_lane_label(item.action_key),
            "count": item.count,
            "share_percent": round((item.count / open_total) * 100, 1) if open_total else 0.0,
            "high_priority_count": item.high_priority_count,
            "stale_count": item.stale_count,
            "sla_breach_count": item.sla_breach_count,
            "top_category": item.top_category,
            "top_category_label": support_category_label(item.top_category) if item.top_category else None,
        }
        for item in insights.escalation_actions
    ]
    priority_focus = [
        {
            "key": item.key,
            "label": support_priority_label(item.key),
            "count": item.count,
            "share_percent": round((item.count / open_total) * 100, 1) if open_total else 0.0,
            "awaiting_admin_count": item.awaiting_admin_count,
            "awaiting_user_count": item.awaiting_user_count,
            "stale_count": item.stale_count,
            "sla_warning_count": item.sla_warning_count,
            "sla_breach_count": item.sla_breach_count,
            "top_category": item.top_category,
            "top_category_label": support_category_label(item.top_category) if item.top_category else None,
            "top_action_lane": item.top_action_lane,
            "top_action_lane_label": support_action_lane_label(item.top_action_lane) if item.top_action_lane else None,
            "top_escalation_lane": item.top_escalation_lane,
            "top_escalation_lane_label": support_escalation_lane_label(item.top_escalation_lane) if item.top_escalation_lane else None,
        }
        for item in insights.priority_focus
    ]
    escalation_watchlist = [
        {
            "key": item.key,
            "label": support_escalation_lane_label(item.key),
            "count": item.count,
            "share_percent": round((item.count / open_total) * 100, 1) if open_total else 0.0,
            "awaiting_admin_count": item.awaiting_admin_count,
            "awaiting_user_count": item.awaiting_user_count,
            "high_priority_count": item.high_priority_count,
            "stale_count": item.stale_count,
            "sla_breach_count": item.sla_breach_count,
            "top_priority": item.top_priority,
            "top_priority_label": support_priority_label(item.top_priority) if item.top_priority else None,
            "top_category": item.top_category,
            "top_category_label": support_category_label(item.top_category) if item.top_category else None,
            "top_action_lane": item.top_action_lane,
            "top_action_lane_label": support_action_lane_label(item.top_action_lane) if item.top_action_lane else None,
            "watch_score": item.watch_score,
            "note": item.note,
        }
        for item in insights.escalation_watchlist
    ]
    escalation_trends = [
        {
            "key": item.key,
            "label": support_escalation_lane_label(item.key),
            "current_count": item.current_count,
            "previous_count": item.previous_count,
            "delta": item.delta,
        }
        for item in insights.escalation_trends
    ]
    operator_action_trends = [
        {
            "key": item.key,
            "label": f"{support_canned_reply_pack_label(item.pack_key)} -> {support_action_lane_label(item.action_key)}",
            "pack_key": item.pack_key,
            "pack_label": support_canned_reply_pack_label(item.pack_key),
            "close_reason": item.close_reason,
            "close_reason_label": support_close_reason_label(item.close_reason),
            "action_key": item.action_key,
            "action_label": support_action_lane_label(item.action_key),
            "current_count": item.current_count,
            "previous_count": item.previous_count,
            "delta": item.delta,
            "note": item.note,
        }
        for item in insights.operator_action_trends
    ]
    top_recent = recent_close_reasons[0] if recent_close_reasons else None
    strongest_trend = close_reason_trends[0] if close_reason_trends else None
    top_pack_outcome = canned_reply_pack_outcomes[0] if canned_reply_pack_outcomes else None
    top_hotspot = sla_hotspots[0] if sla_hotspots else None
    top_sla_action = sla_actions[0] if sla_actions else None
    top_action_lane = action_lanes[0] if action_lanes else None
    top_escalation_lane = escalation_lanes[0] if escalation_lanes else None
    top_escalation_action = escalation_actions[0] if escalation_actions else None
    top_priority_focus = priority_focus[0] if priority_focus else None
    top_escalation_watch = escalation_watchlist[0] if escalation_watchlist else None
    top_escalation_trend = escalation_trends[0] if escalation_trends else None
    top_operator_action_trend = operator_action_trends[0] if operator_action_trends else None
    return {
        "priority_counts": priority_items,
        "waiting_state_counts": waiting_state_items,
        "category_counts": category_items,
        "canned_reply_packs": canned_reply_packs,
        "recent_close_reasons": recent_close_reasons,
        "previous_close_reasons": previous_close_reasons,
        "close_reason_trends": close_reason_trends,
        "canned_reply_pack_outcomes": canned_reply_pack_outcomes,
        "sla_hotspots": sla_hotspots,
        "sla_actions": sla_actions,
        "action_lanes": action_lanes,
        "escalation_lanes": escalation_lanes,
        "escalation_actions": escalation_actions,
        "priority_focus": priority_focus,
        "escalation_watchlist": escalation_watchlist,
        "escalation_trends": escalation_trends,
        "operator_action_trends": operator_action_trends,
        "recent_close_summary": {
            "window_days": insights.recent_close_days,
            "total_closed": insights.recent_close_total,
            "previous_total_closed": insights.previous_close_total,
            "top_close_reason": top_recent["key"] if top_recent is not None else None,
            "top_close_reason_label": top_recent["label"] if top_recent is not None else None,
            "top_close_reason_count": top_recent["count"] if top_recent is not None else 0,
            "top_close_reason_share_percent": top_recent["share_percent"] if top_recent is not None else 0.0,
        },
        "trend_summary": {
            "strongest_reason": strongest_trend["key"] if strongest_trend is not None else None,
            "strongest_reason_label": strongest_trend["label"] if strongest_trend is not None else None,
            "strongest_delta": strongest_trend["delta"] if strongest_trend is not None else 0,
        },
        "pack_outcome_summary": {
            "window_days": insights.pack_outcome_days,
            "top_pack_key": top_pack_outcome["key"] if top_pack_outcome is not None else None,
            "top_pack_label": top_pack_outcome["label"] if top_pack_outcome is not None else None,
            "top_pack_resolved_rate_percent": top_pack_outcome["resolved_rate_percent"] if top_pack_outcome is not None else 0.0,
        },
        "sla_hotspot_summary": {
            "top_kind": top_hotspot["kind"] if top_hotspot is not None else None,
            "top_kind_label": top_hotspot["kind_label"] if top_hotspot is not None else None,
            "top_category_label": top_hotspot["category_label"] if top_hotspot is not None else None,
            "top_priority_label": top_hotspot["priority_label"] if top_hotspot is not None else None,
            "top_count": top_hotspot["count"] if top_hotspot is not None else 0,
        },
        "sla_action_summary": {
            "top_sla_action_key": top_sla_action["key"] if top_sla_action is not None else None,
            "top_sla_action_label": top_sla_action["label"] if top_sla_action is not None else None,
            "top_kind": top_sla_action["kind"] if top_sla_action is not None else None,
            "top_action_key": top_sla_action["action_key"] if top_sla_action is not None else None,
            "top_action_label": top_sla_action["action_label"] if top_sla_action is not None else None,
            "top_escalation_key": top_sla_action["escalation_key"] if top_sla_action is not None else None,
            "top_escalation_label": top_sla_action["escalation_label"] if top_sla_action is not None else None,
            "top_count": top_sla_action["count"] if top_sla_action is not None else 0,
        },
        "action_lane_summary": {
            "top_action_lane": top_action_lane["key"] if top_action_lane is not None else None,
            "top_action_lane_label": top_action_lane["label"] if top_action_lane is not None else None,
            "top_action_lane_count": top_action_lane["count"] if top_action_lane is not None else 0,
            "top_action_lane_share_percent": top_action_lane["share_percent"] if top_action_lane is not None else 0.0,
        },
        "escalation_lane_summary": {
            "top_escalation_lane": top_escalation_lane["key"] if top_escalation_lane is not None else None,
            "top_escalation_lane_label": top_escalation_lane["label"] if top_escalation_lane is not None else None,
            "top_escalation_lane_count": top_escalation_lane["count"] if top_escalation_lane is not None else 0,
            "top_escalation_lane_share_percent": top_escalation_lane["share_percent"] if top_escalation_lane is not None else 0.0,
        },
        "escalation_action_summary": {
            "top_escalation_action": top_escalation_action["key"] if top_escalation_action is not None else None,
            "top_escalation_action_label": top_escalation_action["label"] if top_escalation_action is not None else None,
            "top_escalation_action_count": top_escalation_action["count"] if top_escalation_action is not None else 0,
            "top_escalation_action_share_percent": top_escalation_action["share_percent"] if top_escalation_action is not None else 0.0,
        },
        "priority_focus_summary": {
            "top_priority": top_priority_focus["key"] if top_priority_focus is not None else None,
            "top_priority_label": top_priority_focus["label"] if top_priority_focus is not None else None,
            "top_priority_count": top_priority_focus["count"] if top_priority_focus is not None else 0,
            "top_priority_share_percent": top_priority_focus["share_percent"] if top_priority_focus is not None else 0.0,
            "top_priority_sla_breach_count": top_priority_focus["sla_breach_count"] if top_priority_focus is not None else 0,
        },
        "escalation_watchlist_summary": {
            "top_watch_key": top_escalation_watch["key"] if top_escalation_watch is not None else None,
            "top_watch_label": top_escalation_watch["label"] if top_escalation_watch is not None else None,
            "top_watch_score": top_escalation_watch["watch_score"] if top_escalation_watch is not None else 0,
            "top_watch_count": top_escalation_watch["count"] if top_escalation_watch is not None else 0,
        },
        "escalation_trend_summary": {
            "top_trend_key": top_escalation_trend["key"] if top_escalation_trend is not None else None,
            "top_trend_label": top_escalation_trend["label"] if top_escalation_trend is not None else None,
            "top_trend_delta": top_escalation_trend["delta"] if top_escalation_trend is not None else 0,
            "top_trend_current_count": top_escalation_trend["current_count"] if top_escalation_trend is not None else 0,
        },
        "operator_action_trend_summary": {
            "top_operator_action_key": top_operator_action_trend["key"] if top_operator_action_trend is not None else None,
            "top_operator_action_label": top_operator_action_trend["label"] if top_operator_action_trend is not None else None,
            "top_pack_key": top_operator_action_trend["pack_key"] if top_operator_action_trend is not None else None,
            "top_pack_label": top_operator_action_trend["pack_label"] if top_operator_action_trend is not None else None,
            "top_close_reason": top_operator_action_trend["close_reason"] if top_operator_action_trend is not None else None,
            "top_close_reason_label": top_operator_action_trend["close_reason_label"] if top_operator_action_trend is not None else None,
            "top_action_key": top_operator_action_trend["action_key"] if top_operator_action_trend is not None else None,
            "top_action_label": top_operator_action_trend["action_label"] if top_operator_action_trend is not None else None,
            "top_delta": top_operator_action_trend["delta"] if top_operator_action_trend is not None else 0,
            "top_current_count": top_operator_action_trend["current_count"] if top_operator_action_trend is not None else 0,
        },
    }


def _serialize_support_close_reason_analytics(
    counts: dict[str, int],
) -> dict[str, object]:
    total_closed = sum(counts.values())
    items = [
        {
            "key": key,
            "label": support_close_reason_label(key),
            "count": count,
            "share_percent": round((count / total_closed) * 100, 1) if total_closed else 0.0,
        }
        for key, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], support_close_reason_label(item[0])),
        )
    ]
    top_item = items[0] if items else None
    return {
        "total_closed": total_closed,
        "top_close_reason": top_item["key"] if top_item is not None else None,
        "top_close_reason_label": top_item["label"] if top_item is not None else None,
        "top_close_reason_count": top_item["count"] if top_item is not None else 0,
        "top_close_reason_share_percent": (
            top_item["share_percent"] if top_item is not None else 0.0
        ),
        "items": items,
    }


async def _support_overview(session: AsyncSession, *, settings: Settings) -> dict[str, object]:
    current_time = ensure_aware_utc(utcnow())
    stale_before = current_time - timedelta(hours=24)
    inbox = await build_admin_support_inbox(
        session,
        status="open",
        limit=PREVIEW_LIMIT,
        now=current_time,
    )
    close_reason_analytics = _serialize_support_close_reason_analytics(
        inbox.close_reason_counts
    )
    support_insights = _serialize_support_insights(inbox.insights)
    return {
        "open_count": inbox.open_count,
        "closed_count": inbox.closed_count,
        "awaiting_admin_count": inbox.awaiting_admin_count,
        "awaiting_user_count": inbox.awaiting_user_count,
        "stale_open_count": inbox.stale_open_count,
        "high_priority_open_count": inbox.high_priority_open_count,
        "sla_warning_count": inbox.sla_warning_count,
        "sla_breach_count": inbox.sla_breach_count,
        "close_reason_counts": close_reason_analytics["items"],
        "close_reason_summary": {
            "total_closed": close_reason_analytics["total_closed"],
            "top_close_reason": close_reason_analytics["top_close_reason"],
            "top_close_reason_label": close_reason_analytics["top_close_reason_label"],
            "top_close_reason_count": close_reason_analytics["top_close_reason_count"],
            "top_close_reason_share_percent": close_reason_analytics[
                "top_close_reason_share_percent"
            ],
        },
        "insights": support_insights,
        "recent": [
            _serialize_support_ticket_list_item(
                item,
                settings=settings,
                stale_before=stale_before,
                reference_time=current_time,
            )
            for item in inbox.tickets
        ],
    }


async def _promo_overview(session: AsyncSession, *, settings: Settings) -> dict[str, object]:
    result = await session.execute(
        select(PromoCode)
        .options(selectinload(PromoCode.tariff))
        .order_by(PromoCode.created_at.desc(), PromoCode.id.desc())
        .limit(PREVIEW_LIMIT)
    )
    return {
        "active_count": await _count(
            session, select(func.count(PromoCode.id)).where(PromoCode.is_active.is_(True))
        ),
        "pending_redemptions": await _count(
            session,
            select(func.count(PromoRedemption.id)).where(PromoRedemption.status == "pending"),
        ),
        "recent": [
            {
                "id": item.id,
                "code": item.code,
                "promo_type": item.promo_type,
                "promo_type_label": PROMO_TYPE_LABELS.get(item.promo_type, item.promo_type),
                "value_label": _promo_value(item),
                "campaign_name": item.campaign_name,
                "tariff_name": _tariff_name(item.tariff, item.tariff_id),
                "is_active": bool(item.is_active),
                "valid_until_label": _dt(item.valid_until, settings.timezone),
            }
            for item in result.scalars()
        ],
    }


async def _tariff_overview(session: AsyncSession) -> dict[str, object]:
    result = await session.execute(
        select(Tariff)
        .options(selectinload(Tariff.channel))
        .order_by(Tariff.sort_order.asc(), Tariff.id.asc())
        .limit(PREVIEW_LIMIT)
    )
    return {
        "active_count": await _count(
            session,
            select(func.count(Tariff.id))
            .where(Tariff.is_active.is_(True))
            .where(Tariff.archived_at.is_(None)),
        ),
        "inactive_count": await _count(
            session, select(func.count(Tariff.id)).where(Tariff.is_active.is_(False))
        ),
        "items": [
            {
                "id": item.id,
                "name": safe_ui_text(item.name, f"\u0422\u0430\u0440\u0438\u0444 #{item.id}"),
                "duration_days": item.duration_days,
                "price_stars": item.price_stars,
                "channel_title": safe_ui_text(
                    item.channel.title if item.channel is not None else None,
                    f"\u041a\u0430\u043d\u0430\u043b #{item.channel_id or '?'}",
                ),
                "is_active": bool(item.is_active),
            }
            for item in result.scalars()
        ],
    }


async def _broadcast_overview(session: AsyncSession, *, settings: Settings) -> dict[str, object]:
    result = await session.execute(
        select(BroadcastCampaign)
        .order_by(BroadcastCampaign.created_at.desc(), BroadcastCampaign.id.desc())
        .limit(PREVIEW_LIMIT)
    )
    return {
        "total_count": await _count(session, select(func.count(BroadcastCampaign.id))),
        "active_count": await _count(
            session,
            select(func.count(BroadcastCampaign.id)).where(BroadcastCampaign.status == "running"),
        ),
        "recent": [
            {
                "id": item.id,
                "filter_name": item.filter_name,
                "status": item.status,
                "total_targets": item.total_targets,
                "sent_count": item.sent_count,
                "failed_count": item.failed_count,
                "finished_at_label": _dt(item.finished_at, settings.timezone),
            }
            for item in result.scalars()
        ],
    }


async def _channel_overview(session: AsyncSession) -> dict[str, object]:
    result = await session.execute(
        select(Channel)
        .order_by(Channel.is_active.desc(), Channel.title.asc(), Channel.id.asc())
        .limit(PREVIEW_LIMIT)
    )
    return {
        "total_count": await _count(session, select(func.count(Channel.id))),
        "active_count": await _count(
            session, select(func.count(Channel.id)).where(Channel.is_active.is_(True))
        ),
        "invite_warning_count": await _count(
            session,
            select(func.count(Channel.id)).where(Channel.invite_users_permission.is_(False)),
        ),
        "restrict_warning_count": await _count(
            session, select(func.count(Channel.id)).where(Channel.ban_users_permission.is_(False))
        ),
        "items": [
            {
                "id": item.id,
                "title": safe_ui_text(item.title, f"\u041a\u0430\u043d\u0430\u043b #{item.id}"),
                "telegram_chat_id": item.telegram_chat_id,
                "is_active": bool(item.is_active),
            }
            for item in result.scalars()
        ],
    }


def _build_product_catalog_for_dashboard(tariffs) -> list:
    from app.services.product_service import build_product_catalog

    return build_product_catalog(list(tariffs))


def _serialize_offer_inventory_preview(snapshot) -> dict[str, object]:
    inventory = snapshot.inventory
    return {
        "total_products": inventory.total_products,
        "featured_products": inventory.featured_products,
        "default_products": inventory.default_products,
        "bundle_group_count": inventory.bundle_group_count,
        "upgrade_ready_products": inventory.upgrade_ready_products,
        "cross_sell_product_count": inventory.cross_sell_product_count,
        "limited_offer_count": inventory.limited_offer_count,
        "hero_offers": [
            {
                "channel_id": item.channel_id,
                "channel_title": item.channel_title,
                "tariff_id": item.tariff_id,
                "tariff_name": item.tariff_name,
                "price_stars": item.price_stars,
                "reason_label": item.reason_label,
                "offer_group": item.offer_group,
                "is_featured": item.is_featured,
                "is_default_offer": item.is_default_offer,
                "is_limited_time": item.is_limited_time,
                "offer_expires_at": item.offer_expires_at.isoformat()
                if item.offer_expires_at is not None
                else None,
            }
            for item in inventory.hero_offers
        ],
    }


def _serialize_lifecycle_offer_mix(snapshot) -> dict[str, object]:
    return {
        "total_sent_count": snapshot.total_sent_count,
        "limited_primary_count": snapshot.limited_primary_count,
        "bundle_primary_count": snapshot.bundle_primary_count,
        "bundle_extra_touch_count": snapshot.bundle_extra_touch_count,
        "cross_sell_touch_count": snapshot.cross_sell_touch_count,
        "variants": [
            {
                "variant": item.variant,
                "label": item.label,
                "sent_count": item.sent_count,
            }
            for item in snapshot.variants
        ],
    }


def _serialize_lifecycle_campaign_attribution(snapshot) -> dict[str, object]:
    return {
        "total_sent_count": snapshot.total_sent_count,
        "total_paid_users": snapshot.total_paid_users,
        "total_payment_count": snapshot.total_payment_count,
        "total_invite_issued_users": snapshot.total_invite_issued_users,
        "revenue_total": snapshot.revenue_total,
        "variants": [
            {
                "variant": item.variant,
                "label": item.label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "limited_primary_count": item.limited_primary_count,
                "bundle_primary_count": item.bundle_primary_count,
                "bundle_extra_touch_count": item.bundle_extra_touch_count,
                "cross_sell_touch_count": item.cross_sell_touch_count,
                "paid_conversion_percent": item.paid_conversion_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
            }
            for item in snapshot.variants
        ],
        "families": [
            {
                "family": item.family,
                "label": item.label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "limited_primary_count": item.limited_primary_count,
                "bundle_primary_count": item.bundle_primary_count,
                "bundle_extra_touch_count": item.bundle_extra_touch_count,
                "cross_sell_touch_count": item.cross_sell_touch_count,
                "top_variant": item.top_variant,
                "top_variant_label": item.top_variant_label,
                "paid_conversion_percent": item.paid_conversion_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
            }
            for item in snapshot.families
        ],
        "rules": [
            {
                "rule_key": item.rule_key,
                "label": item.label,
                "family": item.family,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "limited_primary_count": item.limited_primary_count,
                "bundle_primary_count": item.bundle_primary_count,
                "bundle_extra_touch_count": item.bundle_extra_touch_count,
                "cross_sell_touch_count": item.cross_sell_touch_count,
                "top_variant": item.top_variant,
                "top_variant_label": item.top_variant_label,
                "paid_conversion_percent": item.paid_conversion_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
            }
            for item in snapshot.rules
        ],
        "waves": [
            {
                "wave_mode": item.wave_mode,
                "label": item.label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "limited_primary_count": item.limited_primary_count,
                "bundle_primary_count": item.bundle_primary_count,
                "bundle_extra_touch_count": item.bundle_extra_touch_count,
                "cross_sell_touch_count": item.cross_sell_touch_count,
                "top_rule_key": item.top_rule_key,
                "top_rule_label": item.top_rule_label,
                "paid_conversion_percent": item.paid_conversion_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
            }
            for item in snapshot.waves
        ],
        "highlights": [
            {
                "scope": item.scope,
                "scope_label": item.scope_label,
                "metric": item.metric,
                "metric_label": item.metric_label,
                "entity_key": item.entity_key,
                "entity_label": item.entity_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "note": item.note,
                "paid_conversion_percent": item.paid_conversion_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
            }
            for item in snapshot.highlights
        ],
        "roi": [
            {
                "rule_key": item.rule_key,
                "label": item.label,
                "family": item.family,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "top_secondary_channel_id": item.top_secondary_channel_id,
                "top_secondary_channel_title": item.top_secondary_channel_title,
                "second_product_attach_from_paid_percent": item.second_product_attach_from_paid_percent,
                "second_product_attach_from_sent_percent": item.second_product_attach_from_sent_percent,
            }
            for item in snapshot.roi
        ],
        "source_roi": [
            {
                "source": item.source,
                "source_label": item.source_label,
                "source_acquired_users": item.source_acquired_users,
                "source_paid_users": item.source_paid_users,
                "rule_key": item.rule_key,
                "rule_label": item.rule_label,
                "wave_mode": item.wave_mode,
                "wave_label": item.wave_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "paid_conversion_percent": item.paid_conversion_percent,
                "paid_share_of_source_paid_percent": item.paid_share_of_source_paid_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
                "second_product_attach_percent": item.second_product_attach_percent,
                "average_revenue_per_paid_user": item.average_revenue_per_paid_user,
                "average_revenue_per_source_paid_user": item.average_revenue_per_source_paid_user,
                "second_product_revenue_share_percent": item.second_product_revenue_share_percent,
                "source_paid_gap_users": item.source_paid_gap_users,
                "invite_gap_users": item.invite_gap_users,
                "second_product_upside_users": item.second_product_upside_users,
            }
            for item in snapshot.source_roi
        ],
        "source_opportunities": [
            {
                "source": item.source,
                "source_label": item.source_label,
                "source_acquired_users": item.source_acquired_users,
                "source_paid_users": item.source_paid_users,
                "rule_key": item.rule_key,
                "rule_label": item.rule_label,
                "wave_mode": item.wave_mode,
                "wave_label": item.wave_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "paid_conversion_percent": item.paid_conversion_percent,
                "paid_share_of_source_paid_percent": item.paid_share_of_source_paid_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
                "second_product_attach_percent": item.second_product_attach_percent,
                "average_revenue_per_paid_user": item.average_revenue_per_paid_user,
                "average_revenue_per_source_paid_user": item.average_revenue_per_source_paid_user,
                "second_product_revenue_share_percent": item.second_product_revenue_share_percent,
                "source_paid_gap_users": item.source_paid_gap_users,
                "invite_gap_users": item.invite_gap_users,
                "second_product_upside_users": item.second_product_upside_users,
                "opportunity_score": item.opportunity_score,
                "opportunity_label": item.opportunity_label,
            }
            for item in snapshot.source_opportunities
        ],
        "source_actions": [
            {
                "source": item.source,
                "source_label": item.source_label,
                "source_acquired_users": item.source_acquired_users,
                "source_paid_users": item.source_paid_users,
                "rule_key": item.rule_key,
                "rule_label": item.rule_label,
                "wave_mode": item.wave_mode,
                "wave_label": item.wave_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "paid_conversion_percent": item.paid_conversion_percent,
                "paid_share_of_source_paid_percent": item.paid_share_of_source_paid_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
                "second_product_attach_percent": item.second_product_attach_percent,
                "average_revenue_per_paid_user": item.average_revenue_per_paid_user,
                "average_revenue_per_source_paid_user": item.average_revenue_per_source_paid_user,
                "second_product_revenue_share_percent": item.second_product_revenue_share_percent,
                "source_paid_gap_users": item.source_paid_gap_users,
                "invite_gap_users": item.invite_gap_users,
                "second_product_upside_users": item.second_product_upside_users,
                "opportunity_score": item.opportunity_score,
                "opportunity_label": item.opportunity_label,
                "primary_issue_key": item.primary_issue_key,
                "primary_issue_label": item.primary_issue_label,
                "recommended_action_key": item.recommended_action_key,
                "recommended_action_label": item.recommended_action_label,
                "recommended_action_note": item.recommended_action_note,
            }
            for item in snapshot.source_actions
        ],
        "source_highlights": [
            {
                "metric": item.metric,
                "metric_label": item.metric_label,
                "source": item.source,
                "source_label": item.source_label,
                "source_acquired_users": item.source_acquired_users,
                "source_paid_users": item.source_paid_users,
                "rule_key": item.rule_key,
                "rule_label": item.rule_label,
                "wave_mode": item.wave_mode,
                "wave_label": item.wave_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "note": item.note,
                "paid_conversion_percent": item.paid_conversion_percent,
                "paid_share_of_source_paid_percent": item.paid_share_of_source_paid_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
                "second_product_attach_percent": item.second_product_attach_percent,
            }
            for item in snapshot.source_highlights
        ],
        "source_watchlist": [
            {
                "metric": item.metric,
                "metric_label": item.metric_label,
                "source": item.source,
                "source_label": item.source_label,
                "source_acquired_users": item.source_acquired_users,
                "source_paid_users": item.source_paid_users,
                "rule_key": item.rule_key,
                "rule_label": item.rule_label,
                "wave_mode": item.wave_mode,
                "wave_label": item.wave_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "note": item.note,
                "paid_conversion_percent": item.paid_conversion_percent,
                "paid_share_of_source_paid_percent": item.paid_share_of_source_paid_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
                "second_product_attach_percent": item.second_product_attach_percent,
            }
            for item in snapshot.source_watchlist
        ],
        "source_campaigns": [
            {
                "source": item.source,
                "source_label": item.source_label,
                "source_acquired_users": item.source_acquired_users,
                "source_paid_users": item.source_paid_users,
                "rule_key": item.rule_key,
                "rule_label": item.rule_label,
                "wave_mode": item.wave_mode,
                "wave_label": item.wave_label,
                "sent_count": item.sent_count,
                "paid_users": item.paid_users,
                "payment_count": item.payment_count,
                "invite_issued_users": item.invite_issued_users,
                "revenue_total": item.revenue_total,
                "second_product_paid_users": item.second_product_paid_users,
                "second_product_payment_count": item.second_product_payment_count,
                "second_product_revenue_total": item.second_product_revenue_total,
                "paid_conversion_percent": item.paid_conversion_percent,
                "paid_share_of_source_paid_percent": item.paid_share_of_source_paid_percent,
                "invite_conversion_percent": item.invite_conversion_percent,
                "second_product_attach_percent": item.second_product_attach_percent,
            }
            for item in snapshot.source_campaigns
        ],
    }


def _serialize_pricing_intelligence_preview(
    snapshot: PricingIntelligenceSnapshot,
) -> dict[str, object]:
    return {
        "average_payment_amount": snapshot.average_payment_amount,
        "stars_revenue_total": snapshot.stars_revenue_total,
        "crypto_revenue_total": snapshot.crypto_revenue_total,
        "stars_revenue_share_percent": snapshot.stars_revenue_share_percent,
        "crypto_revenue_share_percent": snapshot.crypto_revenue_share_percent,
        "multi_product_paid_users": snapshot.multi_product_paid_users,
        "multi_product_attach_rate_percent": snapshot.multi_product_attach_rate_percent,
        "featured_revenue_total": snapshot.featured_revenue_total,
        "default_revenue_total": snapshot.default_revenue_total,
        "limited_revenue_total": snapshot.limited_revenue_total,
        "active_limited_offer_count": snapshot.active_limited_offer_count,
        "top_product_pairs": [
            _serialize_product_pair_preview(item) for item in snapshot.top_product_pairs
        ],
        "top_pair_campaigns": [
            _serialize_product_pair_campaign_preview(item) for item in snapshot.top_pair_campaigns
        ],
        "top_revenue_offer": _serialize_offer_performance_preview(snapshot.top_revenue_offer),
        "top_conversion_offer": _serialize_offer_performance_preview(snapshot.top_conversion_offer),
        "top_offers": [_serialize_offer_performance_preview(item) for item in snapshot.top_offers],
    }


def _serialize_product_pair_preview(item) -> dict[str, object] | None:
    if item is None:
        return None
    return {
        "primary_channel_id": item.primary_channel_id,
        "primary_channel_title": item.primary_channel_title,
        "secondary_channel_id": item.secondary_channel_id,
        "secondary_channel_title": item.secondary_channel_title,
        "attached_paid_users": item.attached_paid_users,
        "base_paid_users": item.base_paid_users,
        "attach_rate_percent": item.attach_rate_percent,
        "secondary_revenue_total": item.secondary_revenue_total,
        "pair_revenue_total": item.pair_revenue_total,
    }


def _serialize_product_pair_campaign_preview(item) -> dict[str, object] | None:
    if item is None:
        return None
    return {
        "primary_channel_id": item.primary_channel_id,
        "primary_channel_title": item.primary_channel_title,
        "secondary_channel_id": item.secondary_channel_id,
        "secondary_channel_title": item.secondary_channel_title,
        "rule_key": item.rule_key,
        "rule_label": item.rule_label,
        "wave_mode": item.wave_mode,
        "wave_label": item.wave_label,
        "attached_paid_users": item.attached_paid_users,
        "base_paid_users": item.base_paid_users,
        "attach_rate_percent": item.attach_rate_percent,
        "payment_count": item.payment_count,
        "secondary_revenue_total": item.secondary_revenue_total,
    }


def _serialize_offer_performance_preview(item) -> dict[str, object] | None:
    if item is None:
        return None
    return {
        "tariff_id": item.tariff_id,
        "tariff_name": item.tariff_name,
        "channel_id": item.channel_id,
        "channel_title": item.channel_title,
        "offer_group": item.offer_group,
        "price_stars": item.price_stars,
        "duration_days": item.duration_days,
        "is_featured": item.is_featured,
        "is_default_offer": item.is_default_offer,
        "is_limited_time": item.is_limited_time,
        "offer_expires_at": item.offer_expires_at.isoformat()
        if item.offer_expires_at is not None
        else None,
        "opened_users": item.opened_users,
        "clicked_users": item.clicked_users,
        "invoice_created_users": item.invoice_created_users,
        "paid_users": item.paid_users,
        "payment_count": item.payment_count,
        "revenue_total": item.revenue_total,
        "open_to_click_percent": item.open_to_click_percent,
        "click_to_paid_percent": item.click_to_paid_percent,
        "invoice_to_paid_percent": item.invoice_to_paid_percent,
        "average_payment_amount": item.average_payment_amount,
    }


def _capabilities(role: str) -> dict[str, bool]:
    return {
        "analytics": has_permission(role, PERMISSION_ANALYTICS),
        "users": has_permission(role, PERMISSION_USERS_VIEW),
        "payments": has_permission(role, PERMISSION_PAYMENTS),
        "support": has_permission(role, PERMISSION_SUPPORT),
        "promos": has_permission(role, PERMISSION_PROMOS),
        "tariffs": has_permission(role, PERMISSION_TARIFFS),
        "broadcasts": has_permission(role, PERMISSION_BROADCASTS),
        "diagnostics": has_permission(role, PERMISSION_DIAGNOSTICS),
        "observability": has_permission(role, PERMISSION_OBSERVABILITY),
        "channels": has_permission(role, PERMISSION_CHANNELS),
    }


def _paginate(items, *, page: int, page_size: int):
    safe_page_size = min(max(int(page_size or DEFAULT_PAGE_SIZE), 1), MAX_PAGE_SIZE)
    total_pages = max(1, (len(items) + safe_page_size - 1) // safe_page_size)
    current_page = min(max(int(page or 1), 1), total_pages)
    start = (current_page - 1) * safe_page_size
    return items[start : start + safe_page_size], current_page, total_pages


def _user_search_blob(item) -> str:
    user = item.user
    return " ".join(
        part.casefold()
        for part in (
            str(user.id),
            str(user.telegram_id),
            user.username or "",
            user.first_name or "",
            user.last_name or "",
            item.status,
        )
        if part
    )


def _payment_search_blob(item: Payment) -> str:
    return " ".join(
        part.casefold()
        for part in (
            str(item.id),
            str(item.user_id),
            str(item.user.telegram_id) if item.user is not None else "",
            item.user.username if item.user is not None and item.user.username else "",
            item.tariff.name if item.tariff is not None else "",
            item.provider,
            item.currency,
        )
        if part
    )


def _display_name(user) -> str:
    if user is None:
        return "\u2014"
    parts = [
        part for part in (user.first_name, user.last_name) if isinstance(part, str) and part.strip()
    ]
    if parts:
        return " ".join(part.strip() for part in parts)
    if user.username:
        return f"@{user.username}"
    return f"User {user.telegram_id}"


def _serialize_support_ticket_list_item(
    ticket: SupportTicket,
    *,
    settings: Settings,
    stale_before: datetime | None = None,
    reference_time: datetime | None = None,
) -> dict[str, object]:
    waiting_state = _support_waiting_state(ticket)
    sla_bucket = support_sla_bucket(ticket, now=reference_time)
    action_lane = support_action_lane(ticket, now=reference_time)
    escalation_lane = support_escalation_lane(ticket, now=reference_time)
    return {
        "id": ticket.id,
        "user_id": ticket.user_id,
        "telegram_id": ticket.user.telegram_id if ticket.user is not None else None,
        "user_display_name": _display_name(ticket.user),
        "category": ticket.category,
        "category_label": support_category_label(ticket.category),
        "status": ticket.status,
        "status_label": support_status_label(ticket.status),
        "priority": ticket.priority,
        "priority_label": support_priority_label(ticket.priority),
        "close_reason": ticket.close_reason,
        "close_reason_label": support_close_reason_label(ticket.close_reason),
        "waiting_state": waiting_state,
        "waiting_state_label": SUPPORT_WAITING_STATE_LABELS.get(waiting_state, waiting_state),
        "action_lane_key": action_lane,
        "action_lane_label": support_action_lane_label(action_lane),
        "escalation_lane_key": escalation_lane,
        "escalation_lane_label": support_escalation_lane_label(escalation_lane),
        "sla_bucket": sla_bucket,
        "sla_bucket_label": SUPPORT_SLA_BUCKET_LABELS.get(sla_bucket, sla_bucket),
        "sla_due_hours": support_sla_due_hours(ticket),
        "updated_at_label": _dt(ticket.updated_at, settings.timezone),
        "created_at_label": _dt(ticket.created_at, settings.timezone),
        "closed_at_label": _dt(ticket.closed_at, settings.timezone),
        "message_count": len(ticket.messages or []),
        "last_message_preview": _support_last_message_preview(ticket),
        "is_open": ticket.status == "open",
        "is_stale": _is_support_ticket_stale(ticket, stale_before=stale_before),
    }




def _hours_since(reference_time: datetime, value: datetime | None) -> float | None:
    if value is None:
        return None
    delta = ensure_aware_utc(reference_time) - ensure_aware_utc(value)
    return round(max(delta.total_seconds() / 3600, 0), 1)


def _serialize_support_ticket_pinned_context(
    ticket: SupportTicket,
    *,
    profile_snapshot,
    payments: list[Payment],
    settings: Settings,
    reference_time: datetime,
) -> dict[str, object]:
    waiting_state = _support_waiting_state(ticket)
    sla_bucket = support_sla_bucket(ticket, now=reference_time)
    latest_payment = payments[0] if payments else None
    return {
        "queue_label": SUPPORT_WAITING_STATE_LABELS.get(waiting_state, waiting_state),
        "sla_bucket_label": SUPPORT_SLA_BUCKET_LABELS.get(sla_bucket, sla_bucket),
        "priority_label": support_priority_label(ticket.priority),
        "action_lane_label": support_action_lane_label(support_action_lane(ticket, now=reference_time)),
        "escalation_lane_label": support_escalation_lane_label(support_escalation_lane(ticket, now=reference_time)),
        "open_age_hours": _hours_since(reference_time, ticket.created_at),
        "idle_hours": _hours_since(reference_time, ticket.updated_at),
        "last_user_message_at_label": _dt(ticket.last_user_message_at, settings.timezone),
        "last_user_gap_hours": _hours_since(reference_time, ticket.last_user_message_at),
        "last_admin_message_at_label": _dt(ticket.last_admin_message_at, settings.timezone),
        "last_admin_gap_hours": _hours_since(reference_time, ticket.last_admin_message_at),
        "active_subscription_count": (
            profile_snapshot.active_subscription_count if profile_snapshot is not None else 0
        ),
        "current_tariff_label": (
            profile_snapshot.current_tariff_label if profile_snapshot is not None else None
        ),
        "current_channel_label": (
            profile_snapshot.current_channel_label if profile_snapshot is not None else None
        ),
        "remaining_label": (
            profile_snapshot.remaining_label if profile_snapshot is not None else None
        ),
        "latest_payment_amount_label": (
            _payment_amount(latest_payment) if latest_payment is not None else None
        ),
        "latest_payment_provider_label": (
            "Crypto Pay"
            if latest_payment is not None and latest_payment.provider.startswith("crypto")
            else ("Telegram Stars" if latest_payment is not None else None)
        ),
        "latest_payment_paid_at_label": (
            _dt(latest_payment.paid_at, settings.timezone) if latest_payment is not None else None
        ),
        "latest_payment_age_hours": (
            _hours_since(reference_time, latest_payment.paid_at)
            if latest_payment is not None
            else None
        ),
    }


def _build_support_operator_hints(
    ticket: SupportTicket,
    *,
    profile_snapshot,
    payments: list[Payment],
    reference_time: datetime,
) -> list[dict[str, object]]:
    hints: list[dict[str, object]] = []
    seen: set[str] = set()
    stale_before = reference_time - timedelta(hours=24)
    waiting_state = _support_waiting_state(ticket)
    sla_bucket = support_sla_bucket(ticket, now=reference_time)
    idle_hours = _hours_since(reference_time, ticket.updated_at)
    due_hours = support_sla_due_hours(ticket)

    def add_hint(key: str, label: str, note: str, *, severity: str) -> None:
        if key in seen:
            return
        seen.add(key)
        hints.append(
            {
                "key": key,
                "label": label,
                "note": note,
                "severity": severity,
            }
        )

    if ticket.status != "open":
        add_hint(
            "closed_ticket",
            "????? ??? ??????",
            "???? ???????????? ???????? ? ????? ?????????, ????? ??????? ????? ?????? ? ??????????? ????????.",
            severity="info",
        )
        return hints

    if sla_bucket == SUPPORT_SLA_BUCKET_BREACH:
        add_hint(
            "reply_now",
            "????? ????? ????? ??????",
            f"SLA ??? ???????: ??? ??????? {idle_hours}? ??? ?????? {due_hours}?.",
            severity="warn",
        )
    elif sla_bucket == SUPPORT_SLA_BUCKET_WARNING:
        add_hint(
            "sla_warning",
            "????? ???????? ? ??????? SLA",
            f"?? breach ???????? ???? ???????: ??????? idle {idle_hours}? ?? {due_hours}?.",
            severity="info",
        )

    if _is_support_ticket_stale(ticket, stale_before=stale_before):
        add_hint(
            "stale_thread",
            "????? ?????????",
            "????? ??? ??????? ??????? ?????? 24 ?????: ???? ????????, ???? ????????? ?? ? ????? ???????? ????????????.",
            severity="warn",
        )

    if ticket.priority in {SUPPORT_PRIORITY_HIGH, SUPPORT_PRIORITY_URGENT}:
        add_hint(
            "high_priority_watch",
            "??????? ?????????",
            "???? ????? ?????? ?????????? ? ???????? ??????? ?? ?????? ????????????? ??????? ?? ??????? ????????????.",
            severity="warn",
        )

    if waiting_state == "awaiting_admin":
        if ticket.category == SUPPORT_CATEGORY_PAYMENT:
            add_hint(
                "payment_review",
                "????????? ?????? ? ?????????",
                "??????? ??????, ?????, ?????? ???????? ? ???? ?????? ??????? ????? ????????? ???????.",
                severity="warn" if payments else "info",
            )
        elif ticket.category == SUPPORT_CATEGORY_ACCESS:
            add_hint(
                "access_review",
                "????????? ?????? ? ??????",
                "????????? ???????? ????????, ??????-?????? ? ?????? ????? ???????????? ? ?????.",
                severity="warn",
            )
        elif ticket.category == SUPPORT_CATEGORY_TECHNICAL:
            add_hint(
                "technical_triage",
                "????? ??????????? triage-????????",
                "???????? ???? ???????????????, ?????? ????? ? ???????????, ??? ?????? ??? ?????????.",
                severity="info",
            )
        else:
            add_hint(
                "clarify_request",
                "????? ?????????????? ?????",
                "?????? ????????? ??? ? ???? ???? ???????, ???? ???? ????????? ??????????? ??????.",
                severity="info",
            )
    elif waiting_state == "awaiting_user":
        add_hint(
            "waiting_user_followup",
            "?????? ??????? ?? ????????????",
            "????? ???????????? follow-up canned reply ??? ????????? ??????? ????? ??? ?????? ?????????? ??????.",
            severity="info",
        )

    if payments and profile_snapshot is not None and not profile_snapshot.current_channel_label:
        add_hint(
            "access_gap_after_payment",
            "????? ?????? ??? ????????? ???????",
            "???? ?????????? ???????, ?? ???????? ????? ?? ?????: ????????? ????????? ???????? ? ?????????? ??????.",
            severity="warn",
        )

    if (
        ticket.category == SUPPORT_CATEGORY_ACCESS
        and profile_snapshot is not None
        and profile_snapshot.current_channel_label
        and waiting_state == "awaiting_admin"
    ):
        add_hint(
            "verify_join_state",
            "?????? ???????, ?? ????? live-check ?????",
            "???????? ???????: ?????????, ?? ?????? ?? ???????????? ? expired invite ??? ??????????? Telegram ?? ????.",
            severity="info",
        )

    return hints
def _serialize_support_profile_summary(snapshot, *, settings: Settings) -> dict[str, object] | None:
    if snapshot is None:
        return None
    return {
        "telegram_id": snapshot.user.telegram_id,
        "display_name": _display_name(snapshot.user),
        "status_label": snapshot.status_label,
        "latest_expires_at_label": _dt(snapshot.latest_expires_at, settings.timezone),
        "remaining_label": snapshot.remaining_label,
        "current_tariff_label": snapshot.current_tariff_label,
        "current_channel_label": snapshot.current_channel_label,
        "active_subscription_count": snapshot.active_subscription_count,
        "total_stars_amount": snapshot.total_stars_amount,
    }


def _support_search_blob(ticket: SupportTicket) -> str:
    return " ".join(
        part.casefold()
        for part in (
            str(ticket.id),
            str(ticket.user_id),
            str(ticket.user.telegram_id) if ticket.user is not None else "",
            ticket.user.username if ticket.user is not None and ticket.user.username else "",
            ticket.user.first_name if ticket.user is not None and ticket.user.first_name else "",
            ticket.user.last_name if ticket.user is not None and ticket.user.last_name else "",
            ticket.category,
            support_category_label(ticket.category),
            ticket.status,
            support_status_label(ticket.status),
            ticket.priority,
            support_priority_label(ticket.priority),
            ticket.close_reason or "",
            support_close_reason_label(ticket.close_reason),
        )
        if part
    )


def _support_last_message_preview(ticket: SupportTicket) -> str | None:
    if not ticket.messages:
        return None
    preview = sanitize_observability_text(_plain(ticket.messages[-1].body))
    return _truncate(preview, limit=160)


def _matches_support_queue(
    ticket: SupportTicket,
    *,
    queue: str,
    stale_before: datetime,
    reference_time: datetime | None = None,
) -> bool:
    if queue == "all":
        return True
    if queue == "awaiting_admin":
        return _support_waiting_state(ticket) == "awaiting_admin"
    if queue == "awaiting_user":
        return _support_waiting_state(ticket) == "awaiting_user"
    if queue == "priority_high":
        return ticket.priority in {SUPPORT_PRIORITY_HIGH, SUPPORT_PRIORITY_URGENT}
    if queue == "sla_warning":
        return support_sla_bucket(ticket, now=reference_time) == SUPPORT_SLA_BUCKET_WARNING
    if queue == "sla_breach":
        return support_sla_bucket(ticket, now=reference_time) == SUPPORT_SLA_BUCKET_BREACH
    if queue == "stale":
        return _is_support_ticket_stale(ticket, stale_before=stale_before)
    return True


def _support_queue_counts(
    tickets: list[SupportTicket],
    *,
    stale_before: datetime,
    reference_time: datetime | None = None,
) -> dict[str, int]:
    return {
        "all": len(tickets),
        "awaiting_admin": sum(
            1 for ticket in tickets if _support_waiting_state(ticket) == "awaiting_admin"
        ),
        "awaiting_user": sum(
            1 for ticket in tickets if _support_waiting_state(ticket) == "awaiting_user"
        ),
        "priority_high": sum(
            1
            for ticket in tickets
            if ticket.priority in {SUPPORT_PRIORITY_HIGH, SUPPORT_PRIORITY_URGENT}
        ),
        "sla_warning": sum(
            1
            for ticket in tickets
            if support_sla_bucket(ticket, now=reference_time) == SUPPORT_SLA_BUCKET_WARNING
        ),
        "sla_breach": sum(
            1
            for ticket in tickets
            if support_sla_bucket(ticket, now=reference_time) == SUPPORT_SLA_BUCKET_BREACH
        ),
        "stale": sum(
            1 for ticket in tickets if _is_support_ticket_stale(ticket, stale_before=stale_before)
        ),
    }


def _is_support_ticket_stale(
    ticket: SupportTicket,
    *,
    stale_before: datetime | None,
) -> bool:
    if stale_before is None or ticket.status != "open" or ticket.updated_at is None:
        return False
    return ensure_aware_utc(ticket.updated_at) < stale_before


def _truncate(value: str | None, *, limit: int) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)].rstrip() + "?"


def _support_waiting_state(ticket) -> str:
    if ticket.status != "open":
        return "closed"
    if ticket.last_user_message_at and (
        ticket.last_admin_message_at is None
        or ticket.last_user_message_at > ticket.last_admin_message_at
    ):
        return "awaiting_admin"
    if ticket.last_admin_message_at is not None:
        return "awaiting_user"
    return "new"


def _payment_amount(item: Payment) -> str:
    if item.provider == "telegram_stars" or item.currency == "XTR":
        return f"{item.amount} Stars"
    return f"{item.amount} {item.currency}"


def _tariff_name(tariff: Tariff | None, tariff_id: int | None) -> str:
    if tariff is not None:
        return safe_ui_text(tariff.name, f"\u0422\u0430\u0440\u0438\u0444 #{tariff.id}")
    if tariff_id is not None:
        return f"\u0422\u0430\u0440\u0438\u0444 #{tariff_id}"
    return "\u2014"


def _channel_name(item: Payment) -> str | None:
    if item.tariff is not None and item.tariff.channel is not None:
        return safe_ui_text(
            item.tariff.channel.title,
            f"\u041a\u0430\u043d\u0430\u043b #{item.channel_id or '?'}",
        )
    return None


def _promo_value(item: PromoCode) -> str:
    if item.promo_type == "discount_percent":
        return f"-{item.value}%"
    if item.promo_type == "discount_stars":
        return f"-{item.value} Stars"
    if item.promo_type == "fixed_price":
        return f"{item.value} Stars"
    if item.promo_type == "free_days":
        return f"+{item.value} \u0434\u043d."
    return str(item.value)


def _dt(value: datetime | None, timezone: str) -> str | None:
    if value is None:
        return None
    return format_datetime(ensure_aware_utc(value), timezone)


def _plain(value: str) -> str:
    return " ".join(_TAG_RE.sub("", unescape(value)).split())


async def _count(session: AsyncSession, statement) -> int:
    return int((await session.execute(statement)).scalar_one() or 0)
