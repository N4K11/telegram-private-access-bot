# Telegram Private Access Bot

Production-oriented Telegram bot for selling access to private channels with Telegram Stars as the default payment method and optional Crypto Pay support.

## Implemented features

- Russian user and admin inline navigation.
- Smart onboarding for first-time users with persistent three-step progress and skip flow.
- Content / FAQ CMS for FAQ, channel rules, post-payment guide, crypto guide and offer pages backed by managed text templates.
- Smart channel guard that checks active channels in the background and alerts admins once when bot rights are lost.
- Daily/weekly automatic admin reports with new users, payments, revenue, active subscriptions and anomalies.
- Minimalist runtime banners with safe text-only fallback.
- Channel and tariff management from the admin panel.
- `/admin_channel_check` for live channel diagnostics and bot rights verification.
- `/admin_health` for an admin-only runtime health dashboard.
- Promo system 2.0 with validity windows, first-purchase-only rules, per-user limits, campaigns, notes and Telegram Stars discount previews.
- Referral dashboard for users, admin referral analytics and anti-fraud audit around reward issuance.
- Telegram Stars payments with idempotent processing.
- Optional Crypto Pay invoices with reconciliation worker, signed webhook processor and admin diagnostics.
- Admin finance dashboard with Stars/Crypto overview and CSV exports.
- Personal invite links for active subscriptions.
- Automatic subscription expiration, warnings and channel access revocation.
- Admin analytics, user directory, direct messaging and manual subscription actions.
- Role-based admin permissions with `owner`, `admin`, `support` and `analyst` scopes plus owner-only `/admin_roles`.
- `/admin_observability`
- In-bot support tickets with categories, user thread view and admin inbox with reply/close/reopen.
- Admin audit log viewer with filters by target user, actor, action and period, event details and redacted CSV export.
- Broadcast 2.0 with segmentation, preview samples, explicit confirm, delivery report and reusable templates.
- Managed text templates with mojibake protection and reset to defaults.
- Managed legal texts for terms, privacy, refunds and payment support.
- Daily and manual backups with retention and Telegram document delivery.
- Healthcheck, JSON logs, anti-spam, runtime telemetry and rate limiting middleware.
- Dual runtime modes: polling by default and production webhook mode with `/healthz`, `/readyz` and the Telegram Mini App cabinet with profile, multi-product catalog, active product access, tariffs, payments, referrals, promos, support, renew CTA and an admin dashboard for users, payments, crypto invoices, promos, tickets, broadcasts, anomalies and live channel check.

## Stack

- Python 3.12+
- aiogram 3.x
- aiohttp
- SQLAlchemy async
- Alembic
- PostgreSQL for production
- SQLite for local tests only
- Docker / Docker Compose
- pytest / Ruff

## Local commands

```bash
python -m compileall app tests alembic
ruff check .
pytest -q
alembic upgrade head
python -m app.main
python -m app.healthcheck
python -m app.tools.generate_minimal_assets
```

`python -m app.main` starts polling by default. Set `USE_WEBHOOK=true` to start the aiohttp webhook runtime instead.

## Docker

```bash
docker compose config
docker compose up -d --build
```

The bot container includes a healthcheck based on `python -m app.healthcheck`.

## Environment

Start from `.env.example` and fill at least:

- `BOT_TOKEN`
- `ADMIN_IDS`
- `DATABASE_URL`

Optional production flags:

- `USE_WEBHOOK`
- `PUBLIC_WEBHOOK_URL`
- `BOT_PUBLIC_USERNAME`
- `WEBHOOK_SECRET_TOKEN`
- `WEBHOOK_PATH`
- `WEBAPP_HOST`
- `WEBAPP_PORT`
- `DELETE_WEBHOOK_ON_SHUTDOWN`
- `MINI_APP_PATH`
- `MINI_APP_AUTH_MAX_AGE_SECONDS`
- `CRYPTO_PAY_ENABLED`
- `CRYPTO_PAY_TOKEN`
- `CRYPTO_PAY_WEBHOOK_PATH`
- `BACKUP_*`
- `RATE_LIMIT_*`
- `REFERRAL_REWARD_DAYS`

## Webhook mode

When `USE_WEBHOOK=true`, the runtime:

- starts an aiohttp server;
- binds the Telegram webhook endpoint at `WEBHOOK_PATH`;
- validates `X-Telegram-Bot-Api-Secret-Token`;
- registers `PUBLIC_WEBHOOK_URL + WEBHOOK_PATH` via `setWebhook`;
- serves the Mini App page at `MINI_APP_PATH` with strict Telegram `initData` auth plus profile, multi-product catalog, payment, promo, support and admin dashboard widgets;
- keeps background workers running;
- exposes `GET /healthz` and `GET /readyz`.

`USE_WEBHOOK=false` keeps the old polling flow unchanged.

## Admin commands

- `/admin`
- `/admin_channel_check`
- `/admin_health`
- `/admin_finance`
- `/admin_audit`
- `/admin_roles`
- `/admin_observability`
- `/admin_promo_create CODE TYPE VALUE LIMIT [TARIFF_ID|-] [VALID_DAYS|-] [from=ISO] [until=ISO] [first=0|1] [per_user=N] [campaign=NAME] [notes=TEXT]`
- `/admin_promo_disable CODE`
- `/admin_promo_view CODE`
- `/admin_promo_list [QUERY]`
- `/admin_promo_stats CODE`
- `/admin_referrals`
- `/admin_support`

## User commands

- `/promo CODE`
- `/my_referrals`
- `/paysupport`
- `/terms`
- `/privacy`
- `/refunds`
- `/support`
- `/cabinet`

## Mini App admin API

- `GET MINI_APP_PATH/api/admin/dashboard`
- `GET MINI_APP_PATH/api/admin/users?filter=...&query=...&page=...`
- `GET MINI_APP_PATH/api/admin/payments?provider=...&query=...&page=...`
- `POST MINI_APP_PATH/api/admin/actions/channel-check`

## Project layout

- `app/` application code.
- `app/bot/` routers, filters, keyboards and middlewares.
- `app/services/` payment, invite, analytics, diagnostics, backup, reporting and text logic.
- `app/db/` models, repositories and session helpers.
- `app/webhook/` webhook runtime server and HTTP handlers.
- `app/webapp/` Mini App HTTP handlers and auth binding.
- `web/` Mini App static frontend.
- `app/workers/` background workers.
- `assets/` runtime PNG banners and avatar.
- `design/` editable SVG concepts and previews.
- `tests/` unit, integration and smoke tests.
- `.github/workflows/` CI workflow definitions.
- `deploy/` deployment artifacts including the systemd example.
- `scripts/` operational shell helpers for backup, verify, restore and deploy.

See also:

- `DEPLOY.md`
- `TESTING.md`
- `PROJECT_OVERVIEW.md`
- `CHANGELOG.md`
- `BACKUP_RESTORE.md`
- `RUNTIME_MAP.md`
- `DIAGNOSTICS.md`
- `VISUAL_ASSETS.md`






