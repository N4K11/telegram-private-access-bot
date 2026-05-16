from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.admin_analytics_text import render_admin_analytics_text
from app.services.admin_read_models import (
    ANALYTICS_FACT_KEY_ADMIN_ANALYTICS_TEXT,
    ANALYTICS_FACT_KEY_CABINET_ADMIN_SUMMARY,
    ANALYTICS_FACT_KEY_WEB_ADMIN_ACQUISITION,
    ANALYTICS_FACT_KEY_WEB_ADMIN_CONVERSION,
    ANALYTICS_FACT_KEY_WEB_ADMIN_DASHBOARD,
    ANALYTICS_FACT_KEY_WEB_ADMIN_PRICING,
    ANALYTICS_FACT_KEY_WEB_ADMIN_PROMO_REFERRAL,
    ANALYTICS_FACT_KEY_WEB_ADMIN_READ_MODELS,
    PAYLOAD_BUDGET_ADMIN_ACQUISITION,
    PAYLOAD_BUDGET_ADMIN_CONVERSION,
    PAYLOAD_BUDGET_ADMIN_DASHBOARD,
    PAYLOAD_BUDGET_ADMIN_LIFECYCLE,
    PAYLOAD_BUDGET_ADMIN_PRICING,
    PAYLOAD_BUDGET_ADMIN_PROMO_REFERRAL,
    PAYLOAD_BUDGET_ADMIN_READ_MODELS,
    PAYLOAD_BUDGET_ADMIN_SUMMARY,
    PAYLOAD_BUDGET_ADMIN_SUPPORT_INSIGHTS,
    QUERY_BUDGET_ADMIN_ACQUISITION,
    QUERY_BUDGET_ADMIN_CONVERSION,
    QUERY_BUDGET_ADMIN_DASHBOARD,
    QUERY_BUDGET_ADMIN_LIFECYCLE,
    QUERY_BUDGET_ADMIN_PRICING,
    QUERY_BUDGET_ADMIN_PROMO_REFERRAL,
    QUERY_BUDGET_ADMIN_READ_MODELS,
    QUERY_BUDGET_ADMIN_SUMMARY,
    QUERY_BUDGET_ADMIN_SUPPORT_INSIGHTS,
    latest_analytics_generated_at,
    latest_lifecycle_generated_at,
    latest_support_generated_at,
    snapshot_due,
    timed_read_model_payload,
    upsert_analytics_fact_payload,
    upsert_lifecycle_fact_payload,
    upsert_support_queue_fact_payload,
    with_read_model_meta,
)
from app.services.admin_roles import ADMIN_ROLES
from app.services.analytics import build_analytics_snapshot
from app.services.support import build_admin_support_inbox
from app.services.web_admin_dashboard import _build_web_admin_dashboard_payload_live
from app.services.web_admin_dashboard_analytics_sections import (
    _build_web_admin_acquisition_payload_live,
    _build_web_admin_conversion_payload_live,
    _build_web_admin_pricing_payload_live,
    _build_web_admin_promo_referral_payload_live,
)
from app.services.web_admin_dashboard_lifecycle_sections import (
    LIFECYCLE_VIEWS,
    _build_web_admin_lifecycle_payload_live,
)
from app.services.web_admin_dashboard_limits import ADMIN_DETAIL_DEFAULT_LIMIT
from app.services.web_admin_dashboard_read_model_sections import (
    _build_web_admin_read_models_payload_live,
)
from app.services.web_admin_dashboard_summary_sections import (
    _build_cabinet_admin_summary_payload_live,
)
from app.services.web_admin_dashboard_support_sections import (
    SUPPORT_INSIGHT_VIEWS,
    _build_web_admin_support_insights_payload_live,
)
from app.utils.datetime import ensure_aware_utc, utcnow


@dataclass(frozen=True, slots=True)
class AdminReadModelRefreshResult:
    generated_at: datetime
    refreshed_analytics: bool
    refreshed_lifecycle: bool
    refreshed_support: bool
    lifecycle_views: int
    support_views: int

    @property
    def has_work(self) -> bool:
        return self.refreshed_analytics or self.refreshed_lifecycle or self.refreshed_support


async def refresh_admin_read_models(
    session: AsyncSession,
    *,
    settings: Settings,
    now: datetime | None = None,
    force: bool = False,
) -> AdminReadModelRefreshResult:
    if not settings.admin_read_models_enabled:
        return AdminReadModelRefreshResult(
            generated_at=ensure_aware_utc(now or utcnow()),
            refreshed_analytics=False,
            refreshed_lifecycle=False,
            refreshed_support=False,
            lifecycle_views=0,
            support_views=0,
        )

    current_time = ensure_aware_utc(now or utcnow())
    refresh_analytics = force or await _analytics_refresh_due(
        session,
        settings=settings,
        now=current_time,
    )
    refresh_lifecycle = force or await _lifecycle_refresh_due(
        session,
        settings=settings,
        now=current_time,
    )
    refresh_support = force or await _support_refresh_due(
        session,
        settings=settings,
        now=current_time,
    )

    analytics_snapshot = None
    lifecycle_view_count = 0
    support_view_count = 0

    if refresh_analytics or refresh_lifecycle:
        analytics_snapshot = await build_analytics_snapshot(session, now=current_time)

    if refresh_analytics:
        shared_build_duration_ms = 0
        for viewer_role in ADMIN_ROLES:
            dashboard_payload = await timed_read_model_payload(
                lambda viewer_role=viewer_role: _build_web_admin_dashboard_payload_live(
                    session,
                    settings=settings,
                    viewer_role=viewer_role,
                    now=current_time,
                ),
                session=session,
                query_budget=QUERY_BUDGET_ADMIN_DASHBOARD,
                payload_budget=PAYLOAD_BUDGET_ADMIN_DASHBOARD,
                now=current_time,
            )
            shared_build_duration_ms = max(
                shared_build_duration_ms,
                int(dashboard_payload.get("build_duration_ms") or 0),
            )
            await upsert_analytics_fact_payload(
                session,
                fact_key=ANALYTICS_FACT_KEY_WEB_ADMIN_DASHBOARD,
                fact_date=current_time.date(),
                payload=dashboard_payload,
                generated_at=current_time,
                scope_key=f"role:{viewer_role}",
            )
        cabinet_summary_payload = await timed_read_model_payload(
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
        await upsert_analytics_fact_payload(
            session,
            fact_key=ANALYTICS_FACT_KEY_CABINET_ADMIN_SUMMARY,
            fact_date=current_time.date(),
            payload=cabinet_summary_payload,
            generated_at=current_time,
        )
        pricing_payload = await timed_read_model_payload(
            lambda: _build_web_admin_pricing_payload_live(
                session,
                settings=settings,
                now=current_time,
                analytics_snapshot=analytics_snapshot,
            ),
            session=session,
            query_budget=QUERY_BUDGET_ADMIN_PRICING,
            payload_budget=PAYLOAD_BUDGET_ADMIN_PRICING,
            now=current_time,
        )
        await upsert_analytics_fact_payload(
            session,
            fact_key=ANALYTICS_FACT_KEY_WEB_ADMIN_PRICING,
            fact_date=current_time.date(),
            payload=pricing_payload,
            generated_at=current_time,
        )
        acquisition_payload = await timed_read_model_payload(
            lambda: _build_web_admin_acquisition_payload_live(
                session,
                settings=settings,
                now=current_time,
                analytics_snapshot=analytics_snapshot,
            ),
            session=session,
            query_budget=QUERY_BUDGET_ADMIN_ACQUISITION,
            payload_budget=PAYLOAD_BUDGET_ADMIN_ACQUISITION,
            now=current_time,
        )
        await upsert_analytics_fact_payload(
            session,
            fact_key=ANALYTICS_FACT_KEY_WEB_ADMIN_ACQUISITION,
            fact_date=current_time.date(),
            payload=acquisition_payload,
            generated_at=current_time,
        )
        conversion_payload = await timed_read_model_payload(
            lambda: _build_web_admin_conversion_payload_live(
                session,
                settings=settings,
                now=current_time,
                analytics_snapshot=analytics_snapshot,
            ),
            session=session,
            query_budget=QUERY_BUDGET_ADMIN_CONVERSION,
            payload_budget=PAYLOAD_BUDGET_ADMIN_CONVERSION,
            now=current_time,
        )
        await upsert_analytics_fact_payload(
            session,
            fact_key=ANALYTICS_FACT_KEY_WEB_ADMIN_CONVERSION,
            fact_date=current_time.date(),
            payload=conversion_payload,
            generated_at=current_time,
        )
        promo_referral_payload = await timed_read_model_payload(
            lambda: _build_web_admin_promo_referral_payload_live(
                session,
                settings=settings,
                now=current_time,
                analytics_snapshot=analytics_snapshot,
            ),
            session=session,
            query_budget=QUERY_BUDGET_ADMIN_PROMO_REFERRAL,
            payload_budget=PAYLOAD_BUDGET_ADMIN_PROMO_REFERRAL,
            now=current_time,
        )
        await upsert_analytics_fact_payload(
            session,
            fact_key=ANALYTICS_FACT_KEY_WEB_ADMIN_PROMO_REFERRAL,
            fact_date=current_time.date(),
            payload=promo_referral_payload,
            generated_at=current_time,
        )
        if analytics_snapshot is not None:
            text_payload = with_read_model_meta(
                {"text_body": render_admin_analytics_text(analytics_snapshot)},
                generated_at=current_time,
                source="snapshot",
                build_duration_ms=shared_build_duration_ms,
                payload_budget=PAYLOAD_BUDGET_ADMIN_SUMMARY,
                now=current_time,
            )
            await upsert_analytics_fact_payload(
                session,
                fact_key=ANALYTICS_FACT_KEY_ADMIN_ANALYTICS_TEXT,
                fact_date=current_time.date(),
                payload=text_payload,
                generated_at=current_time,
            )

    if refresh_lifecycle and analytics_snapshot is not None:
        for view_key in LIFECYCLE_VIEWS:
            payload = await timed_read_model_payload(
                lambda view_key=view_key: _build_web_admin_lifecycle_payload_live(
                    session,
                    settings=settings,
                    view=view_key,
                    limit=ADMIN_DETAIL_DEFAULT_LIMIT,
                    now=current_time,
                    analytics_snapshot=analytics_snapshot,
                ),
                session=session,
                query_budget=QUERY_BUDGET_ADMIN_LIFECYCLE,
                payload_budget=PAYLOAD_BUDGET_ADMIN_LIFECYCLE,
                now=current_time,
            )
            await upsert_lifecycle_fact_payload(
                session,
                view_key=view_key,
                payload=payload,
                generated_at=current_time,
            )
            lifecycle_view_count += 1

    if refresh_support:
        inbox = await build_admin_support_inbox(
            session,
            status="open",
            limit=1,
            now=current_time,
        )
        for view_key in SUPPORT_INSIGHT_VIEWS:
            payload = await timed_read_model_payload(
                lambda view_key=view_key: _build_web_admin_support_insights_payload_live(
                    session,
                    settings=settings,
                    view=view_key,
                    limit=ADMIN_DETAIL_DEFAULT_LIMIT,
                    now=current_time,
                    support_inbox=inbox,
                ),
                session=session,
                query_budget=QUERY_BUDGET_ADMIN_SUPPORT_INSIGHTS,
                payload_budget=PAYLOAD_BUDGET_ADMIN_SUPPORT_INSIGHTS,
                now=current_time,
            )
            await upsert_support_queue_fact_payload(
                session,
                view_key=view_key,
                payload=payload,
                generated_at=current_time,
            )
            support_view_count += 1

    if refresh_analytics or refresh_lifecycle or refresh_support:
        await session.flush()
        read_models_payload = await timed_read_model_payload(
            lambda: _build_web_admin_read_models_payload_live(
                session,
                settings=settings,
                now=current_time,
            ),
            session=session,
            query_budget=QUERY_BUDGET_ADMIN_READ_MODELS,
            payload_budget=PAYLOAD_BUDGET_ADMIN_READ_MODELS,
            now=current_time,
        )
        await upsert_analytics_fact_payload(
            session,
            fact_key=ANALYTICS_FACT_KEY_WEB_ADMIN_READ_MODELS,
            fact_date=current_time.date(),
            payload=read_models_payload,
            generated_at=current_time,
        )

    if refresh_analytics or refresh_lifecycle or refresh_support:
        await session.commit()

    return AdminReadModelRefreshResult(
        generated_at=current_time,
        refreshed_analytics=refresh_analytics,
        refreshed_lifecycle=refresh_lifecycle,
        refreshed_support=refresh_support,
        lifecycle_views=lifecycle_view_count,
        support_views=support_view_count,
    )


async def _analytics_refresh_due(
    session: AsyncSession,
    *,
    settings: Settings,
    now: datetime,
) -> bool:
    latest = await latest_analytics_generated_at(session)
    if latest is None or ensure_aware_utc(latest).date() != now.date():
        return True
    return snapshot_due(
        latest,
        now=now,
        interval_minutes=settings.admin_read_models_analytics_interval_minutes,
    )


async def _lifecycle_refresh_due(
    session: AsyncSession,
    *,
    settings: Settings,
    now: datetime,
) -> bool:
    latest = await latest_lifecycle_generated_at(session)
    if latest is None or ensure_aware_utc(latest).date() != now.date():
        return True
    return snapshot_due(
        latest,
        now=now,
        interval_minutes=settings.admin_read_models_analytics_interval_minutes,
    )


async def _support_refresh_due(
    session: AsyncSession,
    *,
    settings: Settings,
    now: datetime,
) -> bool:
    latest = await latest_support_generated_at(session)
    if latest is None or ensure_aware_utc(latest).date() != now.date():
        return True
    return snapshot_due(
        latest,
        now=now,
        interval_minutes=settings.admin_read_models_support_interval_minutes,
    )
