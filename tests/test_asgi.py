"""Lightweight ASGI smoke tests without real Postgres/Redis.

We construct a FastAPI app manually, register the MCP routes, and plug fake
state — enough to exercise auth dependency + request/response shape.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.errors import auth_error_handler
from app.api.health import build_health_router
from app.audit import AuditWriter
from app.auth.errors import AuthError
from app.auth.jwt_verify import JwtVerifier
from app.auth.roles import RoleResolver
from app.dispatchers.base import Dispatcher, ToolInvocation, ToolResult
from app.mcp.handler import McpHandler
from app.mcp.streamable import build_streamable_router
from app.registry.cache import ToolCache
from app.registry.service import ToolRegistry
from app.settings import settings
from tests.conftest import make_token
from tests.factories import make_tool_view


class _InMemRedis:
    def __init__(self):
        self.store = {}

    async def get(self, k):
        return self.store.get(k)

    async def setex(self, k, ttl, v):
        self.store[k] = v

    async def delete(self, k):
        self.store.pop(k, None)

    async def ping(self):
        return True

    async def aclose(self):
        return None


class _NoopDispatcher(Dispatcher):
    name = "http_adapter"

    async def invoke(self, inv: ToolInvocation) -> ToolResult:
        return ToolResult(content=[{"type": "text", "text": "mock"}])

    async def close(self):
        return None


def _make_test_app(tools=None) -> FastAPI:
    app = FastAPI()

    cache = ToolCache(ttl_sec=300)
    registry = ToolRegistry(cache)

    views = tools or [make_tool_view(name="kb.search")]

    async def loader():
        class _G:
            def __init__(self, r): self.role = r
        class _T:
            def __init__(self, v):
                for k in ("id","name","display_name","description","category","dispatcher",
                          "config","auth_mode","secret_env_name","auth_header","auth_prefix",
                          "input_schema","output_schema"):
                    setattr(self, k, getattr(v, k))
                self.grants = [_G(r) for r in v.roles]
        return [_T(v) for v in views]
    registry._load = loader  # type: ignore[attr-defined]

    redis = _InMemRedis()

    app.state.redis = redis
    app.state.jwks_cache = None
    app.state.jwt_verifier = JwtVerifier(settings, jwks=None)
    app.state.role_resolver = RoleResolver(
        roles_claim=settings.casdoor_roles_claim, redis=redis, casdoor=None,
    )
    app.state.tool_cache = cache
    app.state.tool_registry = registry

    bucket: list = []

    class _Sess:
        def add(self, e): bucket.append(e)
        async def commit(self): return None

    @asynccontextmanager
    async def sm():
        yield _Sess()

    audit = AuditWriter(sm)
    app.state.audit_bucket = bucket
    app.state.audit_writer = audit
    app.state.dispatchers = {"http_adapter": _NoopDispatcher(), "mcp_proxy": _NoopDispatcher()}
    app.state.mcp_handler = McpHandler(
        settings=settings,
        registry=registry,
        dispatchers=app.state.dispatchers,
        audit=audit,
    )

    app.add_exception_handler(AuthError, auth_error_handler)
    app.include_router(build_health_router())
    app.include_router(build_streamable_router())
    return app


@pytest.mark.asyncio
async def test_healthz():
    app = _make_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_mcp_rejects_missing_bearer():
    app = _make_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mcp_initialize_with_token():
    app = _make_test_app()
    token = make_token(roles=["cloud_admin"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2024-11-05"}},
            headers={"Authorization": f"Bearer {token}"},
        )
    body = resp.json()
    assert resp.status_code == 200
    assert body["result"]["serverInfo"]["name"] == settings.server_name


@pytest.mark.asyncio
async def test_mcp_tools_list_filters_for_viewer():
    app = _make_test_app(tools=[
        make_tool_view(id=1, name="kb.search", roles=frozenset({"cloud_admin", "cloud_viewer"})),
        make_tool_view(id=2, name="sales.list_customers", roles=frozenset({"cloud_admin"})),
    ])
    viewer = make_token(roles=["cloud_viewer"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers={"Authorization": f"Bearer {viewer}"},
        )
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert names == {"kb.search"}
