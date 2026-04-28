# Deploy

## Docker Compose

1. Copy `.env.example` to `.env`.
2. Set `DATABASE_URL` to the PostgreSQL service from `docker-compose.yml` or to an external database.
3. Fill `BOT_TOKEN` and `ADMIN_IDS`.
4. Start services:

```bash
docker compose up -d --build
```

5. Apply migrations if needed:

```bash
docker compose exec bot alembic upgrade head
```

## Ubuntu target

A dedicated Ubuntu deployment flow will be documented after the GitHub publication stop-point and server credentials stop-point described in the project brief.
