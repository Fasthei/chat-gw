from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

from app.audit import AuditWriter
from app.dispatchers.base import Dispatcher, DispatchError, ToolInvocation, ToolResult
from app.mcp.handler import McpHandler
from app.registry.cache import ToolCache
from app.registry.service import ToolRegistry
from app.settings import settings
from tests.factories import make_auth_ctx, make_tool_view


# ─── Shared fixtures (no DB, no HTTP) ────────────────────────────────

def _make_registry(tools):
    cache = ToolCache(ttl_sec=300)
    registry = ToolRegistry(cache)

    async def loader():
        class _G:
            def __init__(self, role): self.role = role
        class _T:
            def __init__(self, v):
                self.id = v.id
                self.name = v.name
                self.display_name = v.display_name
                self.description = v.description
                self.category = v.category
                self.dispatcher = v.dispatcher
                self.config = v.config
                self.auth_mode = v.auth_mode
                self.secret_env_name = v.secret_env_name
                self.auth_header = v.auth_header
                self.auth_prefix = v.auth_prefix
                self.input_schema = v.input_schema
                self.output_schema = v.output_schema
                self.grants = [_G(r) for r in v.roles]
        return [_T(v) for v in tools]
    registry._load = loader  # type: ignore[attr-defined]
    return registry


def _make_audit():
    bucket: list = []

    class _Sess:
        def add(self, entry):
            bucket.append(entry)
        async def commit(self):
            return None

    @asynccontextmanager
    async def sm():
        yield _Sess()

    return AuditWriter(sm), bucket


class _StaticDispatcher(Dispatcher):
    name = "http_adapter"

    def __init__(self, result: ToolResult | None = None, error: DispatchError | None = None):
        self._result = result
        self._error = error
        self.calls: list[ToolInvocation] = []

    async def invoke(self, inv: ToolInvocation) -> ToolResult:
        self.calls.append(inv)
        if self._error:
            raise self._error
        return self._result or ToolResult(content=[{"type": "text", "text": "ok"}])

    async def close(self): return None


def _make_handler(tools, dispatcher):
    registry = _make_registry(tools)
    audit, bucket = _make_audit()
    handler = McpHandler(
        settings=settings,
        registry=registry,
        dispatchers={"http_adapter": dispatcher, "mcp_proxy": dispatcher},
        audit=audit,
    )
    return handler, bucket


# ─── Tests ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_initialize_returns_server_info():
    handler, _ = _make_handler([], _StaticDispatcher())
    resp = await handler.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05"}},
        make_auth_ctx(),
    )
    assert resp["result"]["serverInfo"]["name"] == settings.server_name
    assert resp["result"]["capabilities"]["tools"]["listChanged"] is True


@pytest.mark.asyncio
async def test_tools_list_filters_by_role():
    tools = [
        make_tool_view(id=1, name="kb.search", roles=frozenset({"cloud_admin", "cloud_viewer"})),
        make_tool_view(
            id=2, name="sales.list_customers",
            config={"base_url_env": "SUPER_OPS_API_BASE", "path": "/customers", "method": "GET"},
            roles=frozenset({"cloud_admin"}),
        ),
    ]
    handler, _ = _make_handler(tools, _StaticDispatcher())

    resp = await handler.handle(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        make_auth_ctx(roles=["cloud_viewer"]),
    )
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {"kb.search"}

    resp = await handler.handle(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        make_auth_ctx(roles=["cloud_admin"]),
    )
    assert {t["name"] for t in resp["result"]["tools"]} == {"kb.search", "sales.list_customers"}


@pytest.mark.asyncio
async def test_tools_call_denied_on_role_miss():
    tools = [make_tool_view(name="sales.x", roles=frozenset({"cloud_admin"}))]
    handler, bucket = _make_handler(tools, _StaticDispatcher())

    resp = await handler.handle(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "sales.x", "arguments": {"query": "q"}}},
        make_auth_ctx(roles=["cloud_viewer"]),
    )
    assert resp["error"]["code"] == -32001
    assert len(bucket) == 1
    assert bucket[0].status == "denied"
    assert bucket[0].deny_reason == "not_found_or_no_role"


@pytest.mark.asyncio
async def test_tools_call_schema_error_audited():
    tools = [make_tool_view(name="kb.search")]
    handler, bucket = _make_handler(tools, _StaticDispatcher())

    resp = await handler.handle(
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
         "params": {"name": "kb.search", "arguments": {"top": 5}}},  # missing query
        make_auth_ctx(roles=["cloud_admin"]),
    )
    assert resp["error"]["code"] == -32602
    assert bucket[0].status == "error"
    assert "schema" in (bucket[0].error_message or "")


@pytest.mark.asyncio
async def test_tools_call_success_audited_and_sensitive_tagged():
    tools = [
        make_tool_view(
            name="kb.search",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "token": {"type": "string"},
                },
                "required": ["query"],
            },
        )
    ]
    disp = _StaticDispatcher(result=ToolResult(content=[{"type": "text", "text": "hit"}]))
    handler, bucket = _make_handler(tools, disp)

    resp = await handler.handle(
        {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
         "params": {"name": "kb.search", "arguments": {"query": "hi", "token": "secret"}}},
        make_auth_ctx(roles=["cloud_admin"]),
    )
    assert resp["result"]["content"][0]["text"] == "hit"
    assert len(bucket) == 1
    row = bucket[0]
    assert row.status == "ok"
    assert row.latency_ms is not None
    assert "token" in row.sensitive_fields_hit
    assert disp.calls[0].arguments == {"query": "hi", "token": "secret"}


@pytest.mark.asyncio
async def test_tools_call_dispatch_error_normalized():
    tools = [make_tool_view(name="kb.search")]
    err = DispatchError("denied", mcp_code=-32001, kind="upstream_denied", upstream_status=403)
    handler, bucket = _make_handler(tools, _StaticDispatcher(error=err))

    resp = await handler.handle(
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
         "params": {"name": "kb.search", "arguments": {"query": "x"}}},
        make_auth_ctx(roles=["cloud_admin"]),
    )
    assert resp["error"]["code"] == -32001
    assert resp["error"]["data"]["kind"] == "upstream_denied"
    assert resp["error"]["data"]["upstreamStatus"] == 403
    assert bucket[0].status == "error"


@pytest.mark.asyncio
async def test_unknown_method():
    handler, _ = _make_handler([], _StaticDispatcher())
    resp = await handler.handle(
        {"jsonrpc": "2.0", "id": 9, "method": "foo/bar"},
        make_auth_ctx(),
    )
    assert resp["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_notification_returns_none():
    handler, _ = _make_handler([], _StaticDispatcher())
    resp = await handler.handle(
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        make_auth_ctx(),
    )
    assert resp is None
