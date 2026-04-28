from __future__ import annotations

import ctypes
import os
from contextlib import suppress
from pathlib import Path

import pytest

from app.config import get_settings


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