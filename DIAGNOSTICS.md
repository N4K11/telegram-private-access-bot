# Diagnostics

## Admin commands

## Observability 2.0

- Runtime stores the last 20 critical errors in memory with sanitized messages.
- Worker status is tracked for `subscription_expirer`, `broadcast_sender`, `backup_worker`, `crypto_reconciler`, `channel_guard` and `admin_reports`.
- Structured logs redact token-like values, invite links and secret assignments.
- `CRITICAL_ERROR_WEBHOOK_URL` is optional and disabled by default.

## Role-based admin permissions

- `owner` - full access, including `/admin_roles` and `Р В РЎСљР В Р’В°Р РЋР С“Р РЋРІР‚С™Р РЋР вЂљР В РЎвЂўР В РІвЂћвЂ“Р В РЎвЂќР В РЎвЂ`.
- `admin` - operational access without role management/settings.
- `support` - support inbox, audit, diagnostics and read-only user directory.
- `analyst` - analytics, audit and diagnostics.

Guardrails now enforced in runtime:

- manual subscription grants, direct messages and user blocking are owner/admin only;
- broadcasts and finance/payment recovery are owner/admin only;
- support ticket inbox is support/admin/owner;
- settings and role changes are owner only.

- `/admin` - open the admin panel.
- `/admin_channel_check` - live-check connected channels and the bot's rights.
- `/admin_health` - runtime health dashboard for admins.
- `/admin_finance` - read-only finance dashboard with Stars/Crypto summary and CSV export.
- `/admin_audit` - audit viewer with filters by target user, actor, action and period plus redacted CSV export.
- `/admin_roles` - owner-only role management for `owner`, `admin`, `support` and `analyst`.
- `/admin_observability` - recent critical errors, worker status, Telegram API errors and backup result.
- `/admin_crypto_invoices` - Crypto Pay reconciliation summary and latest invoice statuses.
- `/admin_crypto_diag <user_id|invoice_id>` - detailed Crypto Pay diagnostics for a user or a specific invoice.
- `/admin_promo_create CODE TYPE VALUE LIMIT [TARIFF_ID|-] [VALID_DAYS|-] [from=ISO] [until=ISO] [first=0|1] [per_user=N] [campaign=NAME] [notes=TEXT]` - create a promo code.
- `/admin_promo_disable CODE` - disable a promo code.
- `/admin_promo_view CODE` - show the promo card with scope, validity and abuse rules.
- `/admin_promo_list [QUERY]` - search promo codes by code or campaign.
- `/admin_promo_stats CODE` - show promo statistics.
- `/admin_referrals` - referral analytics with top referrers and suspicious cases.
- `/admin_support` - support inbox with open/closed ticket views and reply actions.
- `/promo CODE` - apply a user promo code.
- `/my_referrals` - user referral dashboard with link, counts and pending reward days.
- `/paysupport` - user payment support text.
- `/terms` - show the managed terms text.
- `/privacy` - show the managed privacy text.
- `/refunds` - show the managed refund policy text.
- `/support` - open the in-bot support screen and create a ticket.
- `/cabinet` - send a Telegram WebApp button for the Mini App cabinet.

## Channel diagnostics

`/admin_channel_check` verifies:

- that `getMe` succeeds;
- that the channel is reachable through Telegram API;
- that the bot is present in the channel;
- that the bot is an administrator;
- that the bot can create invite links;
- that the bot can restrict or ban users;
- that stored rights in the database do not diverge from live Telegram state.

If the report shows a `store/live` mismatch, open `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦` and refresh the channel.

## Webhook runtime

When `USE_WEBHOOK=true`, the process exposes:

- `POST WEBHOOK_PATH` for Telegram updates;
- `GET /healthz` for liveness;
- `GET /readyz` for readiness.

Readiness fails with HTTP `503` if the database is unavailable or the backup directory cannot be prepared.

Common webhook failures:

- `Missing required environment variables ... PUBLIC_WEBHOOK_URL`:
  set `PUBLIC_WEBHOOK_URL` when `USE_WEBHOOK=true`.
- `Missing required environment variables ... WEBHOOK_SECRET_TOKEN`:
  set `WEBHOOK_SECRET_TOKEN` when `USE_WEBHOOK=true`.
- Telegram receives `401 Unauthorized` on webhook delivery:
  check that the reverse proxy keeps the `X-Telegram-Bot-Api-Secret-Token` header intact and that `.env` uses the same secret as Telegram.
- Telegram does not deliver updates after deploy:
  check the public path, reverse proxy and the configured webhook URL in logs.
- `GET /readyz` returns `503`:
  verify database connectivity and permissions to `BACKUP_DIRECTORY`.

## Smart onboarding

New users now see a three-step onboarding flow on the first `/start`.

It explains:

- what the bot does;
- how payment works;
- how to get into the private channel after payment.

Operational rules:

- existing users are backfilled as completed during migration and must not see onboarding again;
- `Пропустить` marks onboarding completed immediately;
- partial progress is stored in `users.onboarding_step`;
- if the user already paid or already has a subscription, onboarding auto-completes and the normal home screen opens.

If someone reports that `/start` keeps showing onboarding unexpectedly:

- verify whether `users.onboarding_completed_at` is empty for that user;
- verify that the user really has no successful payments and no subscriptions yet;
- if needed, complete onboarding manually by setting `onboarding_completed_at` in the database.
## Expiration warnings and grace period

The expiration worker runs in four steps:

- warning 3 days before expiry, if `WARNING_3D_ENABLED=true`;
- warning 1 day before expiry, if `WARNING_1D_ENABLED=true`;
- expired notice immediately after the subscription ends;
- revoke only after `GRACE_PERIOD_HOURS`.

If the user renews before revoke, access is extended normally and the old grace-period record must not be revoked again.

## Admin reports

Background scheduler sends admin summaries at `09:00` in `TIMEZONE`.

Rules:

- daily report is sent once per local day;
- weekly report is additionally sent on Monday and deduplicated by ISO week;
- delivery goes only to `ADMIN_IDS`;
- duplicate protection is stored in `audit_logs` with actions `admin_report_sent_daily` and `admin_report_sent_weekly`.

Report payload includes:

- new users;
- paid payments count;
- Stars revenue;
- Crypto revenue by asset;
- active subscriptions;
- subscriptions expired during the period;
- anomalies from recent runtime critical errors.

If reports do not arrive:

- check `/admin_observability` and worker status `admin_reports`;
- verify `ADMIN_IDS` is not empty;
- verify `TIMEZONE` is set correctly;
- inspect audit events `admin_report_sent_daily` and `admin_report_sent_weekly`;
- verify the process was alive around `09:00` local time.

## Runtime health dashboard

`/admin_health` shows:

- process uptime;
- bot username and `getMe` availability;
- whether active channels exist in the database;
- store read/write status;
- total users;
- active subscriptions;
- payments for the current day;
- last update id and event type, when telemetry exists;
- last maintenance run from the background scheduler;
- last Telegram API error, if recorded;
- timestamp of the latest backup.

If `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦: Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦` is `?`, do not restart blindly. Check the database and DB user permissions first.

If `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦` is `?`, verify `BOT_TOKEN`, network connectivity and Telegram API reachability.

## Finance dashboard

`/admin_finance` and `menu:admin:payments` show read-only Stars/Crypto totals, unpaid and expired crypto invoice counts, promo/referral counters and top tariffs.

Use the CSV export buttons to download day/week/month/all reports without raw payloads, invite links or secrets.

## Crypto Pay diagnostics

Use `/admin_crypto_invoices` to inspect active, paid-but-not-activated and expired invoices.
Use `/admin_crypto_diag <user_id|invoice_id>` to inspect one invoice or a specific user history.

If `Paid but not activated` is not zero:

- inspect the target invoice with `/admin_crypto_diag`;
- check audit events `crypto_invoice_paid`, `crypto_subscription_activated`, `crypto_invoice_duplicate`, `crypto_reconcile_error`;
- verify the linked tariff/channel still exists;
- verify the reconcile summary has a recent successful run.

## Broadcast diagnostics

The broadcast screen now supports:

- segmentation by `all`, `active`, `expired`, `never_paid`, `expires_soon`, `pending_join`, specific tariff and specific channel;
- preview with recipient count and the first sample recipients;
- explicit confirm before queueing;
- reusable templates;
- delivery report with sent, failed, blocked and `rate_limited` counts.

If a broadcast behaves unexpectedly:

- open the broadcast card and check `Р В РЎвЂєР РЋР С“Р РЋРІР‚С™Р В Р’В°Р В Р’В»Р В РЎвЂўР РЋР С“Р РЋР Р‰`, `Р В РЎвЂєР РЋРІвЂљВ¬Р В РЎвЂР В Р’В±Р В РЎвЂўР В РЎвЂќ`, `Rate limited` and `Р В РІР‚вЂќР В Р’В°Р В Р’В±Р В Р’В»Р В РЎвЂўР В РЎвЂќР В РЎвЂР РЋР вЂљР В РЎвЂўР В Р вЂ Р В Р’В°Р В Р’В»Р В РЎвЂ Р В Р’В±Р В РЎвЂўР РЋРІР‚С™Р В Р’В°`;
- inspect recent `broadcast_batch_processed` audit events;
- verify the selected segment really contains users now, not historically;
- for `pending_join`, verify the user still has an active invite link;
- for `expires_soon`, verify the subscription expires within the next 3 days.

A plain admin message without the broadcast FSM context must not queue a campaign.

## Legal texts

`/terms`, `/privacy`, `/refunds` and the help-screen legal buttons are backed by managed text templates.
`/paysupport` now renders the managed `payment_support` text.

If the wording must be changed:

- open `/admin` -> `?? ??????`;
- edit `terms`, `privacy`, `refund_policy` or `payment_support`;
- reset the template to default if the customized version became broken.

## Support ticket diagnostics

The support flow now stores `support_tickets` and `support_messages` in the database.

If a user says support is not responding:

- verify `/support` opens the support screen and allows category selection;
- verify the user does not already have an open ticket blocking new creation;
- verify the user did not hit the daily creation cap of 3 tickets per 24 hours;
- open `/admin_support` and check whether the ticket is in the `open` inbox;
- open the ticket and verify reply/close/reopen actions work;
- check recent `support_ticket_*` audit events for create, reply, close and reopen actions.

## Audit viewer

`/admin_audit` and `menu:admin:audit` show recent audit events with filters by target user, actor, action and period.

Use the prompt buttons to set user filters by internal ID (`id:123`) or Telegram ID (`tg:755815181`).

CSV export always uses redacted payloads: direct message text, invite links, token-like values and other sensitive raw fields are hidden before delivery.

If you need to investigate a manual grant, recovery or suspicious payment flow:

- open `/admin_audit`;
- narrow the period first, then add target user or actor filters;
- inspect the detail card for the exact event;
- jump into the linked user profile when the event has a target or actor user;
- export CSV if you need an external incident timeline without exposing secrets.


## Promo diagnostics

If a user says the discount was not applied:

- check `/admin_promo_stats CODE`;
- verify the promo is active, already started and not expired;
- verify the tariff matches `TARIFF_ID` when the promo is scoped;
- verify irst_purchase_only and per_user_limit conditions on the promo card;
- verify the user is paying through Telegram Stars, not Crypto Pay;
- inspect audit events `promo_applied_pending`, `promo_applied_free_days` and `payment_paid_stars`.

## Referral diagnostics

Use `/my_referrals` to verify that the user sees:

- the deep link with `ref_*` payload;
- invited users count;
- paid referrals count;
- earned reward days;
- pending reward days for the next renewal.

Use `/admin_referrals` to verify that admins see:

- total invited users;
- total paid referrals;
- conversion percent;
- rewards issued and reward days;
- top referrers;
- suspicious cases from audit events.

Suspicious reasons currently include `already_bound`, `already_customer`, `self_referral` and duplicate reward attempts.

If referral numbers look wrong:

- inspect audit events `referral_bound`, `referral_reward_granted`, `referral_reward_applied`, `referral_suspicious`;
- verify the referred user paid through the normal successful payment flow;
- verify the reward was not already granted earlier for that referred user.
## Local checks

```bash
python -m compileall app tests alembic
ruff check .
pytest -q
python -m app.healthcheck
```

## Server checks

```bash
docker compose ps
docker compose logs --tail=100 bot
python -m app.healthcheck
```

For webhook deployments, also verify:

```bash
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/readyz
```

## Common failures

- `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦` or `bot Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦`:
  check `chat_id`, ensure the bot is in the channel and has not been removed.
- `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦: Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦`:
  grant administrator rights.
- `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ invite links: Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦`:
  enable invite permissions.
- `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦: Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦`:
  enable restrict/ban permissions.
- `getMe` does not pass:
  verify `BOT_TOKEN`, network and Telegram API reachability.
- `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦: Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦` does not pass:
  verify DB user permissions, read-only mode and transaction health.
- `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ backup: Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦`:
  verify `BACKUP_*` settings and trigger a manual backup from the admin panel.
- `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦`:
  verify promo scope, promo status and that payment was done through Stars.

## Repo hygiene

If local junk appears in the repository or you suspect a secret leak:

- check `.gitignore` and `tests/unit/test_repo_hygiene.py`;
- verify `.env`, `dev.db`, `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `.tmp/`, `.vendor/`, `.tooling/` and runtime logs are not tracked;
- verify tracked source/docs do not contain Telegram token-like strings.







## Mini App cabinet

When `USE_WEBHOOK=true`, the same aiohttp runtime serves the cabinet page at `MINI_APP_PATH`.
All cabinet API calls require a valid Telegram `initData` signature and reject expired auth data with `401 unauthorized`.

Endpoints:

- `GET MINI_APP_PATH` - HTML shell for Telegram WebApp.
- `POST MINI_APP_PATH/api/auth` - validate `initData` once and sync the Telegram user into the database.
- `GET MINI_APP_PATH/api/bootstrap` - own profile, grouped products, active product access, flat tariffs, payments, referral stats, pending promos, support state and action links.
- `GET MINI_APP_PATH/api/users/{telegram_id}/profile` - own profile, or another profile for admins only.
- `GET MINI_APP_PATH/api/admin/summary` - admin-only analytics snapshot.
- `GET MINI_APP_PATH/api/admin/dashboard` - Mini App admin dashboard with overview cards and capability-aware sections.
- `GET MINI_APP_PATH/api/admin/users?filter=...&query=...&page=...` - admin-only filterable user directory payload.
- `GET MINI_APP_PATH/api/admin/payments?provider=...&query=...&page=...` - admin-only filterable payments payload with redacted fields only.
- `POST MINI_APP_PATH/api/admin/actions/channel-check` - admin-only live channel check that also writes audit `webapp_admin_channel_check`.

If the cabinet does not open correctly:

- verify `PUBLIC_WEBHOOK_URL`, `MINI_APP_PATH` and optional `BOT_PUBLIC_USERNAME`;
- verify reverse proxy routing to the aiohttp app port;
- verify Telegram opens the page from a WebApp button and not from a stale browser tab;
- if APIs return `401`, regenerate fresh `initData` by reopening the Mini App from Telegram;
- if APIs return `403`, verify the requested target user and admin role.
- if Mini App admin panels are empty, verify the role has the required permissions (`admin_panel`, `users_view`, `payments`, `diagnostics`).`r`n- if user buy/tariffs screens show a product picker unexpectedly, verify more than one active channel currently has at least one active tariff.

## Content / FAQ CMS

- Пользовательские страницы `FAQ`, `Правила канала`, `После оплаты`, `Crypto Pay`, `Оферта` рендерятся через managed `TextTemplate`.
- Раздел `Возвраты` остаётся доступен и через legal-flow, и как часть content-registry.
- Для безопасного рендера content-страницы экранируют HTML/markup из шаблона, поэтому админский текст не ломает caption-разметку.
- Быстрый вход для админа: `/admin_content` или кнопка `📚 Content / FAQ CMS` внутри `✍️ Тексты`.

## Smart channel guard

- Фоновый worker проверяет только активные каналы через live diagnostics.
- Если бот исключён, потерял admin-статус или права `invite/restrict`, владельцы получают alert в Telegram.
- Повторяющиеся alert-сообщения по одной и той же проблеме подавляются до изменения состояния.
- Для ручной расшифровки проблемы используйте `/admin_channel_check`.
