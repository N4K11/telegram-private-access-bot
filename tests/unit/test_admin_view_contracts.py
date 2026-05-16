from __future__ import annotations

from pathlib import Path

from app.services.admin_view_contracts import (
    BUDGETED_ADMIN_VIEW_CONTRACTS,
    validate_admin_view_payload_contract,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HANDLERS_PATH = PROJECT_ROOT / "app" / "webapp" / "handlers.py"
SMOKE_SCRIPT = PROJECT_ROOT / "scripts" / "smoke_webhook_runtime.sh"


def test_budgeted_admin_view_contracts_are_registered_and_smoked() -> None:
    handlers_text = HANDLERS_PATH.read_text(encoding="utf-8")
    smoke_text = SMOKE_SCRIPT.read_text(encoding="utf-8")

    for contract in BUDGETED_ADMIN_VIEW_CONTRACTS.values():
        assert contract.route_suffix in handlers_text
        assert contract.smoke_path in smoke_text


def test_budgeted_admin_view_contracts_have_unique_keys() -> None:
    keys = [contract.key for contract in BUDGETED_ADMIN_VIEW_CONTRACTS.values()]

    assert sorted(keys) == sorted(BUDGETED_ADMIN_VIEW_CONTRACTS)
    assert len(keys) == len(set(keys))


def test_admin_view_payload_contract_accepts_valid_payload() -> None:
    contract = BUDGETED_ADMIN_VIEW_CONTRACTS["dashboard"]
    payload = {
        "source": "snapshot",
        "generated_at": "2026-05-10T10:00:00+00:00",
        "staleness_seconds": 0,
        "build_duration_ms": 12,
        "query_count": 2,
        "query_budget": contract.query_budget,
        "query_budget_ok": True,
        "payload_bytes": 512,
        "payload_budget": contract.payload_budget,
        "payload_budget_ok": True,
    }

    assert validate_admin_view_payload_contract(payload, contract) == []


def test_admin_view_payload_contract_reports_missing_or_invalid_meta() -> None:
    contract = BUDGETED_ADMIN_VIEW_CONTRACTS["dashboard"]
    payload = {
        "source": "broken",
        "staleness_seconds": -1,
        "build_duration_ms": "slow",
        "query_count": 2,
        "query_budget": contract.query_budget + 1,
        "query_budget_ok": "yes",
        "payload_bytes": 512,
        "payload_budget": contract.payload_budget + 1,
        "payload_budget_ok": None,
    }

    issues = validate_admin_view_payload_contract(payload, contract)

    assert "missing:generated_at" in issues
    assert "invalid:source" in issues
    assert "invalid:staleness_seconds" in issues
    assert "invalid:build_duration_ms" in issues
    assert "budget:query_budget" in issues
    assert "budget:payload_budget" in issues
    assert "invalid:query_budget_ok" in issues
    assert "invalid:payload_budget_ok" in issues
    assert "invalid:generated_at" in issues
