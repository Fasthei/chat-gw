from __future__ import annotations

import httpx

from app.dispatchers.base import Dispatcher
from app.dispatchers.daytona import DaytonaAdapter
from app.dispatchers.http_adapter import GenericHttpAdapter
from app.dispatchers.mcp_proxy import McpProxyAdapter
from app.settings import Settings


def build_http_client(settings: Settings) -> httpx.AsyncClient:
    """Process-wide httpx client for all HTTP dispatchers.

    Keep-alive + connection pooling; explicit timeout applied per-request.
    """
    limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)
    timeout = httpx.Timeout(settings.http_default_timeout_sec, connect=10.0)
    return httpx.AsyncClient(limits=limits, timeout=timeout)


def build_dispatcher_registry(
    settings: Settings, http_client: httpx.AsyncClient
) -> dict[str, Dispatcher]:
    http_adapter = GenericHttpAdapter(
        client=http_client,
        default_timeout_sec=settings.http_default_timeout_sec,
        default_retries=settings.http_default_retries,
        retry_backoff_base_sec=settings.http_retry_backoff_base_sec,
    )
    mcp_proxy = McpProxyAdapter(
        client=http_client,
        default_timeout_sec=settings.mcp_proxy_default_timeout_sec,
        client_name=settings.server_name,
        client_version=settings.server_version,
    )
    daytona = DaytonaAdapter(
        client=http_client,
        default_timeout_sec=settings.daytona_default_timeout_sec,
        max_timeout_sec=settings.daytona_max_timeout_sec,
    )
    return {
        http_adapter.name: http_adapter,
        mcp_proxy.name: mcp_proxy,
        daytona.name: daytona,
    }
