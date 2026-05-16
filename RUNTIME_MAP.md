# Runtime Map

## Audit checkpoint 2026-05-10

This map reflects the current single-brand/single-owner runtime after the continuation audit. No SaaS or multi-tenant runtime is active.

Runtime spine:

- `app.main.run()` loads `Settings`, validates required runtime configuration, creates the async SQLAlchemy engine/session factory, seeds default texts, starts the bot dispatcher and launches background workers.
- Runtime mode is selected by `USE_WEBHOOK`; polling uses `dispatcher.start_polling`, webhook mode uses aiohttp and registers `PUBLIC_WEBHOOK_URL + WEBHOOK_PATH` with Telegram.
- `app.webhook.handlers` owns external HTTP safety: Telegram secret-token check, Crypto Pay signature check, invalid JSON handling, `/healthz` liveness and `/readyz` DB readiness.
- `app.webapp.handlers` owns Mini App HTTP routing; all API reads authenticate Telegram `initData`, then admin paths pass role permission gates before serializers run.

Commercial/access spine:

- Stars payments are handled by `app.services.payments.stars`; successful Telegram payment payloads validate currency, tariff id, expected amount and duplicate charge id before subscription activation and paid payment creation.
- Crypto Pay invoices are handled by `app.services.payments.crypto_pay`; active invoices are reconciled by the scheduler, paid invoices dedupe by `crypto:invoice:{external_id}`, then activate/extend subscription and write paid payment/audit/referral events.
- Subscription activation is centralized in `app.services.subscriptions.activate_or_extend_subscription`; current active access is extended from current expiry, otherwise a new subscription starts at payment time.
- Invite delivery is centralized in `app.services.invites.issue_subscription_invite_link`; it reuses a still-active invite for the subscription or creates a one-user Telegram invite link.

Snapshot/admin read spine:

- Snapshot tables are `analytics_daily_facts`, `lifecycle_campaign_facts` and `support_queue_facts`.
- `app.services.admin_read_model_refresh` materializes dashboard, summary, conversion, acquisition, pricing, promo/referral, lifecycle and support insight payloads.
- Scheduler cadence is controlled by `ADMIN_READ_MODELS_ANALYTICS_INTERVAL_MINUTES` default `15` and `ADMIN_READ_MODELS_SUPPORT_INTERVAL_MINUTES` default `5`.
- Mini App admin serializers default to `source=snapshot`; `source=live` remains an explicit admin-only recompute/debug path.
- Admin responses expose read-model metadata: `generated_at`, `staleness_seconds`, `build_duration_ms`, `query_count`, `query_budget`, `payload_bytes`, `payload_budget` and budget booleans.

Operational spine:

- Background workers cover subscription expiry/revoke, broadcasts, backups, Crypto Pay reconciliation, channel guard, scheduled admin reports, admin read-model refresh and retention automation.
- Deploy hygiene is centered on `scripts/deploy.sh`: pull, install, `python -m app.tools.quality_gate --summary-json "$QUALITY_GATE_SUMMARY_PATH"`, persisted quality-gate JSON, deterministic `predeploy-$DEPLOY_STAMP-db-backup.tar.gz` backup, rollback notes, service restart and webhook smoke with optional persisted smoke JSON.
- Local/CI quality hygiene is centered on `python -m app.tools.quality_gate`, which runs the same source-scoped compile/lint/repo-sanity/test/db/text checks without traversing local dependency/cache directories and prints per-step timing plus a final pass/fail summary. CI uploads the JSON summary as `quality-gate-summary`.
- Webhook smoke covers health/readiness, Mini App page/auth/bootstrap/profile/admin gates, key lazy admin endpoints, support inbox/insights and invalid webhook-token rejection.
- Current local baseline is green for scoped compile, ruff, pytest, Alembic, healthcheck, Mini App JS syntax and repository text encoding scan.

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
- `app.webapp.handlers` serves the Mini App page at `MINI_APP_PATH` and strict auth APIs under `MINI_APP_PATH/api/*`, including admin dashboard/users/payments/support endpoints, the Mini App lifecycle/pricing/acquisition/promo consoles, the read-model diagnostics/watchlist/actions/drift consoles, and the Mini App channel-check action.
- `app.services.web_cabinet` serializes only the user cabinet payload: profile, grouped products, recommended offers, active product access, flat tariffs, recent payments, referrals, pending promos, support state and Telegram deep-link actions. Admin summary analytics are kept out of this user-facing service.
- `app.services.web_admin_dashboard` is now a thin snapshot-first facade for the Mini App admin dashboard, while section-specific builders live in dedicated `web_admin_dashboard_*_sections` modules for analytics, lifecycle, support, directory, overview/dashboard wiring and read-model diagnostics. Support admin triage mutations live in `app.services.web_admin_dashboard_support_actions`, support inbox/overview endpoint orchestration lives in `app.services.web_admin_dashboard_support_inbox_sections`, support insight endpoint orchestration lives in `app.services.web_admin_dashboard_support_insight_sections`, support ticket detail endpoint orchestration lives in `app.services.web_admin_dashboard_support_ticket_sections`, support insight serialization lives in `app.services.web_admin_dashboard_support_insight_serializers`, closed-ticket insight distribution/outcome serialization lives in `app.services.web_admin_dashboard_support_closed_insight_serializers`, SLA/action insight serialization lives in `app.services.web_admin_dashboard_support_action_insight_serializers`, escalation/priority/operator trend insight serialization lives in `app.services.web_admin_dashboard_support_escalation_insight_serializers`, support insight view registry/selection lives in `app.services.web_admin_dashboard_support_insight_views`, triage queue/plan/confirm serialization lives in `app.services.web_admin_dashboard_support_triage_queue_serializers`, triage-apply list serialization lives in `app.services.web_admin_dashboard_support_triage_apply_view_serializers`, triage queue/plan/confirm summary orchestration lives in `app.services.web_admin_dashboard_support_triage_summary_serializers`, triage-apply summary serialization lives in `app.services.web_admin_dashboard_support_triage_apply_summary_serializers`, triage view orchestration and compatibility re-exports live in `app.services.web_admin_dashboard_support_triage_apply_serializers`, support list/filter/queue serializers live in `app.services.web_admin_dashboard_support_ticket_list_serializers`, support ticket detail/operator serializers live in `app.services.web_admin_dashboard_support_ticket_detail_serializers`, and support ticket compatibility re-exports live in `app.services.web_admin_dashboard_support_ticket_serializers`, leaving `web_admin_dashboard_support_sections` as the support compatibility facade. Heavy Mini App admin reads expose `generated_at`, `staleness_seconds`, `build_duration_ms`, `query_count`, `query_budget`, `query_budget_ok`, `payload_bytes`, `payload_budget`, `payload_budget_ok` and `source=snapshot|live`, and support section-scoped dashboard payloads for lazy admin boot.
- `app.services.web_admin_dashboard_summary_sections` owns the Mini App `/api/admin/summary` snapshot/live serializer and its read-model focus/digest enrichment, so admin summary logic stays inside the admin serializer layer instead of `web_cabinet`.
- Dedicated lazy admin consoles now exist for conversion/products, acquisition/sources, promo/referrals, pricing/offers, lifecycle, support insights (`hotspots`, `sla_queue`, `next_actions`, `action_routes`, `triage_queue`, `triage_plans`, `triage_confirm`, `triage_apply_history`, `triage_apply_routes`, `triage_apply_actors`, `triage_apply_replies`, `triage_apply_actor_replies`, `triage_apply_route_actors`, `triage_apply_reply_packs`, `triage_apply_route_reply_actors`, `triage_apply_focus`, `triage_apply_effectiveness`, escalation/routing views with sample ticket jumps and canned-reply previews for the main action queues) and read-model diagnostics/watchlist/actions/drift, so the initial dashboard summary can stay compact while deep cuts are fetched on demand.
- `app.services.web_admin_dashboard_analytics_sections` is now the snapshot wrapper/live payload facade for pricing, acquisition, conversion and promo/referral Mini App consoles; shared dashboard/summary/detail serializers live in `app.services.web_admin_dashboard_analytics_serializers`.
- `app.services.web_admin_dashboard_lifecycle_sections` is now the snapshot wrapper/compatibility facade for the lifecycle Mini App console; live lifecycle payload construction lives in `app.services.web_admin_dashboard_lifecycle_live`, source acquisition/campaign lifecycle view serialization lives in `app.services.web_admin_dashboard_lifecycle_source_serializers`, lifecycle attribution rule/ROI/wave/family/variant view serialization lives in `app.services.web_admin_dashboard_lifecycle_attribution_serializers`, compact lifecycle campaign source summary serialization lives in `app.services.web_admin_dashboard_lifecycle_campaign_source_serializers`, and compact dashboard/summary lifecycle serializers live in `app.services.web_admin_dashboard_lifecycle_serializers`.
- `app.services.admin_view_contracts` is the guardrail for budgeted Mini App admin views: route registration, smoke path, query budget, payload budget and required read-model meta are tested as one contract before new heavy views can land.
- Support triage now also has an operator-safe manual confirm/apply flow implemented in `app.services.web_admin_dashboard_support_actions`: `support-triage-confirm` takes a `triage_key`, writes audit and returns a draft-only batch preview with primary canned reply, signed confirm token, operator steps and sample ticket jumps; `support-triage-apply` consumes that token, revalidates the live route/pack and applies only canned replies to the confirmed sample scope.
- Support inbox list items and ticket detail now carry additive `triage_pack` / `triage_route` hints plus batch-aware `triage_batch` metadata, so operators can see the recommended canned-reply pack, escalation-to-action route, primary batch reply and nearby tickets directly in the main support workflow without opening the insights console first.
- Support domain code is modularized for Wave 3: `app.services.support` owns inbox orchestration and insight composition, `app.services.support_models` owns DTO/dataclass contracts, `app.services.support_catalog` owns support constants/labels/pure label helpers, `app.services.support_reply_packs` owns canned reply pack definitions and builders, `app.services.support_sla` owns waiting-state/SLA/action/escalation routing helpers, `app.services.support_sla_queues` owns SLA hotspot/action/action-lane queue builders, `app.services.support_action_queues` owns next-action, action-route and triage queue builders, `app.services.support_escalation_queues` owns escalation-lane/action/priority/watchlist builders, `app.services.support_queue_ranking` owns open-ticket ranking and sample ticket selection helpers, `app.services.support_open_queues` keeps compatibility re-exports for open-ticket queue builders, `app.services.support_triage_apply_history` owns triage-apply audit-log history loading, `app.services.support_triage_apply_notes` owns triage-apply aggregate note text, `app.services.support_triage_apply_core` owns route/actor aggregate builders, `app.services.support_triage_apply_replies` owns reply/actor-reply/route-actor aggregate builders, `app.services.support_triage_apply` keeps compatibility re-exports, `app.services.support_triage_apply_combinations` owns reply-pack and route/reply/actor aggregate combinations, `app.services.support_triage_apply_rankings` owns triage-apply focus/effectiveness rankings, `app.services.support_ticket_flow` owns ticket validation, user/admin thread reads and ticket mutations and `app.services.support_insight_trends` owns closed-ticket pack/close-reason/operator-action trend builders.
- The dashboard `support` overview stays compact on purpose: detailed support insights are loaded via the dedicated `support/insights` endpoint instead of being embedded into the initial dashboard payload.
- The dashboard `summary` is compact as well: it carries only top lifecycle/pricing/acquisition/promo/referral/conversion topline signals, while product funnel detail stays in the dedicated conversion endpoint, source/cohort attribution cuts stay in the dedicated lazy-loaded acquisition and lifecycle endpoints, promo/referral detail stays in the dedicated promo/referral endpoint, and managed-wave / touch-family / retention detail stays in the lifecycle endpoint.
- That same summary now also receives compact snapshot-backed `read_model_focus`, `read_model_digest` and unified `read_model_operator_summary` previews, so the top read-model issue and the short watch/action summary are visible in dashboard/admin summary boot without loading the full diagnostics views.
- `app.services.admin_read_models` stores and restores Postgres-backed read-model payloads for admin dashboard summary, read-model diagnostics, pricing/acquisition/conversion/promo slices, lifecycle views and support insights; drift compares reuse those stored baselines and only execute live when explicitly requested.
- `app.services.admin_read_model_refresh` materializes those read models on a cadence from the background scheduler.
- `app.services.admin_read_model_reporting` is the compatibility facade for operator-facing snapshot and drift summaries so `/admin`, `/admin_health` and `/admin_observability` can surface read-model risk, budget/query/payload regressions and top drift items without duplicating Mini App admin payload logic; its shared DTO contracts live in `app.services.admin_read_model_reporting_models`, snapshot payload-to-summary builders live in `app.services.admin_read_model_reporting_summaries`, digest/focus/payload renderers live in `app.services.admin_read_model_reporting_digests`, and async snapshot/live loaders live in `app.services.admin_read_model_reporting_loaders`.
- `app.services.admin_home`, `app.services.health_service`, `app.services.report_service` and `app.services.observability` now reuse that layer for shared compact read-model watchlist/action/drift digests in bot-side operator views and scheduled reports; `/admin` now renders a single compact `Read-model summary`, while `/admin_health` exposes dedicated snapshot/watchlist/drift health metrics.
- The same layer now also builds a unified `Read-model focus`/operator summary path for `/admin` and scheduled reports, with priority `live drift -> snapshot watchlist -> next action`.
- `app.services.web_admin_dashboard_read_model_sections` now also serializes `focus_summary` and `operator_digest_summary` for the Mini App read-model diagnostics views, with watchlist/action/focus helper logic isolated in `app.services.web_admin_dashboard_read_model_actions`, action digest decision helpers isolated in `app.services.web_admin_dashboard_read_model_action_digest`, watchlist item/leader helpers isolated in `app.services.web_admin_dashboard_read_model_watchlist`, the tracked snapshot surface registry isolated in `app.services.web_admin_dashboard_read_model_descriptors`, read-model constants/status helpers isolated in `app.services.web_admin_dashboard_read_model_core`, read-model drift serializers isolated in `app.services.web_admin_dashboard_read_model_drift_serializers`, read-model overview item serializers isolated in `app.services.web_admin_dashboard_read_model_serializers`, live descriptor dispatch isolated in `app.services.web_admin_dashboard_read_model_live_descriptors`, live overview builder isolated in `app.services.web_admin_dashboard_read_model_live_overview`, snapshot row lookups isolated in `app.services.web_admin_dashboard_read_model_store`, and live watchlist/actions/drift recompute builders isolated in `app.services.web_admin_dashboard_read_model_live`; `app.services.admin_read_model_text` and `app.services.observability` render the same signals for in-bot diagnostics and `/admin_observability`.
- `app.services.report_service` now reuses that reporting layer for daily/weekly admin digests, so scheduled ops reports can mention top read-model actions plus live drift/budget regressions alongside revenue/anomaly toplines.
- `app.services.admin_analytics_text` renders the in-bot admin analytics report so the Telegram admin route can consume the same snapshot-backed data model as Mini App admin surfaces.
- Analytics domain code is modularized for Wave 3: `app.services.analytics` owns snapshot orchestration and compatibility re-exports, `app.services.analytics_models` owns analytics DTO/dataclass contracts, `app.services.analytics_lifecycle` owns lifecycle/source-campaign attribution helper logic, `app.services.analytics_lifecycle_builders` owns lifecycle queue/offer/campaign builders, `app.services.analytics_common` owns shared query/payload helpers, `app.services.analytics_funnel` owns product/source funnel builders, `app.services.analytics_acquisition` owns source acquisition builders, `app.services.analytics_pricing` owns pricing/offer/product-pair intelligence builders and `app.services.analytics_promo_referral` owns promo/referral attribution builders.
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
- `app.bot.routers.admin.observability` - `/admin_observability`, read-only runtime error dashboard plus in-bot read-model snapshot/watchlist/actions/live/drift diagnostics callbacks and unified read-model focus rendering.
- `app.bot.routers.admin.diagnostics` - `/admin_channel_check` and live channel diagnostics.
- `app.bot.routers.admin.health` - `/admin_health`, runtime health dashboard and read-model snapshot health surface.
- `app.bot.routers.admin.support` - `/admin_support`, admin inbox, replies, ticket status changes and in-thread `next action` guidance.
- `app.bot.routers.admin.audit` - `/admin_audit`, filterable audit viewer, event detail cards and redacted CSV export.
- `app.services.support` - support ticket orchestration, validation, rate limits, thread lifecycle, insights construction and audit writes.
- `app.services.support_models` - support DTO/dataclass contracts shared by bot admin, Mini App admin and support service internals.
- `app.services.support_catalog` - support status/category/priority/SLA/action/escalation constants plus pure operator-facing label helpers.
- `app.services.support_reply_packs` - canned reply pack definitions and canned-reply builders used by ticket detail, insights and triage apply flows.
- `app.services.support_sla` - support waiting-state, SLA bucket, action-lane, escalation-lane and next-action helper logic re-exported through `app.services.support`.
- `app.services.support_sla_queues` - open-ticket SLA hotspot, SLA action, SLA action queue and action-lane builders.
- `app.services.support_action_queues` - open-ticket next-action queue, escalation/action route and canned-reply triage queue builders.
- `app.services.support_escalation_queues` - open-ticket escalation lane/action, priority focus and escalation watchlist builders.
- `app.services.support_queue_ranking` - shared support queue ranking and sample ticket selection helpers used by open queues and triage-apply aggregates.
- `app.services.support_open_queues` - compatibility re-export facade for open-ticket support insight builders.
- `app.services.support_triage_apply_history` loads support triage-apply audit-log history for recent batch applies.
- `app.services.support_triage_apply_notes` renders triage-apply aggregate notes shared by route/actor/reply builders.
- `app.services.support_triage_apply_core` builds route/actor aggregates from triage-apply history.
- `app.services.support_triage_apply_replies` builds reply/actor-reply/route-actor aggregates from triage-apply history. `app.services.support_triage_apply` keeps compatibility re-exports; reply-pack and route/reply/actor combinations live in `app.services.support_triage_apply_combinations`, while focus/effectiveness rankings live in `app.services.support_triage_apply_rankings`.
- `app.services.support_ticket_flow` - support ticket validation, user/admin thread reads, create/reply/close/reopen mutations and admin reply notification text, re-exported through `app.services.support`.
- `app.services.support_insight_trends` - closed-ticket support insight builders for canned-reply pack outcomes, close-reason trends, historical escalation trends and operator action trends.
- `app.services.onboarding` - first-run onboarding eligibility, progress persistence and onboarding copy rendering.
- `app.services.content_service` - registry and safe rendering for FAQ/content pages.
- `app.services.channel_guard_service` - background protection for active channels with deduplicated admin alerts.
- `app.services.report_service` - scheduled daily/weekly admin KPI reports with duplicate protection.
- `app.services.retention_automation` - lifecycle retention segmentation, dedupe windows and Telegram lifecycle messaging.
- `app.services.lifecycle_campaign_rules` - managed lifecycle wave registry for renewal, grace, final reactivation, trial recovery and win-back offer policy.
- `app.services.legal_texts` - registry of managed legal texts for terms, privacy, refund policy and payment support.
- `app.services.audit` - audit write helper, filter normalization, payload redaction and CSV export for admins.
- `app.db.repositories.support_tickets` - support ticket and support message persistence helpers.
- `app.bot.routers.admin.promos` - admin promo create/view/list/disable/stats commands with campaign and validity options.
- `app.bot.routers.admin.referrals` - `/admin_referrals` with top referrers, suspicious cases and reward totals.
- `app.bot.routers.admin.crypto` - `/admin_crypto_invoices`, `/admin_crypto_diag` and the admin payments dashboard callback.
- `app.bot.routers.admin.channels` - channel CRUD and refresh.
- `app.bot.routers.admin.tariffs` - tariff CRUD.
- `app.bot.routers.admin.analytics` - analytics snapshot, acquisition ROI plus lifecycle source quality, lifecycle ROI/highlights/source ROI/opportunities/leaders/watchlist, pricing intelligence and users entry points.
- `app.services.analytics_models` - analytics snapshot DTO/dataclass contracts for product funnel, acquisition, promo/referral, lifecycle and pricing intelligence payloads.
- `app.services.analytics_lifecycle` - lifecycle attribution constants, highlight/watchlist sorting helpers and source-campaign action ranking used by analytics builders.
- `app.services.analytics_lifecycle_builders` - lifecycle queue, offer-mix and managed-campaign attribution builders used by the admin analytics snapshot.
- `app.services.analytics_common` - shared analytics payload parsing, ID coercion, channel/tariff lookup and distinct-user query helpers.
- `app.services.analytics_funnel` - product funnel and source funnel builders used by the admin analytics snapshot.
- `app.services.analytics_acquisition` - source acquisition and acquisition-lifecycle ROI builders used by the admin analytics snapshot.
- `app.services.analytics_pricing` - pricing intelligence, offer performance and product-pair campaign builders used by the admin analytics snapshot.
- `app.services.analytics_promo_referral` - promo discount attribution and referral revenue attribution builders used by the admin analytics snapshot.
- `app.bot.routers.admin.users` - user directory for allowed admin roles plus owner/admin-only blocking, manual grants and direct message.
- `app.services.admin_roles` - role normalization, `ADMIN_IDS` owner fallback, permission checks and admin menu section policy.
- `app.services.observability` - structured event names, runtime error sanitization and admin observability report builder with read-model drift leaders/items for bot-side diagnostics.
- `app.bot.routers.admin.texts` - managed text templates.
- `app.bot.routers.admin.broadcasts` - segmented broadcasts, preview/confirm flow and reusable templates.
- `app.bot.routers.admin.backups` - manual backups and backup delivery to admin.

## Background workers

- `app.workers.subscription_expirer` - 3d/1d warnings, expired notices, grace period and revoke.
- `app.workers.payment_reconciler` - placeholder module for Crypto Pay reconciliation wiring.
- `app.workers.broadcast_sender` - broadcast queue sender with isolated per-user failures and rate-limited delivery accounting.
- `app.workers.backup_worker` - scheduled backup and retention.
- `app.workers.scheduler` - worker orchestrator, `channel_guard`, `admin_reports`, `retention_automation` and last-maintenance telemetry.
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
- `app.tools.repo_sanity` and `tests/unit/test_repo_hygiene.py` enforce that runtime artifacts are ignored/not tracked, shell scripts keep LF endings and tracked source/docs do not contain token-like secrets.
