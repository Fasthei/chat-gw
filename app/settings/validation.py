"""Runtime configuration validation — placeholder/env guards.

Called from two places:
  1. app startup (main.py lifespan) → raise on hard prod misconfig
  2. `/readyz` endpoint → return structured per-check status

Keeping the scanner here (not inside Pydantic Settings) so it can inspect
tool configs loaded from DB, not just env vars.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.settings.config import Settings

# Strings that indicate a placeholder value. Case-insensitive substring match.
PLACEHOLDER_MARKERS: tuple[str, ...] = (
    "REPLACE_ME",
    "example.com",
    "example.org",
    "changeme",
    "change-me",
    "dev-secret",
    "your-secret-here",
    "placeholder",
    "todo-",
)


def is_placeholder(value: str | None) -> bool:
    if not value:
        return True
    lower = value.lower()
    return any(marker.lower() in lower for marker in PLACEHOLDER_MARKERS)


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "detail": self.detail}


class ConfigValidationError(RuntimeError):
    """Raised when startup validation finds a fatal misconfiguration."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def validate_production_settings(settings: Settings) -> list[Check]:
    """Hard-required checks for APP_ENV=production.

    Returns a list of `Check` entries; any with ok=False means fail-closed.
    """
    checks: list[Check] = []

    if settings.jwt_dev_secret:
        checks.append(Check(
            "jwt_dev_secret_absent", False,
            "JWT_DEV_SECRET must be empty in production (use JWKS_URL)",
        ))
    else:
        checks.append(Check("jwt_dev_secret_absent", True))

    for key, value in (
        ("jwks_url", settings.jwks_url),
        ("jwt_issuer", settings.jwt_issuer),
        ("jwt_audience", settings.jwt_audience),
        ("database_url", settings.database_url),
        ("redis_url", settings.redis_url),
    ):
        if not value:
            checks.append(Check(f"required.{key}", False, f"{key.upper()} must be set"))
        elif is_placeholder(value):
            checks.append(Check(
                f"required.{key}", False, f"{key.upper()} looks like a placeholder",
            ))
        else:
            checks.append(Check(f"required.{key}", True))

    if not settings.database_url.startswith(("postgresql", "postgres")):
        checks.append(Check(
            "database_url_postgres", False,
            "DATABASE_URL must point at Postgres in production",
        ))
    else:
        checks.append(Check("database_url_postgres", True))

    return checks


@dataclass(frozen=True)
class ToolConfigCheck:
    tool_name: str
    ok: bool
    issues: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "issues": list(self.issues)}


def validate_tool_configs(
    tools: list[Any],
    *,
    strict: bool,
) -> list[ToolConfigCheck]:
    """Verify env vars referenced by each tool are present and non-placeholder.

    `tools` is a list of `ToolView` (or duck-typed equivalents).
    `strict=True` treats placeholder values as failures (production).
    """
    results: list[ToolConfigCheck] = []
    for tool in tools:
        issues: list[str] = []

        config = getattr(tool, "config", None) or {}
        base_url_env = config.get("base_url_env")
        remote_url = config.get("remote_url")

        if base_url_env:
            value = os.environ.get(base_url_env, "")
            if not value:
                issues.append(f"env {base_url_env} missing")
            elif strict and is_placeholder(value):
                issues.append(f"env {base_url_env} is a placeholder")

        if remote_url:
            if strict and is_placeholder(remote_url):
                issues.append("remote_url is a placeholder")

        # Non-generic dispatchers (daytona, mcp_proxy) may not need base_url_env.
        if tool.dispatcher == "http_adapter" and not base_url_env:
            issues.append("http_adapter tool missing base_url_env")

        if tool.auth_mode == "service_key":
            secret_env = getattr(tool, "secret_env_name", None)
            if not secret_env:
                issues.append("service_key auth without secret_env_name")
            else:
                value = os.environ.get(secret_env, "")
                if not value:
                    issues.append(f"env {secret_env} missing")
                elif strict and is_placeholder(value):
                    issues.append(f"env {secret_env} is a placeholder")

        results.append(ToolConfigCheck(
            tool_name=tool.name,
            ok=not issues,
            issues=tuple(issues),
        ))

    return results
