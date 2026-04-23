from __future__ import annotations

import logging
from typing import Any

from fastapi import Request

from app.auth.context import AuthContext
from app.auth.errors import InvalidTokenError, MissingTokenError
from app.auth.jwt_verify import JwtVerifier
from app.auth.roles import RoleResolver
from app.external import Customer, GongdanClient, GongdanUpstreamError

log = logging.getLogger(__name__)


def extract_bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization") or request.headers.get("authorization")
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _extract_customer_code(claims: dict[str, Any], primary_claim: str) -> str | None:
    """Read the customer code from JWT claims.

    Accepts both the configured claim name (``customer_code`` by default) and
    the camelCase ``customerCode`` used by the gongdan API, so LobeChat can
    passthrough whichever shape it prefers.
    """
    for key in (primary_claim, "customerCode", "customer_code"):
        if not key:
            continue
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


async def authenticate(request: Request) -> AuthContext:
    """FastAPI dependency: validate Bearer token and resolve roles + customer."""
    verifier: JwtVerifier = request.app.state.jwt_verifier
    resolver: RoleResolver = request.app.state.role_resolver

    token = extract_bearer(request)
    if not token:
        raise MissingTokenError("missing Bearer token")

    claims = await verifier.verify(token)
    user_id = str(claims.get("sub") or "")
    if not user_id:
        raise InvalidTokenError("token missing 'sub'")

    roles = await resolver.resolve(user_id, claims, raw_token=token)

    customer_code: str | None = None
    customer: Customer | None = None
    gongdan: GongdanClient | None = getattr(
        request.app.state, "gongdan_client", None
    )
    primary_claim = getattr(
        request.app.state, "gongdan_customer_claim", "customer_code"
    )
    raw_code = _extract_customer_code(claims, primary_claim)
    if raw_code:
        if gongdan is None or not gongdan.configured():
            log.warning(
                "JWT carried %s=%s but gongdan client is not configured; "
                "refusing to fabricate identity",
                primary_claim,
                raw_code,
            )
            raise InvalidTokenError("customer_code present but gongdan is not configured")
        try:
            customer = await gongdan.get_by_code(raw_code)
        except GongdanUpstreamError as exc:
            log.warning("gongdan upstream error resolving %s: %s", raw_code, exc)
            raise InvalidTokenError(f"gongdan upstream error: {exc}") from exc
        if customer is None:
            raise InvalidTokenError(f"unknown customer_code: {raw_code}")
        customer_code = customer.customer_code or raw_code

    return AuthContext(
        user_id=user_id,
        roles=roles,
        raw_token=token,
        email=claims.get("email"),
        name=claims.get("name"),
        customer_code=customer_code,
        customer_id=customer.id if customer else None,
        customer_tier=customer.tier if customer else None,
        customer_queue_type=customer.queue_type if customer else None,
        claims=claims,
    )
