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

  first_ticket_id=$(printf '%s' "$support_inbox_body" | extract_first_ticket_id || true)
  if [ -n "$first_ticket_id" ]; then
    support_detail_status=$(http_code GET "$BASE_URL$MINI_APP_PATH/api/admin/support/$first_ticket_id" \
      -H "X-Telegram-Init-Data: $admin_init_data")
    if [ "$support_detail_status" != "200" ]; then
      echo "Mini App support detail returned HTTP $support_detail_status" >&2
      exit 1
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

if [ "$AUTH_ENABLED" = true ]; then
  echo "Webhook + Mini App authorized smoke checks passed for $WEBHOOK_URL"
else
  echo "Webhook smoke checks passed for $WEBHOOK_URL (authorized Mini App checks skipped: set BOT_TOKEN and ADMIN_IDS)"
fi
