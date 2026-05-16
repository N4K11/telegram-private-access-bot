from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from time import perf_counter

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalyticsDailyFact, LifecycleCampaignFact, SupportQueueFact
from app.utils.datetime import ensure_aware_utc, utcnow

READ_MODEL_SOURCE_LIVE = "live"
READ_MODEL_SOURCE_SNAPSHOT = "snapshot"

ANALYTICS_FACT_KEY_WEB_ADMIN_DASHBOARD = "web_admin_dashboard"
ANALYTICS_FACT_KEY_CABINET_ADMIN_SUMMARY = "cabinet_admin_summary"
ANALYTICS_FACT_KEY_ADMIN_ANALYTICS_TEXT = "admin_analytics_text"
ANALYTICS_FACT_KEY_WEB_ADMIN_CONVERSION = "web_admin_conversion"
ANALYTICS_FACT_KEY_WEB_ADMIN_PRICING = "web_admin_pricing"
ANALYTICS_FACT_KEY_WEB_ADMIN_ACQUISITION = "web_admin_acquisition"
ANALYTICS_FACT_KEY_WEB_ADMIN_PROMO_REFERRAL = "web_admin_promo_referral"
ANALYTICS_FACT_KEY_WEB_ADMIN_READ_MODELS = "web_admin_read_models"

QUERY_BUDGET_ADMIN_DASHBOARD = 12
QUERY_BUDGET_ADMIN_LIFECYCLE = 3
QUERY_BUDGET_ADMIN_SUPPORT_INSIGHTS = 3
QUERY_BUDGET_ADMIN_PRICING = 3
QUERY_BUDGET_ADMIN_ACQUISITION = 3
QUERY_BUDGET_ADMIN_CONVERSION = 3
QUERY_BUDGET_ADMIN_PROMO_REFERRAL = 3
QUERY_BUDGET_ADMIN_SUMMARY = 6
QUERY_BUDGET_ADMIN_READ_MODELS = 3
QUERY_BUDGET_ADMIN_READ_MODELS_DRIFT = 80
QUERY_BUDGET_ADMIN_READ_MODELS_WATCHLIST = 80
QUERY_BUDGET_ADMIN_READ_MODELS_ACTIONS = 80

PAYLOAD_BUDGET_ADMIN_DASHBOARD = 48_000
PAYLOAD_BUDGET_ADMIN_LIFECYCLE = 32_000
PAYLOAD_BUDGET_ADMIN_SUPPORT_INSIGHTS = 28_000
PAYLOAD_BUDGET_ADMIN_PRICING = 24_000
PAYLOAD_BUDGET_ADMIN_ACQUISITION = 24_000
PAYLOAD_BUDGET_ADMIN_CONVERSION = 24_000
PAYLOAD_BUDGET_ADMIN_PROMO_REFERRAL = 24_000
PAYLOAD_BUDGET_ADMIN_SUMMARY = 18_000
PAYLOAD_BUDGET_ADMIN_READ_MODELS = 28_000
PAYLOAD_BUDGET_ADMIN_READ_MODELS_DRIFT = 48_000
PAYLOAD_BUDGET_ADMIN_READ_MODELS_WATCHLIST = 36_000
PAYLOAD_BUDGET_ADMIN_READ_MODELS_ACTIONS = 40_000


@dataclass(slots=True)
class ReadModelQueryMetrics:
    query_count: int = 0


def _estimate_payload_bytes(payload: dict[str, object]) -> int:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return len(encoded)


def _payload_query_count(payload: dict[str, object]) -> int:
    raw_value = payload.get("query_count")
    try:
        return max(0, int(raw_value))
    except (TypeError, ValueError):
        return 0


def _payload_payload_bytes(payload: dict[str, object]) -> int:
    raw_value = payload.get("payload_bytes")
    try:
        return max(0, int(raw_value))
    except (TypeError, ValueError):
        return max(0, _estimate_payload_bytes(payload))


def _payload_query_budget(payload: dict[str, object]) -> int | None:
    raw_value = payload.get("query_budget")
    try:
        return max(0, int(raw_value))
    except (TypeError, ValueError):
        return None


def _payload_query_budget_ok(payload: dict[str, object]) -> bool | None:
    raw_value = payload.get("query_budget_ok")
    if isinstance(raw_value, bool):
        return raw_value
    return None


def _payload_payload_budget(payload: dict[str, object]) -> int | None:
    raw_value = payload.get("payload_budget")
    try:
        return max(0, int(raw_value))
    except (TypeError, ValueError):
        return None


def _payload_payload_budget_ok(payload: dict[str, object]) -> bool | None:
    raw_value = payload.get("payload_budget_ok")
    if isinstance(raw_value, bool):
        return raw_value
    return None


def _attach_query_counter(session: AsyncSession) -> tuple[ReadModelQueryMetrics, Callable]:
    metrics = ReadModelQueryMetrics()

    def _listener(*_args, **_kwargs) -> None:
        metrics.query_count += 1

    event.listen(session.sync_session, "do_orm_execute", _listener)
    return metrics, _listener


def normalize_read_model_source(raw_value: str | None) -> str:
    normalized = (raw_value or READ_MODEL_SOURCE_SNAPSHOT).strip().lower()
    if normalized not in {READ_MODEL_SOURCE_LIVE, READ_MODEL_SOURCE_SNAPSHOT}:
        return READ_MODEL_SOURCE_SNAPSHOT
    return normalized


def with_read_model_meta(
    payload: dict[str, object],
    *,
    generated_at: datetime,
    source: str,
    build_duration_ms: int,
    query_count: int | None = None,
    payload_bytes: int | None = None,
    query_budget: int | None = None,
    query_budget_ok: bool | None = None,
    payload_budget: int | None = None,
    payload_budget_ok: bool | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    current_time = ensure_aware_utc(now or generated_at)
    normalized_generated_at = ensure_aware_utc(generated_at)
    response = dict(payload)
    response["generated_at"] = normalized_generated_at.isoformat()
    response["source"] = source
    response["build_duration_ms"] = max(0, int(build_duration_ms))
    response["staleness_seconds"] = max(
        0,
        int((current_time - normalized_generated_at).total_seconds()),
    )
    if query_count is not None:
        response["query_count"] = max(0, int(query_count))
    if query_budget is not None:
        response["query_budget"] = max(0, int(query_budget))
    if query_budget_ok is not None:
        response["query_budget_ok"] = bool(query_budget_ok)
    measured_payload_bytes = (
        max(0, int(payload_bytes))
        if payload_bytes is not None
        else _estimate_payload_bytes(response)
    )
    response["payload_bytes"] = measured_payload_bytes
    if payload_budget is not None:
        response["payload_budget"] = max(0, int(payload_budget))
    if payload_budget_ok is not None:
        response["payload_budget_ok"] = bool(payload_budget_ok)
    elif payload_budget is not None:
        response["payload_budget_ok"] = measured_payload_bytes <= max(0, int(payload_budget))
    return response


async def timed_read_model_payload(
    builder: Callable[[], Awaitable[dict[str, object]]],
    *,
    session: AsyncSession | None = None,
    query_budget: int | None = None,
    payload_budget: int | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    generated_at = ensure_aware_utc(now or utcnow())
    started_at = perf_counter()
    metrics: ReadModelQueryMetrics | None = None
    listener = None
    if session is not None:
        metrics, listener = _attach_query_counter(session)
    try:
        payload = await builder()
    finally:
        if session is not None and listener is not None:
            event.remove(session.sync_session, "do_orm_execute", listener)
    build_duration_ms = round((perf_counter() - started_at) * 1000)
    query_count = metrics.query_count if metrics is not None else 0
    return with_read_model_meta(
        payload,
        generated_at=generated_at,
        source=READ_MODEL_SOURCE_LIVE,
        build_duration_ms=build_duration_ms,
        query_count=query_count,
        query_budget=query_budget,
        query_budget_ok=(
            None if query_budget is None or query_count is None else query_count <= query_budget
        ),
        payload_budget=payload_budget,
        now=generated_at,
    )


def _encode_payload(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _decode_payload(raw_payload: str) -> dict[str, object]:
    data = json.loads(raw_payload)
    return data if isinstance(data, dict) else {}


def _payload_generated_at(payload: dict[str, object], *, fallback: datetime) -> datetime:
    raw_value = payload.get("generated_at")
    if isinstance(raw_value, str):
        try:
            return ensure_aware_utc(datetime.fromisoformat(raw_value))
        except ValueError:
            pass
    return ensure_aware_utc(fallback)


def _payload_build_duration_ms(payload: dict[str, object]) -> int:
    raw_value = payload.get("build_duration_ms")
    try:
        return max(0, int(raw_value))
    except (TypeError, ValueError):
        return 0


def _restore_snapshot_payload(
    payload: dict[str, object],
    *,
    source: str,
    generated_at: datetime,
    now: datetime | None = None,
) -> dict[str, object]:
    return with_read_model_meta(
        payload,
        generated_at=_payload_generated_at(payload, fallback=generated_at),
        source=source,
        build_duration_ms=_payload_build_duration_ms(payload),
        query_count=_payload_query_count(payload),
        payload_bytes=_payload_payload_bytes(payload),
        query_budget=_payload_query_budget(payload),
        query_budget_ok=_payload_query_budget_ok(payload),
        payload_budget=_payload_payload_budget(payload),
        payload_budget_ok=_payload_payload_budget_ok(payload),
        now=now or utcnow(),
    )


async def upsert_analytics_fact_payload(
    session: AsyncSession,
    *,
    fact_key: str,
    fact_date: date,
    payload: dict[str, object],
    generated_at: datetime,
    product_channel_id: int | None = None,
    scope_key: str | None = None,
) -> None:
    normalized_scope_key = (
        scope_key.strip()
        if isinstance(scope_key, str) and scope_key.strip()
        else (str(product_channel_id) if product_channel_id is not None else "all")
    )
    row = (
        await session.execute(
            select(AnalyticsDailyFact).where(
                AnalyticsDailyFact.fact_date == fact_date,
                AnalyticsDailyFact.fact_key == fact_key,
                AnalyticsDailyFact.scope_key == normalized_scope_key,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = AnalyticsDailyFact(
            fact_date=fact_date,
            fact_key=fact_key,
            scope_key=normalized_scope_key,
            product_channel_id=product_channel_id,
            payload=_encode_payload(payload),
            generated_at=ensure_aware_utc(generated_at),
        )
        session.add(row)
        return
    row.product_channel_id = product_channel_id
    row.payload = _encode_payload(payload)
    row.generated_at = ensure_aware_utc(generated_at)


async def load_analytics_fact_payload(
    session: AsyncSession,
    *,
    fact_key: str,
    fact_date: date,
    product_channel_id: int | None = None,
    scope_key: str | None = None,
    now: datetime | None = None,
) -> dict[str, object] | None:
    normalized_scope_key = (
        scope_key.strip()
        if isinstance(scope_key, str) and scope_key.strip()
        else (str(product_channel_id) if product_channel_id is not None else "all")
    )
    row = (
        await session.execute(
            select(AnalyticsDailyFact).where(
                AnalyticsDailyFact.fact_date == fact_date,
                AnalyticsDailyFact.fact_key == fact_key,
                AnalyticsDailyFact.scope_key == normalized_scope_key,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return _restore_snapshot_payload(
        _decode_payload(row.payload),
        source=READ_MODEL_SOURCE_SNAPSHOT,
        generated_at=row.generated_at,
        now=now,
    )


async def upsert_lifecycle_fact_payload(
    session: AsyncSession,
    *,
    view_key: str,
    payload: dict[str, object],
    generated_at: datetime,
) -> None:
    row = (
        await session.execute(
            select(LifecycleCampaignFact).where(LifecycleCampaignFact.view_key == view_key)
        )
    ).scalar_one_or_none()
    if row is None:
        row = LifecycleCampaignFact(
            view_key=view_key,
            payload=_encode_payload(payload),
            generated_at=ensure_aware_utc(generated_at),
        )
        session.add(row)
        return
    row.payload = _encode_payload(payload)
    row.generated_at = ensure_aware_utc(generated_at)


async def load_lifecycle_fact_payload(
    session: AsyncSession,
    *,
    view_key: str,
    now: datetime | None = None,
) -> dict[str, object] | None:
    row = (
        await session.execute(
            select(LifecycleCampaignFact).where(LifecycleCampaignFact.view_key == view_key)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return _restore_snapshot_payload(
        _decode_payload(row.payload),
        source=READ_MODEL_SOURCE_SNAPSHOT,
        generated_at=row.generated_at,
        now=now,
    )


async def upsert_support_queue_fact_payload(
    session: AsyncSession,
    *,
    view_key: str,
    payload: dict[str, object],
    generated_at: datetime,
) -> None:
    row = (
        await session.execute(
            select(SupportQueueFact).where(SupportQueueFact.view_key == view_key)
        )
    ).scalar_one_or_none()
    if row is None:
        row = SupportQueueFact(
            view_key=view_key,
            payload=_encode_payload(payload),
            generated_at=ensure_aware_utc(generated_at),
        )
        session.add(row)
        return
    row.payload = _encode_payload(payload)
    row.generated_at = ensure_aware_utc(generated_at)


async def load_support_queue_fact_payload(
    session: AsyncSession,
    *,
    view_key: str,
    now: datetime | None = None,
) -> dict[str, object] | None:
    row = (
        await session.execute(
            select(SupportQueueFact).where(SupportQueueFact.view_key == view_key)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return _restore_snapshot_payload(
        _decode_payload(row.payload),
        source=READ_MODEL_SOURCE_SNAPSHOT,
        generated_at=row.generated_at,
        now=now,
    )


async def latest_analytics_generated_at(session: AsyncSession) -> datetime | None:
    return (
        await session.execute(select(func.max(AnalyticsDailyFact.generated_at)))
    ).scalar_one_or_none()


async def latest_lifecycle_generated_at(session: AsyncSession) -> datetime | None:
    return (
        await session.execute(select(func.max(LifecycleCampaignFact.generated_at)))
    ).scalar_one_or_none()


async def latest_support_generated_at(session: AsyncSession) -> datetime | None:
    return (
        await session.execute(select(func.max(SupportQueueFact.generated_at)))
    ).scalar_one_or_none()


def snapshot_due(
    latest_generated_at: datetime | None,
    *,
    now: datetime,
    interval_minutes: int,
) -> bool:
    if latest_generated_at is None:
        return True
    return (ensure_aware_utc(now) - ensure_aware_utc(latest_generated_at)).total_seconds() >= (
        interval_minutes * 60
    )
