"""/admin/* integration tests using sqlite + a real FastAPI app.

Covers:
- role guard (non-admin → 403)
- tools CRUD (GET/POST/PATCH/DELETE soft+hard)
- grants CRUD (GET/PUT on/off/DELETE)
- audit GET (filters + keyset cursor pagination)
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sqlalchemy import ARRAY, BigInteger, Integer, JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID

from app.admin import build_audit_router, build_grants_router, build_tools_router
from app.api.errors import auth_error_handler
from app.auth.errors import AuthError
from app.auth.jwt_verify import JwtVerifier
from app.auth.roles import RoleResolver
from app.db.engine import get_session
from app.db.models import Base, Tool, ToolAuditLog, ToolRoleGrant
from app.settings import settings
from tests.conftest import make_token


def _retype_for_sqlite() -> list[tuple]:
    """Swap PG-only column types to SQLite-compatible equivalents.

    Returns a restore plan so the teardown can put the original types back.
    Safe to call once per test fixture; mutations are local to the
    SQLAlchemy metadata and reversed in the fixture's finally block.
    """
    restore: list[tuple] = []
    for table in Base.metadata.tables.values():
        for col in table.columns:
            original = col.type
            if isinstance(original, JSONB):
                col.type = JSON()
            elif isinstance(original, ARRAY):
                col.type = JSON()
            elif isinstance(original, PgUUID):
                col.type = String(36)
            elif isinstance(original, BigInteger) and col.primary_key:
                # SQLite autoincrement only works on INTEGER PRIMARY KEY.
                col.type = Integer()
            else:
                continue
            restore.append((col, original))
    return restore


def _restore_types(plan) -> None:
    for col, original in plan:
        col.type = original


class _InMemRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

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


@pytest.fixture
async def sqlite_sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Ephemeral SQLite + tables created + bound as module-level
    async_session so admin routes using Depends(get_session) hit this DB."""
    # Drop chat_gw schema + swap PG-only types (JSONB/ARRAY/UUID) for SQLite.
    saved_schemas = []
    for t in Base.metadata.tables.values():
        saved_schemas.append((t, t.schema))
        t.schema = None
    restore_plan = _retype_for_sqlite()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield sessionmaker
    finally:
        await engine.dispose()
        _restore_types(restore_plan)
        for t, schema in saved_schemas:
            t.schema = schema


def _build_app(sessionmaker: async_sessionmaker[AsyncSession]) -> FastAPI:
    app = FastAPI()
    redis = _InMemRedis()
    app.state.redis = redis
    app.state.jwks_cache = None
    app.state.jwt_verifier = JwtVerifier(settings, jwks=None)
    app.state.role_resolver = RoleResolver(
        roles_claim=settings.casdoor_roles_claim, redis=redis, casdoor=None
    )

    # No real registry: admin routers tolerate missing tool_registry.
    app.state.tool_registry = None

    # Override get_session to use test sessionmaker.
    async def _override_session():
        async with sessionmaker() as s:
            yield s

    app.dependency_overrides[get_session] = _override_session

    app.add_exception_handler(AuthError, auth_error_handler)
    app.include_router(build_tools_router())
    app.include_router(build_grants_router())
    app.include_router(build_audit_router())
    return app


async def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _admin_header() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub='admin-user', roles=['cloud_admin'])}"}


def _viewer_header() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub='viewer', roles=['cloud_viewer'])}"}


# ─── seed helpers ────────────────────────────────────────────────────


async def _seed_tool(sm, **overrides) -> Tool:
    base = dict(
        name="kb.search",
        display_name="KB Search",
        description="search the kb",
        category="kb",
        enabled=True,
        dispatcher="http_adapter",
        config={"base_url_env": "KB_AGENT_URL", "path": "/q", "method": "POST"},
        auth_mode="service_key",
        secret_env_name="KB_AGENT_API_KEY",
        auth_header="api-key",
        auth_prefix="",
        input_schema={"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
    )
    base.update(overrides)
    async with sm() as s:
        row = Tool(**base)
        s.add(row)
        await s.commit()
        await s.refresh(row)
        return row


async def _seed_grant(sm, tool_id: int, role: str) -> None:
    async with sm() as s:
        s.add(ToolRoleGrant(tool_id=tool_id, role=role))
        await s.commit()


async def _seed_audit_row(sm, *, started_at: datetime, **overrides) -> ToolAuditLog:
    base = dict(
        # sqlite has no UUID type → store as string; keep wire API uuid-ish
        trace_id=str(uuid4()),
        user_id="alice",
        user_email="a@x.com",
        roles=["cloud_admin"],
        tool_name="kb.search",
        tool_id=None,
        arguments={"q": "hi"},
        sensitive_fields_hit=[],
        status="ok",
        deny_reason=None,
        error_message=None,
        error_code=None,
        error_kind=None,
        latency_ms=10,
        started_at=started_at,
        finished_at=started_at,
    )
    base.update(overrides)
    async with sm() as s:
        row = ToolAuditLog(**base)
        s.add(row)
        await s.commit()
        await s.refresh(row)
        return row


# ─── role guard ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_non_admin_gets_403(sqlite_sessionmaker):
    app = _build_app(sqlite_sessionmaker)
    async with await _client(app) as c:
        r = await c.get("/admin/tools", headers=_viewer_header())
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_missing_token_gets_401(sqlite_sessionmaker):
    app = _build_app(sqlite_sessionmaker)
    async with await _client(app) as c:
        r = await c.get("/admin/tools")
    assert r.status_code == 401


# ─── tools CRUD ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_tools_includes_disabled(sqlite_sessionmaker):
    await _seed_tool(sqlite_sessionmaker, name="a.one")
    await _seed_tool(sqlite_sessionmaker, name="b.two", enabled=False)
    app = _build_app(sqlite_sessionmaker)
    async with await _client(app) as c:
        r = await c.get("/admin/tools", headers=_admin_header())
        assert r.status_code == 200
        names = {t["name"] for t in r.json()["tools"]}
        assert names == {"a.one", "b.two"}
        # explicit exclude
        r = await c.get("/admin/tools?include_disabled=false", headers=_admin_header())
        assert {t["name"] for t in r.json()["tools"]} == {"a.one"}


@pytest.mark.asyncio
async def test_upsert_tool_inserts_and_then_updates(sqlite_sessionmaker):
    app = _build_app(sqlite_sessionmaker)
    body = {
        "name": "kb.search",
        "display_name": "KB Search",
        "description": "search",
        "category": "kb",
        "dispatcher": "http_adapter",
        "config": {"base_url_env": "KB_AGENT_URL", "path": "/q", "method": "POST"},
        "auth_mode": "service_key",
        "secret_env_name": "KB_AGENT_API_KEY",
        "auth_header": "api-key",
        "auth_prefix": "",
        "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
        "enabled": True,
    }
    async with await _client(app) as c:
        r = await c.post("/admin/tools", json=body, headers=_admin_header())
        assert r.status_code == 200, r.text
        first = r.json()
        assert first["name"] == "kb.search"
        assert first["version"] == 1

        body["description"] = "updated"
        r = await c.post("/admin/tools", json=body, headers=_admin_header())
        assert r.status_code == 200
        second = r.json()
        assert second["description"] == "updated"
        assert second["version"] == 2  # bumped by upsert


@pytest.mark.asyncio
async def test_patch_tool_partial(sqlite_sessionmaker):
    await _seed_tool(sqlite_sessionmaker)
    app = _build_app(sqlite_sessionmaker)
    async with await _client(app) as c:
        r = await c.patch(
            "/admin/tools/kb.search",
            json={"description": "partially updated", "enabled": False},
            headers=_admin_header(),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["description"] == "partially updated"
        assert body["enabled"] is False
        assert body["version"] == 2


@pytest.mark.asyncio
async def test_patch_tool_not_found(sqlite_sessionmaker):
    app = _build_app(sqlite_sessionmaker)
    async with await _client(app) as c:
        r = await c.patch("/admin/tools/no.such", json={"enabled": False}, headers=_admin_header())
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_patch_tool_rejects_empty(sqlite_sessionmaker):
    await _seed_tool(sqlite_sessionmaker)
    app = _build_app(sqlite_sessionmaker)
    async with await _client(app) as c:
        r = await c.patch("/admin/tools/kb.search", json={}, headers=_admin_header())
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_delete_tool_soft_keeps_row(sqlite_sessionmaker):
    await _seed_tool(sqlite_sessionmaker)
    app = _build_app(sqlite_sessionmaker)
    async with await _client(app) as c:
        r = await c.delete("/admin/tools/kb.search", headers=_admin_header())
        assert r.status_code == 204
        r = await c.get("/admin/tools", headers=_admin_header())
        tools = r.json()["tools"]
        assert len(tools) == 1
        assert tools[0]["enabled"] is False


@pytest.mark.asyncio
async def test_delete_tool_hard_removes_row(sqlite_sessionmaker):
    tool = await _seed_tool(sqlite_sessionmaker)
    await _seed_grant(sqlite_sessionmaker, tool.id, "cloud_admin")
    app = _build_app(sqlite_sessionmaker)
    async with await _client(app) as c:
        r = await c.delete("/admin/tools/kb.search?hard=true", headers=_admin_header())
        assert r.status_code == 204
        r = await c.get("/admin/tools", headers=_admin_header())
        assert r.json()["tools"] == []


# ─── grants CRUD ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_grants_ordered(sqlite_sessionmaker):
    t1 = await _seed_tool(sqlite_sessionmaker, name="a.one")
    t2 = await _seed_tool(sqlite_sessionmaker, name="b.two")
    await _seed_grant(sqlite_sessionmaker, t1.id, "cloud_admin")
    await _seed_grant(sqlite_sessionmaker, t2.id, "cloud_viewer")
    app = _build_app(sqlite_sessionmaker)
    async with await _client(app) as c:
        r = await c.get("/admin/tool-role-grants", headers=_admin_header())
        assert r.status_code == 200
        assert r.json()["grants"] == [
            {"role": "cloud_admin", "tool_name": "a.one"},
            {"role": "cloud_viewer", "tool_name": "b.two"},
        ]


@pytest.mark.asyncio
async def test_put_grant_on_and_off_is_idempotent(sqlite_sessionmaker):
    await _seed_tool(sqlite_sessionmaker, name="kb.search")
    app = _build_app(sqlite_sessionmaker)
    async with await _client(app) as c:
        # grant twice — idempotent
        for _ in range(2):
            r = await c.put(
                "/admin/tool-role-grants",
                json={"role": "cloud_ops", "tool_name": "kb.search", "granted": True},
                headers=_admin_header(),
            )
            assert r.status_code == 200
        r = await c.get("/admin/tool-role-grants?role=cloud_ops", headers=_admin_header())
        assert len(r.json()["grants"]) == 1

        # revoke via PUT granted=false
        r = await c.put(
            "/admin/tool-role-grants",
            json={"role": "cloud_ops", "tool_name": "kb.search", "granted": False},
            headers=_admin_header(),
        )
        assert r.status_code == 200
        r = await c.get("/admin/tool-role-grants?role=cloud_ops", headers=_admin_header())
        assert r.json()["grants"] == []


@pytest.mark.asyncio
async def test_put_grant_rejects_unknown_tool(sqlite_sessionmaker):
    app = _build_app(sqlite_sessionmaker)
    async with await _client(app) as c:
        r = await c.put(
            "/admin/tool-role-grants",
            json={"role": "cloud_admin", "tool_name": "no.such", "granted": True},
            headers=_admin_header(),
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_put_grant_rejects_unknown_role(sqlite_sessionmaker):
    await _seed_tool(sqlite_sessionmaker)
    app = _build_app(sqlite_sessionmaker)
    async with await _client(app) as c:
        r = await c.put(
            "/admin/tool-role-grants",
            json={"role": "superuser", "tool_name": "kb.search", "granted": True},
            headers=_admin_header(),
        )
    assert r.status_code == 422  # Literal role enum rejected at Pydantic layer


@pytest.mark.asyncio
async def test_delete_grant_removes(sqlite_sessionmaker):
    tool = await _seed_tool(sqlite_sessionmaker)
    await _seed_grant(sqlite_sessionmaker, tool.id, "cloud_viewer")
    app = _build_app(sqlite_sessionmaker)
    async with await _client(app) as c:
        r = await c.delete(
            "/admin/tool-role-grants?role=cloud_viewer&tool_name=kb.search",
            headers=_admin_header(),
        )
        assert r.status_code == 204
        r = await c.get("/admin/tool-role-grants", headers=_admin_header())
        assert r.json()["grants"] == []


# ─── audit query ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_filters(sqlite_sessionmaker):
    now = datetime.now(timezone.utc)
    await _seed_audit_row(sqlite_sessionmaker, started_at=now - timedelta(hours=2),
                          user_id="alice", tool_name="kb.search", status="ok")
    await _seed_audit_row(sqlite_sessionmaker, started_at=now - timedelta(hours=1),
                          user_id="bob", tool_name="web.search", status="denied",
                          deny_reason="not_found_or_no_role",
                          error_code=-32001, error_kind="not_found_or_no_role")
    await _seed_audit_row(sqlite_sessionmaker, started_at=now,
                          user_id="alice", tool_name="kb.search", status="error",
                          error_code=-32603, error_kind="upstream_error",
                          error_message="upstream boom")
    app = _build_app(sqlite_sessionmaker)
    async with await _client(app) as c:
        # user filter
        r = await c.get("/admin/audit?user_id=alice", headers=_admin_header())
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 2
        assert all(i["user_id"] == "alice" for i in body["items"])

        # tool filter
        r = await c.get("/admin/audit?tool_name=web.search", headers=_admin_header())
        assert [i["tool_name"] for i in r.json()["items"]] == ["web.search"]

        # outcome filter
        r = await c.get("/admin/audit?outcome=denied", headers=_admin_header())
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["error_code"] == -32001
        assert items[0]["error_kind"] == "not_found_or_no_role"


@pytest.mark.asyncio
async def test_audit_date_range(sqlite_sessionmaker):
    now = datetime.now(timezone.utc)
    await _seed_audit_row(sqlite_sessionmaker, started_at=now - timedelta(days=5))
    mid = await _seed_audit_row(sqlite_sessionmaker, started_at=now - timedelta(days=2))
    await _seed_audit_row(sqlite_sessionmaker, started_at=now)
    app = _build_app(sqlite_sessionmaker)
    lo = (now - timedelta(days=3)).isoformat()
    hi = (now - timedelta(days=1)).isoformat()
    async with await _client(app) as c:
        # Use httpx `params=` so the '+' in the tz suffix is URL-encoded.
        r = await c.get(
            "/admin/audit",
            params={"from": lo, "to": hi},
            headers=_admin_header(),
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["trace_id"] == str(mid.trace_id)


@pytest.mark.asyncio
async def test_audit_cursor_pagination(sqlite_sessionmaker):
    now = datetime.now(timezone.utc)
    seeded = []
    for i in range(6):
        row = await _seed_audit_row(
            sqlite_sessionmaker, started_at=now - timedelta(seconds=i)
        )
        seeded.append(row)
    app = _build_app(sqlite_sessionmaker)
    async with await _client(app) as c:
        r = await c.get("/admin/audit?limit=2", headers=_admin_header())
        body = r.json()
        assert len(body["items"]) == 2
        assert body["next_cursor"] is not None

        r2 = await c.get(f"/admin/audit?limit=2&cursor={body['next_cursor']}",
                         headers=_admin_header())
        body2 = r2.json()
        assert len(body2["items"]) == 2
        # no overlap between page 1 and page 2
        page1_ids = {i["trace_id"] for i in body["items"]}
        page2_ids = {i["trace_id"] for i in body2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

        # final page
        r3 = await c.get(f"/admin/audit?limit=2&cursor={body2['next_cursor']}",
                         headers=_admin_header())
        body3 = r3.json()
        assert len(body3["items"]) == 2
        assert body3["next_cursor"] is None


@pytest.mark.asyncio
async def test_audit_bad_cursor(sqlite_sessionmaker):
    app = _build_app(sqlite_sessionmaker)
    async with await _client(app) as c:
        r = await c.get("/admin/audit?cursor=not-base64", headers=_admin_header())
    assert r.status_code == 400
