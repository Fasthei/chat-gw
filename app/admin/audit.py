from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_role
from app.admin.schemas import AuditItem, AuditResponse, Outcome
from app.db.engine import get_session
from app.db.models import ToolAuditLog


DEFAULT_LIMIT = 50
MAX_LIMIT = 500


def build_audit_router() -> APIRouter:
    router = APIRouter(
        prefix="/admin/audit",
        tags=["admin"],
        dependencies=[Depends(require_role("cloud_admin"))],
    )

    @router.get("", response_model=AuditResponse)
    async def query_audit(
        user_id: str | None = Query(None, description="Exact match on AuthContext.user_id"),
        tool_name: str | None = Query(None, description="Exact match"),
        outcome: Outcome | None = Query(None, alias="outcome"),
        from_: datetime | None = Query(None, alias="from",
                                       description="ISO 8601 inclusive lower bound on started_at"),
        to: datetime | None = Query(None, description="ISO 8601 exclusive upper bound on started_at"),
        trace_id: str | None = Query(None, description="Filter to a single trace_id"),
        cursor: str | None = Query(None, description="Opaque keyset cursor from previous response"),
        limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
        db: AsyncSession = Depends(get_session),
    ) -> AuditResponse:
        stmt = select(ToolAuditLog)

        if user_id:
            stmt = stmt.where(ToolAuditLog.user_id == user_id)
        if tool_name:
            stmt = stmt.where(ToolAuditLog.tool_name == tool_name)
        if outcome:
            stmt = stmt.where(ToolAuditLog.status == outcome)
        if from_:
            stmt = stmt.where(ToolAuditLog.started_at >= _as_utc(from_))
        if to:
            stmt = stmt.where(ToolAuditLog.started_at < _as_utc(to))
        if trace_id:
            stmt = stmt.where(ToolAuditLog.trace_id == trace_id)

        if cursor:
            cursor_at, cursor_id = _decode_cursor(cursor)
            # Keyset: rows strictly "older" than (cursor_at, cursor_id) in
            # (started_at DESC, id DESC) ordering.
            stmt = stmt.where(
                or_(
                    ToolAuditLog.started_at < cursor_at,
                    and_(
                        ToolAuditLog.started_at == cursor_at,
                        ToolAuditLog.id < cursor_id,
                    ),
                )
            )

        stmt = stmt.order_by(
            ToolAuditLog.started_at.desc(), ToolAuditLog.id.desc()
        ).limit(limit + 1)  # fetch one extra to know if there's a next page

        rows = (await db.execute(stmt)).scalars().all()
        has_more = len(rows) > limit
        rows = rows[:limit]

        items = [_row_to_item(r) for r in rows]
        next_cursor = (
            _encode_cursor(rows[-1].started_at, rows[-1].id)
            if has_more and rows
            else None
        )
        return AuditResponse(items=items, next_cursor=next_cursor)

    return router


# ─── helpers ─────────────────────────────────────────────────────────


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _row_to_item(row: ToolAuditLog) -> AuditItem:
    return AuditItem(
        trace_id=str(row.trace_id),
        at=row.started_at,
        user_id=row.user_id,
        user_email=row.user_email,
        roles=list(row.roles or []),
        tool_name=row.tool_name,
        tool_id=row.tool_id,
        outcome=row.status,  # type: ignore[arg-type]
        error_code=row.error_code,
        error_kind=row.error_kind,
        latency_ms=row.latency_ms,
        deny_reason=row.deny_reason,
        error_message=row.error_message,
        sensitive_fields_hit=list(row.sensitive_fields_hit or []),
        arguments=row.arguments if isinstance(row.arguments, dict) else None,
    )


def _encode_cursor(started_at: datetime, row_id: int) -> str:
    payload = json.dumps({"at": _as_utc(started_at).isoformat(), "id": int(row_id)})
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        data: dict[str, Any] = json.loads(raw)
        at = datetime.fromisoformat(data["at"])
        return _as_utc(at), int(data["id"])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid cursor: {exc}",
        ) from exc
