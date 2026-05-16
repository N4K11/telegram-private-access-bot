#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

load_project_env() {
  local env_path="$PROJECT_ROOT/.env"
  if [ ! -f "$env_path" ]; then
    return
  fi

  local -a preserve_names=(
    PUBLIC_WEBHOOK_URL
    WEBHOOK_PATH
    MINI_APP_PATH
    BOT_TOKEN
    ADMIN_IDS
    USE_WEBHOOK
    CRYPTO_PAY_ENABLED
    CRYPTO_PAY_WEBHOOK_PATH
    MINI_APP_SMOKE_USER_ID
    MINI_APP_SMOKE_USER_NAME
    MINI_APP_SMOKE_USER_FIRST_NAME
    MINI_APP_SMOKE_ADMIN_ID
    MINI_APP_SMOKE_ADMIN_NAME
    MINI_APP_SMOKE_ADMIN_FIRST_NAME
  )
  local -a preset_names=()
  local name
  for name in "${preserve_names[@]}"; do
    if [ "${!name+x}" = x ]; then
      preset_names+=("$name")
      printf -v "__smoke_preserved_$name" '%s' "${!name}"
    fi
  done

  set -a
  . "$env_path"
  set +a

  for name in "${preset_names[@]}"; do
    local preserved_var="__smoke_preserved_$name"
    printf -v "$name" '%s' "${!preserved_var}"
    export "$name"
    unset "$preserved_var"
  done
}

require_var() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "Missing required env var: $name" >&2
    exit 1
  fi
}

require_command() {
  local name="$1"
  command -v "$name" >/dev/null 2>&1 || {
    echo "$name is required" >&2
    exit 1
  }
}

http_time_ms() {
  local method="$1"
  local url="$2"
  shift 2
  local seconds
  seconds=$(curl -sS -o /dev/null -w '%{time_total}' -X "$method" "$url" "$@")
  python3 - "$seconds" <<'PY'
import sys

seconds = float(sys.argv[1])
print(round(seconds * 1000))
PY
}

http_code() {
  local method="$1"
  local url="$2"
  shift 2
  curl -sS -o /dev/null -w '%{http_code}' -X "$method" "$url" "$@"
}

http_body() {
  local method="$1"
  local url="$2"
  shift 2
  curl -sS -X "$method" "$url" "$@"
}

wait_for_http_code() {
  local expected="$1"
  local label="$2"
  local method="$3"
  local url="$4"
  shift 4

  local status=""
  local attempt
  for attempt in $(seq 1 15); do
    status=$(http_code "$method" "$url" "$@" 2>/dev/null || true)
    if [ "$status" = "$expected" ]; then
      return 0
    fi
    sleep 2
  done

  echo "$label returned HTTP ${status:-unreachable}" >&2
  exit 1
}

first_admin_id() {
  python3 - "$1" <<'PY'
import re
import sys

raw = sys.argv[1]
parts = [item.strip() for item in re.split(r"[\s,]+", raw) if item.strip()]
if not parts:
    raise SystemExit(1)
print(parts[0])
PY
}

build_init_data() {
  python3 - "$BOT_TOKEN" "$1" "$2" "$3" <<'PY'
import hashlib
import hmac
import json
import sys
import time
import urllib.parse

bot_token, telegram_id, username, first_name = sys.argv[1:5]
fields = {
    "auth_date": str(int(time.time())),
    "query_id": "miniapp-smoke-check",
    "user": json.dumps(
        {
            "id": int(telegram_id),
            "username": username,
            "first_name": first_name,
            "language_code": "ru",
        },
        separators=(",", ":"),
        ensure_ascii=False,
    ),
}
data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
fields["hash"] = hmac.new(
    secret,
    data_check_string.encode("utf-8"),
    hashlib.sha256,
).hexdigest()
print(urllib.parse.urlencode(fields))
PY
}

extract_first_ticket_id() {
  python3 -c 'import json, sys; payload = json.load(sys.stdin); items = payload.get("data", {}).get("items", []); print(items[0].get("id", "") if items else "")'
}

extract_triage_confirm_key() {
  python3 -c 'import json, sys; payload = json.load(sys.stdin); print(payload.get("data", {}).get("actions", {}).get("triage_confirm_key", ""))'
}

write_smoke_summary() {
  if [ -z "${SMOKE_SUMMARY_PATH:-}" ]; then
    return
  fi

  mkdir -p "$(dirname -- "$SMOKE_SUMMARY_PATH")"
  export SMOKE_AUTH_ENABLED="$AUTH_ENABLED"
  export SMOKE_BASE_URL="$BASE_URL"
  export SMOKE_WEBHOOK_URL="$WEBHOOK_URL"
  export SMOKE_MINI_APP_PATH="$MINI_APP_PATH"
  export SMOKE_HEALTH_LATENCY_MS="$health_latency_ms"
  export SMOKE_READY_LATENCY_MS="$ready_latency_ms"
  export SMOKE_MINI_APP_LATENCY_MS="$mini_app_latency_ms"
  export SMOKE_WEBHOOK_LATENCY_MS="$webhook_latency_ms"
  export SMOKE_ADMIN_SUMMARY_LATENCY_MS="${admin_summary_latency_ms:-}"
  export SMOKE_ADMIN_DASHBOARD_LATENCY_MS="${admin_dashboard_latency_ms:-}"
  export SMOKE_ADMIN_CONVERSION_LATENCY_MS="${admin_conversion_latency_ms:-}"
  export SMOKE_ADMIN_ACQUISITION_LATENCY_MS="${admin_acquisition_latency_ms:-}"
  export SMOKE_ADMIN_PROMO_REFERRAL_LATENCY_MS="${admin_promo_referral_latency_ms:-}"
  export SMOKE_ADMIN_PRICING_LATENCY_MS="${admin_pricing_latency_ms:-}"
  export SMOKE_ADMIN_READ_MODELS_LATENCY_MS="${admin_read_models_latency_ms:-}"
  export SMOKE_ADMIN_READ_MODELS_WATCHLIST_LATENCY_MS="${admin_read_models_watchlist_latency_ms:-}"
  export SMOKE_ADMIN_READ_MODELS_ACTIONS_LATENCY_MS="${admin_read_models_actions_latency_ms:-}"
  export SMOKE_ADMIN_READ_MODELS_DRIFT_LATENCY_MS="${admin_read_models_drift_latency_ms:-}"
  export SMOKE_ADMIN_LIFECYCLE_LATENCY_MS="${admin_lifecycle_latency_ms:-}"
  export SMOKE_SUPPORT_INBOX_LATENCY_MS="${support_inbox_latency_ms:-}"
  export SMOKE_SUPPORT_INSIGHTS_LATENCY_MS="${support_insights_latency_ms:-}"
  python3 <<'PY'
import json
import os
from pathlib import Path


def optional_int(name):
    value = os.environ.get(name, "")
    if value == "":
        return None
    return int(value)


latency_ms = {
    "healthz": optional_int("SMOKE_HEALTH_LATENCY_MS"),
    "readyz": optional_int("SMOKE_READY_LATENCY_MS"),
    "mini_app": optional_int("SMOKE_MINI_APP_LATENCY_MS"),
    "webhook": optional_int("SMOKE_WEBHOOK_LATENCY_MS"),
}
admin_latency_names = {
    "admin_summary": "SMOKE_ADMIN_SUMMARY_LATENCY_MS",
    "admin_dashboard": "SMOKE_ADMIN_DASHBOARD_LATENCY_MS",
    "admin_conversion": "SMOKE_ADMIN_CONVERSION_LATENCY_MS",
    "admin_acquisition": "SMOKE_ADMIN_ACQUISITION_LATENCY_MS",
    "admin_promo_referral": "SMOKE_ADMIN_PROMO_REFERRAL_LATENCY_MS",
    "admin_pricing": "SMOKE_ADMIN_PRICING_LATENCY_MS",
    "admin_read_models": "SMOKE_ADMIN_READ_MODELS_LATENCY_MS",
    "admin_read_models_watchlist": "SMOKE_ADMIN_READ_MODELS_WATCHLIST_LATENCY_MS",
    "admin_read_models_actions": "SMOKE_ADMIN_READ_MODELS_ACTIONS_LATENCY_MS",
    "admin_read_models_drift": "SMOKE_ADMIN_READ_MODELS_DRIFT_LATENCY_MS",
    "admin_lifecycle": "SMOKE_ADMIN_LIFECYCLE_LATENCY_MS",
    "support_inbox": "SMOKE_SUPPORT_INBOX_LATENCY_MS",
    "support_insights": "SMOKE_SUPPORT_INSIGHTS_LATENCY_MS",
}
for output_name, env_name in admin_latency_names.items():
    value = optional_int(env_name)
    if value is not None:
        latency_ms[output_name] = value

payload = {
    "ok": True,
    "source": "webhook_smoke",
    "deploy_stamp": os.environ.get("DEPLOY_STAMP", "unknown"),
    "rollback_backup": os.environ.get("ROLLBACK_BACKUP_PATH", "unknown"),
    "base_url": os.environ["SMOKE_BASE_URL"],
    "webhook_url": os.environ["SMOKE_WEBHOOK_URL"],
    "mini_app_path": os.environ["SMOKE_MINI_APP_PATH"],
    "authorized_checks": os.environ.get("SMOKE_AUTH_ENABLED") == "true",
    "latency_ms": latency_ms,
    "manual_checks_required": ["/admin_health", "/admin_channel_check"],
}
path = Path(os.environ["SMOKE_SUMMARY_PATH"])
path.write_text(
    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
  echo "Smoke summary: $SMOKE_SUMMARY_PATH"
}

load_project_env

if [ "${USE_WEBHOOK:-true}" != "true" ]; then
  echo "Webhook smoke requires USE_WEBHOOK=true" >&2
  exit 1
fi

require_var PUBLIC_WEBHOOK_URL
require_var WEBHOOK_PATH
require_var MINI_APP_PATH
require_command curl
require_command python3

case "$WEBHOOK_PATH" in
  /*) ;;
  *)
    echo "WEBHOOK_PATH must start with /" >&2
    exit 1
    ;;
esac

BASE_URL="${PUBLIC_WEBHOOK_URL%/}"
WEBHOOK_URL="$BASE_URL$WEBHOOK_PATH"
AUTH_ENABLED=false

wait_for_http_code 200 "Health probe /healthz" GET "$BASE_URL/healthz"
wait_for_http_code 200 "Readiness probe /readyz" GET "$BASE_URL/readyz"
wait_for_http_code 200 "Mini App page" GET "$BASE_URL$MINI_APP_PATH"

health_latency_ms=$(http_time_ms GET "$BASE_URL/healthz")
ready_latency_ms=$(http_time_ms GET "$BASE_URL/readyz")
mini_app_latency_ms=$(http_time_ms GET "$BASE_URL$MINI_APP_PATH")

auth_status=$(http_code POST "$BASE_URL$MINI_APP_PATH/api/auth" \
  -H 'Content-Type: application/json' \
  -d '{"init_data":"broken"}')
if [ "$auth_status" != "401" ] && [ "$auth_status" != "400" ]; then
  echo "Mini App auth probe returned unexpected HTTP $auth_status" >&2
  exit 1
fi

webhook_status=$(http_code POST "$WEBHOOK_URL" \
  -H 'Content-Type: application/json' \
  -H 'X-Telegram-Bot-Api-Secret-Token: invalid-smoke-token' \
  -d '{}')
if [ "$webhook_status" != "401" ]; then
  echo "Telegram webhook probe returned unexpected HTTP $webhook_status" >&2
  exit 1
fi
webhook_latency_ms=$(http_time_ms POST "$WEBHOOK_URL" \
  -H 'Content-Type: application/json' \
  -H 'X-Telegram-Bot-Api-Secret-Token: invalid-smoke-token' \
  -d '{}')

if [ -n "${BOT_TOKEN:-}" ] && [ -n "${ADMIN_IDS:-}" ]; then
  AUTH_ENABLED=true
  MINI_APP_SMOKE_USER_ID=${MINI_APP_SMOKE_USER_ID:-424242424}
  MINI_APP_SMOKE_USER_NAME=${MINI_APP_SMOKE_USER_NAME:-miniapp_smoke_user}
  MINI_APP_SMOKE_USER_FIRST_NAME=${MINI_APP_SMOKE_USER_FIRST_NAME:-Smoke}
  MINI_APP_SMOKE_ADMIN_ID=${MINI_APP_SMOKE_ADMIN_ID:-$(first_admin_id "$ADMIN_IDS")}
  MINI_APP_SMOKE_ADMIN_NAME=${MINI_APP_SMOKE_ADMIN_NAME:-miniapp_smoke_admin}
  MINI_APP_SMOKE_ADMIN_FIRST_NAME=${MINI_APP_SMOKE_ADMIN_FIRST_NAME:-Admin}

  user_init_data=$(build_init_data \
    "$MINI_APP_SMOKE_USER_ID" \
    "$MINI_APP_SMOKE_USER_NAME" \
    "$MINI_APP_SMOKE_USER_FIRST_NAME")
  admin_init_data=$(build_init_data \
    "$MINI_APP_SMOKE_ADMIN_ID" \
    "$MINI_APP_SMOKE_ADMIN_NAME" \
    "$MINI_APP_SMOKE_ADMIN_FIRST_NAME")

  valid_auth_status=$(http_code POST "$BASE_URL$MINI_APP_PATH/api/auth" \
    -H 'Content-Type: application/json' \
    -d "{\"init_data\":\"$user_init_data\"}")
  if [ "$valid_auth_status" != "200" ]; then
    echo "Mini App valid auth probe returned HTTP $valid_auth_status" >&2
    exit 1
  fi

  bootstrap_status=$(http_code GET "$BASE_URL$MINI_APP_PATH/api/bootstrap" \
    -H "X-Telegram-Init-Data: $user_init_data")
  if [ "$bootstrap_status" != "200" ]; then
    echo "Mini App bootstrap probe returned HTTP $bootstrap_status" >&2
    exit 1
  fi

  profile_status=$(http_code GET "$BASE_URL$MINI_APP_PATH/api/users/$MINI_APP_SMOKE_USER_ID/profile" \
    -H "X-Telegram-Init-Data: $user_init_data")
  if [ "$profile_status" != "200" ]; then
    echo "Mini App own profile probe returned HTTP $profile_status" >&2
    exit 1
  fi

  forbidden_admin_status=$(http_code GET "$BASE_URL$MINI_APP_PATH/api/admin/dashboard" \
    -H "X-Telegram-Init-Data: $user_init_data")
  if [ "$forbidden_admin_status" != "403" ]; then
    echo "Mini App admin dashboard gate returned unexpected HTTP $forbidden_admin_status" >&2
    exit 1
  fi

  admin_dashboard_status=$(http_code GET "$BASE_URL$MINI_APP_PATH/api/admin/dashboard" \
    -H "X-Telegram-Init-Data: $admin_init_data")
  if [ "$admin_dashboard_status" != "200" ]; then
    echo "Mini App admin dashboard returned HTTP $admin_dashboard_status" >&2
    exit 1
  fi
  admin_dashboard_latency_ms=$(http_time_ms GET "$BASE_URL$MINI_APP_PATH/api/admin/dashboard" \
    -H "X-Telegram-Init-Data: $admin_init_data")

  admin_summary_status=$(http_code GET "$BASE_URL$MINI_APP_PATH/api/admin/summary" \
    -H "X-Telegram-Init-Data: $admin_init_data")
  if [ "$admin_summary_status" != "200" ]; then
    echo "Mini App admin summary returned HTTP $admin_summary_status" >&2
    exit 1
  fi
  admin_summary_latency_ms=$(http_time_ms GET "$BASE_URL$MINI_APP_PATH/api/admin/summary" \
    -H "X-Telegram-Init-Data: $admin_init_data")

  admin_conversion_status=$(http_code GET "$BASE_URL$MINI_APP_PATH/api/admin/conversion" \
    -H "X-Telegram-Init-Data: $admin_init_data")
  if [ "$admin_conversion_status" != "200" ]; then
    echo "Mini App admin conversion returned HTTP $admin_conversion_status" >&2
    exit 1
  fi
  admin_conversion_latency_ms=$(http_time_ms GET "$BASE_URL$MINI_APP_PATH/api/admin/conversion" \
    -H "X-Telegram-Init-Data: $admin_init_data")

  admin_lifecycle_status=$(http_code GET "$BASE_URL$MINI_APP_PATH/api/admin/lifecycle?view=rules&limit=5" \
    -H "X-Telegram-Init-Data: $admin_init_data")
  if [ "$admin_lifecycle_status" != "200" ]; then
    echo "Mini App admin lifecycle returned HTTP $admin_lifecycle_status" >&2
    exit 1
  fi
  admin_lifecycle_latency_ms=$(http_time_ms GET "$BASE_URL$MINI_APP_PATH/api/admin/lifecycle?view=rules&limit=5" \
    -H "X-Telegram-Init-Data: $admin_init_data")

  admin_acquisition_status=$(http_code GET "$BASE_URL$MINI_APP_PATH/api/admin/acquisition" \
    -H "X-Telegram-Init-Data: $admin_init_data")
  if [ "$admin_acquisition_status" != "200" ]; then
    echo "Mini App admin acquisition returned HTTP $admin_acquisition_status" >&2
    exit 1
  fi
  admin_acquisition_latency_ms=$(http_time_ms GET "$BASE_URL$MINI_APP_PATH/api/admin/acquisition" \
    -H "X-Telegram-Init-Data: $admin_init_data")

  admin_promo_referral_status=$(http_code GET "$BASE_URL$MINI_APP_PATH/api/admin/promo-referrals" \
    -H "X-Telegram-Init-Data: $admin_init_data")
  if [ "$admin_promo_referral_status" != "200" ]; then
    echo "Mini App admin promo/referral returned HTTP $admin_promo_referral_status" >&2
    exit 1
  fi
  admin_promo_referral_latency_ms=$(http_time_ms GET "$BASE_URL$MINI_APP_PATH/api/admin/promo-referrals" \
    -H "X-Telegram-Init-Data: $admin_init_data")

  admin_pricing_status=$(http_code GET "$BASE_URL$MINI_APP_PATH/api/admin/pricing" \
    -H "X-Telegram-Init-Data: $admin_init_data")
  if [ "$admin_pricing_status" != "200" ]; then
    echo "Mini App admin pricing returned HTTP $admin_pricing_status" >&2
    exit 1
  fi
  admin_pricing_latency_ms=$(http_time_ms GET "$BASE_URL$MINI_APP_PATH/api/admin/pricing" \
    -H "X-Telegram-Init-Data: $admin_init_data")

  admin_read_models_status=$(http_code GET "$BASE_URL$MINI_APP_PATH/api/admin/read-models?limit=5" \
    -H "X-Telegram-Init-Data: $admin_init_data")
  if [ "$admin_read_models_status" != "200" ]; then
    echo "Mini App admin read-model diagnostics returned HTTP $admin_read_models_status" >&2
    exit 1
  fi
  admin_read_models_latency_ms=$(http_time_ms GET "$BASE_URL$MINI_APP_PATH/api/admin/read-models?limit=5" \
    -H "X-Telegram-Init-Data: $admin_init_data")

  admin_read_models_watchlist_status=$(http_code GET "$BASE_URL$MINI_APP_PATH/api/admin/read-models?view=watchlist&limit=5&source=live" \
    -H "X-Telegram-Init-Data: $admin_init_data")
  if [ "$admin_read_models_watchlist_status" != "200" ]; then
    echo "Mini App admin read-model watchlist returned HTTP $admin_read_models_watchlist_status" >&2
    exit 1
  fi
  admin_read_models_watchlist_latency_ms=$(http_time_ms GET "$BASE_URL$MINI_APP_PATH/api/admin/read-models?view=watchlist&limit=5&source=live" \
    -H "X-Telegram-Init-Data: $admin_init_data")

  admin_read_models_actions_status=$(http_code GET "$BASE_URL$MINI_APP_PATH/api/admin/read-models?view=actions&limit=5&source=live" \
    -H "X-Telegram-Init-Data: $admin_init_data")
  if [ "$admin_read_models_actions_status" != "200" ]; then
    echo "Mini App admin read-model action digest returned HTTP $admin_read_models_actions_status" >&2
    exit 1
  fi
  admin_read_models_actions_latency_ms=$(http_time_ms GET "$BASE_URL$MINI_APP_PATH/api/admin/read-models?view=actions&limit=5&source=live" \
    -H "X-Telegram-Init-Data: $admin_init_data")

  admin_read_models_drift_status=$(http_code GET "$BASE_URL$MINI_APP_PATH/api/admin/read-models?view=drift&limit=5&source=live" \
    -H "X-Telegram-Init-Data: $admin_init_data")
  if [ "$admin_read_models_drift_status" != "200" ]; then
    echo "Mini App admin read-model drift returned HTTP $admin_read_models_drift_status" >&2
    exit 1
  fi
  admin_read_models_drift_latency_ms=$(http_time_ms GET "$BASE_URL$MINI_APP_PATH/api/admin/read-models?view=drift&limit=5&source=live" \
    -H "X-Telegram-Init-Data: $admin_init_data")

  admin_users_status=$(http_code GET "$BASE_URL$MINI_APP_PATH/api/admin/users?query=$MINI_APP_SMOKE_USER_ID" \
    -H "X-Telegram-Init-Data: $admin_init_data")
  if [ "$admin_users_status" != "200" ]; then
    echo "Mini App admin users returned HTTP $admin_users_status" >&2
    exit 1
  fi

  admin_payments_status=$(http_code GET "$BASE_URL$MINI_APP_PATH/api/admin/payments?provider=all&page=1" \
    -H "X-Telegram-Init-Data: $admin_init_data")
  if [ "$admin_payments_status" != "200" ]; then
    echo "Mini App admin payments returned HTTP $admin_payments_status" >&2
    exit 1
  fi

  support_inbox_body=$(http_body GET "$BASE_URL$MINI_APP_PATH/api/admin/support?status=open&queue=awaiting_admin&page=1" \
    -H "X-Telegram-Init-Data: $admin_init_data")
  support_inbox_status=$(printf '%s' "$support_inbox_body" | python3 -c 'import json, sys; payload = json.load(sys.stdin); print(200 if payload.get("ok") else 500)')
  if [ "$support_inbox_status" != "200" ]; then
    echo "Mini App support inbox returned an invalid payload" >&2
    exit 1
  fi
  support_inbox_latency_ms=$(http_time_ms GET "$BASE_URL$MINI_APP_PATH/api/admin/support?status=open&queue=awaiting_admin&page=1" \
    -H "X-Telegram-Init-Data: $admin_init_data")

  support_insights_status=$(http_code GET "$BASE_URL$MINI_APP_PATH/api/admin/support/insights?view=hotspots&limit=5" \
    -H "X-Telegram-Init-Data: $admin_init_data")
  if [ "$support_insights_status" != "200" ]; then
    echo "Mini App support insights returned HTTP $support_insights_status" >&2
    exit 1
  fi
  support_insights_latency_ms=$(http_time_ms GET "$BASE_URL$MINI_APP_PATH/api/admin/support/insights?view=hotspots&limit=5" \
    -H "X-Telegram-Init-Data: $admin_init_data")

  first_ticket_id=$(printf '%s' "$support_inbox_body" | extract_first_ticket_id || true)
  if [ -n "$first_ticket_id" ]; then
    support_detail_body=$(http_body GET "$BASE_URL$MINI_APP_PATH/api/admin/support/$first_ticket_id" \
      -H "X-Telegram-Init-Data: $admin_init_data")
    support_detail_status=$(printf '%s' "$support_detail_body" | python3 -c 'import json, sys; payload = json.load(sys.stdin); print(200 if payload.get("ok") else 500)')
    if [ "$support_detail_status" != "200" ]; then
      echo "Mini App support detail returned HTTP $support_detail_status" >&2
      exit 1
    fi
    triage_confirm_key=$(printf '%s' "$support_detail_body" | extract_triage_confirm_key || true)
    if [ -n "$triage_confirm_key" ]; then
      support_triage_confirm_status=$(http_code POST "$BASE_URL$MINI_APP_PATH/api/admin/actions/support-triage-confirm" \
        -H "Content-Type: application/json" \
        -H "X-Telegram-Init-Data: $admin_init_data" \
        -d "{\"triage_key\":\"$triage_confirm_key\",\"ticket_id\":$first_ticket_id}")
      if [ "$support_triage_confirm_status" != "200" ]; then
        echo "Mini App support triage confirm returned HTTP $support_triage_confirm_status" >&2
        exit 1
      fi
    fi
  fi
fi

if [ "${CRYPTO_PAY_ENABLED:-false}" = "true" ] && [ -n "${CRYPTO_PAY_WEBHOOK_PATH:-}" ]; then
  crypto_status=$(http_code POST "$BASE_URL$CRYPTO_PAY_WEBHOOK_PATH" \
    -H 'Content-Type: application/json' \
    -H 'crypto-pay-api-signature: invalid-smoke-signature' \
    -d '{}')
  if [ "$crypto_status" != "401" ] && [ "$crypto_status" != "404" ]; then
    echo "Crypto webhook probe returned unexpected HTTP $crypto_status" >&2
    exit 1
  fi
fi

echo "Deploy stamp: ${DEPLOY_STAMP:-unknown}"
echo "Rollback backup: ${ROLLBACK_BACKUP_PATH:-unknown}"
echo "Latency baseline (ms): healthz=$health_latency_ms readyz=$ready_latency_ms mini_app=$mini_app_latency_ms webhook=$webhook_latency_ms"
if [ "$AUTH_ENABLED" = true ]; then
  echo "Latency baseline (ms): admin_summary=$admin_summary_latency_ms admin_dashboard=$admin_dashboard_latency_ms admin_conversion=$admin_conversion_latency_ms admin_acquisition=$admin_acquisition_latency_ms admin_promo_referral=$admin_promo_referral_latency_ms admin_pricing=$admin_pricing_latency_ms admin_read_models=$admin_read_models_latency_ms admin_read_models_watchlist=$admin_read_models_watchlist_latency_ms admin_read_models_actions=$admin_read_models_actions_latency_ms admin_read_models_drift=$admin_read_models_drift_latency_ms admin_lifecycle=$admin_lifecycle_latency_ms support_inbox=$support_inbox_latency_ms support_insights=$support_insights_latency_ms"
  echo "Manual Telegram checks still required: /admin_health, /admin_channel_check"
  echo "Webhook + Mini App authorized smoke checks passed for $WEBHOOK_URL"
else
  echo "Manual Telegram checks required: /admin_health, /admin_channel_check"
  echo "Webhook smoke checks passed for $WEBHOOK_URL (authorized Mini App checks skipped: set BOT_TOKEN and ADMIN_IDS)"
fi
write_smoke_summary
