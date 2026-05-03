from collections.abc import Iterable
from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeConfigurationError(RuntimeError):
    """Raised when the bot is started without required runtime settings."""


def _split_csv(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [chunk.strip() for chunk in value.split(",") if chunk.strip()]
    if isinstance(value, Iterable):
        return [str(chunk).strip() for chunk in value if str(chunk).strip()]
    return [str(value).strip()]


def _normalize_path(
    value: object,
    *,
    default: str,
    strip_trailing: bool = False,
) -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    normalized = text if text.startswith("/") else f"/{text}"
    if strip_trailing and normalized != "/":
        normalized = normalized.rstrip("/")
    return normalized or default


class Settings(BaseSettings):
    bot_token: SecretStr | None = None
    admin_ids: list[int] = Field(default_factory=list)
    database_url: str = "sqlite+aiosqlite:///./dev.db"

    timezone: str = "UTC"
    log_level: str = "INFO"
    environment: str = "development"
    critical_error_webhook_url: str | None = None

    public_webhook_url: str | None = None
    bot_public_username: str | None = None
    use_webhook: bool = False
    webhook_secret_token: SecretStr | None = None
    webhook_path: str = "/telegram/webhook"
    webapp_host: str = "0.0.0.0"
    webapp_port: int = Field(default=8080, ge=1, le=65535)
    delete_webhook_on_shutdown: bool = False
    mini_app_path: str = "/cabinet"
    mini_app_auth_max_age_seconds: int = Field(default=3600, ge=60, le=86400)

    crypto_pay_enabled: bool = False
    crypto_pay_token: SecretStr | None = None
    crypto_pay_testnet: bool = True
    crypto_pay_accepted_assets: list[str] = Field(default_factory=lambda: ["TON", "USDT"])
    crypto_pay_webhook_path: str = "/crypto-pay/webhook"

    backup_enabled: bool = True
    backup_time: str = "03:00"
    backup_retention_days: int = 14
    backup_send_to_admin: bool = True
    backup_directory: str = "./backups"

    broadcast_rate_limit_per_second: int = 20
    default_invite_link_ttl_hours: int = 24
    referral_reward_days: int = 7
    grace_period_hours: int = 6
    warning_3d_enabled: bool = True
    warning_1d_enabled: bool = True
    rate_limit_window_seconds: int = 5
    rate_limit_max_events: int = 6
    anti_spam_duplicate_window_seconds: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        enable_decoding=False,
    )

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> list[int]:
        return [int(item) for item in _split_csv(value)]

    @field_validator("crypto_pay_accepted_assets", mode="before")
    @classmethod
    def parse_crypto_assets(cls, value: object) -> list[str]:
        return [item.upper() for item in _split_csv(value)]

    @field_validator("public_webhook_url", "critical_error_webhook_url", mode="before")
    @classmethod
    def normalize_optional_url(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("bot_public_username", mode="before")
    @classmethod
    def normalize_optional_username(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip().lstrip("@")
        return text or None

    @field_validator("webhook_path", mode="before")
    @classmethod
    def normalize_webhook_path(cls, value: object) -> str:
        return _normalize_path(value, default="/telegram/webhook")

    @field_validator("mini_app_path", mode="before")
    @classmethod
    def normalize_mini_app_path(cls, value: object) -> str:
        normalized = _normalize_path(
            value,
            default="/cabinet",
            strip_trailing=True,
        )
        return "/cabinet" if normalized == "/" else normalized

    @field_validator("crypto_pay_webhook_path", mode="before")
    @classmethod
    def normalize_crypto_pay_webhook_path(cls, value: object) -> str:
        return _normalize_path(value, default="/crypto-pay/webhook")

    def require_runtime_ready(self) -> None:
        missing: list[str] = []
        if self.bot_token is None or not self.bot_token.get_secret_value().strip():
            missing.append("BOT_TOKEN")
        if not self.admin_ids:
            missing.append("ADMIN_IDS")
        if self.use_webhook:
            if not self.public_webhook_url or not self.public_webhook_url.strip():
                missing.append("PUBLIC_WEBHOOK_URL")
            secret = self.webhook_secret_token
            if secret is None or not secret.get_secret_value().strip():
                missing.append("WEBHOOK_SECRET_TOKEN")
        if missing:
            joined = ", ".join(missing)
            raise RuntimeConfigurationError(
                f"Missing required environment variables for bot runtime: {joined}"
            )

    @property
    def admin_ids_set(self) -> set[int]:
        return set(self.admin_ids)

    @property
    def webhook_url(self) -> str:
        base = (self.public_webhook_url or "").rstrip("/")
        return f"{base}{self.webhook_path}"

    @property
    def mini_app_url(self) -> str:
        base = (self.public_webhook_url or "").rstrip("/")
        return f"{base}{self.mini_app_path}"

    @property
    def bot_public_link(self) -> str | None:
        if not self.bot_public_username:
            return None
        return f"https://t.me/{self.bot_public_username}"

    @property
    def crypto_pay_webhook_url(self) -> str:
        base = (self.public_webhook_url or "").rstrip("/")
        return f"{base}{self.crypto_pay_webhook_path}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
