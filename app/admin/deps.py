from __future__ import annotations

from fastapi import Depends, HTTPException, status

from app.auth import AuthContext, authenticate


def require_role(role: str):
    """FastAPI dependency: pass only when `role` is in the caller's roles.

    Reuses the same `authenticate` stack as /mcp (Casdoor JWT verify +
    RoleResolver), adding a 403 gate for admin-only surfaces. `cloud_admin`
    is the spec's superuser role (AI-BRAIN-API §1.2) and the only role that
    satisfies this guard by default.
    """

    async def _check(ctx: AuthContext = Depends(authenticate)) -> AuthContext:
        if role not in ctx.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role '{role}' required",
            )
        return ctx

    return _check
