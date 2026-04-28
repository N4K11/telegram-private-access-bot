# Project Overview

## Goal

The project sells time-limited access to private Telegram channels, grants access after payment and revokes access after expiration.

## Main runtime flow

1. A Telegram user opens `/start`.
2. Middleware syncs the user into the database.
3. The user selects a tariff.
4. Payment is processed through Telegram Stars or optional Crypto Pay.
5. The bot activates or extends the subscription.
6. The bot generates a personal invite link.
7. Background workers revoke access after expiration and process broadcasts, backups and crypto reconciliation.

## Architecture

- `app/main.py` bootstraps settings, logging, DB, dispatcher and workers.
- `app/bot/` contains filters, routers, keyboards and middlewares.
- `app/services/` contains business logic.
- `app/db/` contains schema and repositories.
- `app/workers/` contains polling background jobs.

## Operational hardening

- JSON structured logs.
- Runtime healthcheck.
- Container healthcheck and graceful stop settings.
- Rate-limit and duplicate-request protection.
- Backup retention and restore notes.
- Audit log records for sensitive operations.

## Deployment model

- Docker Compose for container deployment.
- PostgreSQL as the production database.
- Optional systemd example for host-managed processes.