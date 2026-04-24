from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

log = logging.getLogger(__name__)

OnChangeCallback = Callable[[str], Awaitable[None]]

_SSL_TRUTHY = {"true", "1", "yes", "on", "t"}


class PgNotifyListener:
    """Listen to Postgres `LISTEN <channel>` and invoke callback on NOTIFY.

    Uses asyncpg directly (bypassing SQLAlchemy) because `LISTEN` requires a
    dedicated connection that stays open for the lifetime of the listener.
    """

    def __init__(
        self,
        dsn: str,
        channel: str,
        on_change: OnChangeCallback,
        reconnect_delay_sec: float = 2.0,
    ) -> None:
        self._dsn, self._connect_kwargs = _parse_asyncpg_dsn(dsn)
        self._channel = channel
        self._on_change = on_change
        self._reconnect_delay = reconnect_delay_sec
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name=f"pg-listen-{self._channel}")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _run(self) -> None:
        try:
            import asyncpg
        except ImportError:
            log.warning("asyncpg not available; NOTIFY listener disabled")
            return

        while not self._stop.is_set():
            conn = None
            try:
                conn = await asyncpg.connect(self._dsn, **self._connect_kwargs)
                await conn.add_listener(self._channel, self._handle)
                log.info("pg-listen started on %s", self._channel)
                while not self._stop.is_set():
                    await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.warning("pg-listen error on %s: %s", self._channel, exc)
                await asyncio.sleep(self._reconnect_delay)
            finally:
                if conn is not None:
                    try:
                        await conn.close()
                    except Exception:
                        pass

    def _handle(self, _conn: Any, _pid: int, _channel: str, payload: str) -> None:
        try:
            asyncio.create_task(self._on_change(payload or ""))
        except RuntimeError:
            log.warning("pg-notify callback failed (no running loop)")


def _parse_asyncpg_dsn(dsn: str) -> tuple[str, dict[str, Any]]:
    """Convert a SQLAlchemy-style DSN to a raw asyncpg DSN + connect kwargs.

    asyncpg.connect(dsn) does not recognise ``ssl`` as a URL parameter — it
    forwards unknown params as Postgres ``server_settings`` and the server
    rejects ``SET ssl = ...`` with ``parameter "ssl" cannot be changed now``.
    SQLAlchemy's asyncpg dialect would translate ``ssl=`` into the proper
    connect kwarg; the raw path here must do the same.
    """
    if dsn.startswith("postgresql+asyncpg://"):
        dsn = "postgresql://" + dsn[len("postgresql+asyncpg://") :]
    parsed = urlparse(dsn)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    kwargs: dict[str, Any] = {}
    remaining: list[tuple[str, str]] = []
    for key, value in query:
        if key == "ssl":
            kwargs["ssl"] = "require" if value.lower() in _SSL_TRUTHY else value
        else:
            remaining.append((key, value))
    cleaned = urlunparse(parsed._replace(query=urlencode(remaining, doseq=True)))
    return cleaned, kwargs
