from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.repositories.tariffs import TariffRepository
from app.services.admin_read_model_reporting import (
    build_admin_read_model_snapshot_digest_payload,
    build_admin_read_model_snapshot_focus_payload,
    build_admin_read_model_snapshot_operator_payload,
)
from app.services.admin_read_models import (
    ANALYTICS_FACT_KEY_CABINET_ADMIN_SUMMARY,
    ANALYTICS_FACT_KEY_WEB_ADMIN_READ_MODELS,
    PAYLOAD_BUDGET_ADMIN_SUMMARY,
    QUERY_BUDGET_ADMIN_SUMMARY,
    load_analytics_fact_payload,
    normalize_read_model_source,
    timed_read_model_payload,
)
from app.services.admin_summary_previews import compact_admin_summary_payload
from app.services.analytics import build_analytics_snapshot
from app.services.offer_engine import build_offer_engine_snapshot
from app.services.product_service import build_product_catalog
from app.services.web_admin_dashboard_analytics_sections import (
    _serialize_offer_inventory_preview,
    _serialize_pricing_intelligence_preview,
    _serialize_promo_attribution_summary,
    _serialize_referral_attribution_summary,
)
from app.services.web_admin_dashboard_lifecycle_sections import (
    _serialize_lifecycle_campaign_attribution,
    _serialize_lifecycle_offer_mix,
)
from app.utils.datetime import ensure_aware_utc, format_datetime, utcnow


async def build_cabinet_admin_summary_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    now: datetime | None = None,
    source: str = "snapshot",
) -> dict[str, object]:
    current_time = ensure_aware_utc(now or utcnow())
    normalized_source = normalize_read_model_source(source)
    if normalized_source != "live":
        snapshot_payload = await load_analytics_fact_payload(
            session,
            fact_key=ANALYTICS_FACT_KEY_CABINET_ADMIN_SUMMARY,
            fact_date=current_time.date(),
            now=current_time,
        )
        if snapshot_payload is not None:
            return await _with_admin_read_model_summary(
                session,
                snapshot_payload=snapshot_payload,
                now=current_time,
            )
    return await timed_read_model_payload(
        lambda: _build_cabinet_admin_summary_payload_live(
            session,
            settings=settings,
            now=current_time,
        ),
        session=session,
        query_budget=QUERY_BUDGET_ADMIN_SUMMARY,
        payload_budget=PAYLOAD_BUDGET_ADMIN_SUMMARY,
        now=current_time,
    )


async def _with_admin_read_model_summary(
    session: AsyncSession,
    *,
    snapshot_payload: dict[str, object],
    now: datetime,
) -> dict[str, object]:
    read_models_snapshot = await load_analytics_fact_payload(
        session,
        fact_key=ANALYTICS_FACT_KEY_WEB_ADMIN_READ_MODELS,
        fact_date=now.date(),
        now=now,
    )
    read_model_focus = build_admin_read_model_snapshot_focus_payload(
        read_models_snapshot,
    )
    read_model_digest = build_admin_read_model_snapshot_digest_payload(
        read_models_snapshot,
    )
    read_model_operator_summary = build_admin_read_model_snapshot_operator_payload(
        read_models_snapshot,
    )
    updated_payload = dict(snapshot_payload)
    if read_model_focus is not None:
        updated_payload["read_model_focus"] = read_model_focus
    if read_model_operator_summary is not None:
        updated_payload["read_model_operator_summary"] = read_model_operator_summary
    if read_model_digest is not None:
        updated_payload["read_model_digest"] = read_model_digest
    return updated_payload


async def _build_cabinet_admin_summary_payload_live(
    session: AsyncSession,
    *,
    settings: Settings,
    now: datetime | None = None,
) -> dict[str, object]:
    current_time = ensure_aware_utc(now or utcnow())
    snapshot = await build_analytics_snapshot(session, now=current_time)
    tariffs = await TariffRepository(session).list_active()
    offer_engine = build_offer_engine_snapshot(
        build_product_catalog(tariffs),
        now=current_time,
    )
    return compact_admin_summary_payload(
        {
            "timezone": settings.timezone,
            "generated_at_label": format_datetime(current_time, settings.timezone),
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
            "lifecycle_offer_mix": _serialize_lifecycle_offer_mix(
                snapshot.lifecycle_offer_mix
            ),
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
            "promo_attribution": _serialize_promo_attribution_summary(
                snapshot.promo_attribution
            ),
            "referral_attribution": _serialize_referral_attribution_summary(
                snapshot.referral_attribution
            ),
        }
    )
