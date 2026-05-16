from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import User
from app.db.session import create_async_engine, create_session_factory
from app.services.admin_read_models import (
    load_analytics_fact_payload,
    normalize_read_model_source,
    snapshot_due,
    timed_read_model_payload,
    upsert_analytics_fact_payload,
)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


async def test_timed_read_model_payload_adds_runtime_metadata() -> None:
    generated_at = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)

    payload = await timed_read_model_payload(lambda: _payload({"value": 42}), now=generated_at)

    assert payload["value"] == 42
    assert payload["source"] == "live"
    assert payload["generated_at"] == generated_at.isoformat()
    assert payload["staleness_seconds"] == 0
    assert isinstance(payload["build_duration_ms"], int)
    assert payload["build_duration_ms"] >= 0
    assert payload["query_count"] == 0
    assert payload["payload_bytes"] > 0
    assert "payload_budget" not in payload
    assert "payload_budget_ok" not in payload
    assert "query_budget" not in payload
    assert "query_budget_ok" not in payload


async def test_timed_read_model_payload_tracks_query_count_and_budget(
    session: AsyncSession,
) -> None:
    generated_at = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
    session.add(
        User(
            telegram_id=12345,
            username="owner",
            first_name="Owner",
            is_admin=True,
            role="owner",
        )
    )
    await session.commit()

    async def _builder() -> dict[str, object]:
        result = await session.execute(select(User).where(User.telegram_id == 12345))
        user = result.scalar_one()
        return {"telegram_id": user.telegram_id}

    payload = await timed_read_model_payload(
        _builder,
        session=session,
        query_budget=3,
        payload_budget=1024,
        now=generated_at,
    )

    assert payload["telegram_id"] == 12345
    assert payload["query_count"] == 1
    assert payload["query_budget"] == 3
    assert payload["query_budget_ok"] is True
    assert payload["payload_bytes"] > 0
    assert payload["payload_budget"] == 1024
    assert payload["payload_budget_ok"] is True


async def test_analytics_fact_payload_round_trip_is_role_scoped(
    session: AsyncSession,
) -> None:
    generated_at = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
    payload = await timed_read_model_payload(lambda: _payload({"summary": "ok"}), now=generated_at)
    await upsert_analytics_fact_payload(
        session,
        fact_key="web_admin_dashboard",
        fact_date=date(2026, 5, 6),
        scope_key="role:owner",
        payload=payload,
        generated_at=generated_at,
    )
    await session.commit()

    owner_payload = await load_analytics_fact_payload(
        session,
        fact_key="web_admin_dashboard",
        fact_date=date(2026, 5, 6),
        scope_key="role:owner",
        now=generated_at + timedelta(minutes=2),
    )
    analyst_payload = await load_analytics_fact_payload(
        session,
        fact_key="web_admin_dashboard",
        fact_date=date(2026, 5, 6),
        scope_key="role:analyst",
        now=generated_at + timedelta(minutes=2),
    )

    assert owner_payload is not None
    assert owner_payload["summary"] == "ok"
    assert owner_payload["source"] == "snapshot"
    assert owner_payload["staleness_seconds"] == 120
    assert owner_payload["query_count"] == 0
    assert owner_payload["payload_bytes"] > 0
    assert owner_payload.get("payload_budget") is None
    assert analyst_payload is None


def test_snapshot_due_uses_interval_budget() -> None:
    now = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)

    assert snapshot_due(None, now=now, interval_minutes=5) is True
    assert (
        snapshot_due(
            now - timedelta(minutes=4, seconds=59),
            now=now,
            interval_minutes=5,
        )
        is False
    )
    assert snapshot_due(now - timedelta(minutes=5), now=now, interval_minutes=5) is True


def test_normalize_read_model_source_defaults_to_snapshot() -> None:
    assert normalize_read_model_source(None) == "snapshot"
    assert normalize_read_model_source("live") == "live"
    assert normalize_read_model_source("snapshot") == "snapshot"
    assert normalize_read_model_source("broken") == "snapshot"


async def _payload(value: dict[str, object]) -> dict[str, object]:
    return value
