from __future__ import annotations

import ctypes
import os
import shutil
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import pytest

from app.config import get_settings

TESTS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TESTS_ROOT.parent
TMP_ROOT = Path(os.environ.get("CODEX_TEST_TMP_ROOT") or r"D:\botproj\.tmp\pytest-temp")
TMP_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["TMP"] = str(TMP_ROOT)
os.environ["TEMP"] = str(TMP_ROOT)
os.environ["TMPDIR"] = str(TMP_ROOT)


def _preload_ssl_dlls() -> None:
    try:
        import ssl  # noqa: F401
        return
    except Exception:
        pass

    candidates = [
        Path(r"C:\Program Files\MySQL\MySQL Workbench 8.0\swb\shell\bin"),
        Path(r"C:\Program Files\MySQL\MySQL Workbench 8.0"),
    ]

    for candidate in candidates:
        crypto = candidate / "libcrypto-3-x64.dll"
        ssl_dll = candidate / "libssl-3-x64.dll"
        if not crypto.exists() or not ssl_dll.exists():
            continue

        with suppress(AttributeError, FileNotFoundError, OSError):
            os.add_dll_directory(str(candidate))

        ctypes.CDLL(str(crypto))
        ctypes.CDLL(str(ssl_dll))
        import ssl  # noqa: F401
        return


_preload_ssl_dlls()


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def workspace_tmp_path() -> Iterator[Path]:
    path = TMP_ROOT / f"case-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)