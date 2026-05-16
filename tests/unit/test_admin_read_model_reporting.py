from __future__ import annotations

from datetime import UTC, datetime

from app.config import Settings
from app.services.admin_read_model_reporting import (
    AdminReadModelActionItemSummary,
    AdminReadModelActionSummary,
    AdminReadModelDriftSummary,
    AdminReadModelOperatorDigest,
    AdminReadModelWatchItemSummary,
    AdminReadModelWatchlistSummary,
    build_admin_read_model_action_digest,
    build_admin_read_model_drift_digest,
    build_admin_read_model_drift_summary,
    build_admin_read_model_focus_summary,
    build_admin_read_model_operator_digest,
    build_admin_read_model_snapshot_digest_payload,
    build_admin_read_model_snapshot_focus_payload,
    build_admin_read_model_snapshot_operator_payload,
    build_admin_read_model_watchlist_digest,
)


async def test_build_admin_read_model_drift_summary_keeps_top_regression_items(
    monkeypatch,
) -> None:
    async def fake_build_web_admin_read_models_payload(
        session,
        *,
        settings,
        viewer_role,
        limit,
        now,
        source,
        view,
    ) -> dict[str, object]:
        assert viewer_role == "owner"
        assert source == "live"
        assert view == "drift"
        return {
            "view": "drift",
            "source": "live",
            "generated_at_label": "06.05.2026 12:00",
            "staleness_seconds": 0,
            "compared_count": 3,
            "missing_snapshot_count": 0,
            "regression_count": 2,
            "improvement_count": 1,
            "budget_regression_count": 1,
            "query_regression_count": 1,
            "payload_regression_count": 2,
            "build_regression_count": 1,
            "top_regression_item": {
                "label": "Pricing / Offers",
                "note": (
                    "Live build drifted above snapshot baseline: "
                    "budget regression, +3 queries, +2048 bytes."
                ),
            },
            "top_budget_regression_item": {"label": "Support insights"},
            "top_query_regression_item": {"label": "Pricing / Offers"},
            "top_payload_regression_item": {"label": "Support insights"},
            "top_build_regression_item": {"label": "Admin summary"},
            "items": [
                {
                    "label": "Pricing / Offers",
                    "note": (
                        "Live build drifted above snapshot baseline: "
                        "budget regression, +3 queries, +2048 bytes."
                    ),
                    "query_count_delta": 3,
                    "payload_bytes_delta": 2048,
                    "build_duration_ms_delta": 0,
                    "budget_regressed": True,
                },
                {
                    "label": "Support insights",
                    "note": "Live build drifted above snapshot baseline: +512 bytes, +12 ms.",
                    "query_count_delta": 0,
                    "payload_bytes_delta": 512,
                    "build_duration_ms_delta": 12,
                    "budget_regressed": False,
                },
                {
                    "label": "Promo / Referral",
                    "note": "Live build is lighter than the stored snapshot baseline: -1 queries.",
                    "query_count_delta": -1,
                    "payload_bytes_delta": 0,
                    "build_duration_ms_delta": 0,
                    "budget_regressed": False,
                },
            ],
        }

    monkeypatch.setattr(
        "app.services.web_admin_dashboard_read_model_sections.build_web_admin_read_models_payload",
        fake_build_web_admin_read_models_payload,
    )
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [42]})

    summary = await build_admin_read_model_drift_summary(
        None,
        settings=settings,
        viewer_role="owner",
        now=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        limit=5,
    )

    assert summary.has_regressions is True
    assert summary.top_regression_label == "Pricing / Offers"
    assert summary.top_budget_regression_label == "Support insights"
    assert summary.top_query_regression_label == "Pricing / Offers"
    assert summary.top_payload_regression_label == "Support insights"
    assert summary.top_build_regression_label == "Admin summary"
    assert len(summary.top_items) == 2
    assert summary.top_items[0].budget_regressed is True
    assert summary.top_items[0].query_count_delta == 3
    assert summary.top_items[1].payload_bytes_delta == 512
    assert summary.top_items[1].build_duration_ms_delta == 12

    digest = build_admin_read_model_drift_digest(summary, max_items=3)
    assert "regressions 2" in digest.summary_line
    assert "budget 1" in digest.summary_line
    assert "query 1" in digest.summary_line
    assert "payload 2" in digest.summary_line
    assert "build 1" in digest.extended_summary_line
    assert digest.top_label == "Pricing / Offers"
    assert "budget regression" in digest.top_detail
    assert "+3 queries" in digest.top_detail
    assert "+2048 bytes" in digest.top_detail
    assert "Pricing / Offers" in digest.item_lines[0]
    assert "+3 queries" in digest.item_lines[0]
    assert "+2048 bytes" in digest.item_lines[0]
    assert "Support insights" in digest.item_lines[1]
    assert "+512 bytes" in digest.item_lines[1]
    assert "+12 ms" in digest.item_lines[1]


def test_build_admin_read_model_action_digest_prefers_matching_top_item() -> None:
    summary = AdminReadModelActionSummary(
        source="snapshot",
        generated_at_label="06.05.2026 12:00",
        staleness_seconds=0,
        tracked_count=4,
        surface_count=3,
        alert_item_count=2,
        snapshot_action_count=1,
        budget_action_count=1,
        drift_action_count=1,
        top_action_label="Support insights",
        top_action_note=None,
        top_budget_action_label="Pricing / Offers",
        top_drift_action_label="Support insights",
        top_items=(
            AdminReadModelActionItemSummary(
                label="Support insights",
                action_label="refresh snapshot",
                action_note="force a refresh",
                issue_summary_label="snapshot stale",
                action_category_label="snapshot",
            ),
            AdminReadModelActionItemSummary(
                label="Pricing / Offers",
                action_label="review query budget",
                action_note=None,
                issue_summary_label="query budget exceeded",
                action_category_label="budget",
            ),
        ),
    )

    digest = build_admin_read_model_action_digest(summary, max_items=3)

    assert "surfaces 3" in digest.summary_line
    assert "snapshot 1" in digest.summary_line
    assert "budget 1" in digest.summary_line
    assert "drift 1" in digest.summary_line
    assert digest.top_label == "Support insights"
    assert "refresh snapshot" in digest.top_detail
    assert "snapshot stale" in digest.top_detail
    assert "Support insights" in digest.item_lines[0]
    assert "refresh snapshot" in digest.item_lines[0]
    assert "snapshot stale" in digest.item_lines[0]
    assert "Pricing / Offers" in digest.item_lines[1]
    assert "review query budget" in digest.item_lines[1]
    assert "query budget exceeded" in digest.item_lines[1]


def test_build_admin_read_model_watchlist_digest_uses_top_attention() -> None:
    summary = AdminReadModelWatchlistSummary(
        source="snapshot",
        generated_at_label="06.05.2026 12:00",
        staleness_seconds=0,
        tracked_count=5,
        alert_item_count=3,
        missing_count=1,
        stale_count=1,
        budget_exceeded_count=1,
        regression_count=0,
        top_attention_label="Support insights",
        top_attention_kind_label="Stale snapshot",
        top_attention_note=None,
        top_regression_label=None,
        top_budget_label="Pricing / Offers",
        top_items=(
            AdminReadModelWatchItemSummary(
                label="Support insights",
                watch_kind_label="Stale snapshot",
                source_mode_label="Snapshot",
                note=None,
                status_label="Stale",
            ),
            AdminReadModelWatchItemSummary(
                label="Pricing / Offers",
                watch_kind_label="Budget exceeded",
                source_mode_label="Snapshot",
                note="Query budget exceeded: 6 > 3.",
                status_label="Budget exceeded",
            ),
        ),
    )

    digest = build_admin_read_model_watchlist_digest(summary, max_items=3)

    assert "alerts 3" in digest.summary_line
    assert "missing 1" in digest.summary_line
    assert "stale 1" in digest.summary_line
    assert "budget 1" in digest.summary_line
    assert "drift 0" in digest.summary_line
    assert digest.top_label == "Support insights"
    assert "Stale snapshot" in digest.top_detail
    assert "Snapshot" in digest.top_detail
    assert "Support insights" in digest.item_lines[0]
    assert "Stale snapshot" in digest.item_lines[0]
    assert "Snapshot" in digest.item_lines[0]
    assert "Pricing / Offers" in digest.item_lines[1]
    assert "Budget exceeded" in digest.item_lines[1]
    assert "Snapshot" in digest.item_lines[1]


def test_build_admin_read_model_focus_summary_prefers_drift_then_watch_then_action() -> None:
    watchlist_summary = AdminReadModelWatchlistSummary(
        source="snapshot",
        generated_at_label="06.05.2026 12:00",
        staleness_seconds=0,
        tracked_count=5,
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
        top_items=(
            AdminReadModelWatchItemSummary(
                label="Support insights",
                watch_kind_label="Stale snapshot",
                source_mode_label="Snapshot",
                note=None,
                status_label="Stale",
            ),
        ),
    )
    action_summary = AdminReadModelActionSummary(
        source="snapshot",
        generated_at_label="06.05.2026 12:00",
        staleness_seconds=0,
        tracked_count=4,
        surface_count=3,
        alert_item_count=2,
        snapshot_action_count=1,
        budget_action_count=1,
        drift_action_count=0,
        top_action_label="Pricing / Offers",
        top_action_note=None,
        top_budget_action_label="Pricing / Offers",
        top_drift_action_label=None,
        top_items=(
            AdminReadModelActionItemSummary(
                label="Pricing / Offers",
                action_label="review query budget",
                action_note=None,
                issue_summary_label="query budget exceeded",
                action_category_label="budget",
            ),
        ),
    )
    drift_summary = AdminReadModelDriftSummary(
        source="live",
        generated_at_label="06.05.2026 12:00",
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
        top_regression_note="budget regression",
        top_budget_regression_label="Pricing / Offers",
        top_query_regression_label="Pricing / Offers",
        top_payload_regression_label=None,
        top_build_regression_label=None,
        top_items=(),
    )

    focus = build_admin_read_model_focus_summary(
        watchlist_summary=watchlist_summary,
        action_summary=action_summary,
        drift_summary=drift_summary,
    )
    assert focus is not None
    assert focus.kind == "drift"
    assert "Live drift" in focus.line
    assert "Pricing / Offers" in focus.line
    assert "budget regression" in focus.line

    focus = build_admin_read_model_focus_summary(
        watchlist_summary=watchlist_summary,
        action_summary=action_summary,
        drift_summary=None,
    )
    assert focus is not None
    assert focus.kind == "watchlist"
    assert "Snapshot watch" in focus.line
    assert "Support insights" in focus.line
    assert "Stale snapshot" in focus.line
    assert "Snapshot" in focus.line

    focus = build_admin_read_model_focus_summary(
        watchlist_summary=None,
        action_summary=action_summary,
        drift_summary=None,
    )
    assert focus is not None
    assert focus.kind == "action"
    assert "Next action" in focus.line
    assert "Pricing / Offers" in focus.line
    assert "review query budget" in focus.line
    assert "query budget exceeded" in focus.line


def test_build_admin_read_model_operator_digest_compacts_focus_watch_action_and_drift() -> None:
    watchlist_summary = AdminReadModelWatchlistSummary(
        source="snapshot",
        generated_at_label="06.05.2026 12:00",
        staleness_seconds=0,
        tracked_count=5,
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
        top_items=(
            AdminReadModelWatchItemSummary(
                label="Support insights",
                watch_kind_label="Stale snapshot",
                source_mode_label="Snapshot",
                note=None,
                status_label="Stale",
            ),
        ),
    )
    action_summary = AdminReadModelActionSummary(
        source="snapshot",
        generated_at_label="06.05.2026 12:00",
        staleness_seconds=0,
        tracked_count=4,
        surface_count=3,
        alert_item_count=2,
        snapshot_action_count=1,
        budget_action_count=1,
        drift_action_count=0,
        top_action_label="Pricing / Offers",
        top_action_note=None,
        top_budget_action_label="Pricing / Offers",
        top_drift_action_label=None,
        top_items=(
            AdminReadModelActionItemSummary(
                label="Pricing / Offers",
                action_label="review query budget",
                action_note=None,
                issue_summary_label="query budget exceeded",
                action_category_label="budget",
            ),
        ),
    )
    drift_summary = AdminReadModelDriftSummary(
        source="live",
        generated_at_label="06.05.2026 12:00",
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
        top_regression_note="budget regression",
        top_budget_regression_label="Pricing / Offers",
        top_query_regression_label="Pricing / Offers",
        top_payload_regression_label=None,
        top_build_regression_label=None,
        top_items=(),
    )

    digest = build_admin_read_model_operator_digest(
        watchlist_summary=watchlist_summary,
        action_summary=action_summary,
        drift_summary=drift_summary,
    )

    assert isinstance(digest, AdminReadModelOperatorDigest)
    assert digest is not None
    assert "focus live drift: Pricing / Offers" in digest.summary_line
    assert "watch alerts 2" in digest.summary_line
    assert "actions surfaces 3" in digest.summary_line
    assert "drift regressions 1" in digest.summary_line
    assert digest.focus_line is not None and "Live drift" in digest.focus_line
    assert digest.watch_line is not None and "Support insights" in digest.watch_line
    assert digest.action_line is not None and "review query budget" in digest.action_line
    assert digest.drift_line is not None and "budget regression" in digest.drift_line


def test_build_admin_read_model_snapshot_focus_payload_uses_overview_attention() -> None:
    payload = {
        "view": "overview",
        "source": "snapshot",
        "generated_at_label": "06.05.2026 12:00",
        "staleness_seconds": 120,
        "tracked_count": 9,
        "missing_count": 1,
        "stale_count": 1,
        "budget_exceeded_count": 1,
        "top_attention_item": {
            "label": "Support insights",
            "status_label": "Stale",
            "note": "Older than the 5 minute refresh cadence.",
        },
    }

    focus = build_admin_read_model_snapshot_focus_payload(payload)

    assert focus is not None
    assert focus["kind"] == "watchlist"
    assert "Snapshot watch" in focus["line"]
    assert "Support insights" in focus["line"]
    assert "Older than the 5 minute refresh cadence." in focus["line"]
    assert focus["tracked_count"] == 9
    assert focus["alert_item_count"] == 3
    assert focus["missing_count"] == 1
    assert focus["stale_count"] == 1
    assert focus["budget_exceeded_count"] == 1


def test_build_admin_read_model_snapshot_digest_payload_uses_embedded_digest() -> None:
    payload = {
        "view": "overview",
        "generated_at_label": "06.05.2026 12:00",
        "staleness_seconds": 90,
        "digest_summary": {
            "tracked_count": 9,
            "alert_item_count": 3,
            "missing_count": 1,
            "stale_count": 1,
            "budget_exceeded_count": 1,
            "watch_summary_line": "alerts 3 В· missing 1 В· stale 1 В· budget 1 В· drift 0",
            "action_summary_line": "surfaces 3 В· snapshot 1 В· budget 1 В· drift 1",
            "top_watch_label": "Support insights",
            "top_watch_detail": "Stale snapshot В· Snapshot",
            "top_action_label": "Pricing / Offers",
            "top_action_detail": "review query budget В· query budget exceeded",
            "generated_at_label": "06.05.2026 12:00",
            "staleness_seconds": 90,
        },
    }

    digest = build_admin_read_model_snapshot_digest_payload(payload)

    assert digest is not None
    assert "alerts 3" in digest["watch_summary_line"]
    assert "snapshot 1" in digest["action_summary_line"]
    assert digest["top_watch_label"] == "Support insights"
    assert "Stale snapshot" in digest["top_watch_detail"]
    assert digest["top_action_label"] == "Pricing / Offers"
    assert "review query budget" in digest["top_action_detail"]
    assert digest["tracked_count"] == 9
    assert digest["alert_item_count"] == 3


def test_build_admin_read_model_snapshot_operator_payload_uses_embedded_operator_digest() -> None:
    payload = {
        "view": "overview",
        "generated_at_label": "06.05.2026 12:00",
        "staleness_seconds": 90,
        "focus_summary": {
            "kind": "watchlist",
            "kind_label": "Snapshot watch",
            "label": "Support insights",
            "detail": "Stale snapshot В· Snapshot",
            "line": "Snapshot watch В· Support insights В· Stale snapshot В· Snapshot",
        },
        "digest_summary": {
            "tracked_count": 9,
            "alert_item_count": 3,
            "missing_count": 1,
            "stale_count": 1,
            "budget_exceeded_count": 1,
            "watch_summary_line": "alerts 3 Р’В· missing 1 Р’В· stale 1 Р’В· budget 1 Р’В· drift 0",
            "action_summary_line": "surfaces 3 Р’В· snapshot 1 Р’В· budget 1 Р’В· drift 1",
            "top_watch_label": "Support insights",
            "top_watch_detail": "Stale snapshot Р’В· Snapshot",
            "top_action_label": "Pricing / Offers",
            "top_action_detail": "review query budget Р’В· query budget exceeded",
            "generated_at_label": "06.05.2026 12:00",
            "staleness_seconds": 90,
        },
        "operator_digest_summary": {
            "summary_line": (
                "focus snapshot watch: Support insights Р’В· "
                "watch alerts 3 Р’В· actions surfaces 3"
            ),
            "focus_line": "Snapshot watch Р’В· Support insights Р’В· Stale snapshot Р’В· Snapshot",
            "watch_line": "Support insights Р’В· Stale snapshot Р’В· Snapshot",
            "action_line": "Pricing / Offers Р’В· review query budget Р’В· query budget exceeded",
            "drift_line": "",
        },
    }

    operator_summary = build_admin_read_model_snapshot_operator_payload(payload)

    assert operator_summary is not None
    assert "focus snapshot watch" in operator_summary["summary_line"]
    assert "Support insights" in operator_summary["focus_line"]
    assert "Support insights" in operator_summary["watch_line"]
    assert "Pricing / Offers" in operator_summary["action_line"]
    assert operator_summary["tracked_count"] == 9
    assert operator_summary["alert_item_count"] == 3
    assert operator_summary["missing_count"] == 1
    assert operator_summary["stale_count"] == 1
    assert operator_summary["budget_exceeded_count"] == 1
