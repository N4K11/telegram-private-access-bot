from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import User

ROLE_USER: Final = "user"
ROLE_OWNER: Final = "owner"
ROLE_ADMIN: Final = "admin"
ROLE_SUPPORT: Final = "support"
ROLE_ANALYST: Final = "analyst"

KNOWN_ROLES: Final[tuple[str, ...]] = (
    ROLE_USER,
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_SUPPORT,
    ROLE_ANALYST,
)
ADMIN_ROLES: Final[tuple[str, ...]] = (
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_SUPPORT,
    ROLE_ANALYST,
)
ASSIGNABLE_ROLES: Final[tuple[str, ...]] = (
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_SUPPORT,
    ROLE_ANALYST,
    ROLE_USER,
)

ROLE_LABELS: Final[dict[str, str]] = {
    ROLE_USER: "Пользователь",
    ROLE_OWNER: "Owner",
    ROLE_ADMIN: "Админ",
    ROLE_SUPPORT: "Поддержка",
    ROLE_ANALYST: "Аналитик",
}

PERMISSION_ADMIN_PANEL: Final = "admin_panel"
PERMISSION_ANALYTICS: Final = "analytics"
PERMISSION_USERS_VIEW: Final = "users_view"
PERMISSION_USERS_MANAGE: Final = "users_manage"
PERMISSION_SUPPORT: Final = "support"
PERMISSION_PAYMENTS: Final = "payments"
PERMISSION_AUDIT: Final = "audit"
PERMISSION_TARIFFS: Final = "tariffs"
PERMISSION_CHANNELS: Final = "channels"
PERMISSION_TEXTS: Final = "texts"
PERMISSION_BROADCASTS: Final = "broadcasts"
PERMISSION_BACKUPS: Final = "backups"
PERMISSION_DIAGNOSTICS: Final = "diagnostics"
PERMISSION_HEALTH: Final = "health"
PERMISSION_OBSERVABILITY: Final = "observability"
PERMISSION_PROMOS: Final = "promos"
PERMISSION_REFERRALS: Final = "referrals"
PERMISSION_SETTINGS: Final = "settings"

PERMISSION_LABELS: Final[dict[str, str]] = {
    PERMISSION_ADMIN_PANEL: "Админ-панель",
    PERMISSION_ANALYTICS: "Аналитика",
    PERMISSION_USERS_VIEW: "Просмотр пользователей",
    PERMISSION_USERS_MANAGE: "Управление пользователями",
    PERMISSION_SUPPORT: "Тикеты поддержки",
    PERMISSION_PAYMENTS: "Платежи и recovery",
    PERMISSION_AUDIT: "Аудит",
    PERMISSION_TARIFFS: "Тарифы",
    PERMISSION_CHANNELS: "Каналы",
    PERMISSION_TEXTS: "Тексты",
    PERMISSION_BROADCASTS: "Рассылки",
    PERMISSION_BACKUPS: "Бэкапы",
    PERMISSION_DIAGNOSTICS: "Диагностика",
    PERMISSION_HEALTH: "Health",
    PERMISSION_OBSERVABILITY: "Наблюдаемость",
    PERMISSION_PROMOS: "Промокоды",
    PERMISSION_REFERRALS: "Рефералка",
    PERMISSION_SETTINGS: "Настройки и роли",
}

ALL_PERMISSIONS: Final[frozenset[str]] = frozenset(PERMISSION_LABELS)

ROLE_PERMISSIONS: Final[dict[str, frozenset[str]]] = {
    ROLE_USER: frozenset(),
    ROLE_OWNER: ALL_PERMISSIONS,
    ROLE_ADMIN: frozenset(ALL_PERMISSIONS - {PERMISSION_SETTINGS}),
    ROLE_SUPPORT: frozenset(
        {
            PERMISSION_ADMIN_PANEL,
            PERMISSION_USERS_VIEW,
            PERMISSION_SUPPORT,
            PERMISSION_AUDIT,
            PERMISSION_DIAGNOSTICS,
            PERMISSION_HEALTH,
            PERMISSION_OBSERVABILITY,
        }
    ),
    ROLE_ANALYST: frozenset(
        {
            PERMISSION_ADMIN_PANEL,
            PERMISSION_ANALYTICS,
            PERMISSION_AUDIT,
            PERMISSION_DIAGNOSTICS,
            PERMISSION_HEALTH,
            PERMISSION_OBSERVABILITY,
        }
    ),
}


@dataclass(frozen=True, slots=True)
class AdminMenuSection:
    key: str
    button_text: str
    title: str
    permission: str


ADMIN_MENU_SECTIONS: Final[tuple[AdminMenuSection, ...]] = (
    AdminMenuSection("analytics", "📊 Аналитика", "Аналитика", PERMISSION_ANALYTICS),
    AdminMenuSection("users", "👥 Пользователи", "Пользователи", PERMISSION_USERS_VIEW),
    AdminMenuSection("support", "🎫 Поддержка", "Поддержка", PERMISSION_SUPPORT),
    AdminMenuSection("payments", "💳 Платежи", "Платежи", PERMISSION_PAYMENTS),
    AdminMenuSection("audit", "📜 Аудит", "Аудит", PERMISSION_AUDIT),
    AdminMenuSection("tariffs", "🧾 Тарифы", "Тарифы", PERMISSION_TARIFFS),
    AdminMenuSection("channels", "📣 Каналы", "Каналы", PERMISSION_CHANNELS),
    AdminMenuSection("texts", "✍️ Тексты", "Тексты", PERMISSION_TEXTS),
    AdminMenuSection("broadcasts", "📢 Рассылки", "Рассылки", PERMISSION_BROADCASTS),
    AdminMenuSection("backups", "💾 Бэкапы", "Бэкапы", PERMISSION_BACKUPS),
    AdminMenuSection("settings", "⚙️ Настройки", "Настройки", PERMISSION_SETTINGS),
    AdminMenuSection("diagnostics", "🧪 Диагностика", "Диагностика", PERMISSION_DIAGNOSTICS),
)


def normalize_admin_role(role: str | None) -> str:
    normalized = (role or ROLE_USER).strip().lower()
    if normalized not in KNOWN_ROLES:
        return ROLE_USER
    return normalized


def role_label(role: str | None) -> str:
    normalized = normalize_admin_role(role)
    return ROLE_LABELS.get(normalized, ROLE_LABELS[ROLE_USER])


def role_button_label(role: str | None) -> str:
    normalized = normalize_admin_role(role)
    icons = {
        ROLE_OWNER: "👑",
        ROLE_ADMIN: "🛠",
        ROLE_SUPPORT: "🎫",
        ROLE_ANALYST: "📊",
        ROLE_USER: "🙍",
    }
    return f"{icons.get(normalized, '🙍')} {role_label(normalized)}"


def is_admin_role(role: str | None) -> bool:
    return normalize_admin_role(role) in ADMIN_ROLES


def has_permission(role: str | None, permission: str) -> bool:
    normalized = normalize_admin_role(role)
    return permission in ROLE_PERMISSIONS.get(normalized, frozenset())


def permission_labels_for_role(role: str | None) -> list[str]:
    normalized = normalize_admin_role(role)
    permissions = sorted(ROLE_PERMISSIONS.get(normalized, frozenset()))
    return [PERMISSION_LABELS[item] for item in permissions if item in PERMISSION_LABELS]


def allowed_admin_menu_sections(role: str | None) -> tuple[AdminMenuSection, ...]:
    return tuple(
        section for section in ADMIN_MENU_SECTIONS if has_permission(role, section.permission)
    )


def get_admin_section_title(section_key: str) -> str | None:
    for section in ADMIN_MENU_SECTIONS:
        if section.key == section_key:
            return section.title
    return None


def resolve_role_from_user(
    user: User | None,
    *,
    telegram_user_id: int | None,
    settings: Settings | None,
) -> str:
    if (
        telegram_user_id is not None
        and settings is not None
        and telegram_user_id in settings.admin_ids_set
    ):
        return ROLE_OWNER
    if user is None:
        return ROLE_USER
    return normalize_admin_role(user.role)


async def get_user_by_telegram_id(
    session: AsyncSession,
    *,
    telegram_user_id: int,
) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_user_id))
    return result.scalar_one_or_none()


async def resolve_telegram_role(
    session: AsyncSession,
    *,
    telegram_user_id: int | None,
    settings: Settings | None,
) -> str:
    if telegram_user_id is None:
        return ROLE_USER
    user = await get_user_by_telegram_id(session, telegram_user_id=telegram_user_id)
    return resolve_role_from_user(user, telegram_user_id=telegram_user_id, settings=settings)


def is_owner_fallback(
    *,
    telegram_user_id: int | None,
    settings: Settings | None,
) -> bool:
    return (
        telegram_user_id is not None
        and settings is not None
        and telegram_user_id in settings.admin_ids_set
    )