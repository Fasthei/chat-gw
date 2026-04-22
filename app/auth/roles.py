from __future__ import annotations

import json
import logging
from typing import Any

from app.auth.casdoor import CasdoorClient

log = logging.getLogger(__name__)

RedisLike = Any  # redis.asyncio.Redis | None


class RoleResolver:
    """Resolve roles for a user with Redis caching and optional Casdoor fallback.

    Resolution order:
      1. Token `claims[roles_claim]` when present
      2. Redis GET `roles:<user_id>` (60s TTL) when token claim is empty
      3. Casdoor `/api/get-account` (when roles empty & client configured)

    JWT roles are authoritative for the current request. The Redis cache is a
    fallback for tokens that do not carry roles, not an override for fresh
    token claims.
    """

    def __init__(
        self,
        roles_claim: str,
        redis: RedisLike | None,
        casdoor: CasdoorClient | None,
        ttl_sec: int = 60,
    ) -> None:
        self._claim = roles_claim
        self._redis = redis
        self._casdoor = casdoor
        self._ttl = ttl_sec

    async def resolve(
        self,
        user_id: str,
        claims: dict[str, Any],
        raw_token: str | None = None,
    ) -> list[str]:
        claim_roles = _normalize(claims.get(self._claim))
        if claim_roles:
            await self._cache_set(user_id, claim_roles)
            return claim_roles

        cached = await self._cache_get(user_id)
        if cached is not None:
            return cached

        roles: list[str] = []
        if self._casdoor is not None and self._casdoor.configured():
            roles = await self._casdoor.get_user_roles(user_id, bearer_token=raw_token)

        await self._cache_set(user_id, roles)
        return roles

    async def invalidate(self, user_id: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.delete(f"roles:{user_id}")
        except Exception as exc:
            log.warning("redis DEL roles:%s failed: %s", user_id, exc)

    async def _cache_get(self, user_id: str) -> list[str] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(f"roles:{user_id}")
        except Exception as exc:
            log.warning("redis GET roles:%s failed: %s", user_id, exc)
            return None
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return _normalize(json.loads(raw))
        except ValueError:
            return None

    async def _cache_set(self, user_id: str, roles: list[str]) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.setex(f"roles:{user_id}", self._ttl, json.dumps(roles))
        except Exception as exc:
            log.warning("redis SETEX roles:%s failed: %s", user_id, exc)


def _normalize(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("displayName")
                if name:
                    out.append(str(name))
        return out
    return []
