from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_role
from app.admin.schemas import GrantPair, GrantPutIn, GrantPutOut, GrantsListResponse
from app.db.engine import get_session
from app.db.models import Tool, ToolRoleGrant


def build_grants_router() -> APIRouter:
    router = APIRouter(
        prefix="/admin/tool-role-grants",
        tags=["admin"],
        dependencies=[Depends(require_role("cloud_admin"))],
    )

    @router.get("", response_model=GrantsListResponse)
    async def list_grants(
        role: str | None = Query(None),
        tool_name: str | None = Query(None),
        db: AsyncSession = Depends(get_session),
    ) -> GrantsListResponse:
        stmt = (
            select(ToolRoleGrant.role, Tool.name)
            .join(Tool, Tool.id == ToolRoleGrant.tool_id)
            .order_by(ToolRoleGrant.role.asc(), Tool.name.asc())
        )
        if role:
            stmt = stmt.where(ToolRoleGrant.role == role)
        if tool_name:
            stmt = stmt.where(Tool.name == tool_name)
        rows = (await db.execute(stmt)).all()
        return GrantsListResponse(
            grants=[GrantPair(role=r, tool_name=t) for r, t in rows]
        )

    @router.put("", response_model=GrantPutOut)
    async def put_grant(
        payload: GrantPutIn,
        request: Request,
        db: AsyncSession = Depends(get_session),
    ) -> GrantPutOut:
        tool_id = await _resolve_tool_id(db, payload.tool_name)
        if payload.granted:
            stmt = (
                pg_insert(ToolRoleGrant)
                .values(tool_id=tool_id, role=payload.role)
                .on_conflict_do_nothing(index_elements=[ToolRoleGrant.tool_id, ToolRoleGrant.role])
            )
            await db.execute(stmt)
        else:
            await db.execute(
                sa_delete(ToolRoleGrant).where(
                    ToolRoleGrant.tool_id == tool_id,
                    ToolRoleGrant.role == payload.role,
                )
            )
        await db.commit()
        await _refresh_registry(request)
        return GrantPutOut(role=payload.role, tool_name=payload.tool_name, granted=payload.granted)

    @router.delete("", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_grant(
        request: Request,
        role: str = Query(..., description="Role to revoke"),
        tool_name: str = Query(..., description="Tool name to revoke from"),
        db: AsyncSession = Depends(get_session),
    ) -> Response:
        tool_id = await _resolve_tool_id(db, tool_name)
        await db.execute(
            sa_delete(ToolRoleGrant).where(
                ToolRoleGrant.tool_id == tool_id,
                ToolRoleGrant.role == role,
            )
        )
        await db.commit()
        await _refresh_registry(request)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


async def _resolve_tool_id(db: AsyncSession, tool_name: str) -> int:
    row = (
        await db.execute(select(Tool.id).where(Tool.name == tool_name))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"tool '{tool_name}' not found",
        )
    return row


async def _refresh_registry(request: Request) -> None:
    registry = getattr(request.app.state, "tool_registry", None)
    if registry is not None:
        try:
            await registry.force_refresh()
        except Exception:
            pass
