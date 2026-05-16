# Deploy

## Docker Compose

1. Copy `.env.example` to `.env`.
2. Fill `BOT_TOKEN`, `ADMIN_IDS` and `DATABASE_URL`.
3. Choose runtime mode:
   - polling: leave `USE_WEBHOOK=false`;
   - webhook: set `USE_WEBHOOK=true` and fill `PUBLIC_WEBHOOK_URL`, `WEBHOOK_SECRET_TOKEN`, `WEBHOOK_PATH`, `WEBAPP_HOST`, `WEBAPP_PORT`, `MINI_APP_PATH`, `MINI_APP_AUTH_MAX_AGE_SECONDS`.
   - if Crypto Pay webhooks are enabled, also set `CRYPTO_PAY_WEBHOOK_PATH`.
4. Adjust optional sections for Crypto Pay, backups and rate limits.
5. Validate the compose file:

```bash
docker compose config
```

6. Build and start the stack:

```bash
docker compose up -d --build
```

7. Apply migrations:

```bash
docker compose exec bot alembic upgrade head
```

8. Check runtime health:

```bash
docker compose exec bot python -m app.healthcheck
```

9. If webhook mode is enabled, verify probes through your reverse proxy or directly on the app port:

```bash
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/readyz
```

## systemd

An example unit file is available at `deploy/systemd/telegram-private-access-bot.service`.

Typical layout on Ubuntu:

- project: `/opt/telegram-private-access-bot`
- environment file: `/opt/telegram-private-access-bot/.env`
- service user: `telegrambot`

Basic commands:

```bash
sudo cp deploy/systemd/telegram-private-access-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable telegram-private-access-bot
sudo systemctl start telegram-private-access-bot
sudo systemctl status telegram-private-access-bot
```

## Webhook notes

- `PUBLIC_WEBHOOK_URL` should be the public base URL without the webhook path.
- The runtime registers `PUBLIC_WEBHOOK_URL + WEBHOOK_PATH` in Telegram.
- `WEBHOOK_SECRET_TOKEN` is required when `USE_WEBHOOK=true`.
- `CRYPTO_PAY_WEBHOOK_PATH` is the signed HTTP endpoint for Crypto Pay updates when `CRYPTO_PAY_ENABLED=true`.
- `MINI_APP_PATH` serves the Telegram WebApp cabinet from the same aiohttp runtime.
- `MINI_APP_AUTH_MAX_AGE_SECONDS` limits how long Telegram `initData` remains valid for cabinet API calls.
- In Docker Compose mode the bot publishes WEBAPP_PORT on 127.0.0.1, so a host reverse proxy can safely proxy webhook and Mini App traffic without exposing the raw aiohttp port publicly.
- `DELETE_WEBHOOK_ON_SHUTDOWN=true` is optional and usually useful only in controlled maintenance flows.
- `/readyz` checks database connectivity and backup directory availability.

## Webhook smoke

After a webhook deploy, run the smoke script from the project root. It auto-loads `.env` when present, while explicit environment overrides still win:

```bash
bash scripts/smoke_webhook_runtime.sh
```

If `BOT_TOKEN` and `ADMIN_IDS` are available in the environment, the script also verifies:

- valid Mini App auth;
- `/api/bootstrap` and own profile access;
- non-admin `403` on `/api/admin/dashboard`;
- admin access to dashboard, lifecycle, users, payments, support inbox and support insights;
- optional support ticket detail, when at least one open ticket exists.

The smoke output now also prints:

- `Deploy stamp`;
- `Rollback backup`;
- `Smoke summary`, when `SMOKE_SUMMARY_PATH` is set by `scripts/deploy.sh`;
- latency baseline for `/healthz`, `/readyz`, Mini App page, webhook and authorized admin endpoints.

Optional overrides:

- `MINI_APP_SMOKE_USER_ID`
- `MINI_APP_SMOKE_USER_NAME`
- `MINI_APP_SMOKE_ADMIN_ID`
- `MINI_APP_SMOKE_ADMIN_NAME`

## Notes

- SQLite is intended only for local tests and development bootstrap.
- PostgreSQL is the production target.
- Backups intentionally exclude `.env` and runtime secrets.

## Deploy script

For non-container systemd deployments you can use `scripts/deploy.sh`.
It pulls the repo, installs dependencies, runs `python -m app.tools.quality_gate --summary-json "$QUALITY_GATE_SUMMARY_PATH"` (scoped compile/lint/repo-sanity/tests, Alembic, healthcheck and text scan with per-step timing summary), writes a machine-readable quality summary to `backups/deploy/quality-gate-$DEPLOY_STAMP.json`, creates a deterministic `predeploy-$DEPLOY_STAMP-db-backup.tar.gz` backup, writes rollback notes to `backups/deploy/rollback-$DEPLOY_STAMP.txt`, restarts the service and, in webhook mode, executes the runtime smoke automatically. When webhook smoke runs, it writes `backups/deploy/smoke-$DEPLOY_STAMP.json` with deploy stamp, rollback backup, checked runtime surface and latency baseline.
