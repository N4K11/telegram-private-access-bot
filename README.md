# Telegram Private Access Bot

Production-oriented Telegram bot for selling access to private channels with Telegram Stars as the default payment method and optional Crypto Pay support.

## Implemented features

- Russian user and admin inline navigation.
- Smart onboarding for first-time users with persistent three-step progress and skip flow.
- Content / FAQ CMS for FAQ, channel rules, post-payment guide, crypto guide and offer pages backed by managed text templates.
- Smart channel guard that checks active channels in the background and alerts admins once when bot rights are lost.
- Daily/weekly automatic admin reports with new users, payments, revenue, active subscriptions, anomalies, a read-model action digest and a live drift/budget regression digest.
- Retention automation for first-payment follow-up, pending-join reminders, recent-expiry win-back, inactive paid users and lost-after-trial recovery.
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
- Admin analytics, product funnel, acquisition ROI with lifecycle source quality, lifecycle ROI, pricing intelligence, promo/referral ROI, user directory, direct messaging and manual subscription actions.
- Snapshot-first Mini App admin diagnostics for read-model freshness, query budgets, payload size, slow/heavy admin views, a ranked watchlist, an action digest and an explicit `snapshot vs live` drift console.
- `/admin` and `/admin_health` now also surface a short read-model drift summary, so top live regressions are visible without opening the full diagnostics console.
- `/admin`, `/admin_health`, `/admin_observability` and scheduled admin reports now reuse the same compact read-model action/drift digest layer, so operator summaries stay consistent across bot-side surfaces.
- `/admin_observability` and scheduled admin reports now also surface a compact read-model watchlist summary, so the top missing/stale/budget issue is visible without opening the full diagnostics/watchlist consoles.
- `/admin` now surfaces a compact `Read-model summary` line built from the same watch/action/drift layer, while `/admin_health` keeps the dedicated snapshot/watchlist/drift metrics.
- Scheduled admin reports now also emit a unified `Read-model summary` line, prioritising live drift first, then snapshot watchlist, then the next recommended action.
- `/admin_observability` and the Mini App `Read-model diagnostics` card now expose the same compact `Read-model focus` plus `Summary` signal, so the top operator-facing issue and the short watch/action/drift digest stay aligned across bot-side and web-side diagnostics.
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
python -m app.tools.quality_gate
python -m compileall -q app tests alembic scripts
ruff check app tests alembic
python -m app.tools.repo_sanity
pytest -q -p no:cacheprovider
python -m alembic upgrade head
python -m app.main
python -m app.healthcheck
python -m app.tools.generate_minimal_assets
```

`python -m app.tools.quality_gate` is the preferred local gate. It avoids root-level `compileall .` over `.vendor`, `.tooling`, `.tmp` and other local cache directories, and includes tracked-file repository sanity checks.

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
- serves the Mini App page at `MINI_APP_PATH` with strict Telegram `initData` auth plus profile, multi-product catalog, payment, promo, support, recommendation surfaces and admin dashboard widgets;
- keeps background workers running;
- exposes `GET /healthz` and `GET /readyz`.

`USE_WEBHOOK=false` keeps the old polling flow unchanged.

## Admin commands

- `/admin`
- `/admin_channel_check`
- `/admin_health`
  Includes read-model snapshot health alongside bot/store/runtime checks.
- `/admin_finance`
- `/admin_audit`
- `/admin_roles`
- `/admin_observability`
  Includes snapshot summary plus explicit live `watchlist / action digest / snapshot vs live` visibility for admin read models, with in-bot callbacks for `snapshot / live / watchlist / actions / drift` diagnostics.
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
- `GET MINI_APP_PATH/api/admin/dashboard?source=snapshot|live`
- `GET MINI_APP_PATH/api/admin/dashboard?sections=summary,users_preview,payments_preview,...&source=snapshot|live`
- `GET MINI_APP_PATH/api/admin/conversion?source=snapshot|live`
- `GET MINI_APP_PATH/api/admin/acquisition?source=snapshot|live`
- `GET MINI_APP_PATH/api/admin/promo-referrals?source=snapshot|live`
- `GET MINI_APP_PATH/api/admin/pricing?source=snapshot|live`
- `GET MINI_APP_PATH/api/admin/read-models?view=overview|watchlist|actions|drift&limit=N&source=snapshot|live`
- `GET MINI_APP_PATH/api/admin/users?filter=...&query=...&page=...`
- `GET MINI_APP_PATH/api/admin/payments?provider=...&query=...&page=...`
- `GET MINI_APP_PATH/api/admin/support?status=...&queue=...&query=...&page=...`
- `GET MINI_APP_PATH/api/admin/support/insights?view=hotspots|sla_queue|sla_actions|pack_outcomes|close_trends|action_lanes|next_actions|action_routes|triage_queue|triage_plans|triage_confirm|triage_apply_history|triage_apply_routes|triage_apply_actors|triage_apply_replies|triage_apply_actor_replies|triage_apply_route_actors|triage_apply_reply_packs|triage_apply_route_reply_actors|triage_apply_focus|triage_apply_effectiveness|escalation_lanes|escalation_actions|priority_focus|escalation_watchlist|escalation_trends|operator_action_trends&limit=N&source=snapshot|live`
- `POST MINI_APP_PATH/api/admin/actions/support-triage-confirm`
- `POST MINI_APP_PATH/api/admin/actions/support-triage-apply`
- `GET MINI_APP_PATH/api/admin/support/{ticket_id}`
  Returns ticket thread, explicit `next_action`, pinned operator context, batch-aware `triage_batch`, triage pack/route hints, escalation hints, action-lane metadata, escalation-lane metadata, profile/payment context, suggested canned replies and operator-safe support metadata. The inbox payload also includes read-only support insights: queue priorities, SLA hotspots, SLA queue, SLA action plans, managed next-action queues, action routes, pack-aware triage queues, `triage_plans` with route-aware canned reply previews, `triage_confirm` with preview-only bulk triage confirmation notes, `triage_apply_history` with recent batch apply actions, `triage_apply_routes` with aggregated `route + pack + reply` history, `triage_apply_actors` with aggregated actor effectiveness by top route/reply, `triage_apply_replies` with aggregated reply mix by top actor/route, `triage_apply_actor_replies` with aggregated `actor + reply` usage by top route/pack, `triage_apply_route_actors` with aggregated `route + actor` usage by top reply/pack, `triage_apply_reply_packs` with aggregated `reply + pack` usage by top route/actor, `triage_apply_route_reply_actors` with aggregated `route + reply + actor` usage by top pack, `triage_apply_focus` with a compact ranked digest over those cross-cuts, `triage_apply_effectiveness` with the strongest recent apply path by route/reply/actor/pack coverage, plus sample ticket jumps for `sla_queue`, `next_actions`, `action_routes`, `triage_queue`, `triage_plans`, `triage_confirm`, `triage_apply_history`, `triage_apply_routes`, `triage_apply_actors`, `triage_apply_replies`, `triage_apply_actor_replies`, `triage_apply_route_actors`, `triage_apply_reply_packs` and `triage_apply_route_reply_actors`, canned-reply pack outcomes, close-reason trends, managed action lanes, managed escalation lanes, escalation-action mix, priority handling, escalation watchlist, escalation trends and operator action trends.
  `support-triage-confirm` accepts `triage_key` and optional `ticket_id`, writes an admin audit event and returns a preview-only manual draft: primary canned reply, sample tickets, signed confirm token and explicit operator steps. It does not send bulk replies automatically.
  `support-triage-apply` accepts `triage_key`, `confirm_token`, optional `reply_key` and optional `ticket_id`, revalidates the current triage route/pack against live open tickets, limits scope to the confirmed sample batch and applies only canned replies from the allowed pack.
- `GET MINI_APP_PATH/api/admin/lifecycle?view=rules|roi|sources|source_campaigns|source_roi|source_opportunities|source_actions|source_highlights|source_watchlist|highlights|waves|families|variants&limit=N&source=snapshot|live`
- `POST MINI_APP_PATH/api/admin/actions/channel-check`

Snapshot-backed Mini App admin responses expose:

- `generated_at`
- `staleness_seconds`
- `build_duration_ms`
- `query_count`
- `query_budget`
- `query_budget_ok`
- `payload_bytes`
- `payload_budget`
- `payload_budget_ok`
- `source` (`snapshot` by default, `live` on fallback or explicit override)

`/api/admin/dashboard` also supports additive section filtering for lazy admin boot and lighter request paths. Supported section keys: `summary`, `revenue_chart`, `users_preview`, `payments_preview`, `crypto_invoices`, `support`, `promos`, `tariffs`, `broadcasts`, `channels`, `anomalies`.

The dashboard `support` overview is intentionally compact; detailed support insights are lazy-loaded from `/api/admin/support/insights` instead of being embedded into the initial dashboard payload.
The dashboard `summary` is also preview-only on purpose: lifecycle/pricing/acquisition blocks expose only topline signals, while source/cohort and deeper attribution cuts stay in the dedicated lazy-loaded acquisition/lifecycle/support consoles.
The dashboard and `/api/admin/summary` now also embed compact snapshot-backed `read_model_focus`, `read_model_digest` and unified `read_model_operator_summary` previews, so the top operator issue plus the short watch/action summary are visible in the initial summary without loading the full read-model diagnostics console.

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






