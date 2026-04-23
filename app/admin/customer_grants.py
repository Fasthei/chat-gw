"""Admin CRUD for customer-scoped tool grants.

Mirrors :mod:`app.admin.grants` for the ``tool_customer_grants`` table.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_role
from app.admin.schemas import (
    CustomerGrantPair,
    CustomerGrantPutIn,
    CustomerGrantPutOut,
    CustomerGrantsListResponse,
)
from app.db.engine import get_session
from app.db.models import Tool, ToolCustomerGrant


def build_customer_grants_router() -> APIRouter:
    router = APIRouter(
        prefix="/admin/tool-customer-grants",
        tags=["admin"],
        dependencies=[Depends(require_role("cloud_admin"))],
    )

    @router.get("", response_model=CustomerGrantsListResponse)
    async def list_customer_grants(
        customer_code: str | None = Query(None),
        tool_name: str | None = Query(None),
        db: AsyncSession = Depends(get_session),
    ) -> CustomerGrantsListResponse:
        stmt = (
            select(ToolCustomerGrant.customer_code, Tool.name)
            .join(Tool, Tool.id == ToolCustomerGrant.tool_id)
            .order_by(ToolCustomerGrant.customer_code.asc(), Tool.name.asc())
        )
        if customer_code:
            stmt = stmt.where(ToolCustomerGrant.customer_code == customer_code)
        if tool_name:
            stmt = stmt.where(Tool.name == tool_name)
        rows = (await db.execute(stmt)).all()
        return CustomerGrantsListResponse(
            grants=[CustomerGrantPair(customer_code=c, tool_name=t) for c, t in rows]
        )

    @router.put("", response_model=CustomerGrantPutOut)
    async def put_customer_grant(
        payload: CustomerGrantPutIn,
        request: Request,
        db: AsyncSession = Depends(get_session),
    ) -> CustomerGrantPutOut:
        tool_id = await _resolve_tool_id(db, payload.tool_name)
        if payload.granted:
            stmt = (
                pg_insert(ToolCustomerGrant)
                .values(tool_id=tool_id, customer_code=payload.customer_code)
                .on_conflict_do_nothing(
                    index_elements=[
                        ToolCustomerGrant.tool_id,
                        ToolCustomerGrant.customer_code,
                    ]
                )
            )
            await db.execute(stmt)
        else:
            await db.execute(
                sa_delete(ToolCustomerGrant).where(
                    ToolCustomerGrant.tool_id == tool_id,
                    ToolCustomerGrant.customer_code == payload.customer_code,
                )
            )
        await db.commit()
        await _refresh_registry(request)
        return CustomerGrantPutOut(
            customer_code=payload.customer_code,
            tool_name=payload.tool_name,
            granted=payload.granted,
        )

    @router.delete("", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_customer_grant(
        request: Request,
        customer_code: str = Query(..., description="Customer code to revoke"),
        tool_name: str = Query(..., description="Tool name to revoke from"),
        db: AsyncSession = Depends(get_session),
    ) -> Response:
        tool_id = await _resolve_tool_id(db, tool_name)
        await db.execute(
            sa_delete(ToolCustomerGrant).where(
                ToolCustomerGrant.tool_id == tool_id,
                ToolCustomerGrant.customer_code == customer_code,
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
