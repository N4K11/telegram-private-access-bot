# Backup Restore

Each generated backup is a ZIP archive with three core parts:

1. `metadata.json`
2. `database/export.json`
3. `restore/RESTORE.txt`

Important:
- `.env` and runtime secrets are intentionally excluded.
- Restore secrets separately before starting the bot.
- Apply migrations before importing any restored data.
- Validate subscriptions, channels and payment history after recovery.
Shell helpers:
- `scripts/backup_db.sh` creates a PostgreSQL SQL archive with a validated `manifest.json`.
- `scripts/verify_backup.sh` verifies archive structure, manifest JSON and dump presence.
- `scripts/restore_db.sh /path/to/archive.tar.gz` requires an explicit archive path and creates a safety backup before restore.