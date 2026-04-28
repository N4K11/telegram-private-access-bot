# Testing

## Required checks

```bash
python -m compileall app tests alembic
ruff check .
pytest -q
alembic upgrade head
python -m app.healthcheck
```

## Docker validation

```bash
docker compose config
docker compose build
```

## Coverage areas in the current test suite

- settings parsing and runtime validation;
- user sync middleware;
- user/admin navigation;
- channels and tariffs;
- Telegram Stars payments;
- Crypto Pay processing and reconciliation;
- invite links;
- subscription expiration worker;
- analytics and admin user actions;
- broadcasts;
- text templates and mojibake protection;
- backups;
- rate limiting, logging and healthcheck.

## Known local warning

`pytest` may emit `PytestCacheWarning` in this Windows workspace because `.pytest_cache` is not writable in the ASCII junction environment. This does not affect test correctness.