from __future__ import annotations

from app.services.admin_read_model_text import render_admin_read_models_text


def test_render_admin_read_models_text_overview() -> None:
    text = render_admin_read_models_text(
        {
            "view": "overview",
            "source": "snapshot",
            "generated_at_label": "06.05.2026 10:00",
            "build_duration_ms": 18,
            "operator_digest_summary": {
                "summary_line": "focus snapshot watch: Pricing / Offers В· watch alerts 3",
            },
            "focus_summary": {
                "line": "Snapshot watch В· Pricing / Offers В· Budget exceeded",
            },
            "query_count": 2,
            "query_budget": 3,
            "payload_bytes": 4096,
            "payload_budget": 28000,
            "available_count": 7,
            "tracked_count": 9,
            "missing_count": 1,
            "stale_count": 1,
            "budget_exceeded_count": 1,
            "top_attention_item": {
                "label": "Pricing / Offers",
                "status_label": "Budget exceeded",
            },
            "top_query_item": {"label": "Support insights", "query_count": 3},
            "top_payload_item": {"label": "Lifecycle", "payload_bytes": 8192},
            "top_build_item": {"label": "Admin summary", "build_duration_ms": 27},
            "items": [
                {
                    "label": "Pricing / Offers",
                    "status": "budget",
                    "status_label": "Budget exceeded",
                    "staleness_seconds": 0,
                    "query_count": 4,
                    "query_budget": 3,
                    "payload_bytes": 8192,
                    "payload_budget": 28000,
                    "build_duration_ms": 27,
                }
            ],
        }
    )

    assert "Read-model diagnostics" in text
    assert "Summary: focus snapshot watch: Pricing / Offers В· watch alerts 3" in text
    assert "Focus: Snapshot watch В· Pricing / Offers В· Budget exceeded" in text
    assert "Alerts: missing 1" in text
    assert "stale 1" in text
    assert "budget 1" in text
    assert "Top risk: Pricing / Offers" in text
    assert "Budget exceeded" in text
    assert "Pricing / Offers: Budget exceeded" in text


def test_render_admin_read_models_text_drift() -> None:
    text = render_admin_read_models_text(
        {
            "view": "drift",
            "source": "live",
            "generated_at_label": "06.05.2026 10:05",
            "build_duration_ms": 96,
            "operator_digest_summary": {
                "summary_line": "focus live drift: Lifecycle / families В· drift regressions 2",
            },
            "focus_summary": {
                "line": (
                    "Live drift В· Lifecycle / families В· "
                    "Live build drifted above snapshot baseline: +2 queries."
                ),
            },
            "query_count": 14,
            "query_budget": 80,
            "payload_bytes": 12000,
            "payload_budget": 48000,
            "compared_count": 8,
            "tracked_count": 9,
            "regression_count": 2,
            "budget_regression_count": 1,
            "improvement_count": 1,
            "missing_snapshot_count": 1,
            "top_regression_item": {
                "label": "Lifecycle / families",
                "note": "Live build drifted above snapshot baseline: +2 queries.",
            },
            "top_budget_regression_item": {"label": "Support insights"},
            "top_improvement_item": {"label": "Promo / Referral"},
            "items": [
                {
                    "label": "Lifecycle / families",
                    "status": "regression",
                    "status_label": "Live drifted up",
                    "query_count_delta": 2,
                    "payload_bytes_delta": 256,
                    "build_duration_ms_delta": 14,
                }
            ],
        }
    )

    assert "Snapshot vs live drift" in text
    assert "Summary: focus live drift: Lifecycle / families В· drift regressions 2" in text
    assert "Focus: Live drift В· Lifecycle / families" in text
    assert "Drift: regressions 2" in text
    assert "budget 1" in text
    assert "improvements 1" in text
    assert "missing 1" in text
    assert "Top regression: Lifecycle / families" in text
    assert "Lifecycle / families: Live drifted up" in text
    assert "bytes 256" in text
    assert "ms 14" in text


def test_render_admin_read_models_text_watchlist() -> None:
    text = render_admin_read_models_text(
        {
            "view": "watchlist",
            "source": "live",
            "generated_at_label": "06.05.2026 10:10",
            "build_duration_ms": 110,
            "operator_digest_summary": {
                "summary_line": "focus snapshot watch: Pricing / Offers В· watch alerts 3",
            },
            "focus_summary": {
                "line": "Snapshot watch В· Pricing / Offers В· Budget regression",
            },
            "query_count": 15,
            "query_budget": 80,
            "payload_bytes": 15000,
            "payload_budget": 36000,
            "alert_item_count": 3,
            "tracked_count": 9,
            "missing_count": 1,
            "stale_count": 1,
            "budget_exceeded_count": 1,
            "regression_count": 1,
            "top_attention_item": {
                "label": "Pricing / Offers",
                "watch_kind_label": "Budget regression",
            },
            "top_regression_item": {"label": "Lifecycle / families"},
            "top_budget_item": {"label": "Pricing / Offers"},
            "items": [
                {
                    "label": "Pricing / Offers",
                    "status": "regression",
                    "watch_kind_label": "Budget regression",
                    "source_mode_label": "Live compare",
                    "query_count": 6,
                    "query_budget": 3,
                    "payload_bytes": 9500,
                    "payload_budget": 36000,
                }
            ],
        }
    )

    assert "Read-model watchlist" in text
    assert "Summary: focus snapshot watch: Pricing / Offers В· watch alerts 3" in text
    assert "Focus: Snapshot watch В· Pricing / Offers В· Budget regression" in text
    assert "Open alerts: 3 of 9" in text
    assert "Kinds: missing 1" in text
    assert "stale 1" in text
    assert "budget 1" in text
    assert "drift 1" in text
    assert "Pricing / Offers: Budget regression" in text


def test_render_admin_read_models_text_actions() -> None:
    text = render_admin_read_models_text(
        {
            "view": "actions",
            "source": "live",
            "generated_at_label": "06.05.2026 10:15",
            "build_duration_ms": 120,
            "operator_digest_summary": {
                "summary_line": "focus next action: Pricing / Offers В· actions surfaces 2",
            },
            "focus_summary": {
                "line": (
                    "Next action В· Pricing / Offers В· "
                    "Trim query and payload В· Budget exceeded + Budget regression"
                ),
            },
            "query_count": 18,
            "query_budget": 80,
            "payload_bytes": 17000,
            "payload_budget": 40000,
            "surface_count": 2,
            "tracked_count": 9,
            "snapshot_action_count": 1,
            "budget_action_count": 1,
            "drift_action_count": 0,
            "top_action_item": {
                "label": "Pricing / Offers",
                "action_label": "Trim query and payload",
                "action_note": "Both query count and payload size are over budget.",
            },
            "top_snapshot_action_item": {"label": "Admin dashboard / Owner"},
            "top_budget_action_item": {"label": "Pricing / Offers"},
            "items": [
                {
                    "label": "Pricing / Offers",
                    "status": "budget",
                    "action_label": "Trim query and payload",
                    "action_category_label": "Budget pressure",
                    "issue_summary_label": "Budget exceeded + Budget regression",
                    "source_mode_label": "Live compare",
                    "query_count": 6,
                    "query_budget": 3,
                    "payload_bytes": 9500,
                    "payload_budget": 40000,
                    "action_note": "Reduce joins and shrink the response shape together.",
                }
            ],
        }
    )

    assert "Read-model action digest" in text
    assert "Summary: focus next action: Pricing / Offers В· actions surfaces 2" in text
    assert "Focus: Next action В· Pricing / Offers" in text
    assert "Action mix: snapshot 1" in text
    assert "budget 1" in text
    assert "drift 0" in text
    assert "Top action: Pricing / Offers" in text
    assert "Trim query and payload" in text
    assert "Pricing / Offers: Trim query and payload" in text
