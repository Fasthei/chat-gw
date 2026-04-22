from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)


class JwksCache:
    """In-memory JWKS cache keyed by `kid`.

    Refresh semantics:
      * first access → fetch and cache all keys
      * `get(kid)` miss → force refresh once (cooldown-bound), then fetch again
      * TTL expiry → lazy refresh on next access
    """

    def __init__(
        self,
        jwks_url: str,
        cache_ttl_sec: int = 3600,
        refresh_cooldown_sec: int = 30,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = jwks_url
        self._ttl = cache_ttl_sec
        self._cooldown = refresh_cooldown_sec
        self._client = http_client
        self._owns_client = http_client is None
        self._keys: dict[str, dict[str, Any]] = {}
        self._fetched_at: float = 0.0
        self._last_refresh_attempt: float = 0.0
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(self, kid: str) -> dict[str, Any]:
        """Return JWK matching `kid`; refresh once on miss within cooldown."""
        now = time.monotonic()
        if not self._keys or (now - self._fetched_at) > self._ttl:
            await self._refresh()
        if kid in self._keys:
            return self._keys[kid]
        if (now - self._last_refresh_attempt) > self._cooldown:
            await self._refresh()
        if kid not in self._keys:
            raise KeyError(f"JWKS: kid '{kid}' not found")
        return self._keys[kid]

    async def _refresh(self) -> None:
        async with self._lock:
            self._last_refresh_attempt = time.monotonic()
            client = self._client or httpx.AsyncClient(timeout=10.0)
            owns_temp = self._client is None
            try:
                resp = await client.get(self._url)
                resp.raise_for_status()
                body = resp.json()
            except Exception as exc:
                log.warning("jwks refresh failed: %s", exc)
                if owns_temp:
                    await client.aclose()
                return
            if owns_temp:
                await client.aclose()

            keys: dict[str, dict[str, Any]] = {}
            for entry in body.get("keys", []):
                kid = entry.get("kid")
                if kid:
                    keys[kid] = entry
            if keys:
                self._keys = keys
                self._fetched_at = time.monotonic()
                log.info("jwks refreshed: %d keys", len(keys))
