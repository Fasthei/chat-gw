"""GenericHttpAdapter must serialize list-valued query params as repeated keys.

This is the `account_ids=1&account_ids=2&products=a&products=b` contract that
CloudCost's v1.1 metering endpoints rely on.
"""
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.dispatchers.base import ToolInvocation
from app.dispatchers.http_adapter import GenericHttpAdapter, map_params
from tests.factories import make_auth_ctx, make_tool_view


def test_map_params_keeps_list_value_for_query():
    r = map_params(
        arguments={"account_ids": [1, 2], "products": ["gpt-4o", "claude"]},
        path_template="/api/metering/summary",
        param_map={"account_ids": "query", "products": "query"},
        method="GET",
    )
    assert r["query"] == {"account_ids": [1, 2], "products": ["gpt-4o", "claude"]}


@pytest.mark.asyncio
async def test_adapter_emits_repeated_query_keys(monkeypatch):
    monkeypatch.setenv("CLOUDCOST_API_BASE", "https://cloudcost.test")

    captured: list[httpx.Request] = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, text="[]", headers={"content-type": "application/json"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        adapter = GenericHttpAdapter(client=client, default_timeout_sec=5)
        tool = make_tool_view(
            name="cloud_cost.metering_summary",
            auth_mode="user_passthrough",
            secret_env_name=None,
            auth_header="Authorization",
            auth_prefix="Bearer ",
            input_schema={"type": "object"},
            roles=frozenset({"cloud_admin"}),
            config={
                "base_url_env": "CLOUDCOST_API_BASE",
                "method": "GET",
                "path": "/api/metering/summary",
                "param_map": {"account_ids": "query", "products": "query",
                              "provider": "query"},
                "retries": 0,
            },
        )
        inv = ToolInvocation(
            tool=tool,
            arguments={"account_ids": [1, 2, 3], "products": ["gpt-4o", "claude"],
                       "provider": "aws"},
            auth=make_auth_ctx(token="user-raw-jwt"),
            trace_id=uuid4(),
        )
        await adapter.invoke(inv)
    finally:
        await client.aclose()

    assert len(captured) == 1
    req = captured[0]
    # httpx URL preserves repeated keys when params value is a list.
    raw = str(req.url)
    assert raw.count("account_ids=") == 3, raw
    assert "account_ids=1" in raw and "account_ids=2" in raw and "account_ids=3" in raw
    assert raw.count("products=") == 2
    assert "products=gpt-4o" in raw and "products=claude" in raw
    assert "provider=aws" in raw
    # user_passthrough bearer propagates.
    assert req.headers["Authorization"] == "Bearer user-raw-jwt"
