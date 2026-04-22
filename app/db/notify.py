from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger(__name__)

OnChangeCallback = Callable[[str], Awaitable[None]]


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
        self._dsn = _sqlalchemy_to_asyncpg(dsn)
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
                conn = await asyncpg.connect(self._dsn)
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


def _sqlalchemy_to_asyncpg(dsn: str) -> str:
    """Convert SQLAlchemy-style DSN (postgresql+asyncpg://...) to raw DSN."""
    if dsn.startswith("postgresql+asyncpg://"):
        return "postgresql://" + dsn[len("postgresql+asyncpg://") :]
    return dsn
