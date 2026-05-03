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
    assert "/api/admin/dashboard" in text
    assert "/api/admin/users?query=$MINI_APP_SMOKE_USER_ID" in text
    assert "/api/admin/payments?provider=all&page=1" in text
    assert "/api/admin/support?status=open&queue=awaiting_admin&page=1" in text
    assert "/api/admin/support/$first_ticket_id" in text
    assert "extract_first_ticket_id() {" in text
    assert "python3 -c 'import json, sys; payload = json.load(sys.stdin);" in text
    assert "support_inbox_status=$(printf '%s' \"$support_inbox_body\" | python3 -c" in text
    assert "forbidden_admin_status" in text
    assert 'if [ "$forbidden_admin_status" != "403" ]; then' in text


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
