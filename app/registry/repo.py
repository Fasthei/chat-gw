from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Tool


async def fetch_all_enabled_tools(db: AsyncSession) -> list[Tool]:
    """Fetch all enabled tools with role + customer grants eager-loaded."""
    stmt = (
        select(Tool)
        .where(Tool.enabled.is_(True))
        .options(
            selectinload(Tool.grants),
            selectinload(Tool.customer_grants),
        )
        .order_by(Tool.name)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
