from __future__ import annotations

import logging

from app.db.engine import async_session
from app.registry.cache import ToolCache, ToolView
from app.registry.repo import fetch_all_enabled_tools

log = logging.getLogger(__name__)


class ToolRegistry:
    """Read-side façade: role-filtered listing + authorization lookup."""

    def __init__(self, cache: ToolCache) -> None:
        self._cache = cache

    async def refresh_if_stale(self) -> None:
        await self._cache.ensure_fresh(self._load)

    async def force_refresh(self) -> None:
        await self._cache.invalidate_and_reload(self._load)

    async def list_for_roles(self, roles: list[str] | None) -> list[ToolView]:
        await self.refresh_if_stale()
        if not roles:
            return []
        allowed = set(roles)
        return [t for t in self._cache.snapshot() if t.roles & allowed]

    async def find_authorized(self, name: str, roles: list[str] | None) -> ToolView | None:
        await self.refresh_if_stale()
        if not roles:
            return None
        view = self._cache.get(name)
        if view is None:
            return None
        if not (view.roles & set(roles)):
            return None
        return view

    def subscribe(self):
        return self._cache.subscribe()

    def unsubscribe(self, q) -> None:
        self._cache.unsubscribe(q)

    async def _load(self):
        async with async_session() as db:
            return await fetch_all_enabled_tools(db)
