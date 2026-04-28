# Telegram Private Access Bot

Production-oriented Telegram bot for selling access to private channels with Telegram Stars as the primary payment method and optional Crypto Pay support.

## Current status

Stages 1 and 2 are implemented and verified:

- project skeleton;
- settings and logging;
- async SQLAlchemy models;
- Alembic bootstrap;
- Docker and Docker Compose;
- baseline user/admin bot wiring;
- inline menu navigation with edit fallback;
- user sync middleware that persists Telegram users;
- initial unit, integration and smoke tests.

## Stack

- Python 3.12+
- aiogram 3.x
- SQLAlchemy async
- Alembic
- PostgreSQL for production
- APScheduler for background jobs
- pytest, ruff, black, mypy

## Quick start

1. Create a virtual environment.
2. Install the project with dev dependencies.
3. Copy `.env.example` to `.env` and fill in secrets.
4. Run migrations.
5. Start the bot.

## Local commands

```bash
python -m compileall app tests alembic
ruff check .
pytest -q
alembic upgrade head
python -m app.main
```

## Docker

```bash
docker compose up -d --build
```

## Current bot behavior

- `/start` always sends a new main menu message.
- User navigation after `/start` works through inline callback menus.
- `/admin` is limited by `ADMIN_IDS` and opens the inline admin menu.
- Callback menu edits fall back to sending a new message if Telegram rejects the edit.

## Next stages

The next implementation stages will add channels, tariffs, Telegram Stars payments, invite links, expiring subscriptions, broadcasts, backups and production hardening.