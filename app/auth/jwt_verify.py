from __future__ import annotations

import logging
from typing import Any

from jose import JWTError, jwt

from app.auth.errors import InvalidTokenError
from app.auth.jwks import JwksCache
from app.settings import Settings

log = logging.getLogger(__name__)


class JwtVerifier:
    """Verify Bearer JWT in dev (HS256) or prod (RS256 via JWKS).

    A separate symmetric-HS256 path handles JWTs issued by the gongdan
    ticket system's ``/auth/customer-login`` endpoint. Customers have no
    Casdoor account, so their tokens are signed by gongdan with
    ``JWT_SECRET`` and carry ``role: 'CUSTOMER'`` but no ``aud``/``iss``.
    We peek at the unverified ``role`` claim to route, then verify the
    signature against ``GONGDAN_JWT_SECRET`` with aud/iss checks disabled.
    Routing on an unverified claim is safe because the actual signature
    check happens after routing — forging the ``role`` value just picks
    which key-store to verify against, not whether the token is trusted.
    """

    def __init__(self, settings: Settings, jwks: JwksCache | None = None) -> None:
        self._settings = settings
        self._jwks = jwks
        self._mode = settings.jwt_mode()

    async def verify(self, token: str) -> dict[str, Any]:
        try:
            if self._looks_like_gongdan_customer(token):
                return self._verify_gongdan(token)
            if self._mode == "dev":
                return self._verify_hs256(token)
            return await self._verify_rs256(token)
        except JWTError as exc:
            raise InvalidTokenError(f"jwt verify failed: {exc}") from exc

    def _looks_like_gongdan_customer(self, token: str) -> bool:
        if not self._settings.gongdan_jwt_secret:
            return False
        try:
            unverified = jwt.get_unverified_claims(token)
        except JWTError:
            return False
        role = unverified.get("role")
        target = self._settings.gongdan_customer_role_value
        return isinstance(role, str) and role == target

    def _verify_gongdan(self, token: str) -> dict[str, Any]:
        secret = self._settings.gongdan_jwt_secret or ""
        algorithm = self._settings.gongdan_jwt_algorithm or "HS256"
        # Gongdan signs with no aud/iss; don't enforce ours here.
        options = {
            "leeway": self._settings.jwt_leeway_sec,
            "verify_aud": False,
            "verify_iss": False,
        }
        claims = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            options=options,
        )
        role = claims.get("role")
        if role != self._settings.gongdan_customer_role_value:
            # Defence in depth: only accept customer tokens via this path.
            raise InvalidTokenError("gongdan token role mismatch")
        return claims

    def _verify_hs256(self, token: str) -> dict[str, Any]:
        options = _verify_options(self._settings)
        return jwt.decode(
            token,
            self._settings.jwt_dev_secret or "",
            algorithms=[self._settings.jwt_dev_algorithm],
            audience=self._settings.jwt_audience or None,
            issuer=self._settings.jwt_issuer or None,
            options=options,
        )

    async def _verify_rs256(self, token: str) -> dict[str, Any]:
        if self._jwks is None:
            raise InvalidTokenError("jwks cache not configured in prod mode")
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            raise InvalidTokenError("jwt header missing 'kid'")
        try:
            key = await self._jwks.get(kid)
        except KeyError as exc:
            raise InvalidTokenError(str(exc)) from exc
        options = _verify_options(self._settings)
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=self._settings.jwt_audience or None,
            issuer=self._settings.jwt_issuer or None,
            options=options,
        )


def _verify_options(settings: Settings) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "leeway": settings.jwt_leeway_sec,
    }
    if not settings.jwt_audience:
        opts["verify_aud"] = False
    if not settings.jwt_issuer:
        opts["verify_iss"] = False
    return opts
