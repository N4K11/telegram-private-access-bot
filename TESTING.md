# Testing

## Required checks

Use the scoped quality gate for local and pre-deploy validation:

```bash
python -m app.tools.quality_gate
```

The gate intentionally compiles only source paths (`app`, `tests`, `alembic`, `scripts`) so local dependency/cache directories such as `.vendor`, `.tooling` and `.tmp` do not affect syntax checks. It also runs tracked-file repository sanity checks for ignored runtime artifacts, token-like secrets and shell script line endings. It prints per-step timing plus a final pass/fail summary for release logs.

To persist the same summary for CI/deploy artifacts:

```bash
python -m app.tools.quality_gate --summary-json .tmp/quality-gate.json
```

GitHub Actions uploads that file as the `quality-gate-summary` artifact, including failed gate runs.

Budgeted Mini App admin views must also be registered in `app.services.admin_view_contracts.BUDGETED_ADMIN_VIEW_CONTRACTS`. The contract test checks route registration, smoke coverage, payload metadata keys and the declared query/payload budgets.

Equivalent explicit commands:

```bash
python -m compileall -q app tests alembic scripts
ruff check app tests alembic
python -m app.tools.repo_sanity
pytest -q -p no:cacheprovider
python -m alembic upgrade head
python -m app.healthcheck
python -m app.tools.scan_texts
```

## Webhook smoke

For webhook deployments, also run:

```bash
bash scripts/smoke_webhook_runtime.sh
```

The script auto-loads `.env` from the project root when present. With `BOT_TOKEN` and `ADMIN_IDS` available, it verifies authorized Mini App auth, bootstrap, role gating and admin support/users/payments endpoints.
It also verifies admin read-model diagnostics, read-model drift, lifecycle and support insights endpoints, prints a latency baseline and echoes the deploy stamp / rollback backup context when those env vars are exported by `scripts/deploy.sh`. Set `SMOKE_SUMMARY_PATH` to persist the same post-deploy smoke result as JSON.

## Docker validation

```bash
docker compose config
docker compose build
```

## Coverage areas in the current test suite

- settings parsing and runtime validation;
- user sync middleware;
- user/admin navigation;
- channels and tariffs;
- Telegram Stars payments;
- Crypto Pay processing and reconciliation;
- invite links;
- subscription expiration worker;
- analytics and admin user actions;
- admin read-model snapshots, snapshot/live fallback metadata and explicit `snapshot vs live` drift checks;
- broadcasts;
- text templates and mojibake protection;
- backups;
- rate limiting, logging and healthcheck.

## Known local warning

`pytest` may emit `PytestCacheWarning` in this Windows workspace because `.pytest_cache` is not writable in the ASCII junction environment. This does not affect test correctness.
