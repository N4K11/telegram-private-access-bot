# Telegram Private Access Bot

Production-oriented Telegram bot for selling access to private channels with Telegram Stars as the default payment method and optional Crypto Pay support.

## Implemented features

- Russian user and admin inline navigation.
- Minimalist runtime banners with safe text-only fallback.
- Channel and tariff management from the admin panel.
- `/admin_channel_check` for live channel diagnostics and bot rights verification.
- `/admin_health` for an admin-only runtime health dashboard.
- Promo codes for free days and Telegram Stars discounts.
- Referral codes with reward days credited after the referred user's first successful payment.
- Telegram Stars payments with idempotent processing.
- Optional Crypto Pay invoices with reconciliation worker and webhook processor.
- Personal invite links for active subscriptions.
- Automatic subscription expiration and channel access revocation.
- Admin analytics, user directory, direct messaging and manual subscription actions.
- Broadcast campaigns with queue processing.
- Managed text templates with mojibake protection and reset to defaults.
- Daily and manual backups with retention and Telegram document delivery.
- Healthcheck, JSON logs, anti-spam, runtime telemetry and rate limiting middleware.

## Stack

- Python 3.12+
- aiogram 3.x
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

- `CRYPTO_PAY_ENABLED`
- `CRYPTO_PAY_TOKEN`
- `BACKUP_*`
- `RATE_LIMIT_*`
- `PUBLIC_WEBHOOK_URL`
- `REFERRAL_REWARD_DAYS`

## Admin commands

- `/admin`
- `/admin_channel_check`
- `/admin_health`
- `/admin_promo_create CODE TYPE VALUE LIMIT [TARIFF_ID|-] [VALID_DAYS|-]`
- `/admin_promo_disable CODE`
- `/admin_promo_stats CODE`

## User commands

- `/promo CODE`
- `/paysupport`

## Project layout

- `app/` application code.
- `app/bot/` routers, filters, keyboards and middlewares.
- `app/services/` payment, invite, analytics, diagnostics, backup and text logic.
- `app/db/` models, repositories and session helpers.
- `app/workers/` background workers.
- `assets/` runtime PNG banners and avatar.
- `design/` editable SVG concepts and previews.
- 	ests/ unit and integration tests.
- .github/workflows/ CI workflow definitions.
- deploy/ deployment artifacts including the systemd example.
- scripts/ operational shell helpers for backup, verify and restore.

See also:

- `DEPLOY.md`
- `TESTING.md`
- `PROJECT_OVERVIEW.md`
- `CHANGELOG.md`
- `BACKUP_RESTORE.md`
- `RUNTIME_MAP.md`
- `DIAGNOSTICS.md`
- `VISUAL_ASSETS.md`

