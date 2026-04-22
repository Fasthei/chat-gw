from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest

from app.dispatchers.base import DispatchError, ToolInvocation
from app.dispatchers.mcp_proxy import McpProxyAdapter, _parse_sse_envelope
from app.registry.cache import ToolView
from tests.factories import make_auth_ctx, make_tool_view


def _jina_tool(**overrides):
    cfg = {
        "remote_url": "https://mcp.jina.example/sse",
        "prefix": "jina.",
        "remote_tool_name": "search",
        "skip_initialize": True,
        "timeout_sec": 5,
    }
    cfg.update(overrides.pop("config", {}))
    defaults = dict(
        name="jina.search",
        dispatcher="mcp_proxy",
        auth_mode="service_key",
        secret_env_name="JINA_API_KEY",
        auth_header="Authorization",
        auth_prefix="Bearer ",
        input_schema={"type": "object"},
        roles=frozenset({"cloud_admin"}),
        config=cfg,
    )
    defaults.update(overrides)
    return make_tool_view(**defaults)


def _adapter_with_mock(responses, capture=None, *, skip_init=True):
    captured: list[httpx.Request] = capture if capture is not None else []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        resp = responses.pop(0)
        return resp(request) if callable(resp) else resp

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = McpProxyAdapter(client=client, default_timeout_sec=5)
    return adapter, client, captured


def _json_rpc_result(result: dict, request_id="t"):
    return httpx.Response(
        200,
        headers={"content-type": "application/json"},
        json={"jsonrpc": "2.0", "id": request_id, "result": result},
    )


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("JINA_API_KEY", "jina-test-key")
    yield monkeypatch


@pytest.mark.asyncio
async def test_proxy_forwards_tools_call_and_strips_prefix(env):
    adapter, client, captured = _adapter_with_mock([
        _json_rpc_result({"content": [{"type": "text", "text": "hit"}]}, request_id="trace"),
    ])
    try:
        inv = ToolInvocation(
            tool=_jina_tool(),
            arguments={"query": "hello"},
            auth=make_auth_ctx(roles=["cloud_admin"]),
            trace_id=uuid4(),
        )
        result = await adapter.invoke(inv)
    finally:
        await client.aclose()

    assert len(captured) == 1
    body = json.loads(captured[0].content)
    assert body["method"] == "tools/call"
    assert body["params"]["name"] == "search"  # prefix `jina.` stripped
    assert body["params"]["arguments"] == {"query": "hello"}
    assert captured[0].headers["Authorization"] == "Bearer jina-test-key"
    assert captured[0].headers["X-Gateway-Tool-Name"] == "jina.search"
    assert result.content == [{"type": "text", "text": "hit"}]
    assert not result.is_error


@pytest.mark.asyncio
async def test_proxy_user_passthrough_uses_bearer_token(env):
    captured: list[httpx.Request] = []
    adapter, client, _ = _adapter_with_mock([
        _json_rpc_result({"content": [{"type": "text", "text": "ok"}]})
    ], capture=captured)
    try:
        tool = _jina_tool(auth_mode="user_passthrough", secret_env_name=None)
        inv = ToolInvocation(
            tool=tool,
            arguments={"query": "hi"},
            auth=make_auth_ctx(token="user-raw-jwt"),
            trace_id=uuid4(),
        )
        await adapter.invoke(inv)
    finally:
        await client.aclose()
    assert captured[0].headers["Authorization"] == "Bearer user-raw-jwt"


@pytest.mark.asyncio
async def test_proxy_parses_sse_response(env):
    sse_body = (
        "event: message\n"
        'data: {"jsonrpc":"2.0","id":"t","result":{"content":[{"type":"text","text":"sse-hit"}]}}\n\n'
    )
    adapter, client, _ = _adapter_with_mock([
        httpx.Response(200, headers={"content-type": "text/event-stream"}, text=sse_body),
    ])
    try:
        inv = ToolInvocation(
            tool=_jina_tool(),
            arguments={"query": "x"},
            auth=make_auth_ctx(),
            trace_id=uuid4(),
        )
        res = await adapter.invoke(inv)
    finally:
        await client.aclose()
    assert res.content[0]["text"] == "sse-hit"


@pytest.mark.asyncio
async def test_proxy_upstream_denied_401(env):
    adapter, client, _ = _adapter_with_mock([httpx.Response(401, text="denied")])
    try:
        inv = ToolInvocation(
            tool=_jina_tool(),
            arguments={"query": "x"},
            auth=make_auth_ctx(),
            trace_id=uuid4(),
        )
        with pytest.raises(DispatchError) as exc_info:
            await adapter.invoke(inv)
    finally:
        await client.aclose()
    assert exc_info.value.kind == "upstream_denied"
    assert exc_info.value.mcp_code == -32001


@pytest.mark.asyncio
async def test_proxy_remote_mcp_error_passthrough(env):
    adapter, client, _ = _adapter_with_mock([
        httpx.Response(200, headers={"content-type": "application/json"},
                       json={"jsonrpc": "2.0", "id": "t",
                             "error": {"code": -32602, "message": "bad arg"}}),
    ])
    try:
        inv = ToolInvocation(
            tool=_jina_tool(),
            arguments={"query": "x"},
            auth=make_auth_ctx(),
            trace_id=uuid4(),
        )
        with pytest.raises(DispatchError) as exc_info:
            await adapter.invoke(inv)
    finally:
        await client.aclose()
    assert exc_info.value.mcp_code == -32602
    assert exc_info.value.kind == "remote_mcp_error"


@pytest.mark.asyncio
async def test_proxy_missing_remote_url_is_config_error(env):
    adapter, client, _ = _adapter_with_mock([])
    try:
        tool = ToolView(
            id=99, name="jina.search", display_name="x", description="x",
            category="jina", dispatcher="mcp_proxy",
            config={"skip_initialize": True},  # intentionally no remote_url
            auth_mode="service_key", secret_env_name="JINA_API_KEY",
            auth_header="Authorization", auth_prefix="Bearer ",
            input_schema={"type": "object"}, output_schema=None,
            roles=frozenset({"cloud_admin"}),
        )
        inv = ToolInvocation(
            tool=tool,
            arguments={"query": "x"},
            auth=make_auth_ctx(),
            trace_id=uuid4(),
        )
        with pytest.raises(DispatchError) as exc_info:
            await adapter.invoke(inv)
    finally:
        await client.aclose()
    assert exc_info.value.kind == "config_error"


@pytest.mark.asyncio
async def test_proxy_missing_secret_env_is_config_error(monkeypatch):
    monkeypatch.delenv("JINA_API_KEY", raising=False)
    adapter, client, _ = _adapter_with_mock([])
    try:
        inv = ToolInvocation(
            tool=_jina_tool(),
            arguments={"query": "x"},
            auth=make_auth_ctx(),
            trace_id=uuid4(),
        )
        with pytest.raises(DispatchError) as exc_info:
            await adapter.invoke(inv)
    finally:
        await client.aclose()
    assert exc_info.value.kind == "config_error"


@pytest.mark.asyncio
async def test_proxy_runs_initialize_handshake(env):
    # One init response, then one tools/call response.
    captured: list[httpx.Request] = []
    responses = [
        httpx.Response(
            200,
            headers={"content-type": "application/json", "Mcp-Session-Id": "abc-123"},
            json={"jsonrpc": "2.0", "id": "ignore", "result": {
                "protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                "serverInfo": {"name": "remote", "version": "0"}}},
        ),
        _json_rpc_result({"content": [{"type": "text", "text": "ok"}]}),
    ]
    adapter, client, _ = _adapter_with_mock(responses, capture=captured)
    try:
        tool = _jina_tool(config={
            "remote_url": "https://mcp.jina.example/sse",
            "prefix": "jina.",
            "remote_tool_name": "search",
            "skip_initialize": False,
        })
        inv = ToolInvocation(
            tool=tool,
            arguments={"query": "x"},
            auth=make_auth_ctx(user_id="u"),
            trace_id=uuid4(),
        )
        await adapter.invoke(inv)
    finally:
        await client.aclose()

    # Two requests: initialize, then tools/call with session header.
    assert len(captured) == 2
    assert json.loads(captured[0].content)["method"] == "initialize"
    call_headers = captured[1].headers
    assert call_headers.get("Mcp-Session-Id") == "abc-123"


def test_parse_sse_envelope():
    body = 'event: message\ndata: {"jsonrpc":"2.0","id":"t","result":{}}\n\n'
    payload = _parse_sse_envelope(body)
    assert payload == {"jsonrpc": "2.0", "id": "t", "result": {}}


def test_parse_sse_envelope_rejects_empty():
    with pytest.raises(DispatchError):
        _parse_sse_envelope("event: keepalive\n\n")
