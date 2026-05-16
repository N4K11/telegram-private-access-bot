from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db.models import Tariff
from app.services.admin_read_models import (
    ANALYTICS_FACT_KEY_WEB_ADMIN_ACQUISITION,
    ANALYTICS_FACT_KEY_WEB_ADMIN_CONVERSION,
    ANALYTICS_FACT_KEY_WEB_ADMIN_PRICING,
    ANALYTICS_FACT_KEY_WEB_ADMIN_PROMO_REFERRAL,
    PAYLOAD_BUDGET_ADMIN_ACQUISITION,
    PAYLOAD_BUDGET_ADMIN_CONVERSION,
    PAYLOAD_BUDGET_ADMIN_PRICING,
    PAYLOAD_BUDGET_ADMIN_PROMO_REFERRAL,
    QUERY_BUDGET_ADMIN_ACQUISITION,
    QUERY_BUDGET_ADMIN_CONVERSION,
    QUERY_BUDGET_ADMIN_PRICING,
    QUERY_BUDGET_ADMIN_PROMO_REFERRAL,
    load_analytics_fact_payload,
    normalize_read_model_source,
    timed_read_model_payload,
)
from app.services.analytics import build_analytics_snapshot
from app.services.offer_engine import build_offer_engine_snapshot
from app.services.web_admin_dashboard_analytics_serializers import (
    _build_product_catalog_for_dashboard as _build_product_catalog_for_dashboard,
)
from app.services.web_admin_dashboard_analytics_serializers import (
    _serialize_offer_inventory_preview as _serialize_offer_inventory_preview,
)
from app.services.web_admin_dashboard_analytics_serializers import (
    _serialize_pricing_intelligence_detail as _serialize_pricing_intelligence_detail,
)
from app.services.web_admin_dashboard_analytics_serializers import (
    _serialize_pricing_intelligence_preview as _serialize_pricing_intelligence_preview,
)
from app.services.web_admin_dashboard_analytics_serializers import (
    _serialize_product_funnel_detail as _serialize_product_funnel_detail,
)
from app.services.web_admin_dashboard_analytics_serializers import (
    _serialize_promo_attribution_detail as _serialize_promo_attribution_detail,
)
from app.services.web_admin_dashboard_analytics_serializers import (
    _serialize_promo_attribution_summary as _serialize_promo_attribution_summary,
)
from app.services.web_admin_dashboard_analytics_serializers import (
    _serialize_referral_attribution_detail as _serialize_referral_attribution_detail,
)
from app.services.web_admin_dashboard_analytics_serializers import (
    _serialize_referral_attribution_summary as _serialize_referral_attribution_summary,
)
from app.services.web_admin_dashboard_analytics_serializers import (
    _serialize_source_acquisition_detail as _serialize_source_acquisition_detail,
)
from app.services.web_admin_dashboard_analytics_serializers import (
    _serialize_source_funnel_detail as _serialize_source_funnel_detail,
)
from app.services.web_admin_dashboard_limits import (
    ADMIN_DETAIL_DEFAULT_LIMIT,
    clamp_admin_detail_limit,
)
from app.utils.datetime import ensure_aware_utc, utcnow


async def build_web_admin_pricing_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
    now: datetime | None = None,
    source: str = "snapshot",
) -> dict[str, object]:
    del viewer_role
    current_time = ensure_aware_utc(now or utcnow())
    normalized_source = normalize_read_model_source(source)
    if normalized_source != "live":
        snapshot_payload = await load_analytics_fact_payload(
            session,
            fact_key=ANALYTICS_FACT_KEY_WEB_ADMIN_PRICING,
            fact_date=current_time.date(),
            now=current_time,
        )
        if snapshot_payload is not None:
            return snapshot_payload
    return await timed_read_model_payload(
        lambda: _build_web_admin_pricing_payload_live(
            session,
            settings=settings,
            limit=limit,
            now=current_time,
        ),
        session=session,
        query_budget=QUERY_BUDGET_ADMIN_PRICING,
        payload_budget=PAYLOAD_BUDGET_ADMIN_PRICING,
        now=current_time,
    )


async def _build_web_admin_pricing_payload_live(
    session: AsyncSession,
    *,
    settings: Settings,
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
    now: datetime,
    analytics_snapshot=None,
) -> dict[str, object]:
    del settings
    current_time = ensure_aware_utc(now)
    normalized_limit = clamp_admin_detail_limit(limit)
    snapshot = analytics_snapshot or await build_analytics_snapshot(session, now=current_time)
    pricing = _serialize_pricing_intelligence_detail(
        snapshot.pricing_intelligence,
        limit=normalized_limit,
    )
    pricing["view"] = "overview"
    pricing["view_label"] = "Pricing / Offers"
    pricing["limit"] = normalized_limit
    return pricing


async def build_web_admin_acquisition_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
    now: datetime | None = None,
    source: str = "snapshot",
) -> dict[str, object]:
    del viewer_role
    current_time = ensure_aware_utc(now or utcnow())
    normalized_source = normalize_read_model_source(source)
    if normalized_source != "live":
        snapshot_payload = await load_analytics_fact_payload(
            session,
            fact_key=ANALYTICS_FACT_KEY_WEB_ADMIN_ACQUISITION,
            fact_date=current_time.date(),
            now=current_time,
        )
        if snapshot_payload is not None:
            return snapshot_payload
    return await timed_read_model_payload(
        lambda: _build_web_admin_acquisition_payload_live(
            session,
            settings=settings,
            limit=limit,
            now=current_time,
        ),
        session=session,
        query_budget=QUERY_BUDGET_ADMIN_ACQUISITION,
        payload_budget=PAYLOAD_BUDGET_ADMIN_ACQUISITION,
        now=current_time,
    )


async def _build_web_admin_acquisition_payload_live(
    session: AsyncSession,
    *,
    settings: Settings,
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
    now: datetime,
    analytics_snapshot=None,
) -> dict[str, object]:
    del settings
    current_time = ensure_aware_utc(now)
    normalized_limit = clamp_admin_detail_limit(limit)
    snapshot = analytics_snapshot or await build_analytics_snapshot(session, now=current_time)
    source_funnel = _serialize_source_funnel_detail(
        snapshot.source_funnel,
        limit=normalized_limit,
    )
    source_acquisition = _serialize_source_acquisition_detail(
        snapshot.source_acquisition,
        limit=normalized_limit,
    )
    return {
        "view": "overview",
        "view_label": "Acquisition / Sources",
        "limit": normalized_limit,
        "source_count": len(source_funnel),
        "cohort_count": len(source_acquisition),
        "acquired_users_total": sum(item["acquired_users"] for item in source_acquisition),
        "paid_users_total": sum(item["paid_users"] for item in source_acquisition),
        "repeat_purchase_users_total": sum(
            item["repeat_purchase_users"] for item in source_acquisition
        ),
        "invite_issued_users_total": sum(
            item["invite_issued_users"] for item in source_acquisition
        ),
        "first_paid_revenue_total": sum(
            item["first_paid_revenue_total"] for item in source_acquisition
        ),
        "lifetime_revenue_total": sum(
            item["lifetime_revenue_total"] for item in source_acquisition
        ),
        "top_source_label": source_funnel[0]["label"] if source_funnel else None,
        "top_cohort_label": source_acquisition[0]["label"] if source_acquisition else None,
        "source_funnel": source_funnel,
        "source_acquisition": source_acquisition,
    }


async def build_web_admin_conversion_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
    now: datetime | None = None,
    source: str = "snapshot",
) -> dict[str, object]:
    del viewer_role
    current_time = ensure_aware_utc(now or utcnow())
    normalized_source = normalize_read_model_source(source)
    if normalized_source != "live":
        snapshot_payload = await load_analytics_fact_payload(
            session,
            fact_key=ANALYTICS_FACT_KEY_WEB_ADMIN_CONVERSION,
            fact_date=current_time.date(),
            now=current_time,
        )
        if snapshot_payload is not None:
            return snapshot_payload
    return await timed_read_model_payload(
        lambda: _build_web_admin_conversion_payload_live(
            session,
            settings=settings,
            limit=limit,
            now=current_time,
        ),
        session=session,
        query_budget=QUERY_BUDGET_ADMIN_CONVERSION,
        payload_budget=PAYLOAD_BUDGET_ADMIN_CONVERSION,
        now=current_time,
    )


async def _build_web_admin_conversion_payload_live(
    session: AsyncSession,
    *,
    settings: Settings,
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
    now: datetime,
    analytics_snapshot=None,
) -> dict[str, object]:
    current_time = ensure_aware_utc(now)
    normalized_limit = clamp_admin_detail_limit(limit)
    snapshot = analytics_snapshot or await build_analytics_snapshot(session, now=current_time)
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
    product_funnel = _serialize_product_funnel_detail(
        snapshot.product_funnel,
        limit=normalized_limit,
    )
    return {
        "view": "overview",
        "view_label": "Conversion / Products",
        "limit": normalized_limit,
        "conversion_started": snapshot.conversion_started,
        "conversion_buy_viewed": snapshot.conversion_buy_viewed,
        "conversion_product_selected": snapshot.conversion_product_selected,
        "conversion_tariff_opened": snapshot.conversion_tariff_opened,
        "conversion_offer_clicked": snapshot.conversion_offer_clicked,
        "conversion_invoice_created": snapshot.conversion_invoice_created,
        "conversion_paid": snapshot.conversion_paid,
        "conversion_invite_issued": snapshot.conversion_invite_issued,
        "paid_users_total": snapshot.paid_users_total,
        "repeat_purchase_users": snapshot.repeat_purchase_users,
        "repeat_purchase_rate_percent": snapshot.repeat_purchase_rate_percent,
        "offer_inventory": _serialize_offer_inventory_preview(offer_engine),
        "product_count": len(product_funnel),
        "top_product_label": product_funnel[0]["channel_title"] if product_funnel else None,
        "product_funnel": product_funnel,
    }


async def build_web_admin_promo_referral_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
    now: datetime | None = None,
    source: str = "snapshot",
) -> dict[str, object]:
    del viewer_role
    current_time = ensure_aware_utc(now or utcnow())
    normalized_source = normalize_read_model_source(source)
    if normalized_source != "live":
        snapshot_payload = await load_analytics_fact_payload(
            session,
            fact_key=ANALYTICS_FACT_KEY_WEB_ADMIN_PROMO_REFERRAL,
            fact_date=current_time.date(),
            now=current_time,
        )
        if snapshot_payload is not None:
            return snapshot_payload
    return await timed_read_model_payload(
        lambda: _build_web_admin_promo_referral_payload_live(
            session,
            settings=settings,
            limit=limit,
            now=current_time,
        ),
        session=session,
        query_budget=QUERY_BUDGET_ADMIN_PROMO_REFERRAL,
        payload_budget=PAYLOAD_BUDGET_ADMIN_PROMO_REFERRAL,
        now=current_time,
    )


async def _build_web_admin_promo_referral_payload_live(
    session: AsyncSession,
    *,
    settings: Settings,
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
    now: datetime,
    analytics_snapshot=None,
) -> dict[str, object]:
    del settings
    current_time = ensure_aware_utc(now)
    normalized_limit = clamp_admin_detail_limit(limit)
    snapshot = analytics_snapshot or await build_analytics_snapshot(session, now=current_time)
    promo = _serialize_promo_attribution_detail(
        snapshot.promo_attribution,
        limit=normalized_limit,
    )
    referral = _serialize_referral_attribution_detail(
        snapshot.referral_attribution,
        limit=normalized_limit,
    )
    return {
        "view": "overview",
        "view_label": "Promo / Referral",
        "limit": normalized_limit,
        "promo_attribution": promo,
        "referral_attribution": referral,
        "campaign_count": len(promo["campaigns"]),
        "top_referrer_count": len(referral["top_referrers"]),
    }

