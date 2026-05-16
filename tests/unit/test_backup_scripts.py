from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SCRIPT_NAMES = ["backup_db.sh", "verify_backup.sh", "restore_db.sh"]


def _read_script(name: str) -> str:
    return (SCRIPTS_DIR / name).read_text(encoding="utf-8")


def test_backup_restore_scripts_exist_and_use_posix_shebang() -> None:
    for name in SCRIPT_NAMES:
        path = SCRIPTS_DIR / name
        assert path.exists() is True
        content = path.read_bytes()
        assert content.startswith(b"#!/bin/sh\n")


def test_backup_restore_scripts_do_not_embed_secrets_or_windows_paths() -> None:
    forbidden_literals = [
        "AAEjnqo",
        "Rapira",
        "BOT_TOKEN=",
        "CRYPTO_PAY_TOKEN=",
        "PASSWORD=",
        "D:\\",
        "C:\\",
    ]
    for name in SCRIPT_NAMES:
        text = _read_script(name)
        for literal in forbidden_literals:
            assert literal not in text


def test_restore_script_requires_explicit_argument_and_creates_safety_backup() -> None:
    text = _read_script("restore_db.sh")

    assert "if [ $# -lt 1 ]; then" in text
    assert "Usage: $0 /path/to/archive.tar.gz" in text
    assert 'SAFETY_BACKUP=$(sh "$BACKUP_SCRIPT" safety-restore)' in text


def test_backup_script_does_not_delete_or_restore_current_database() -> None:
    text = _read_script("backup_db.sh")

    forbidden_sequences = [
        "dropdb",
        "DROP DATABASE",
        "DROP SCHEMA",
        "psql ",
    ]
    for forbidden in forbidden_sequences:
        assert forbidden not in text
    assert "pg_dump" in text
    assert "json.load" in text


def test_backup_script_allows_safe_deterministic_archive_name() -> None:
    text = _read_script("backup_db.sh")

    assert "BACKUP_ARCHIVE_NAME" in text
    assert "BACKUP_ARCHIVE_NAME must be a safe file name" in text
    assert "BACKUP_ARCHIVE_NAME must end with .tar.gz" in text
    assert 'ARCHIVE_NAME="${LABEL}-db-backup-${TIMESTAMP}.tar.gz"' in text


def test_verify_script_validates_manifest_json() -> None:
    text = _read_script("verify_backup.sh")

    assert "manifest.json" in text
    assert "json.load" in text
    assert "unsupported backup format" in text
    assert "database.sql is missing or empty" in text
