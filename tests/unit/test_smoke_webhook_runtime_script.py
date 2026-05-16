from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPT = PROJECT_ROOT / "scripts" / "smoke_webhook_runtime.sh"


def test_smoke_script_exists_and_uses_bash_strict_mode() -> None:
    text = SMOKE_SCRIPT.read_text(encoding="utf-8")
    content = SMOKE_SCRIPT.read_bytes()

    assert SMOKE_SCRIPT.exists() is True
    assert content.startswith(b"#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in text
    assert "PROJECT_ROOT=$(CDPATH= cd -- \"$SCRIPT_DIR/..\" && pwd)" in text


def test_smoke_script_auto_loads_project_env_without_overwriting_explicit_overrides() -> None:
    text = SMOKE_SCRIPT.read_text(encoding="utf-8")

    assert "load_project_env() {" in text
    assert "local env_path=\"$PROJECT_ROOT/.env\"" in text
    assert '. "$env_path"' in text
    assert "local -a preserve_names=(" in text
    assert 'if [ "${!name+x}" = x ]; then' in text
    assert 'printf -v "__smoke_preserved_$name"' in text
    assert 'printf -v "$name"' in text
    assert "load_project_env" in text
    assert 'if [ "${USE_WEBHOOK:-true}" != "true" ]; then' in text
    assert "wait_for_http_code() {" in text
    assert 'for attempt in $(seq 1 15); do' in text
    assert 'sleep 2' in text


def test_smoke_script_checks_authorized_mini_app_endpoints_and_role_gates() -> None:
    text = SMOKE_SCRIPT.read_text(encoding="utf-8")

    assert "build_init_data" in text
    assert "WebAppData" in text
    assert "MINI_APP_SMOKE_ADMIN_ID" in text
    assert "/api/bootstrap" in text
    assert "/api/users/$MINI_APP_SMOKE_USER_ID/profile" in text
    assert "/api/admin/summary" in text
    assert "/api/admin/dashboard" in text
    assert "/api/admin/conversion" in text
    assert "/api/admin/acquisition" in text
    assert "/api/admin/promo-referrals" in text
    assert "/api/admin/read-models?limit=5" in text
    assert "/api/admin/read-models?view=watchlist&limit=5&source=live" in text
    assert "/api/admin/read-models?view=actions&limit=5&source=live" in text
    assert "/api/admin/read-models?view=drift&limit=5&source=live" in text
    assert "/api/admin/lifecycle?view=rules&limit=5" in text
    assert "/api/admin/users?query=$MINI_APP_SMOKE_USER_ID" in text
    assert "/api/admin/payments?provider=all&page=1" in text
    assert "/api/admin/support?status=open&queue=awaiting_admin&page=1" in text
    assert "/api/admin/support/insights?view=hotspots&limit=5" in text
    assert "/api/admin/support/$first_ticket_id" in text
    assert "/api/admin/actions/support-triage-confirm" in text
    assert "extract_first_ticket_id() {" in text
    assert "extract_triage_confirm_key() {" in text
    assert "python3 -c 'import json, sys; payload = json.load(sys.stdin);" in text
    assert "support_inbox_status=$(printf '%s' \"$support_inbox_body\" | python3 -c" in text
    assert "forbidden_admin_status" in text
    assert 'if [ "$forbidden_admin_status" != "403" ]; then' in text


def test_smoke_script_reports_deploy_stamp_rollback_path_and_latency_baseline() -> None:
    text = SMOKE_SCRIPT.read_text(encoding="utf-8")

    assert "http_time_ms() {" in text
    assert "health_latency_ms=$(http_time_ms GET \"$BASE_URL/healthz\")" in text
    assert "ready_latency_ms=$(http_time_ms GET \"$BASE_URL/readyz\")" in text
    assert "mini_app_latency_ms=$(http_time_ms GET \"$BASE_URL$MINI_APP_PATH\")" in text
    assert "webhook_latency_ms=$(http_time_ms POST \"$WEBHOOK_URL\"" in text
    assert (
        "admin_summary_latency_ms=$(http_time_ms GET "
        "\"$BASE_URL$MINI_APP_PATH/api/admin/summary\""
    ) in text
    assert (
        "admin_dashboard_latency_ms=$(http_time_ms GET "
        "\"$BASE_URL$MINI_APP_PATH/api/admin/dashboard\""
    ) in text
    assert (
        "admin_conversion_latency_ms=$(http_time_ms GET "
        "\"$BASE_URL$MINI_APP_PATH/api/admin/conversion\""
    ) in text
    assert (
        "admin_acquisition_latency_ms=$(http_time_ms GET "
        "\"$BASE_URL$MINI_APP_PATH/api/admin/acquisition\""
    ) in text
    assert (
        "admin_promo_referral_latency_ms=$(http_time_ms GET "
        "\"$BASE_URL$MINI_APP_PATH/api/admin/promo-referrals\""
    ) in text
    assert (
        "admin_read_models_latency_ms=$(http_time_ms GET "
        "\"$BASE_URL$MINI_APP_PATH/api/admin/read-models?limit=5\""
    ) in text
    assert (
        "admin_read_models_watchlist_latency_ms=$(http_time_ms GET "
        "\"$BASE_URL$MINI_APP_PATH/api/admin/read-models?view=watchlist&limit=5&source=live\""
    ) in text
    assert (
        "admin_read_models_actions_latency_ms=$(http_time_ms GET "
        "\"$BASE_URL$MINI_APP_PATH/api/admin/read-models?view=actions&limit=5&source=live\""
    ) in text
    assert (
        "admin_read_models_drift_latency_ms=$(http_time_ms GET "
        "\"$BASE_URL$MINI_APP_PATH/api/admin/read-models?view=drift&limit=5&source=live\""
    ) in text
    assert (
        "admin_lifecycle_latency_ms=$(http_time_ms GET "
        "\"$BASE_URL$MINI_APP_PATH/api/admin/lifecycle?view=rules&limit=5\""
    ) in text
    assert (
        "support_insights_latency_ms=$(http_time_ms GET "
        "\"$BASE_URL$MINI_APP_PATH/api/admin/support/insights?view=hotspots&limit=5\""
    ) in text
    assert (
        "triage_confirm_key=$(printf '%s' \"$support_detail_body\" | "
        "extract_triage_confirm_key || true)"
    ) in text
    assert (
        "support_triage_confirm_status=$(http_code POST "
        "\"$BASE_URL$MINI_APP_PATH/api/admin/actions/support-triage-confirm\""
    ) in text
    assert 'echo "Deploy stamp: ${DEPLOY_STAMP:-unknown}"' in text
    assert 'echo "Rollback backup: ${ROLLBACK_BACKUP_PATH:-unknown}"' in text
    assert (
        'echo "Latency baseline (ms): healthz=$health_latency_ms '
        'readyz=$ready_latency_ms mini_app=$mini_app_latency_ms '
        'webhook=$webhook_latency_ms"'
    ) in text
    assert (
        'echo "Latency baseline (ms): admin_summary=$admin_summary_latency_ms '
        'admin_dashboard=$admin_dashboard_latency_ms '
        'admin_conversion=$admin_conversion_latency_ms '
        'admin_acquisition=$admin_acquisition_latency_ms '
        'admin_promo_referral=$admin_promo_referral_latency_ms '
        'admin_pricing=$admin_pricing_latency_ms admin_read_models=$admin_read_models_latency_ms '
        'admin_read_models_watchlist=$admin_read_models_watchlist_latency_ms '
        'admin_read_models_actions=$admin_read_models_actions_latency_ms '
        'admin_read_models_drift=$admin_read_models_drift_latency_ms '
        'admin_lifecycle=$admin_lifecycle_latency_ms '
        'support_inbox=$support_inbox_latency_ms support_insights=$support_insights_latency_ms"'
    ) in text
    assert (
        'echo "Manual Telegram checks still required: '
        '/admin_health, /admin_channel_check"'
    ) in text
    assert "write_smoke_summary" in text
    assert 'echo "Smoke summary: $SMOKE_SUMMARY_PATH"' in text


def test_smoke_script_can_write_machine_readable_summary() -> None:
    text = SMOKE_SCRIPT.read_text(encoding="utf-8")

    assert "write_smoke_summary() {" in text
    assert 'if [ -z "${SMOKE_SUMMARY_PATH:-}" ]; then' in text
    assert 'mkdir -p "$(dirname -- "$SMOKE_SUMMARY_PATH")"' in text
    assert 'export SMOKE_AUTH_ENABLED="$AUTH_ENABLED"' in text
    assert 'export SMOKE_ADMIN_SUMMARY_LATENCY_MS="${admin_summary_latency_ms:-}"' in text
    assert '"source": "webhook_smoke"' in text
    assert '"deploy_stamp": os.environ.get("DEPLOY_STAMP", "unknown")' in text
    assert '"rollback_backup": os.environ.get("ROLLBACK_BACKUP_PATH", "unknown")' in text
    assert '"authorized_checks": os.environ.get("SMOKE_AUTH_ENABLED") == "true"' in text
    assert '"latency_ms": latency_ms' in text
    assert '"manual_checks_required": ["/admin_health", "/admin_channel_check"]' in text


def test_smoke_script_requires_core_runtime_tools_and_has_no_secrets() -> None:
    text = SMOKE_SCRIPT.read_text(encoding="utf-8")

    assert "require_command curl" in text
    assert "require_command python3" in text

    forbidden_literals = [
        "AAEjnqo",
        "Rapira",
        "BOT_TOKEN=",
        "CRYPTO_PAY_TOKEN=",
        "D:\\",
        "C:\\",
    ]
    for literal in forbidden_literals:
        assert literal not in text
