# Runtime Map

## Entry points

- `app.main` bootstraps the database/session factory, seeds text templates and starts either polling or webhook runtime.
- `app.healthcheck` performs a local runtime check against the database and backup directory.
- `app.tools.generate_minimal_assets` generates runtime PNG assets from the minimalist visual system.

## Runtime modes

- Polling is the default mode and still uses `dispatcher.start_polling(...)`.
- Webhook mode is enabled with `USE_WEBHOOK=true` and served by `app.webhook.server`.
- `app.webhook.handlers` exposes:
  - `POST WEBHOOK_PATH` for Telegram updates;
  - `GET /healthz` for liveness;
  - `GET /readyz` for readiness.
- `app.webapp.handlers` serves the Mini App page at `MINI_APP_PATH` and strict auth APIs under `MINI_APP_PATH/api/*`, including admin dashboard/users/payments/support endpoints and the Mini App channel-check action.
- `app.services.web_cabinet` serializes the user cabinet payload: profile, grouped products, active product access, flat tariffs, recent payments, referrals, pending promos, support state and Telegram deep-link actions.
- `app.services.web_admin_dashboard` serializes the Mini App admin dashboard, filterable users/payments/support payloads, ticket detail context, safe overview cards and the live channel-check action result.
- In webhook mode the runtime registers `PUBLIC_WEBHOOK_URL + WEBHOOK_PATH` via `setWebhook` and can optionally call `deleteWebhook` on shutdown.

## Runtime state and telemetry

- `app.runtime_state` stores the in-memory process snapshot: uptime, last update, last maintenance run, last Telegram API error and last Crypto Pay reconciliation result.
- `app.bot.middlewares.runtime_state` updates last-update telemetry on every message, callback and pre-checkout event.
- `app.logging_config.TelegramApiErrorCaptureHandler` stores the last Telegram API error from runtime logs.

## Routers

- `app.bot.routers.user.start` - `/start`, referral payload `ref_*`, smart onboarding, main menu, profile, help and invite link.
- `app.bot.routers.user.payments` - Stars, Crypto Pay, product picker, per-product tariffs, purchase flow and `paysupport`.
- `app.bot.routers.user.promos` - `/promo`, promo preview text and free-days/discount promo handling.
- `app.bot.routers.user.referrals` - `/my_referrals` and the inline referral dashboard from the profile screen.
- `app.bot.routers.user.invites` - invite link delivery and resend.
- `app.bot.routers.user.support` - in-bot support ticket creation, user ticket history and follow-up messages.
- `app.bot.routers.user.legal` - `/terms`, `/privacy`, `/refunds` and inline legal cards from the help screen.
- `app.bot.routers.user.cabinet` - `/cabinet` and the WebApp launch button.
- `app.bot.routers.admin.dashboard` - `/admin`, role-aware section navigation and per-role admin menu visibility.
- `app.bot.routers.admin.roles` - `/admin_roles`, owner-only role management and settings screen.
- `app.bot.routers.admin.observability` - `/admin_observability`, read-only runtime error dashboard.
- `app.bot.routers.admin.diagnostics` - `/admin_channel_check` and live channel diagnostics.
- `app.bot.routers.admin.health` - `/admin_health` and runtime health dashboard.
- `app.bot.routers.admin.support` - `/admin_support`, admin inbox, replies and ticket status changes.
- `app.bot.routers.admin.audit` - `/admin_audit`, filterable audit viewer, event detail cards and redacted CSV export.
- `app.services.support` - support ticket validation, rate limits, thread lifecycle and audit writes.
- `app.services.onboarding` - first-run onboarding eligibility, progress persistence and onboarding copy rendering.
- `app.services.content_service` - registry and safe rendering for FAQ/content pages.
- `app.services.channel_guard_service` - background protection for active channels with deduplicated admin alerts.
- `app.services.report_service` - scheduled daily/weekly admin KPI reports with duplicate protection.
- `app.services.legal_texts` - registry of managed legal texts for terms, privacy, refund policy and payment support.
- `app.services.audit` - audit write helper, filter normalization, payload redaction and CSV export for admins.
- `app.db.repositories.support_tickets` - support ticket and support message persistence helpers.
- `app.bot.routers.admin.promos` - admin promo create/view/list/disable/stats commands with campaign and validity options.
- `app.bot.routers.admin.referrals` - `/admin_referrals` with top referrers, suspicious cases and reward totals.
- `app.bot.routers.admin.crypto` - `/admin_crypto_invoices`, `/admin_crypto_diag` and the admin payments dashboard callback.
- `app.bot.routers.admin.channels` - channel CRUD and refresh.
- `app.bot.routers.admin.tariffs` - tariff CRUD.
- `app.bot.routers.admin.analytics` - analytics snapshot and users entry points.
- `app.bot.routers.admin.users` - user directory for allowed admin roles plus owner/admin-only blocking, manual grants and direct message.
- `app.services.admin_roles` - role normalization, `ADMIN_IDS` owner fallback, permission checks and admin menu section policy.
- `app.services.observability` - structured event names, runtime error sanitization and admin observability report builder.
- `app.bot.routers.admin.texts` - managed text templates.
- `app.bot.routers.admin.broadcasts` - segmented broadcasts, preview/confirm flow and reusable templates.
- `app.bot.routers.admin.backups` - manual backups and backup delivery to admin.

## Background workers

- `app.workers.subscription_expirer` - 3d/1d warnings, expired notices, grace period and revoke.
- `app.workers.payment_reconciler` - placeholder module for Crypto Pay reconciliation wiring.
- `app.workers.broadcast_sender` - broadcast queue sender with isolated per-user failures and rate-limited delivery accounting.
- `app.workers.backup_worker` - scheduled backup and retention.
- `app.workers.scheduler` - worker orchestrator, `channel_guard`, `admin_reports` and last-maintenance telemetry.
- Workers run in both polling and webhook modes.

## Persistent data

- PostgreSQL: `users` (including referral codes/referred-by/reward balance and onboarding progress), `channels`, `tariffs`, `subscriptions`, `payments`, `invite_links`, `crypto_invoices`, `audit_logs`, `text_templates`, `broadcast_*`, `backup_records`, `promo_codes` (including validity windows, first-purchase flag, per-user limit, campaign and notes), `promo_redemptions`.
- Local backup files live in `backups/` or the directory from `BACKUP_DIRECTORY`.

## Visual assets

- Runtime banners: `assets/banners/*.png`.
- Bot avatar candidate: `assets/avatar/bot_avatar.png`.
- Source concepts: `design/minimalist-concepts/`.

## Repository hygiene

- `.gitignore` excludes local runtime/cache/dev artifacts such as `.venv/`, `.tmp/`, `.vendor/`, `__pycache__/`, `*.pyc`, `*.db`, `backups/*` and runtime logs.
- `tests/unit/test_repo_hygiene.py` enforces that local artifacts are not tracked and tracked source/docs do not contain token-like secrets.







