from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BannerAsset:
    key: str
    path: Path

    def exists(self) -> bool:
        return self.path.is_file()


def candidate_project_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    env_root = os.getenv("BOT_PROJECT_ROOT")
    if env_root:
        roots.append(Path(env_root).resolve())
    roots.append(Path.cwd().resolve())
    roots.append(Path(__file__).resolve().parents[2])

    unique_roots: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if root not in seen:
            seen.add(root)
            unique_roots.append(root)
    return tuple(unique_roots)


def resolve_project_root() -> Path:
    for root in candidate_project_roots():
        assets_root = root / "assets"
        banners_root = assets_root / "banners"
        avatar_root = assets_root / "avatar"
        if banners_root.is_dir() and avatar_root.is_dir():
            return root
    return candidate_project_roots()[0]


PROJECT_ROOT = resolve_project_root()
ASSETS_ROOT = PROJECT_ROOT / "assets"
BANNERS_ROOT = ASSETS_ROOT / "banners"
AVATAR_ROOT = ASSETS_ROOT / "avatar"

MAIN_BANNER = BannerAsset("main", BANNERS_ROOT / "main.png")
BUY_BANNER = BannerAsset("buy", BANNERS_ROOT / "buy.png")
TARIFFS_BANNER = BannerAsset("tariffs", BANNERS_ROOT / "tariffs.png")
PROFILE_BANNER = BannerAsset("profile", BANNERS_ROOT / "profile.png")
JOIN_BANNER = BannerAsset("join", BANNERS_ROOT / "join.png")
HELP_BANNER = BannerAsset("help", BANNERS_ROOT / "help.png")
ADMIN_BANNER = BannerAsset("admin", BANNERS_ROOT / "admin.png")

BANNERS: dict[str, BannerAsset] = {
    asset.key: asset
    for asset in (
        MAIN_BANNER,
        BUY_BANNER,
        TARIFFS_BANNER,
        PROFILE_BANNER,
        JOIN_BANNER,
        HELP_BANNER,
        ADMIN_BANNER,
    )
}

BOT_AVATAR_PATH = AVATAR_ROOT / "bot_avatar.png"


def get_banner_asset(key: str) -> BannerAsset | None:
    return BANNERS.get(key)


def get_banner_path(key: str) -> Path | None:
    asset = get_banner_asset(key)
    if asset is None or not asset.exists():
        return None
    return asset.path


def has_banner(key: str) -> bool:
    return get_banner_path(key) is not None


def get_avatar_path() -> Path | None:
    return BOT_AVATAR_PATH if BOT_AVATAR_PATH.is_file() else None
