from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db.engine import async_session
from app.settings import settings, validate_production_settings, validate_tool_configs


def build_health_router() -> APIRouter:
    router = APIRouter()

    @router.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @router.get("/readyz")
    async def readyz(request: Request):
        checks: dict[str, object] = {}

        # Postgres
        try:
            async with async_session() as db:
                await db.execute(text("SELECT 1"))
            checks["postgres"] = "ok"
        except Exception as exc:
            checks["postgres"] = f"error: {exc}"

        # Redis
        redis_client = getattr(request.app.state, "redis", None)
        if redis_client is not None:
            try:
                await redis_client.ping()
                checks["redis"] = "ok"
            except Exception as exc:
                checks["redis"] = f"error: {exc}"
        else:
            checks["redis"] = "error: not initialized"

        # JWKS (prod only): report cache state.
        jwks = getattr(request.app.state, "jwks_cache", None)
        if jwks is None:
            checks["jwks"] = "n/a" if not settings.is_production() else "error: not configured"
        else:
            keys = getattr(jwks, "_keys", {}) or {}
            checks["jwks"] = "ok" if keys else "error: no keys cached"

        # Production-specific env checks.
        if settings.is_production():
            prod_checks = validate_production_settings(settings)
            checks["production_env"] = [c.to_dict() | {"name": c.name} for c in prod_checks]

        # Tool config scan (uses ToolRegistry snapshot).
        registry = getattr(request.app.state, "tool_registry", None)
        if registry is not None:
            try:
                await registry.refresh_if_stale()
                tool_views = registry._cache.snapshot()
                tool_results = validate_tool_configs(
                    tool_views, strict=settings.is_production()
                )
                checks["tools"] = {
                    "total": len(tool_views),
                    "ok": sum(1 for t in tool_results if t.ok),
                    "issues": [t.to_dict() | {"name": t.tool_name}
                               for t in tool_results if not t.ok],
                }
            except Exception as exc:
                checks["tools"] = f"error: {exc}"

        all_ok = _all_ok(checks)
        return JSONResponse(
            status_code=200 if all_ok else 503,
            content={"status": "ready" if all_ok else "not_ready", "checks": checks},
        )

    return router


def _all_ok(checks: dict[str, object]) -> bool:
    for key, value in checks.items():
        if isinstance(value, str):
            if value not in ("ok", "n/a"):
                return False
        elif isinstance(value, list):
            # production_env list: every item must be ok=True
            for item in value:
                if isinstance(item, dict) and not item.get("ok"):
                    return False
        elif isinstance(value, dict):
            # tools dict
            if value.get("issues"):
                return False
    return True
