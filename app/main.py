from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI

from app.api.errors import auth_error_handler
from app.api.health import build_health_router
from app.audit import AuditWriter
from app.auth import CasdoorClient, JwksCache, RoleResolver
from app.auth.errors import AuthError
from app.auth.jwt_verify import JwtVerifier
from app.db.engine import async_session, dispose_engine
from app.db.notify import PgNotifyListener
from app.dispatchers import build_dispatcher_registry, build_http_client
from app.mcp.handler import McpHandler
from app.mcp.sse import build_sse_router
from app.mcp.streamable import build_streamable_router
from app.registry import ToolRegistry
from app.registry.cache import ToolCache
from app.settings import (
    ConfigValidationError,
    settings,
    validate_production_settings,
)

log = logging.getLogger(__name__)


def _configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _assert_production_ready() -> None:
    """Fail-closed on hard production misconfiguration."""
    if not settings.is_production():
        return
    errs = [c.detail or c.name for c in validate_production_settings(settings) if not c.ok]
    if errs:
        raise ConfigValidationError(errs)
    # `jwt_mode()` raises when dev-secret is present in prod.
    settings.jwt_mode()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    _assert_production_ready()

    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    jwks_cache: JwksCache | None = None
    if settings.jwks_url:
        jwks_cache = JwksCache(
            jwks_url=settings.jwks_url,
            cache_ttl_sec=settings.jwks_cache_ttl_sec,
            refresh_cooldown_sec=settings.jwks_refresh_cooldown_sec,
        )
    app.state.jwks_cache = jwks_cache
    app.state.jwt_verifier = JwtVerifier(settings, jwks=jwks_cache)

    casdoor = CasdoorClient(
        endpoint=settings.casdoor_endpoint,
        client_id=settings.casdoor_client_id,
        client_secret=settings.casdoor_client_secret,
    )
    app.state.casdoor = casdoor

    app.state.role_resolver = RoleResolver(
        roles_claim=settings.casdoor_roles_claim,
        redis=app.state.redis,
        casdoor=casdoor,
        ttl_sec=settings.role_cache_ttl_sec,
    )

    tool_cache = ToolCache(ttl_sec=settings.registry_cache_ttl_sec)
    registry = ToolRegistry(tool_cache)
    app.state.tool_cache = tool_cache
    app.state.tool_registry = registry

    try:
        await registry.refresh_if_stale()
    except Exception as exc:
        log.warning("initial tool cache load failed: %s", exc)

    http_client = build_http_client(settings)
    app.state.http_client = http_client

    dispatchers = build_dispatcher_registry(settings, http_client)
    app.state.dispatchers = dispatchers

    app.state.audit_writer = AuditWriter(async_session)

    app.state.mcp_handler = McpHandler(
        settings=settings,
        registry=registry,
        dispatchers=dispatchers,
        audit=app.state.audit_writer,
    )

    async def _on_tools_changed(_payload: str) -> None:
        try:
            await registry.force_refresh()
        except Exception as exc:
            log.warning("tool registry refresh failed: %s", exc)

    notify_listener = PgNotifyListener(
        dsn=settings.database_url,
        channel="tools_changed",
        on_change=_on_tools_changed,
    )
    app.state.notify_listener = notify_listener
    try:
        await notify_listener.start()
    except Exception as exc:
        log.warning("pg-notify listener failed to start: %s", exc)

    try:
        yield
    finally:
        await notify_listener.stop()
        for d in dispatchers.values():
            try:
                await d.close()
            except Exception:
                pass
        await http_client.aclose()
        if jwks_cache is not None:
            await jwks_cache.close()
        await casdoor.close()
        try:
            await app.state.redis.aclose()
        except Exception:
            pass
        await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.server_name,
        version=settings.server_version,
        lifespan=lifespan,
    )
    app.add_exception_handler(AuthError, auth_error_handler)
    app.include_router(build_health_router())
    app.include_router(build_streamable_router())
    if settings.enable_mcp_sse:
        app.include_router(build_sse_router())
    return app


app = create_app()
