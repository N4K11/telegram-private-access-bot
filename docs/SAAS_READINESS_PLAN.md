# SaaS Readiness Plan

## Goal

Prepare the current single-owner Telegram subscription bot for a future multi-owner SaaS mode without changing runtime code yet.

## Current state

The project is already production-oriented:

- `aiogram` bot runtime with polling/webhook modes
- async SQLAlchemy + Alembic
- PostgreSQL-ready deployment
- payments, subscriptions, invites, promos, referrals, support, analytics, audit, backups
- role-based admin permissions

The current data model is still logically single-tenant:

- one global admin owner set through `ADMIN_IDS`
- channels and tariffs are assumed to belong to one business space
- `users.telegram_id` is globally unique and directly stores both customer and admin identities
- admin dashboards aggregate all data globally

## What a tenant is

A tenant is one isolated business account that owns:

- its own channels
- its own tariffs
- its own customers
- its own subscriptions and payments
- its own text templates, promos, support tickets, broadcasts and analytics
- its own admin users and roles

In SaaS mode, two different owners must not see or mutate each other's business data, even if the same Telegram user subscribes to both.

## Recommended target model

### Core entities

Add a new `tenants` table:

- `id`
- `slug` or public key
- `name`
- `status`
- `created_at`
- `updated_at`
- optional billing/config columns later

Split identity from membership.

Recommended direction:

1. Global Telegram identity table, for example `telegram_accounts`
2. Tenant-scoped membership table, for example `tenant_users`

Why:

- one human can interact with multiple tenants
- the same `telegram_id` must not force all purchases/support history into one shared row
- tenant-scoped roles become much simpler

### Suggested logical schema

- `telegram_accounts`
  - global Telegram identity
  - unique by `telegram_id`
- `tenants`
  - one business / owner workspace
- `tenant_users`
  - link between `tenant_id` and `telegram_account_id`
  - stores role, blocked flag, referral code and tenant-local metadata

This is safer than trying to keep the current `users` table as both identity and tenant membership.

## Tables that should become tenant-scoped

### Must have `tenant_id` directly

These tables are business-owned and should carry `tenant_id` explicitly for isolation, filtering and index efficiency:

- `channels`
- `tariffs`
- `subscriptions`
- `payments`
- `invite_links`
- `audit_logs`
- `text_templates`
- `broadcast_campaigns`
- `broadcast_deliveries`
- `backup_records`
- `support_tickets`
- `support_messages`
- `crypto_invoices`
- `promo_codes`
- `promo_redemptions`

### User-related migration

Current `users` should not simply get `tenant_id` if SaaS is the real target.

Reason:

- `users.telegram_id` is unique now
- the same Telegram person may need memberships in multiple tenants
- per-tenant role / blocked / referral / support state should not leak across tenants

Recommended replacement:

- keep global identity in `telegram_accounts`
- move tenant-specific behavior into `tenant_users`

### Tables that can derive tenant only through joins, but still benefit from direct `tenant_id`

Even if a table could derive tenant through `subscription -> tariff -> channel`, storing `tenant_id` directly is still recommended for:

- cheap authorization checks
- easier admin filtering
- simpler audit queries
- simpler backup/export boundaries
- safer future row-level security

## Admin isolation model

Current roles are global: `owner`, `admin`, `support`, `analyst`.

In SaaS mode roles must be tenant-scoped.

Recommended approach:

- move admin roles to `tenant_users.role`
- keep platform-level superadmin separate from tenant admins

Two layers:

1. Platform role
   - only for SaaS operator / maintainer
   - can inspect platform health, billing, abuse, migrations
2. Tenant role
   - `owner`, `admin`, `support`, `analyst`
   - valid only inside one tenant

Permission checks then become:

- resolve current tenant
- resolve current `tenant_user`
- evaluate permission against tenant-local role

## Runtime impact expected later

The following runtime areas will eventually need tenant resolution:

- `/start` and user sync middleware
- all payment flows
- invite link creation
- support tickets
- promos and referrals
- analytics dashboards
- backups and exports
- broadcast segmentation
- audit writes and reads
- webhook and Mini App endpoints

A tenant must be resolved before any business query runs.

## How tenant can be resolved

Recommended future options:

- by bot token if each tenant has its own bot
- by channel/tariff ownership if shared control plane exists
- by Mini App domain/subpath if web cabinet becomes multi-tenant
- by deep link / start payload during onboarding

Most robust long-term SaaS model:

- one bot per tenant or at least one clearly scoped tenant context per runtime instance

Trying to multiplex many independent businesses through one bot without a strong tenant context increases support and security complexity sharply.

## Migration strategy from current single-owner data

### Phase 0: analysis only

No runtime change. Document the future shape and all write paths.

### Phase 1: add tenant primitives

Add new tables:

- `tenants`
- `telegram_accounts`
- `tenant_users`

Create one bootstrap tenant representing the current production bot.

### Phase 2: add nullable `tenant_id` columns

Add nullable `tenant_id` to all tenant-owned tables.

Backfill every existing row with the bootstrap tenant id.

Do not yet remove old joins or old `users` assumptions.

### Phase 3: dual-write compatibility layer

Introduce service/repository layer that:

- resolves tenant first
- writes both old and new tenant-aware references where necessary
- keeps old runtime stable during migration window

This is the highest-risk application phase.

### Phase 4: move reads to tenant-aware model

Update dashboards, payments, referrals, support and audit queries to always filter by `tenant_id`.

At this point any query without tenant scoping should be treated as a bug.

### Phase 5: replace current `users` semantics

Move from current direct `users.telegram_id` semantics toward:

- `telegram_accounts`
- `tenant_users`

Possible staged approach:

- keep `users` temporarily as compatibility alias/table
- later split usage site by site

### Phase 6: enforce constraints

After backfill and runtime rollout:

- set `tenant_id` columns `NOT NULL`
- add tenant-aware unique constraints
- add indexes including `tenant_id`

Examples:

- unique tariff ordering within tenant
- unique promo code within tenant
- unique channel username/chat id within tenant
- unique referral code within tenant

### Phase 7: remove global assumptions

Remove:

- global role assumptions tied only to `ADMIN_IDS`
- global analytics queries
- global support/audit visibility for tenant admins

Keep only platform-superadmin paths global.

## Major risks

### 1. Same Telegram user across multiple tenants

This is the biggest data-model risk.

If `users` remains globally unique by `telegram_id`, then:

- role leakage becomes likely
- blocked state can leak across tenants
- referral and support state can mix
- analytics become ambiguous

### 2. Payment ownership mistakes

If a payment is not tenant-scoped, then:

- subscription activation may hit the wrong channel
- finance exports may expose another tenant's revenue
- refund/recovery flows become dangerous

### 3. Audit and support leakage

Audit logs and support messages are highly sensitive.

Any missing tenant filter there becomes an immediate privacy/security bug.

### 4. Broadcast leakage

Broadcasts are one of the highest-risk operations in a SaaS migration.

A missing tenant boundary can message the wrong users.

### 5. Backups and restore scope

Current backups are application-wide.

SaaS may later require:

- per-tenant export
- per-tenant restore tooling
- or clearly documented full-instance restore only

### 6. Referral/promo uniqueness rules

Current referral codes and promo codes may need tenant-local uniqueness instead of global uniqueness.

That affects:

- deep links
- admin UX
- abuse checks
- import/export flows

## Tests required before any real SaaS migration

### Schema and repository tests

- tenant bootstrap migration creates the default tenant
- all backfilled rows receive tenant id
- tenant-aware unique constraints behave correctly
- same `telegram_id` can exist across multiple tenant memberships

### Service tests

- user sync resolves the correct tenant
- subscription activation cannot cross tenant boundary
- promo application cannot use another tenant's promo
- referrals cannot bind across tenants
- support tickets stay inside tenant
- audit exports return only tenant-owned events

### Router / API tests

- admin endpoints reject cross-tenant access
- support/admin inbox only sees tenant-local tickets
- finance/admin dashboards only show tenant-local metrics
- Mini App endpoints cannot read another tenant's profile by id

### Broadcast safety tests

- segment queries never include users from another tenant
- preview counts are tenant-scoped
- delivery records stay tenant-scoped

### Migration tests

- old single-owner dataset backfills cleanly
- rollback plan exists for every Alembic phase
- dual-write phase does not duplicate subscriptions or payments

## Operational safeguards for the future migration

Before any tenant-aware rollout:

- full production backup
- restore rehearsal on a clone
- migration dry run on anonymized production-like data
- query review for every admin screen
- explicit incident rollback plan

## Recommended staged execution order

1. Design review and tenant model sign-off
2. Introduce `tenants`, `telegram_accounts`, `tenant_users`
3. Backfill one default tenant
4. Add nullable `tenant_id` to tenant-owned tables
5. Update repositories/services to require tenant context
6. Update admin permissions to tenant-local roles
7. Update analytics, support, audit and broadcasts
8. Enforce constraints and remove compatibility code

## Recommendation

Do not start SaaS migration directly from handlers or UI.

First refactor toward a hard service boundary where every business operation accepts tenant context explicitly. The current codebase is structured enough for that refactor, but skipping this step would make the migration risky and hard to verify.

## Deliverable status

This file is design-only. No runtime code, schema or production data was changed as part of Stage 15.
