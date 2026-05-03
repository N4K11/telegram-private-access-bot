#!/usr/bin/env bash
set -euo pipefail

require_var() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "Missing required env var: $name" >&2
    exit 1
  fi
}

http_code() {
  local method="$1"
  local url="$2"
  shift 2
  curl -sS -o /dev/null -w '%{http_code}' -X "$method" "$url" "$@"
}

require_var PUBLIC_WEBHOOK_URL
require_var WEBHOOK_PATH
require_var MINI_APP_PATH

case "$WEBHOOK_PATH" in
  /*) ;;
  *)
    echo "WEBHOOK_PATH must start with /" >&2
    exit 1
    ;;
esac

BASE_URL="${PUBLIC_WEBHOOK_URL%/}"
WEBHOOK_URL="$BASE_URL$WEBHOOK_PATH"

curl -fsS "$BASE_URL/healthz" >/dev/null
curl -fsS "$BASE_URL/readyz" >/dev/null

page_status=$(http_code GET "$BASE_URL$MINI_APP_PATH")
if [ "$page_status" != "200" ]; then
  echo "Mini App page returned HTTP $page_status" >&2
  exit 1
fi

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

echo "Webhook smoke checks passed for $WEBHOOK_URL"