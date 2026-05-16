from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.admin_read_model_reporting_models import (
    AdminReadModelActionSummary,
    AdminReadModelAlertSummary,
    AdminReadModelDriftSummary,
    AdminReadModelWatchlistSummary,
)
from app.services.admin_read_model_reporting_summaries import (
    _build_action_summary,
    _build_alert_summary,
    _build_drift_summary,
    _build_watchlist_summary,
)
from app.services.admin_read_models import (
    ANALYTICS_FACT_KEY_WEB_ADMIN_READ_MODELS,
    load_analytics_fact_payload,
)
from app.utils.datetime import ensure_aware_utc, utcnow


async def load_admin_read_model_alert_summary(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> AdminReadModelAlertSummary | None:
    current_time = ensure_aware_utc(now or utcnow())
    payload = await load_analytics_fact_payload(
        session,
        fact_key=ANALYTICS_FACT_KEY_WEB_ADMIN_READ_MODELS,
        fact_date=current_time.date(),
        now=current_time,
    )
    if payload is None:
        return None
    return _build_alert_summary(payload)


async def build_admin_read_model_drift_summary(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str = "owner",
    now: datetime | None = None,
    limit: int = 5,
) -> AdminReadModelDriftSummary:
    from app.services.web_admin_dashboard_read_model_sections import (
        build_web_admin_read_models_payload,
    )

    current_time = ensure_aware_utc(now or utcnow())
    payload = await build_web_admin_read_models_payload(
        session,
        settings=settings,
        viewer_role=viewer_role,
        limit=limit,
        now=current_time,
        source="live",
        view="drift",
    )
    return _build_drift_summary(payload)


async def build_admin_read_model_action_summary(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str = "owner",
    now: datetime | None = None,
    limit: int = 5,
    source: str = "snapshot",
) -> AdminReadModelActionSummary:
    from app.services.web_admin_dashboard_read_model_sections import (
        build_web_admin_read_models_payload,
    )

    current_time = ensure_aware_utc(now or utcnow())
    payload = await build_web_admin_read_models_payload(
        session,
        settings=settings,
        viewer_role=viewer_role,
        limit=limit,
        now=current_time,
        source=source,
        view="actions",
    )
    return _build_action_summary(payload)


async def build_admin_read_model_watchlist_summary(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str = "owner",
    now: datetime | None = None,
    limit: int = 5,
    source: str = "snapshot",
) -> AdminReadModelWatchlistSummary:
    from app.services.web_admin_dashboard_read_model_sections import (
        build_web_admin_read_models_payload,
    )

    current_time = ensure_aware_utc(now or utcnow())
    payload = await build_web_admin_read_models_payload(
        session,
        settings=settings,
        viewer_role=viewer_role,
        limit=limit,
        now=current_time,
        source=source,
        view="watchlist",
    )
    return _build_watchlist_summary(payload)
