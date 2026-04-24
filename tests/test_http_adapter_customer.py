"""Regression tests for the customer_code → X-Customer-Code forwarding.

Context: we had a data-越权 bug where a customer authenticated via
``/api/auth/customer-login`` could invoke ``ticket.list`` through
chat-gw; the tool uses ``service_key`` auth (``X-Api-Key``) and used to
drop the caller's ``customer_code`` entirely, so gongdan treated the
request as ADMIN and returned every ticket in the system.

The fix: when ``inv.auth.customer_code`` is populated, GenericHttpAdapter
now attaches an ``X-Customer-Code`` header to the outgoing request so
gongdan can re-scope the query. These tests pin that behaviour.
"""
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.dispatchers.base import ToolInvocation
from app.dispatchers.http_adapter import GenericHttpAdapter
from tests.factories import make_auth_ctx, make_tool_view


def _adapter_with_mock(responses):
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return responses.pop(0)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = GenericHttpAdapter(
        client=client,
        default_timeout_sec=5.0,
        default_retries=0,
        retry_backoff_base_sec=0.001,
    )
    return adapter, client, captured


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("GONGDAN_API_BASE", "https://tickets.test")
    monkeypatch.setenv("GONGDAN_API_KEY", "gd_live_xxx")
    yield monkeypatch


def _ticket_list_tool():
    return make_tool_view(
        name="ticket.list",
        config={
            "base_url_env": "GONGDAN_API_BASE",
            "path": "/api/tickets",
            "method": "GET",
        },
        auth_header="X-Api-Key",
        secret_env_name="GONGDAN_API_KEY",
        auth_mode="service_key",
        auth_prefix="",
    )


@pytest.mark.asyncio
async def test_customer_code_is_forwarded_as_header(env):
    adapter, client, captured = _adapter_with_mock([httpx.Response(200, text="[]")])
    try:
        inv = ToolInvocation(
            tool=_ticket_list_tool(),
            arguments={},
            auth=make_auth_ctx(
                user_id="customer-user-1",
                roles=["CUSTOMER"],
                customer_code="CUST-C5265489",
            ),
            trace_id=uuid4(),
        )
        await adapter.invoke(inv)
    finally:
        await client.aclose()

    req = captured[0]
    assert req.headers.get("X-Customer-Code") == "CUST-C5265489"
    # service_key auth still intact — we did not disturb it.
    assert req.headers.get("X-Api-Key") == "gd_live_xxx"


@pytest.mark.asyncio
async def test_no_customer_code_means_no_header(env):
    """Employee / internal path: header must be absent, not empty."""
    adapter, client, captured = _adapter_with_mock([httpx.Response(200, text="[]")])
    try:
        inv = ToolInvocation(
            tool=_ticket_list_tool(),
            arguments={},
            auth=make_auth_ctx(user_id="alice", roles=["cloud_admin"]),
            trace_id=uuid4(),
        )
        await adapter.invoke(inv)
    finally:
        await client.aclose()

    req = captured[0]
    assert "X-Customer-Code" not in req.headers
    assert req.headers.get("X-Api-Key") == "gd_live_xxx"


@pytest.mark.asyncio
async def test_empty_customer_code_is_treated_as_absent(env):
    """A falsy customer_code must not turn into ``X-Customer-Code: ``."""
    adapter, client, captured = _adapter_with_mock([httpx.Response(200, text="[]")])
    try:
        inv = ToolInvocation(
            tool=_ticket_list_tool(),
            arguments={},
            auth=make_auth_ctx(
                user_id="edge-case",
                roles=["CUSTOMER"],
                customer_code="",
            ),
            trace_id=uuid4(),
        )
        await adapter.invoke(inv)
    finally:
        await client.aclose()

    req = captured[0]
    assert "X-Customer-Code" not in req.headers
