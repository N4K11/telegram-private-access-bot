from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services import web_admin_dashboard_read_model_live as _read_model_live
from app.services.admin_read_models import (
    ANALYTICS_FACT_KEY_WEB_ADMIN_READ_MODELS,
    PAYLOAD_BUDGET_ADMIN_READ_MODELS,
    PAYLOAD_BUDGET_ADMIN_READ_MODELS_ACTIONS,
    PAYLOAD_BUDGET_ADMIN_READ_MODELS_DRIFT,
    PAYLOAD_BUDGET_ADMIN_READ_MODELS_WATCHLIST,
    QUERY_BUDGET_ADMIN_READ_MODELS,
    QUERY_BUDGET_ADMIN_READ_MODELS_ACTIONS,
    QUERY_BUDGET_ADMIN_READ_MODELS_DRIFT,
    QUERY_BUDGET_ADMIN_READ_MODELS_WATCHLIST,
    load_analytics_fact_payload,
    normalize_read_model_source,
    timed_read_model_payload,
)
from app.services.web_admin_dashboard_limits import (
    ADMIN_DETAIL_DEFAULT_LIMIT,
    clamp_admin_detail_limit,
)
from app.services.web_admin_dashboard_read_model_actions import (
    _apply_read_models_limit,
    _build_read_model_actions_payload_from_watchlist,
    _build_web_admin_read_model_watchlist_from_snapshot_payload,
    _with_overview_focus,
    _with_read_model_focus,
)
from app.services.web_admin_dashboard_read_model_descriptors import (
    ReadModelDescriptor as ReadModelDescriptor,
)
from app.services.web_admin_dashboard_read_model_descriptors import (
    _all_descriptors as _all_descriptors,
)
from app.services.web_admin_dashboard_read_model_live import (
    _build_live_admin_analytics_text_body as _build_live_admin_analytics_text_body,
)
from app.services.web_admin_dashboard_read_model_live import (
    _build_live_admin_analytics_text_payload as _build_live_admin_analytics_text_payload,
)
from app.services.web_admin_dashboard_read_model_live import (
    _build_live_descriptor_payload as _build_live_descriptor_payload,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    READ_MODEL_STATUS_BUDGET as READ_MODEL_STATUS_BUDGET,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    READ_MODEL_STATUS_IMPROVED as READ_MODEL_STATUS_IMPROVED,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    READ_MODEL_STATUS_MISSING as READ_MODEL_STATUS_MISSING,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    READ_MODEL_STATUS_OK as READ_MODEL_STATUS_OK,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    READ_MODEL_STATUS_REGRESSION as READ_MODEL_STATUS_REGRESSION,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    READ_MODEL_STATUS_STALE as READ_MODEL_STATUS_STALE,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    READ_MODEL_VIEW_ACTIONS as READ_MODEL_VIEW_ACTIONS,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    READ_MODEL_VIEW_DRIFT as READ_MODEL_VIEW_DRIFT,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    READ_MODEL_VIEW_LABELS as READ_MODEL_VIEW_LABELS,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    READ_MODEL_VIEW_OVERVIEW as READ_MODEL_VIEW_OVERVIEW,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    READ_MODEL_VIEW_WATCHLIST as READ_MODEL_VIEW_WATCHLIST,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    _available_read_model_views as _available_read_model_views,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    _bool_or_none as _bool_or_none,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    _build_drift_item as _build_drift_item,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    _build_model_item as _build_model_item,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    _decode_payload as _decode_payload,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    _drift_tone as _drift_tone,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    _int_or_default as _int_or_default,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    _leader_item as _leader_item,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    _model_scope_label as _model_scope_label,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    _normalize_read_model_view as _normalize_read_model_view,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    _read_model_note as _read_model_note,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    _read_model_severity as _read_model_severity,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    _read_model_status as _read_model_status,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    _sort_items as _sort_items,
)
from app.services.web_admin_dashboard_read_model_serializers import (
    _staleness_seconds as _staleness_seconds,
)
from app.services.web_admin_dashboard_read_model_store import (
    _load_snapshot_payload_lookups as _load_snapshot_payload_lookups,
)
from app.services.web_admin_dashboard_read_model_store import (
    _lookup_descriptor_snapshot as _lookup_descriptor_snapshot,
)
from app.utils.datetime import ensure_aware_utc, utcnow

_build_web_admin_read_model_actions_payload_live = (
    _read_model_live._build_web_admin_read_model_actions_payload_live
)
_build_web_admin_read_model_drift_payload_live = (
    _read_model_live._build_web_admin_read_model_drift_payload_live
)
_build_web_admin_read_model_watchlist_payload_live = (
    _read_model_live._build_web_admin_read_model_watchlist_payload_live
)
_build_web_admin_read_models_payload_live = (
    _read_model_live._build_web_admin_read_models_payload_live
)


async def build_web_admin_read_models_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
    now: datetime | None = None,
    source: str = "snapshot",
    view: str = READ_MODEL_VIEW_OVERVIEW,
) -> dict[str, object]:
    current_time = ensure_aware_utc(now or utcnow())
    normalized_source = normalize_read_model_source(source)
    normalized_view = _normalize_read_model_view(view)
    if normalized_view == READ_MODEL_VIEW_OVERVIEW and normalized_source != "live":
        snapshot_payload = await load_analytics_fact_payload(
            session,
            fact_key=ANALYTICS_FACT_KEY_WEB_ADMIN_READ_MODELS,
            fact_date=current_time.date(),
            now=current_time,
        )
        if snapshot_payload is not None:
            return _apply_read_models_limit(
                _with_overview_focus(snapshot_payload),
                limit=limit,
            )
    if normalized_view == READ_MODEL_VIEW_WATCHLIST and normalized_source != "live":
        snapshot_payload = await load_analytics_fact_payload(
            session,
            fact_key=ANALYTICS_FACT_KEY_WEB_ADMIN_READ_MODELS,
            fact_date=current_time.date(),
            now=current_time,
        )
        if snapshot_payload is not None:
            return _apply_read_models_limit(
                _with_read_model_focus(
                    _build_web_admin_read_model_watchlist_from_snapshot_payload(
                        snapshot_payload,
                        limit=limit,
                    ),
                    watchlist_payload=_build_web_admin_read_model_watchlist_from_snapshot_payload(
                        snapshot_payload,
                        limit=clamp_admin_detail_limit(50),
                    ),
                ),
                limit=limit,
            )
    if normalized_view == READ_MODEL_VIEW_ACTIONS and normalized_source != "live":
        snapshot_payload = await load_analytics_fact_payload(
            session,
            fact_key=ANALYTICS_FACT_KEY_WEB_ADMIN_READ_MODELS,
            fact_date=current_time.date(),
            now=current_time,
        )
        if snapshot_payload is not None:
            snapshot_watchlist_payload = (
                _build_web_admin_read_model_watchlist_from_snapshot_payload(
                    snapshot_payload,
                    limit=clamp_admin_detail_limit(50),
                )
            )
            return _apply_read_models_limit(
                _with_read_model_focus(
                    _build_read_model_actions_payload_from_watchlist(
                        snapshot_watchlist_payload,
                        limit=limit,
                    ),
                    action_payload=_build_read_model_actions_payload_from_watchlist(
                        snapshot_watchlist_payload,
                        limit=clamp_admin_detail_limit(50),
                    ),
                ),
                limit=limit,
            )
    if normalized_view == READ_MODEL_VIEW_DRIFT:
        return await timed_read_model_payload(
            lambda: _build_web_admin_read_model_drift_payload_live(
                session,
                settings=settings,
                viewer_role=viewer_role,
                limit=limit,
                now=current_time,
            ),
            session=session,
            query_budget=QUERY_BUDGET_ADMIN_READ_MODELS_DRIFT,
            payload_budget=PAYLOAD_BUDGET_ADMIN_READ_MODELS_DRIFT,
            now=current_time,
        )
    if normalized_view == READ_MODEL_VIEW_WATCHLIST:
        return await timed_read_model_payload(
            lambda: _build_web_admin_read_model_watchlist_payload_live(
                session,
                settings=settings,
                viewer_role=viewer_role,
                limit=limit,
                now=current_time,
            ),
            session=session,
            query_budget=QUERY_BUDGET_ADMIN_READ_MODELS_WATCHLIST,
            payload_budget=PAYLOAD_BUDGET_ADMIN_READ_MODELS_WATCHLIST,
            now=current_time,
        )
    if normalized_view == READ_MODEL_VIEW_ACTIONS:
        return await timed_read_model_payload(
            lambda: _build_web_admin_read_model_actions_payload_live(
                session,
                settings=settings,
                viewer_role=viewer_role,
                limit=limit,
                now=current_time,
            ),
            session=session,
            query_budget=QUERY_BUDGET_ADMIN_READ_MODELS_ACTIONS,
            payload_budget=PAYLOAD_BUDGET_ADMIN_READ_MODELS_ACTIONS,
            now=current_time,
        )
    return await timed_read_model_payload(
        lambda: _build_web_admin_read_models_payload_live(
            session,
            settings=settings,
            limit=limit,
            now=current_time,
        ),
        session=session,
        query_budget=QUERY_BUDGET_ADMIN_READ_MODELS,
        payload_budget=PAYLOAD_BUDGET_ADMIN_READ_MODELS,
        now=current_time,
    )
