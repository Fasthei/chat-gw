from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_role
from app.admin.schemas import ToolOut, ToolPatchIn, ToolsListResponse, ToolUpsertIn
from app.db.engine import get_session
from app.db.models import Tool


def build_tools_router() -> APIRouter:
    router = APIRouter(
        prefix="/admin/tools",
        tags=["admin"],
        dependencies=[Depends(require_role("cloud_admin"))],
    )

    @router.get("", response_model=ToolsListResponse)
    async def list_tools(
        include_disabled: bool = Query(True, description="Include enabled=false rows"),
        db: AsyncSession = Depends(get_session),
    ) -> ToolsListResponse:
        stmt = select(Tool).order_by(Tool.category.asc().nulls_last(), Tool.name.asc())
        if not include_disabled:
            stmt = stmt.where(Tool.enabled.is_(True))
        rows = (await db.execute(stmt)).scalars().all()
        return ToolsListResponse(tools=[ToolOut.model_validate(r) for r in rows])

    @router.post("", response_model=ToolOut)
    async def upsert_tool(
        payload: ToolUpsertIn,
        request: Request,
        db: AsyncSession = Depends(get_session),
    ) -> ToolOut:
        values = payload.model_dump()
        stmt = pg_insert(Tool).values(**values)
        # ON CONFLICT(name) DO UPDATE — bump version to signal change.
        update_cols: dict[str, Any] = {
            c: stmt.excluded[c]
            for c in (
                "display_name", "description", "category", "dispatcher",
                "config", "auth_mode", "secret_env_name", "auth_header",
                "auth_prefix", "input_schema", "output_schema", "enabled",
            )
        }
        update_cols["version"] = Tool.version + 1
        stmt = stmt.on_conflict_do_update(
            index_elements=[Tool.name], set_=update_cols
        ).returning(Tool)
        result = await db.execute(stmt)
        await db.commit()
        row = result.scalar_one()
        await _refresh_registry(request)
        return ToolOut.model_validate(row)

    @router.patch("/{name}", response_model=ToolOut)
    async def patch_tool(
        name: str,
        payload: ToolPatchIn,
        request: Request,
        db: AsyncSession = Depends(get_session),
    ) -> ToolOut:
        row = (await db.execute(select(Tool).where(Tool.name == name))).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"tool '{name}' not found")
        changed = payload.model_dump(exclude_unset=True)
        if not changed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="no fields to update"
            )
        for key, value in changed.items():
            setattr(row, key, value)
        row.version = (row.version or 1) + 1
        await db.commit()
        await db.refresh(row)
        await _refresh_registry(request)
        return ToolOut.model_validate(row)

    @router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_tool(
        name: str,
        request: Request,
        hard: bool = Query(False, description="true → DELETE row + cascade grants; "
                                              "false (default) → soft disable via enabled=false"),
        db: AsyncSession = Depends(get_session),
    ) -> Response:
        row = (await db.execute(select(Tool).where(Tool.name == name))).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"tool '{name}' not found")
        if hard:
            await db.execute(sa_delete(Tool).where(Tool.id == row.id))
        else:
            row.enabled = False
            row.version = (row.version or 1) + 1
        await db.commit()
        await _refresh_registry(request)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


async def _refresh_registry(request: Request) -> None:
    """Trigger an in-process cache refresh.

    Postgres LISTEN/NOTIFY triggers already fire via the `trg_tools_notify`
    trigger on every INSERT/UPDATE/DELETE, so remote gateway instances pick
    up changes automatically. Refreshing the *current* instance eagerly
    eliminates the 30s stale window for the admin who just made the edit.
    """
    registry = getattr(request.app.state, "tool_registry", None)
    if registry is not None:
        try:
            await registry.force_refresh()
        except Exception:
            # Never fail the admin mutation because of a cache miss.
            pass
