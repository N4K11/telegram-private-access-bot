from __future__ import annotations

from pathlib import Path

from app.bot.assets import (
    BANNERS,
    BOT_AVATAR_PATH,
    candidate_project_roots,
    get_avatar_path,
    get_banner_path,
    resolve_project_root,
)


def test_minimal_banner_assets_exist() -> None:
    for key, asset in BANNERS.items():
        path = get_banner_path(key)
        assert path == asset.path
        assert path is not None
        assert path.is_file()
        assert path.suffix == ".png"


def test_bot_avatar_asset_exists() -> None:
    path = get_avatar_path()
    assert path == BOT_AVATAR_PATH
    assert path is not None
    assert path.is_file()
    assert path.suffix == ".png"


def test_unknown_banner_returns_none() -> None:
    assert get_banner_path("missing") is None


def test_resolve_project_root_finds_runtime_assets() -> None:
    project_root = resolve_project_root()

    assert project_root == Path.cwd().resolve()
    assert (project_root / "assets" / "banners" / "main.png").is_file()
    assert candidate_project_roots()[0] == Path.cwd().resolve()
