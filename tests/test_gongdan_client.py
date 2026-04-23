"""Unit tests for :mod:`app.external.gongdan`."""
from __future__ import annotations

import httpx
import pytest

from app.external.gongdan import (
    Customer,
    GongdanClient,
    GongdanUpstreamError,
)


pytestmark = pytest.mark.asyncio


def _client_with(handler) -> GongdanClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return GongdanClient(
        base_url="https://gongdan.test",
        api_key="gd_live_test",
        client=http,
    )


async def test_configured_requires_base_and_key() -> None:
    c = GongdanClient(base_url=None, api_key=None)
    assert c.configured() is False
    await c.close()


async def test_get_by_id_ok() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["X-Api-Key"] == "gd_live_test"
        assert req.url.path == "/api/customers/abc-123"
        return httpx.Response(
            200,
            json={
                "id": "abc-123",
                "customerCode": "CUST-AAA",
                "name": "Alpha",
                "tier": "NORMAL",
                "queueType": "PUBLIC",
                "boundEngineerId": None,
            },
        )

    c = _client_with(handler)
    cust = await c.get_by_id("abc-123")
    await c.close()
    assert cust == Customer(
        id="abc-123",
        customer_code="CUST-AAA",
        name="Alpha",
        tier="NORMAL",
        queue_type="PUBLIC",
        bound_engineer_id=None,
    )


async def test_get_by_id_404_returns_none() -> None:
    c = _client_with(lambda req: httpx.Response(404, json={"error": "not found"}))
    assert await c.get_by_id("missing") is None
    await c.close()


async def test_get_by_code_matches_list() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/customers"
        return httpx.Response(
            200,
            json=[
                {"id": "1", "customerCode": "CUST-AAA", "name": "Alpha"},
                {"id": "2", "customerCode": "CUST-BBB", "name": "Beta"},
            ],
        )

    c = _client_with(handler)
    cust = await c.get_by_code("CUST-BBB")
    await c.close()
    assert cust is not None
    assert cust.id == "2"
    assert cust.customer_code == "CUST-BBB"


async def test_get_by_code_unknown_returns_none() -> None:
    c = _client_with(
        lambda req: httpx.Response(
            200,
            json=[{"id": "1", "customerCode": "CUST-AAA", "name": "A"}],
        )
    )
    assert await c.get_by_code("CUST-XXX") is None
    await c.close()


async def test_get_by_code_upstream_error_raises() -> None:
    c = _client_with(lambda req: httpx.Response(502, text="upstream down"))
    with pytest.raises(GongdanUpstreamError):
        await c.get_by_code("CUST-AAA")
    await c.close()


async def test_get_by_code_unconfigured_returns_none() -> None:
    c = GongdanClient(base_url="", api_key="")
    assert await c.get_by_code("CUST-AAA") is None
    await c.close()


async def test_get_by_code_empty_input() -> None:
    c = _client_with(lambda req: httpx.Response(200, json=[]))
    assert await c.get_by_code("") is None
    await c.close()
