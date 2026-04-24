from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Values override via environment variables; `.env` loaded for local dev.
    Every secret referenced via env var name only (see `tools.secret_env_name`).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    server_name: str = "chat-gw"
    server_version: str = "0.2.1"

    jwt_dev_secret: str | None = None
    jwt_dev_algorithm: str = "HS256"

    jwks_url: str | None = None
    jwt_audience: str = "chat-gw"
    jwt_issuer: str | None = None
    jwt_leeway_sec: int = 30
    jwks_refresh_cooldown_sec: int = 30
    jwks_cache_ttl_sec: int = 3600

    casdoor_endpoint: str | None = None
    casdoor_client_id: str | None = None
    casdoor_client_secret: str | None = None
    casdoor_org: str | None = None
    casdoor_app_name: str = "chat-gw"
    casdoor_roles_claim: str = "roles"

    database_url: str = "postgresql+asyncpg://chatgw:chatgw@postgres:5432/chat_gw"
    database_pool_size: int = 10
    database_max_overflow: int = 5

    redis_url: str = "redis://redis:6379/0"
    role_cache_ttl_sec: int = 60

    registry_cache_ttl_sec: int = 30

    http_default_timeout_sec: float = 30.0
    http_default_retries: int = 2
    http_retry_backoff_base_sec: float = 0.25

    mcp_proxy_default_timeout_sec: float = 60.0
    daytona_default_timeout_sec: float = 60.0
    daytona_max_timeout_sec: float = 300.0

    enable_mcp_sse: bool = True

    # ─── Gongdan (ticket system) integration ──────────────────────────
    # Resolves the `customer_code` carried in JWT claims to a real customer
    # by calling the gongdan API on every request (no cache — real-time).
    gongdan_api_base: str | None = None
    gongdan_api_key: str | None = None
    gongdan_timeout_sec: float = 5.0
    gongdan_customer_claim: str = "customer_code"

    # Gongdan-signed JWT (issued by ticket-system /auth/customer-login for
    # passwordless customer login). Symmetric HS256; secret shared with
    # gongdan's JWT_SECRET. When set, requests whose JWT carries
    # `role == gongdan_customer_role_value` are verified against this
    # secret instead of Casdoor JWKS. Customers have no Casdoor account.
    gongdan_jwt_secret: str | None = None
    gongdan_jwt_algorithm: str = "HS256"
    gongdan_customer_role_value: str = "CUSTOMER"

    def is_production(self) -> bool:
        return self.app_env == "production"

    def jwt_mode(self) -> Literal["dev", "prod"]:
        if self.jwks_url:
            return "prod"
        if self.jwt_dev_secret:
            if self.is_production():
                raise RuntimeError(
                    "JWT_DEV_SECRET is set while APP_ENV=production; refuse to start.",
                )
            return "dev"
        raise RuntimeError(
            "Neither JWT_DEV_SECRET nor JWKS_URL configured; refuse to start.",
        )


settings = Settings()
