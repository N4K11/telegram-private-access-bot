from __future__ import annotations

import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROMPT_FILES = {
    "BOT_FUTURE_IMPROVEMENTS_CODEX_PROMPTS.md",
    "CODEX_FIX_UI_ENCODING_ADMIN_PROMPT.md",
    "CURRENT_BOT_NEXT_IMPROVEMENTS_ROADMAP.md",
    "UI_MINIMAL_REDESIGN_PROMPT.md",
}


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout


def test_gitignore_contains_required_runtime_artifact_patterns() -> None:
    text = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    required_patterns = {
        ".env",
        ".venv/",
        "__pycache__/",
        "*.pyc",
        ".pytest_cache/",
        ".ruff_cache/",
        ".tmp/",
        ".vendor/",
        ".tooling/",
        "*.db",
        "backups/*",
        "*.log",
        "logs/",
    }
    lines = {line.strip() for line in text.splitlines() if line.strip()}
    assert required_patterns.issubset(lines)


def test_local_runtime_artifacts_are_not_tracked() -> None:
    tracked = _git("ls-files").splitlines()
    forbidden_exact = {".env", "dev.db"}
    forbidden_prefixes = (
        ".venv/",
        "__pycache__/",
        ".pytest_cache/",
        ".ruff_cache/",
        ".tmp/",
        ".vendor/",
        ".tooling/",
        "backups/",
        "logs/",
    )

    assert forbidden_exact.isdisjoint(tracked)
    for path in tracked:
        if path == "backups/.gitkeep":
            continue
        assert not path.endswith(".pyc")
        assert not path.endswith(".log")
        assert not any(path.startswith(prefix) for prefix in forbidden_prefixes)


def test_no_real_token_like_patterns_in_tracked_source_and_docs() -> None:
    tracked = _git("ls-files").splitlines()
    token_pattern = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{20,}\b")
    forbidden_fragments = (
        "Rapira322^",
        "ssh root@193.23.201.190",
    )
    scanned_suffixes = {
        ".py",
        ".md",
        ".txt",
        ".toml",
        ".yml",
        ".yaml",
        ".ini",
        ".sh",
        ".service",
        ".html",
        ".svg",
        ".gitignore",
    }

    for relative in tracked:
        path = PROJECT_ROOT / relative
        if path.name in PROMPT_FILES:
            continue
        if relative.startswith("tests/"):
            continue
        if (
            path.suffix.lower() not in scanned_suffixes
            and path.name not in {"Dockerfile", "Makefile"}
        ):
            continue
        text = path.read_text(encoding="utf-8")
        assert token_pattern.search(text) is None, relative
        for fragment in forbidden_fragments:
            assert fragment not in text, relative
