from __future__ import annotations

import os
from uuid import uuid4

import httpx
import pytest

from app.dispatchers.base import DispatchError, ToolInvocation
from app.dispatchers.http_adapter import GenericHttpAdapter, map_params
from tests.factories import make_auth_ctx, make_tool_view


# ─── param mapping (pure) ────────────────────────────────────────────

def test_map_params_default_bucket_for_get():
    r = map_params(arguments={"q": "x", "top": 5}, path_template="/search",
                   param_map={}, method="GET")
    assert r["path"] == "/search"
    assert r["query"] == {"q": "x", "top": 5}
    assert r["body"] == {}
    assert r["header"] == {}


def test_map_params_default_bucket_for_post():
    r = map_params(arguments={"q": "x"}, path_template="/search",
                   param_map={}, method="POST")
    assert r["body"] == {"q": "x"}
    assert r["query"] == {}


def test_map_params_path_template_auto_consumes():
    r = map_params(arguments={"id": "abc", "verbose": True},
                   path_template="/tickets/{id}", param_map={}, method="GET")
    assert r["path"] == "/tickets/abc"
    assert r["query"] == {"verbose": True}


def test_map_params_path_template_url_encoded():
    r = map_params(arguments={"id": "a/b c"},
                   path_template="/items/{id}", param_map={}, method="GET")
    assert r["path"] == "/items/a%2Fb%20c"


def test_map_params_explicit_mapping_and_header():
    r = map_params(
        arguments={"id": "x", "pin": "1234", "mode": "fast", "trace": "t1"},
        path_template="/items/{id}",
        param_map={"pin": "body", "mode": "query", "trace": "header:X-Trace"},
        method="POST",
    )
    assert r["path"] == "/items/x"
    assert r["query"] == {"mode": "fast"}
    assert r["body"] == {"pin": "1234"}
    assert r["header"] == {"X-Trace": "t1"}


def test_map_params_body_wrap():
    r = map_params(arguments={"q": "x"}, path_template="/s", param_map={},
                   method="POST", body_wrap="data")
    assert r["body"] == {"data": {"q": "x"}}


def test_map_params_missing_path_arg_raises():
    with pytest.raises(DispatchError):
        map_params(arguments={}, path_template="/items/{id}",
                   param_map={"id": "path"}, method="GET")


def test_map_params_unknown_target_raises():
    with pytest.raises(DispatchError):
        map_params(arguments={"x": 1}, path_template="/",
                   param_map={"x": "cookie"}, method="GET")


# ─── end-to-end adapter with mock transport ──────────────────────────

@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("KB_AGENT_URL", "https://kb.test")
    monkeypatch.setenv("KB_AGENT_API_KEY", "kb-secret")
    monkeypatch.setenv("GONGDAN_API_BASE", "https://tickets.test")
    monkeypatch.setenv("GONGDAN_API_KEY", "gd_live_xxx")
    yield monkeypatch


def _adapter_with_mock(responses):
    """Build a GenericHttpAdapter whose httpx client uses MockTransport."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        resp = responses.pop(0)
        if callable(resp):
            return resp(request)
        return resp

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = GenericHttpAdapter(client=client, default_timeout_sec=5.0, default_retries=2, retry_backoff_base_sec=0.001)
    return adapter, client, captured


@pytest.mark.asyncio
async def test_adapter_service_key_header_and_body(env):
    adapter, client, captured = _adapter_with_mock([httpx.Response(200, text='{"ok":true}')])
    try:
        inv = ToolInvocation(
            tool=make_tool_view(
                name="kb.search",
                config={"base_url_env": "KB_AGENT_URL", "path": "/api/v1/search", "method": "POST"},
                auth_header="api-key",
                secret_env_name="KB_AGENT_API_KEY",
                auth_mode="service_key",
            ),
            arguments={"query": "hello", "top": 3},
            auth=make_auth_ctx(user_id="alice", roles=["cloud_admin"]),
            trace_id=uuid4(),
        )
        result = await adapter.invoke(inv)
    finally:
        await client.aclose()

    assert len(captured) == 1
    req = captured[0]
    assert req.method == "POST"
    assert str(req.url) == "https://kb.test/api/v1/search"
    assert req.headers["api-key"] == "kb-secret"
    assert req.headers["X-Gateway-User-Id"] == "alice"
    assert req.headers["X-Gateway-Tool-Name"] == "kb.search"
    assert b'"query"' in req.content
    assert result.content[0]["text"] == '{"ok":true}'


@pytest.mark.asyncio
async def test_adapter_user_passthrough_uses_bearer(env):
    adapter, client, captured = _adapter_with_mock([httpx.Response(200, text="ok")])
    try:
        inv = ToolInvocation(
            tool=make_tool_view(
                name="cloud_cost.overview",
                config={"base_url_env": "KB_AGENT_URL", "path": "/overview", "method": "GET"},
                auth_header="Authorization",
                auth_prefix="Bearer ",
                auth_mode="user_passthrough",
            ),
            arguments={},
            auth=make_auth_ctx(token="user-jwt-xyz"),
            trace_id=uuid4(),
        )
        await adapter.invoke(inv)
    finally:
        await client.aclose()
    assert captured[0].headers["Authorization"] == "Bearer user-jwt-xyz"


@pytest.mark.asyncio
async def test_adapter_path_and_query_split(env):
    adapter, client, captured = _adapter_with_mock([httpx.Response(200, text="[]")])
    try:
        inv = ToolInvocation(
            tool=make_tool_view(
                name="ticket.list_messages",
                config={
                    "base_url_env": "GONGDAN_API_BASE",
                    "path": "/api/tickets/{ticket_id}/messages",
                    "method": "GET",
                    "param_map": {"ticket_id": "path", "page": "query"},
                },
                auth_header="X-Api-Key",
                secret_env_name="GONGDAN_API_KEY",
                auth_mode="service_key",
            ),
            arguments={"ticket_id": "T-42", "page": 2},
            auth=make_auth_ctx(),
            trace_id=uuid4(),
        )
        await adapter.invoke(inv)
    finally:
        await client.aclose()
    req = captured[0]
    assert req.url.path == "/api/tickets/T-42/messages"
    assert dict(req.url.params) == {"page": "2"}


@pytest.mark.asyncio
async def test_adapter_401_maps_to_upstream_denied(env):
    adapter, client, _ = _adapter_with_mock([httpx.Response(401, text="nope")])
    try:
        inv = ToolInvocation(
            tool=make_tool_view(config={"base_url_env": "KB_AGENT_URL", "path": "/s", "method": "GET"}),
            arguments={},
            auth=make_auth_ctx(),
            trace_id=uuid4(),
        )
        with pytest.raises(DispatchError) as exc_info:
            await adapter.invoke(inv)
    finally:
        await client.aclose()
    assert exc_info.value.kind == "upstream_denied"
    assert exc_info.value.mcp_code == -32001
    assert exc_info.value.upstream_status == 401


@pytest.mark.asyncio
async def test_adapter_400_maps_to_invalid_params(env):
    adapter, client, _ = _adapter_with_mock([httpx.Response(400, text="bad")])
    try:
        inv = ToolInvocation(
            tool=make_tool_view(config={"base_url_env": "KB_AGENT_URL", "path": "/s", "method": "POST"}),
            arguments={},
            auth=make_auth_ctx(),
            trace_id=uuid4(),
        )
        with pytest.raises(DispatchError) as exc_info:
            await adapter.invoke(inv)
    finally:
        await client.aclose()
    assert exc_info.value.mcp_code == -32602


@pytest.mark.asyncio
async def test_adapter_retries_on_503(env):
    adapter, client, captured = _adapter_with_mock([
        httpx.Response(503, text="busy"),
        httpx.Response(503, text="busy"),
        httpx.Response(200, text="ok"),
    ])
    try:
        inv = ToolInvocation(
            tool=make_tool_view(config={"base_url_env": "KB_AGENT_URL", "path": "/s", "method": "GET"}),
            arguments={},
            auth=make_auth_ctx(),
            trace_id=uuid4(),
        )
        res = await adapter.invoke(inv)
    finally:
        await client.aclose()
    assert len(captured) == 3
    assert res.content[0]["text"] == "ok"


@pytest.mark.asyncio
async def test_adapter_user_passthrough_does_not_retry(env):
    adapter, client, captured = _adapter_with_mock([
        httpx.Response(503, text="busy"),
    ])
    try:
        inv = ToolInvocation(
            tool=make_tool_view(
                config={"base_url_env": "KB_AGENT_URL", "path": "/s", "method": "GET"},
                auth_header="Authorization",
                auth_prefix="Bearer ",
                auth_mode="user_passthrough",
            ),
            arguments={},
            auth=make_auth_ctx(token="t"),
            trace_id=uuid4(),
        )
        with pytest.raises(DispatchError):
            await adapter.invoke(inv)
    finally:
        await client.aclose()
    assert len(captured) == 1
