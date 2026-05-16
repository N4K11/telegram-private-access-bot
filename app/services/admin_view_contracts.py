from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.admin_read_models import (
    PAYLOAD_BUDGET_ADMIN_ACQUISITION,
    PAYLOAD_BUDGET_ADMIN_CONVERSION,
    PAYLOAD_BUDGET_ADMIN_DASHBOARD,
    PAYLOAD_BUDGET_ADMIN_LIFECYCLE,
    PAYLOAD_BUDGET_ADMIN_PRICING,
    PAYLOAD_BUDGET_ADMIN_PROMO_REFERRAL,
    PAYLOAD_BUDGET_ADMIN_READ_MODELS,
    PAYLOAD_BUDGET_ADMIN_READ_MODELS_ACTIONS,
    PAYLOAD_BUDGET_ADMIN_READ_MODELS_DRIFT,
    PAYLOAD_BUDGET_ADMIN_READ_MODELS_WATCHLIST,
    PAYLOAD_BUDGET_ADMIN_SUMMARY,
    PAYLOAD_BUDGET_ADMIN_SUPPORT_INSIGHTS,
    QUERY_BUDGET_ADMIN_ACQUISITION,
    QUERY_BUDGET_ADMIN_CONVERSION,
    QUERY_BUDGET_ADMIN_DASHBOARD,
    QUERY_BUDGET_ADMIN_LIFECYCLE,
    QUERY_BUDGET_ADMIN_PRICING,
    QUERY_BUDGET_ADMIN_PROMO_REFERRAL,
    QUERY_BUDGET_ADMIN_READ_MODELS,
    QUERY_BUDGET_ADMIN_READ_MODELS_ACTIONS,
    QUERY_BUDGET_ADMIN_READ_MODELS_DRIFT,
    QUERY_BUDGET_ADMIN_READ_MODELS_WATCHLIST,
    QUERY_BUDGET_ADMIN_SUMMARY,
    QUERY_BUDGET_ADMIN_SUPPORT_INSIGHTS,
)

ADMIN_VIEW_META_KEYS = (
    "source",
    "generated_at",
    "staleness_seconds",
    "build_duration_ms",
    "query_count",
    "query_budget",
    "query_budget_ok",
    "payload_bytes",
    "payload_budget",
    "payload_budget_ok",
)


@dataclass(frozen=True, slots=True)
class AdminViewContract:
    key: str
    route_suffix: str
    smoke_path: str
    query_budget: int
    payload_budget: int
    default_source: str = "snapshot"


BUDGETED_ADMIN_VIEW_CONTRACTS: dict[str, AdminViewContract] = {
    "summary": AdminViewContract(
        key="summary",
        route_suffix="/api/admin/summary",
        smoke_path="/api/admin/summary",
        query_budget=QUERY_BUDGET_ADMIN_SUMMARY,
        payload_budget=PAYLOAD_BUDGET_ADMIN_SUMMARY,
    ),
    "dashboard": AdminViewContract(
        key="dashboard",
        route_suffix="/api/admin/dashboard",
        smoke_path="/api/admin/dashboard",
        query_budget=QUERY_BUDGET_ADMIN_DASHBOARD,
        payload_budget=PAYLOAD_BUDGET_ADMIN_DASHBOARD,
    ),
    "conversion": AdminViewContract(
        key="conversion",
        route_suffix="/api/admin/conversion",
        smoke_path="/api/admin/conversion",
        query_budget=QUERY_BUDGET_ADMIN_CONVERSION,
        payload_budget=PAYLOAD_BUDGET_ADMIN_CONVERSION,
    ),
    "acquisition": AdminViewContract(
        key="acquisition",
        route_suffix="/api/admin/acquisition",
        smoke_path="/api/admin/acquisition",
        query_budget=QUERY_BUDGET_ADMIN_ACQUISITION,
        payload_budget=PAYLOAD_BUDGET_ADMIN_ACQUISITION,
    ),
    "promo_referrals": AdminViewContract(
        key="promo_referrals",
        route_suffix="/api/admin/promo-referrals",
        smoke_path="/api/admin/promo-referrals",
        query_budget=QUERY_BUDGET_ADMIN_PROMO_REFERRAL,
        payload_budget=PAYLOAD_BUDGET_ADMIN_PROMO_REFERRAL,
    ),
    "pricing": AdminViewContract(
        key="pricing",
        route_suffix="/api/admin/pricing",
        smoke_path="/api/admin/pricing",
        query_budget=QUERY_BUDGET_ADMIN_PRICING,
        payload_budget=PAYLOAD_BUDGET_ADMIN_PRICING,
    ),
    "lifecycle": AdminViewContract(
        key="lifecycle",
        route_suffix="/api/admin/lifecycle",
        smoke_path="/api/admin/lifecycle?view=rules&limit=5",
        query_budget=QUERY_BUDGET_ADMIN_LIFECYCLE,
        payload_budget=PAYLOAD_BUDGET_ADMIN_LIFECYCLE,
    ),
    "read_models": AdminViewContract(
        key="read_models",
        route_suffix="/api/admin/read-models",
        smoke_path="/api/admin/read-models?limit=5",
        query_budget=QUERY_BUDGET_ADMIN_READ_MODELS,
        payload_budget=PAYLOAD_BUDGET_ADMIN_READ_MODELS,
    ),
    "read_models_watchlist": AdminViewContract(
        key="read_models_watchlist",
        route_suffix="/api/admin/read-models",
        smoke_path="/api/admin/read-models?view=watchlist&limit=5&source=live",
        query_budget=QUERY_BUDGET_ADMIN_READ_MODELS_WATCHLIST,
        payload_budget=PAYLOAD_BUDGET_ADMIN_READ_MODELS_WATCHLIST,
        default_source="live",
    ),
    "read_models_actions": AdminViewContract(
        key="read_models_actions",
        route_suffix="/api/admin/read-models",
        smoke_path="/api/admin/read-models?view=actions&limit=5&source=live",
        query_budget=QUERY_BUDGET_ADMIN_READ_MODELS_ACTIONS,
        payload_budget=PAYLOAD_BUDGET_ADMIN_READ_MODELS_ACTIONS,
        default_source="live",
    ),
    "read_models_drift": AdminViewContract(
        key="read_models_drift",
        route_suffix="/api/admin/read-models",
        smoke_path="/api/admin/read-models?view=drift&limit=5&source=live",
        query_budget=QUERY_BUDGET_ADMIN_READ_MODELS_DRIFT,
        payload_budget=PAYLOAD_BUDGET_ADMIN_READ_MODELS_DRIFT,
        default_source="live",
    ),
    "support_insights": AdminViewContract(
        key="support_insights",
        route_suffix="/api/admin/support/insights",
        smoke_path="/api/admin/support/insights?view=hotspots&limit=5",
        query_budget=QUERY_BUDGET_ADMIN_SUPPORT_INSIGHTS,
        payload_budget=PAYLOAD_BUDGET_ADMIN_SUPPORT_INSIGHTS,
    ),
}


def validate_admin_view_payload_contract(
    payload: dict[str, Any],
    contract: AdminViewContract,
) -> list[str]:
    issues: list[str] = []
    for key in ADMIN_VIEW_META_KEYS:
        if key not in payload:
            issues.append(f"missing:{key}")
    source = payload.get("source")
    if source not in {"snapshot", "live"}:
        issues.append("invalid:source")
    _check_non_negative_int(payload, "staleness_seconds", issues)
    _check_non_negative_int(payload, "build_duration_ms", issues)
    _check_non_negative_int(payload, "query_count", issues)
    _check_non_negative_int(payload, "payload_bytes", issues)
    if payload.get("query_budget") != contract.query_budget:
        issues.append("budget:query_budget")
    if payload.get("payload_budget") != contract.payload_budget:
        issues.append("budget:payload_budget")
    if not isinstance(payload.get("query_budget_ok"), bool):
        issues.append("invalid:query_budget_ok")
    if not isinstance(payload.get("payload_budget_ok"), bool):
        issues.append("invalid:payload_budget_ok")
    generated_at = payload.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at.strip():
        issues.append("invalid:generated_at")
    return issues


def _check_non_negative_int(payload: dict[str, Any], key: str, issues: list[str]) -> None:
    value = payload.get(key)
    if not isinstance(value, int) or value < 0:
        issues.append(f"invalid:{key}")
