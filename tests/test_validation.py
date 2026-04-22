from __future__ import annotations

import pytest

from app.settings.config import Settings
from app.settings.validation import (
    is_placeholder,
    validate_production_settings,
    validate_tool_configs,
)
from tests.factories import make_tool_view


def test_is_placeholder_detects_common_markers():
    assert is_placeholder("REPLACE_ME")
    assert is_placeholder("something-replace_me-else")
    assert is_placeholder("https://example.com/api")
    assert is_placeholder("dev-secret-change-me")
    assert is_placeholder("")
    assert is_placeholder(None)
    assert not is_placeholder("https://real.internal/api")
    assert not is_placeholder("kb_real_secret_123")


def test_production_requires_jwks_url():
    s = Settings(
        app_env="production",
        jwt_dev_secret=None,
        jwks_url=None,
        jwt_issuer="https://casdoor.internal/",
        jwt_audience="chat-gw",
        database_url="postgresql+asyncpg://u:p@h/db",
        redis_url="rediss://r",
    )
    checks = validate_production_settings(s)
    failures = [c for c in checks if not c.ok]
    assert any(c.name == "required.jwks_url" for c in failures)


def test_production_rejects_jwt_dev_secret():
    s = Settings(
        app_env="production",
        jwt_dev_secret="leaked",
        jwks_url="https://casdoor.internal/.well-known/jwks.json",
        jwt_issuer="https://casdoor.internal/",
        jwt_audience="chat-gw",
        database_url="postgresql+asyncpg://u:p@h/db",
        redis_url="rediss://r",
    )
    checks = validate_production_settings(s)
    failures = [c for c in checks if not c.ok]
    assert any(c.name == "jwt_dev_secret_absent" for c in failures)


def test_production_rejects_placeholder_jwks_url():
    s = Settings(
        app_env="production",
        jwt_dev_secret=None,
        jwks_url="https://example.com/jwks.json",
        jwt_issuer="https://casdoor.internal/",
        jwt_audience="chat-gw",
        database_url="postgresql+asyncpg://u:p@h/db",
        redis_url="rediss://r",
    )
    checks = validate_production_settings(s)
    failures = {c.name for c in checks if not c.ok}
    assert "required.jwks_url" in failures


def test_production_requires_postgres_database_url():
    s = Settings(
        app_env="production",
        jwt_dev_secret=None,
        jwks_url="https://casdoor.internal/.well-known/jwks.json",
        jwt_issuer="https://casdoor.internal/",
        jwt_audience="chat-gw",
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="rediss://r",
    )
    failures = {c.name for c in validate_production_settings(s) if not c.ok}
    assert "database_url_postgres" in failures


def test_production_happy_path():
    s = Settings(
        app_env="production",
        jwt_dev_secret=None,
        jwks_url="https://casdoor.internal/.well-known/jwks.json",
        jwt_issuer="https://casdoor.internal/",
        jwt_audience="chat-gw",
        database_url="postgresql+asyncpg://u:p@db.internal:5432/chat_gw",
        redis_url="rediss://r.internal",
    )
    checks = validate_production_settings(s)
    assert all(c.ok for c in checks), [c for c in checks if not c.ok]


def test_jwt_mode_raises_when_dev_secret_in_production():
    s = Settings(
        app_env="production",
        jwt_dev_secret="whoops",
        jwks_url=None,
    )
    with pytest.raises(RuntimeError):
        s.jwt_mode()


def test_jwt_mode_dev_hs256_in_development():
    s = Settings(app_env="development", jwt_dev_secret="secret-123", jwks_url=None)
    assert s.jwt_mode() == "dev"


def test_jwt_mode_prod_when_jwks_set():
    s = Settings(app_env="production", jwt_dev_secret=None, jwks_url="https://x")
    assert s.jwt_mode() == "prod"


def test_jwt_mode_fails_when_nothing_set():
    s = Settings(app_env="development", jwt_dev_secret=None, jwks_url=None)
    with pytest.raises(RuntimeError):
        s.jwt_mode()


def test_validate_tool_configs_reports_missing_env(monkeypatch):
    monkeypatch.delenv("KB_AGENT_URL", raising=False)
    monkeypatch.setenv("KB_AGENT_API_KEY", "real-value")
    tool = make_tool_view()  # default config references KB_AGENT_URL
    results = validate_tool_configs([tool], strict=False)
    assert len(results) == 1
    issues = results[0].issues
    assert any("KB_AGENT_URL" in i for i in issues)


def test_validate_tool_configs_strict_rejects_placeholder(monkeypatch):
    monkeypatch.setenv("KB_AGENT_URL", "https://kb-agent.example.com")
    monkeypatch.setenv("KB_AGENT_API_KEY", "REPLACE_ME")
    tool = make_tool_view()
    results = validate_tool_configs([tool], strict=True)
    assert not results[0].ok
    joined = " ".join(results[0].issues)
    assert "placeholder" in joined


def test_validate_tool_configs_ok_when_real(monkeypatch):
    monkeypatch.setenv("KB_AGENT_URL", "https://kb.internal")
    monkeypatch.setenv("KB_AGENT_API_KEY", "abc-real")
    tool = make_tool_view()
    results = validate_tool_configs([tool], strict=True)
    assert results[0].ok
