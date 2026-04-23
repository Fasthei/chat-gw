from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import AuthContext
from app.db.models import ToolAuditLog

log = logging.getLogger(__name__)

AuditStatus = Literal["allowed", "denied", "error", "ok"]


async def write_audit(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    trace_id: UUID,
    ctx: AuthContext,
    tool_name: str,
    arguments: Any,
    status: AuditStatus,
    tool_id: int | None = None,
    sensitive_fields_hit: list[str] | None = None,
    deny_reason: str | None = None,
    error_message: str | None = None,
    error_code: int | None = None,
    error_kind: str | None = None,
    latency_ms: int | None = None,
    started_at: datetime | None = None,
) -> None:
    """Insert a single audit row.

    Never raises — audit failures are logged and swallowed so a logging
    outage can't take down request handling.
    """
    now = datetime.now(timezone.utc)
    entry = ToolAuditLog(
        trace_id=trace_id,
        user_id=ctx.user_id,
        user_email=ctx.email,
        roles=list(ctx.roles),
        tool_name=tool_name,
        tool_id=tool_id,
        arguments=arguments if isinstance(arguments, dict) or arguments is None else {"_raw": arguments},
        sensitive_fields_hit=sensitive_fields_hit or [],
        status=status,
        deny_reason=deny_reason,
        error_message=error_message,
        error_code=error_code,
        error_kind=error_kind,
        latency_ms=latency_ms,
        started_at=started_at or now,
        finished_at=now,
    )
    try:
        async with session_factory() as db:
            db.add(entry)
            await db.commit()
    except Exception as exc:
        log.error("audit write failed: %s (tool=%s status=%s)", exc, tool_name, status)


class AuditWriter:
    """Request-scoped audit helper bound to one session factory."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def log(
        self,
        *,
        trace_id: UUID,
        ctx: AuthContext,
        tool_name: str,
        arguments: Any,
        status: AuditStatus,
        tool_id: int | None = None,
        sensitive_fields_hit: list[str] | None = None,
        deny_reason: str | None = None,
        error_message: str | None = None,
        error_code: int | None = None,
        error_kind: str | None = None,
        latency_ms: int | None = None,
        started_at: datetime | None = None,
    ) -> None:
        await write_audit(
            self._session_factory,
            trace_id=trace_id,
            ctx=ctx,
            tool_name=tool_name,
            arguments=arguments,
            status=status,
            tool_id=tool_id,
            sensitive_fields_hit=sensitive_fields_hit,
            deny_reason=deny_reason,
            error_message=error_message,
            error_code=error_code,
            error_kind=error_kind,
            latency_ms=latency_ms,
            started_at=started_at,
        )
