from __future__ import annotations

import logging

from app.db.engine import async_session
from app.registry.cache import ToolCache, ToolView
from app.registry.repo import fetch_all_enabled_tools

log = logging.getLogger(__name__)


class ToolRegistry:
    """Read-side façade: principal-filtered listing + authorization lookup.

    Authorization is the OR of two independent grant channels:

    * ``roles`` — enterprise RBAC (``tool_role_grants``).
    * ``customer_code`` — per-customer grants (``tool_customer_grants``),
      populated from LobeChat clients whose JWT carries a ``customer_code``
      resolved against the gongdan ticket system.

    A tool is visible to a principal when *either* channel matches. The
    legacy ``list_for_roles``/``find_authorized`` methods are preserved for
    existing call sites and simply delegate with ``customer_code=None``.
    """

    def __init__(self, cache: ToolCache) -> None:
        self._cache = cache

    async def refresh_if_stale(self) -> None:
        await self._cache.ensure_fresh(self._load)

    async def force_refresh(self) -> None:
        await self._cache.invalidate_and_reload(self._load)

    async def list_for_principal(
        self,
        roles: list[str] | None,
        customer_code: str | None,
    ) -> list[ToolView]:
        await self.refresh_if_stale()
        role_set = set(roles or [])
        code = customer_code or None
        if not role_set and not code:
            return []
        return [
            t
            for t in self._cache.snapshot()
            if (role_set and (t.roles & role_set))
            or (code is not None and code in t.customer_codes)
        ]

    async def find_authorized_for_principal(
        self,
        name: str,
        roles: list[str] | None,
        customer_code: str | None,
    ) -> ToolView | None:
        await self.refresh_if_stale()
        role_set = set(roles or [])
        code = customer_code or None
        if not role_set and not code:
            return None
        view = self._cache.get(name)
        if view is None:
            return None
        role_hit = bool(role_set and (view.roles & role_set))
        code_hit = code is not None and code in view.customer_codes
        if not (role_hit or code_hit):
            return None
        return view

    # ─── Legacy shims (role-only) ────────────────────────────────────
    async def list_for_roles(self, roles: list[str] | None) -> list[ToolView]:
        return await self.list_for_principal(roles, customer_code=None)

    async def find_authorized(
        self, name: str, roles: list[str] | None
    ) -> ToolView | None:
        return await self.find_authorized_for_principal(
            name, roles, customer_code=None
        )

    def subscribe(self):
        return self._cache.subscribe()

    def unsubscribe(self, q) -> None:
        self._cache.unsubscribe(q)

    async def _load(self):
        async with async_session() as db:
            return await fetch_all_enabled_tools(db)
