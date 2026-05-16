from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.db.models import Base, Channel, SupportMessage, SupportTicket, User
from app.db.session import create_async_engine, create_session_factory
from app.runtime_state import record_critical_error, reset_runtime_state
from app.services.admin_home import build_admin_home_snapshot
from app.services.admin_read_model_reporting import (
    AdminReadModelDriftSummary,
    AdminReadModelWatchlistSummary,
)
from app.services.admin_read_models import upsert_analytics_fact_payload
from app.services.admin_roles import ROLE_OWNER


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


@pytest.mark.asyncio
async def test_admin_home_snapshot_collects_badges_and_summary(session) -> None:
    reset_runtime_state()
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "use_webhook": True,
            "public_webhook_url": "https://example.com",
            "webhook_secret_token": "secret-token",
        }
    )
    now = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)
    user = User(telegram_id=77, first_name="Guest")
    session.add(user)
    await session.flush()
    session.add(
        Channel(
            title="Private Channel",
            telegram_chat_id="-1001",
            is_active=True,
            invite_users_permission=False,
            ban_users_permission=True,
        )
    )
    await session.flush()
    ticket = SupportTicket(
        user_id=user.id,
        category="payment",
        status="open",
        last_user_message_at=now - timedelta(hours=1),
        last_admin_message_at=None,
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=2),
    )
    session.add(ticket)
    await session.flush()
    session.add(
        SupportMessage(
            ticket_id=ticket.id,
            sender_user_id=user.id,
            body="Need help",
            is_admin=False,
            created_at=now - timedelta(days=2),
        )
    )
    await session.commit()
    record_critical_error(
        "channel_guard_alert",
        "Channel permissions drift detected",
        source="channel_guard",
        at=now,
    )

    snapshot = await build_admin_home_snapshot(
        session,
        role=ROLE_OWNER,
        settings=settings,
        now=now,
    )

    assert snapshot.section_badges == {"support": 1, "diagnostics": 1}
    assert "Runtime: webhook" in snapshot.summary_block
    assert "Mini App: /cabinet" in snapshot.summary_block
    assert "Read-model snapshots: missing" in snapshot.summary_block
    assert "Telegram API error" not in snapshot.summary_block

    reset_runtime_state()


@pytest.mark.asyncio
async def test_admin_home_snapshot_includes_read_model_action_digest(session) -> None:
    reset_runtime_state()
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "use_webhook": True,
            "public_webhook_url": "https://example.com",
            "webhook_secret_token": "secret-token",
        }
    )
    now = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)
    await upsert_analytics_fact_payload(
        session,
        fact_key="web_admin_read_models",
        fact_date=now.date(),
        payload={
            "view": "overview",
            "source": "snapshot",
            "generated_at": now.isoformat(),
            "generated_at_label": "03.05.2026 12:00",
            "staleness_seconds": 0,
            "tracked_count": 2,
            "available_count": 2,
            "missing_count": 0,
            "stale_count": 0,
            "budget_exceeded_count": 1,
            "top_attention_item": {
                "label": "Pricing / Offers",
                "status_label": "Budget exceeded",
                "note": "Query budget exceeded",
            },
            "items": [
                {
                    "id": "analytics:web_admin_pricing",
                    "label": "Pricing / Offers",
                    "status": "budget",
                    "status_label": "Budget exceeded",
                    "query_count": 6,
                    "query_budget": 3,
                    "payload_bytes": 9500,
                    "payload_budget": 28000,
                    "build_duration_ms": 21,
                    "staleness_seconds": 0,
                    "severity_score": 1000,
                    "note": "Query budget exceeded",
                },
                {
                    "id": "analytics:cabinet_admin_summary",
                    "label": "Admin summary",
                    "status": "ok",
                    "status_label": "Healthy",
                    "query_count": 1,
                    "query_budget": 6,
                    "payload_bytes": 1200,
                    "payload_budget": 18000,
                    "build_duration_ms": 4,
                    "staleness_seconds": 0,
                    "severity_score": 10,
                    "note": "Within cadence.",
                },
            ],
        },
        generated_at=now,
    )
    await session.commit()

    snapshot = await build_admin_home_snapshot(
        session,
        role=ROLE_OWNER,
        settings=settings,
        now=now,
    )

    assert "Read-model alerts: 1" in snapshot.summary_block
    assert "Read-model summary:" in snapshot.summary_block
    assert "focus snapshot watch: Pricing / Offers" in snapshot.summary_block
    assert "actions surfaces" in snapshot.summary_block

    reset_runtime_state()


@pytest.mark.asyncio
async def test_admin_home_snapshot_includes_read_model_drift_summary(
    session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_runtime_state()
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "use_webhook": True,
            "public_webhook_url": "https://example.com",
            "webhook_secret_token": "secret-token",
        }
    )
    now = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)
    await upsert_analytics_fact_payload(
        session,
        fact_key="web_admin_read_models",
        fact_date=now.date(),
        payload={
            "view": "overview",
            "source": "snapshot",
            "generated_at": now.isoformat(),
            "generated_at_label": "03.05.2026 12:00",
            "staleness_seconds": 0,
            "tracked_count": 1,
            "available_count": 1,
            "missing_count": 0,
            "stale_count": 0,
            "budget_exceeded_count": 0,
            "items": [
                {
                    "id": "analytics:cabinet_admin_summary",
                    "label": "Admin summary",
                    "status": "ok",
                    "status_label": "Healthy",
                    "query_count": 1,
                    "query_budget": 6,
                    "payload_bytes": 1200,
                    "payload_budget": 18000,
                    "build_duration_ms": 4,
                    "staleness_seconds": 0,
                    "severity_score": 10,
                    "note": "Within cadence.",
                }
            ],
        },
        generated_at=now,
    )
    await session.commit()

    async def fake_build_drift_summary(*args, **kwargs) -> AdminReadModelDriftSummary:
        return AdminReadModelDriftSummary(
            source="live",
            generated_at_label="03.05.2026 12:00",
            staleness_seconds=0,
            compared_count=3,
            missing_snapshot_count=0,
            regression_count=1,
            improvement_count=0,
            budget_regression_count=1,
            query_regression_count=1,
            payload_regression_count=0,
            build_regression_count=0,
            top_regression_label="Pricing / Offers",
            top_regression_note="Live build drifted above snapshot baseline.",
            top_budget_regression_label="Pricing / Offers",
            top_query_regression_label="Pricing / Offers",
            top_payload_regression_label=None,
            top_build_regression_label=None,
            top_items=(),
        )

    monkeypatch.setattr(
        "app.services.admin_home.build_admin_read_model_drift_summary",
        fake_build_drift_summary,
    )

    snapshot = await build_admin_home_snapshot(
        session,
        role=ROLE_OWNER,
        settings=settings,
        now=now,
    )

    assert "Read-model summary:" in snapshot.summary_block
    assert "focus live drift: Pricing / Offers" in snapshot.summary_block
    assert "drift regressions 1" in snapshot.summary_block

    reset_runtime_state()


@pytest.mark.asyncio
async def test_admin_home_snapshot_includes_read_model_watch_summary(
    session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_runtime_state()
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "use_webhook": True,
            "public_webhook_url": "https://example.com",
            "webhook_secret_token": "secret-token",
        }
    )
    now = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)
    await upsert_analytics_fact_payload(
        session,
        fact_key="web_admin_read_models",
        fact_date=now.date(),
        payload={
            "view": "overview",
            "source": "snapshot",
            "generated_at": now.isoformat(),
            "generated_at_label": "03.05.2026 12:00",
            "staleness_seconds": 0,
            "tracked_count": 1,
            "available_count": 1,
            "missing_count": 0,
            "stale_count": 0,
            "budget_exceeded_count": 0,
            "items": [],
        },
        generated_at=now,
    )
    await session.commit()

    async def fake_build_watchlist_summary(*args, **kwargs) -> AdminReadModelWatchlistSummary:
        return AdminReadModelWatchlistSummary(
            source="snapshot",
            generated_at_label="03.05.2026 12:00",
            staleness_seconds=0,
            tracked_count=3,
            alert_item_count=2,
            missing_count=0,
            stale_count=1,
            budget_exceeded_count=1,
            regression_count=0,
            top_attention_label="Support insights",
            top_attention_kind_label="Stale snapshot",
            top_attention_note=None,
            top_regression_label=None,
            top_budget_label="Pricing / Offers",
            top_items=(),
        )

    monkeypatch.setattr(
        "app.services.admin_home.build_admin_read_model_watchlist_summary",
        fake_build_watchlist_summary,
    )

    snapshot = await build_admin_home_snapshot(
        session,
        role=ROLE_OWNER,
        settings=settings,
        now=now,
    )

    assert "Read-model summary:" in snapshot.summary_block
    assert "focus snapshot watch: Support insights" in snapshot.summary_block
    assert "watch alerts 2" in snapshot.summary_block

    reset_runtime_state()
