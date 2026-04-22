"""Test bootstrap.

Every test runs without live Postgres/Redis: the env points at in-memory
stand-ins and `tests/infra.py` provides fakes.
"""
from __future__ import annotations

import os
import sys
import time

# Must be set before the `app` package is imported anywhere.
os.environ.setdefault("JWT_DEV_SECRET", "test-dev-secret-12345678")
os.environ.setdefault("JWT_DEV_ALGORITHM", "HS256")
os.environ.setdefault("JWT_AUDIENCE", "chat-gw")
os.environ.setdefault("JWT_ISSUER", "")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault("ENABLE_MCP_SSE", "false")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from jose import jwt

from app.settings import settings  # noqa: E402


DEV_SECRET = settings.jwt_dev_secret or "test-dev-secret-12345678"


def make_token(
    sub: str = "test-user",
    roles: list[str] | None = None,
    *,
    email: str = "test@example.com",
    name: str = "Test User",
    exp_offset: int = 3600,
    audience: str | None = None,
    issuer: str | None = None,
    secret: str | None = None,
) -> str:
    payload: dict = {
        "sub": sub,
        "roles": roles if roles is not None else ["cloud_admin"],
        "email": email,
        "name": name,
        "iat": int(time.time()),
        "exp": int(time.time()) + exp_offset,
    }
    aud = audience if audience is not None else settings.jwt_audience
    if aud:
        payload["aud"] = aud
    iss = issuer if issuer is not None else (settings.jwt_issuer or "")
    if iss:
        payload["iss"] = iss
    return jwt.encode(payload, secret or DEV_SECRET, algorithm="HS256")


@pytest.fixture
def admin_token() -> str:
    return make_token(sub="admin-user", roles=["cloud_admin"])


@pytest.fixture
def viewer_token() -> str:
    return make_token(sub="viewer-user", roles=["cloud_viewer"])


@pytest.fixture
def empty_roles_token() -> str:
    return make_token(sub="nobody", roles=[])
