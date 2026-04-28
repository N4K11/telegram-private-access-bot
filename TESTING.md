# Testing

## Baseline checks

```bash
python -m compileall app tests
ruff check .
pytest -q
alembic upgrade head
```

## Notes

- Tests use SQLite through `aiosqlite` for local verification.
- Production is expected to use PostgreSQL.
- The runtime bot process still requires `BOT_TOKEN` and `ADMIN_IDS`.
