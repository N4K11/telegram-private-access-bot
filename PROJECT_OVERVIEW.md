# Project Overview

## Goal

Build a Telegram bot that sells time-limited access to one or more private Telegram channels, grants access after payment, and revokes access when subscriptions expire.

## Layout

- `app/`: application source code.
- `app/bot/`: aiogram routers, filters, middlewares and keyboards.
- `app/services/`: domain services.
- `app/db/`: models, repositories and session management.
- `app/workers/`: background jobs.
- `tests/`: unit, integration and smoke tests.
- `alembic/`: migrations.
- `deploy/`: deployment artifacts.

## Stage 1 decisions

- Keep runtime secrets in the environment only.
- Keep PostgreSQL as the production database target.
- Allow SQLite only for local tests and bootstrap verification.
- Front-load the core schema so future stages can extend behavior without a structural rewrite.
