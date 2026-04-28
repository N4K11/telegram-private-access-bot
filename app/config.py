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


class Settings(BaseSettings):
    bot_token: SecretStr | None = None
    admin_ids: list[int] = Field(default_factory=list)
    database_url: str = "sqlite+aiosqlite:///./dev.db"

    timezone: str = "UTC"
    log_level: str = "INFO"
    environment: str = "development"

    public_webhook_url: str | None = None
    use_webhook: bool = False

    crypto_pay_enabled: bool = False
    crypto_pay_token: SecretStr | None = None
    crypto_pay_testnet: bool = True
    crypto_pay_accepted_assets: list[str] = Field(default_factory=lambda: ["TON", "USDT"])

    backup_enabled: bool = True
    backup_time: str = "03:00"
    backup_retention_days: int = 14
    backup_send_to_admin: bool = True

    broadcast_rate_limit_per_second: int = 20
    default_invite_link_ttl_hours: int = 24

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> list[int]:
        return [int(item) for item in _split_csv(value)]

    @field_validator("crypto_pay_accepted_assets", mode="before")
    @classmethod
    def parse_crypto_assets(cls, value: object) -> list[str]:
        return [item.upper() for item in _split_csv(value)]

    def require_runtime_ready(self) -> None:
        missing: list[str] = []
        if self.bot_token is None or not self.bot_token.get_secret_value().strip():
            missing.append("BOT_TOKEN")
        if not self.admin_ids:
            missing.append("ADMIN_IDS")
        if missing:
            joined = ", ".join(missing)
            raise RuntimeConfigurationError(
                f"Missing required environment variables for bot runtime: {joined}"
            )

    @property
    def admin_ids_set(self) -> set[int]:
        return set(self.admin_ids)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
