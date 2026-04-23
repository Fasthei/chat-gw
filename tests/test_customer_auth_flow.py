"""End-to-end auth dependency test for gongdan-signed customer tokens."""
from __future__ import annotations

import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi import Request
from jose import jwt

from app.auth.dependency import authenticate
from app.auth.errors import InvalidTokenError
from app.auth.jwt_verify import JwtVerifier
from app.auth.roles import RoleResolver
from app.external.gongdan import GongdanClient
from app.settings import Settings
from tests.conftest import DEV_SECRET


GONGDAN_SECRET = "gongdan-flow-secret-abcdefghijklmnop"
CUSTOMER_UUID = "11111111-2222-3333-4444-555555555555"
CUSTOMER_CODE = "CUST-ABCDEF"


pytestmark = pytest.mark.asyncio


def _sign_customer_token(
    *,
    sub: str = CUSTOMER_UUID,
    customer_id: str | None = CUSTOMER_UUID,
    secret: str = GONGDAN_SECRET,
) -> str:
    payload = {
        "sub": sub,
        "role": "CUSTOMER",
        "iat": int(time.time()),
        "exp": int(time.time()) + 900,
    }
    if customer_id is not None:
        payload["customerId"] = customer_id
    return jwt.encode(payload, secret, algorithm="HS256")


def _build_gongdan_client(handler) -> GongdanClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return GongdanClient(
        base_url="https://gongdan.test",
        api_key="gd_live_test",
        client=http,
    )


def _build_request(token: str, *, settings: Settings, gongdan: GongdanClient) -> Request:
    verifier = JwtVerifier(settings)
    # RoleResolver must be present but should NOT be called for customer tokens.
    # A stub that raises makes the test fail loudly if the branch slips.
    class ExplodingResolver:
        async def resolve(self, *a, **kw):  # pragma: no cover - defensive
            raise AssertionError("RoleResolver must not be invoked for customer tokens")

    app_state = SimpleNamespace(
        jwt_verifier=verifier,
        role_resolver=ExplodingResolver(),
        gongdan_client=gongdan,
        gongdan_customer_claim="customer_code",
    )
    app = SimpleNamespace(state=app_state)
    scope = {
        "type": "http",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
        "app": app,
    }
    return Request(scope)


async def test_customer_token_resolves_to_customer_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/api/customers/{CUSTOMER_UUID}"
        assert request.headers.get("X-Api-Key") == "gd_live_test"
        return httpx.Response(
            200,
            json={
                "id": CUSTOMER_UUID,
                "customerCode": CUSTOMER_CODE,
                "name": "Acme",
                "tier": "GOLD",
                "queueType": "VIP",
                "boundEngineerId": None,
            },
        )

    gongdan = _build_gongdan_client(handler)
    try:
        settings = Settings(
            jwt_dev_secret=DEV_SECRET,
            jwt_audience="chat-gw",
            jwt_issuer="",
            gongdan_jwt_secret=GONGDAN_SECRET,
        )
        req = _build_request(_sign_customer_token(), settings=settings, gongdan=gongdan)
        ctx = await authenticate(req)
        assert ctx.user_id == CUSTOMER_UUID
        assert ctx.roles == []
        assert ctx.customer_code == CUSTOMER_CODE
        assert ctx.customer_id == CUSTOMER_UUID
        assert ctx.customer_tier == "GOLD"
    finally:
        await gongdan.close()


async def test_customer_token_unknown_customer_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    gongdan = _build_gongdan_client(handler)
    try:
        settings = Settings(
            jwt_dev_secret=DEV_SECRET,
            jwt_audience="chat-gw",
            jwt_issuer="",
            gongdan_jwt_secret=GONGDAN_SECRET,
        )
        req = _build_request(_sign_customer_token(), settings=settings, gongdan=gongdan)
        with pytest.raises(InvalidTokenError):
            await authenticate(req)
    finally:
        await gongdan.close()


async def test_customer_token_bad_signature_rejected() -> None:
    gongdan = _build_gongdan_client(lambda r: httpx.Response(500))
    try:
        settings = Settings(
            jwt_dev_secret=DEV_SECRET,
            jwt_audience="chat-gw",
            jwt_issuer="",
            gongdan_jwt_secret=GONGDAN_SECRET,
        )
        bad = _sign_customer_token(secret="forged-secret-xxxxxxxxxxxxxxxxxx")
        req = _build_request(bad, settings=settings, gongdan=gongdan)
        with pytest.raises(InvalidTokenError):
            await authenticate(req)
    finally:
        await gongdan.close()


async def test_customer_token_refused_when_gongdan_unconfigured() -> None:
    settings = Settings(
        jwt_dev_secret=DEV_SECRET,
        jwt_audience="chat-gw",
        jwt_issuer="",
        gongdan_jwt_secret=GONGDAN_SECRET,
    )
    unconfigured = GongdanClient(base_url=None, api_key=None)
    try:
        req = _build_request(
            _sign_customer_token(), settings=settings, gongdan=unconfigured
        )
        with pytest.raises(InvalidTokenError):
            await authenticate(req)
    finally:
        await unconfigured.close()
