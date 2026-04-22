from __future__ import annotations

import logging

from fastapi import Request

from app.auth.context import AuthContext
from app.auth.errors import InvalidTokenError, MissingTokenError
from app.auth.jwt_verify import JwtVerifier
from app.auth.roles import RoleResolver

log = logging.getLogger(__name__)


def extract_bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization") or request.headers.get("authorization")
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


async def authenticate(request: Request) -> AuthContext:
    """FastAPI dependency: validate Bearer token and resolve roles."""
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

    return AuthContext(
        user_id=user_id,
        roles=roles,
        raw_token=token,
        email=claims.get("email"),
        name=claims.get("name"),
        claims=claims,
    )
