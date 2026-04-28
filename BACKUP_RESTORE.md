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