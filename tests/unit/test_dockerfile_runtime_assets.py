from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE_PATH = PROJECT_ROOT / "Dockerfile"


def test_dockerfile_copies_runtime_web_and_assets() -> None:
    text = DOCKERFILE_PATH.read_text(encoding="utf-8")

    assert "COPY assets ./assets" in text
    assert "COPY web ./web" in text