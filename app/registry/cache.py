from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from app.db.models import Tool

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolView:
    """Immutable snapshot of a Tool row used by MCP + dispatchers.

    Decouples request-handling from SQLAlchemy session lifetime.
    """

    id: int
    name: str
    display_name: str
    description: str
    category: str | None
    dispatcher: str
    config: dict = field(default_factory=dict)
    auth_mode: str = "service_key"
    secret_env_name: str | None = None
    auth_header: str | None = None
    auth_prefix: str = ""
    input_schema: dict = field(default_factory=dict)
    output_schema: dict | None = None
    roles: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_model(cls, t: Tool) -> "ToolView":
        return cls(
            id=t.id,
            name=t.name,
            display_name=t.display_name,
            description=t.description,
            category=t.category,
            dispatcher=t.dispatcher,
            config=dict(t.config or {}),
            auth_mode=t.auth_mode,
            secret_env_name=t.secret_env_name,
            auth_header=t.auth_header,
            auth_prefix=t.auth_prefix or "",
            input_schema=dict(t.input_schema or {}),
            output_schema=dict(t.output_schema) if t.output_schema else None,
            roles=frozenset(g.role for g in t.grants),
        )


class ToolCache:
    """TTL-bound in-memory snapshot of all enabled tools.

    Eagerly loaded on `refresh()`; read paths never block on DB.
    `listChanged` subscribers notified after each refresh.
    """

    def __init__(self, ttl_sec: int = 30) -> None:
        self._ttl = ttl_sec
        self._tools: list[ToolView] = []
        self._by_name: dict[str, ToolView] = {}
        self._loaded_at: float = 0.0
        self._lock = asyncio.Lock()
        self._subscribers: list[asyncio.Queue[str]] = []

    def is_fresh(self) -> bool:
        return self._tools != [] and (time.monotonic() - self._loaded_at) < self._ttl

    def snapshot(self) -> list[ToolView]:
        return list(self._tools)

    def get(self, name: str) -> ToolView | None:
        return self._by_name.get(name)

    async def ensure_fresh(self, loader) -> None:
        if self.is_fresh():
            return
        async with self._lock:
            if self.is_fresh():
                return
            await self._load(loader)

    async def invalidate_and_reload(self, loader) -> None:
        async with self._lock:
            self._loaded_at = 0.0
            await self._load(loader)
        await self._broadcast("tools_changed")

    def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=16)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    async def _load(self, loader) -> None:
        rows = await loader()
        views = [ToolView.from_model(r) for r in rows]
        self._tools = views
        self._by_name = {v.name: v for v in views}
        self._loaded_at = time.monotonic()
        log.debug("tool cache refreshed: %d tools", len(views))

    async def _broadcast(self, event: str) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                log.warning("subscriber queue full; dropping %s", event)
