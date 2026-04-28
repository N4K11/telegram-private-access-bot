# Deploy

## Docker Compose

1. Copy `.env.example` to `.env`.
2. Fill `BOT_TOKEN`, `ADMIN_IDS` and `DATABASE_URL`.
3. Adjust optional sections for Crypto Pay, backups and rate limits.
4. Validate the compose file:

```bash
docker compose config
```

5. Build and start the stack:

```bash
docker compose up -d --build
```

6. Apply migrations:

```bash
docker compose exec bot alembic upgrade head
```

7. Check runtime health:

```bash
docker compose exec bot python -m app.healthcheck
```

## systemd

An example unit file is available at `deploy/systemd/telegram-private-access-bot.service`.

Typical layout on Ubuntu:

- project: `/opt/telegram-private-access-bot`
- environment file: `/opt/telegram-private-access-bot/.env`
- service user: `telegrambot`

Basic commands:

```bash
sudo cp deploy/systemd/telegram-private-access-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable telegram-private-access-bot
sudo systemctl start telegram-private-access-bot
sudo systemctl status telegram-private-access-bot
```

## Notes

- SQLite is intended only for local tests and development bootstrap.
- PostgreSQL is the production target.
- Backups intentionally exclude `.env` and runtime secrets.