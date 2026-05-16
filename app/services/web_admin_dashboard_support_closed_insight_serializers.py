# ruff: noqa: E501
from __future__ import annotations

from app.services.support import (
    support_canned_reply_pack_label,
    support_canned_reply_pack_titles,
    support_close_reason_label,
)


def _serialize_support_distribution(
    counts: dict[str, int],
    *,
    label_resolver,
    total: int | None = None,
) -> list[dict[str, object]]:
    base_total = total if total is not None else sum(counts.values())
    return [
        {
            "key": key,
            "label": label_resolver(key),
            "count": count,
            "share_percent": round((count / base_total) * 100, 1) if base_total else 0.0,
        }
        for key, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], label_resolver(item[0])),
        )
    ]


def _serialize_support_close_reason_windows(insights) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    return (
        _serialize_support_distribution(
            insights.recent_close_reason_counts,
            label_resolver=support_close_reason_label,
            total=insights.recent_close_total,
        ),
        _serialize_support_distribution(
            insights.previous_close_reason_counts,
            label_resolver=support_close_reason_label,
            total=insights.previous_close_total,
        ),
    )


def _serialize_support_close_reason_trends(insights) -> list[dict[str, object]]:
    return [
        {
            "key": item.reason,
            "label": support_close_reason_label(item.reason),
            "current_count": item.current_count,
            "previous_count": item.previous_count,
            "delta": item.delta,
        }
        for item in insights.close_reason_trends
    ]


def _serialize_support_canned_reply_pack_outcomes(insights) -> list[dict[str, object]]:
    return [
        {
            "key": item.pack_key,
            "label": support_canned_reply_pack_label(item.pack_key),
            "ticket_count": item.ticket_count,
            "resolved_count": item.resolved_count,
            "no_response_count": item.no_response_count,
            "duplicate_count": item.duplicate_count,
            "other_count": item.other_count,
            "resolved_rate_percent": item.resolved_rate_percent,
            "no_response_rate_percent": item.no_response_rate_percent,
            "duplicate_rate_percent": item.duplicate_rate_percent,
            "sample_titles": support_canned_reply_pack_titles(item.pack_key),
        }
        for item in insights.canned_reply_pack_outcomes
    ]


def _build_support_recent_close_summary(
    insights,
    recent_close_reasons: list[dict[str, object]],
) -> dict[str, object]:
    top_recent = recent_close_reasons[0] if recent_close_reasons else None
    return {
        "window_days": insights.recent_close_days,
        "total_closed": insights.recent_close_total,
        "previous_total_closed": insights.previous_close_total,
        "top_close_reason": top_recent["key"] if top_recent is not None else None,
        "top_close_reason_label": top_recent["label"] if top_recent is not None else None,
        "top_close_reason_count": top_recent["count"] if top_recent is not None else 0,
        "top_close_reason_share_percent": top_recent["share_percent"]
        if top_recent is not None
        else 0.0,
    }


def _build_support_close_reason_trend_summary(
    close_reason_trends: list[dict[str, object]],
) -> dict[str, object]:
    strongest_trend = close_reason_trends[0] if close_reason_trends else None
    return {
        "strongest_reason": strongest_trend["key"] if strongest_trend is not None else None,
        "strongest_reason_label": strongest_trend["label"]
        if strongest_trend is not None
        else None,
        "strongest_delta": strongest_trend["delta"] if strongest_trend is not None else 0,
    }


def _build_support_pack_outcome_summary(
    insights,
    canned_reply_pack_outcomes: list[dict[str, object]],
) -> dict[str, object]:
    top_pack_outcome = canned_reply_pack_outcomes[0] if canned_reply_pack_outcomes else None
    return {
        "window_days": insights.pack_outcome_days,
        "top_pack_key": top_pack_outcome["key"] if top_pack_outcome is not None else None,
        "top_pack_label": top_pack_outcome["label"] if top_pack_outcome is not None else None,
        "top_pack_resolved_rate_percent": top_pack_outcome["resolved_rate_percent"]
        if top_pack_outcome is not None
        else 0.0,
    }
