from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any

import httpx

from app.dispatchers.base import Dispatcher, DispatchError, ToolInvocation, ToolResult

log = logging.getLogger(__name__)


class McpProxyAdapter(Dispatcher):
    """Proxy `tools/call` to a remote MCP server over Streamable HTTP.

    Configuration (from `tools.config` JSONB):
        remote_url            absolute URL of remote MCP endpoint (required)
        remote_tool_name      name to send upstream; defaults to `<tool.name>`
                              with `prefix` stripped when set
        prefix                optional local prefix (e.g. `jina.`) stripped
                              before forwarding (matches spec §6.3 upsert)
        timeout_sec           per-call timeout (default 60)
        skip_initialize       when true, skip the MCP initialize handshake
                              (some remotes are stateless and accept
                              tools/call directly)
        protocol_version      initialize protocolVersion (default 2024-11-05)

    Auth:
        auth_mode == service_key       → Authorization header from env
        auth_mode == user_passthrough  → Authorization header = user raw JWT

    Response handling:
        application/json       → parse JSON-RPC envelope directly
        text/event-stream      → accumulate `data:` lines, decode single JSON
        other                  → raise upstream_error
    """

    name = "mcp_proxy"

    DEFAULT_PROTOCOL_VERSION = "2024-11-05"

    def __init__(
        self,
        client: httpx.AsyncClient,
        default_timeout_sec: float = 60.0,
        client_name: str = "chat-gw-mcp-proxy",
        client_version: str = "0.1.0",
    ) -> None:
        self._client = client
        self._default_timeout = default_timeout_sec
        self._client_name = client_name
        self._client_version = client_version
        # Cached Mcp-Session-Id per (remote_url, auth_identity) pair.
        self._sessions: dict[tuple[str, str], str] = {}
        self._init_locks: dict[tuple[str, str], asyncio.Lock] = {}

    async def close(self) -> None:
        self._sessions.clear()
        self._init_locks.clear()

    async def invoke(self, inv: ToolInvocation) -> ToolResult:
        cfg = inv.tool.config or {}
        remote_url = cfg.get("remote_url")
        if not isinstance(remote_url, str) or not remote_url:
            raise DispatchError(
                "mcp_proxy: missing remote_url in tool.config",
                mcp_code=-32603,
                kind="config_error",
            )

        timeout = float(cfg.get("timeout_sec") or self._default_timeout)
        remote_tool_name = self._remote_tool_name(inv.tool.name, cfg)
        token, auth_identity = self._resolve_token(inv)

        base_headers = self._base_headers(inv, token)

        session_key = (remote_url, auth_identity)
        if not cfg.get("skip_initialize"):
            await self._ensure_initialized(
                remote_url=remote_url,
                session_key=session_key,
                base_headers=base_headers,
                timeout=timeout,
                protocol_version=str(cfg.get("protocol_version") or self.DEFAULT_PROTOCOL_VERSION),
            )

        headers = dict(base_headers)
        session_id = self._sessions.get(session_key)
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        rpc = {
            "jsonrpc": "2.0",
            "id": str(inv.trace_id),
            "method": "tools/call",
            "params": {"name": remote_tool_name, "arguments": inv.arguments},
        }

        payload = await self._rpc_call(remote_url, rpc, headers, timeout)
        return self._build_result(payload)

    # ─── helpers ─────────────────────────────────────────────────────

    def _remote_tool_name(self, local_name: str, cfg: dict[str, Any]) -> str:
        explicit = cfg.get("remote_tool_name")
        if isinstance(explicit, str) and explicit:
            return explicit
        prefix = cfg.get("prefix")
        if isinstance(prefix, str) and prefix and local_name.startswith(prefix):
            return local_name[len(prefix):]
        return local_name

    def _resolve_token(self, inv: ToolInvocation) -> tuple[str, str]:
        if inv.tool.auth_mode == "user_passthrough":
            token = inv.auth.raw_token
            if not token:
                raise DispatchError(
                    "mcp_proxy: user_passthrough requires raw bearer token",
                    mcp_code=-32603,
                    kind="config_error",
                )
            return token, f"user:{inv.auth.user_id}"
        env = inv.tool.secret_env_name or ""
        if not env:
            raise DispatchError(
                "mcp_proxy: tool missing secret_env_name for service_key auth",
                mcp_code=-32603,
                kind="config_error",
            )
        token = os.environ.get(env, "")
        if not token:
            raise DispatchError(
                f"mcp_proxy: missing secret env {env}",
                mcp_code=-32603,
                kind="config_error",
            )
        return token, f"svc:{env}"

    def _base_headers(self, inv: ToolInvocation, token: str) -> dict[str, str]:
        prefix = inv.tool.auth_prefix or "Bearer "
        return {
            "Authorization": f"{prefix}{token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "X-Gateway-User-Id": inv.auth.user_id,
            "X-Gateway-User-Roles": ",".join(inv.auth.roles),
            "X-Gateway-Trace-Id": str(inv.trace_id),
            "X-Gateway-Tool-Name": inv.tool.name,
        }

    async def _ensure_initialized(
        self,
        *,
        remote_url: str,
        session_key: tuple[str, str],
        base_headers: dict[str, str],
        timeout: float,
        protocol_version: str,
    ) -> None:
        if session_key in self._sessions:
            return
        lock = self._init_locks.setdefault(session_key, asyncio.Lock())
        async with lock:
            if session_key in self._sessions:
                return
            rpc = {
                "jsonrpc": "2.0",
                "id": f"init-{uuid.uuid4()}",
                "method": "initialize",
                "params": {
                    "protocolVersion": protocol_version,
                    "capabilities": {"tools": {}},
                    "clientInfo": {"name": self._client_name, "version": self._client_version},
                },
            }
            resp = await self._post(remote_url, rpc, base_headers, timeout)
            session_id = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id") or ""
            # Drain body (content-wise irrelevant; must match JSON-RPC format).
            _ = self._decode_response(resp)
            self._sessions[session_key] = session_id

    async def _rpc_call(
        self,
        remote_url: str,
        rpc: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> dict[str, Any]:
        resp = await self._post(remote_url, rpc, headers, timeout)
        return self._decode_response(resp)

    async def _post(
        self,
        url: str,
        rpc: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> httpx.Response:
        try:
            resp = await self._client.post(url, json=rpc, headers=headers, timeout=timeout)
        except httpx.TimeoutException as exc:
            raise DispatchError(
                f"mcp_proxy timeout after {timeout}s",
                mcp_code=-32603,
                kind="upstream_timeout",
            ) from exc
        except httpx.HTTPError as exc:
            raise DispatchError(
                f"mcp_proxy connection error: {exc}",
                mcp_code=-32603,
                kind="upstream_error",
            ) from exc
        self._raise_for_http_error(resp)
        return resp

    def _raise_for_http_error(self, resp: httpx.Response) -> None:
        status = resp.status_code
        if 200 <= status < 300:
            return
        snippet = resp.text[:500] if resp.text else ""
        if status in (401, 403):
            raise DispatchError(
                f"mcp_proxy upstream denied: {status}",
                mcp_code=-32001,
                kind="upstream_denied",
                upstream_status=status,
            )
        if status == 404:
            raise DispatchError(
                "mcp_proxy upstream not found",
                mcp_code=-32001,
                kind="upstream_not_found",
                upstream_status=status,
            )
        if status == 400:
            raise DispatchError(
                f"mcp_proxy upstream bad request: {snippet}",
                mcp_code=-32602,
                kind="upstream_bad_request",
                upstream_status=status,
            )
        raise DispatchError(
            f"mcp_proxy upstream error {status}: {snippet}",
            mcp_code=-32603,
            kind="upstream_error",
            upstream_status=status,
        )

    def _decode_response(self, resp: httpx.Response) -> dict[str, Any]:
        content_type = (resp.headers.get("content-type") or "").lower()
        body = resp.text or ""

        if "text/event-stream" in content_type:
            payload = _parse_sse_envelope(body)
        else:
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError as exc:
                raise DispatchError(
                    f"mcp_proxy: invalid JSON response: {exc}",
                    mcp_code=-32603,
                    kind="upstream_error",
                ) from exc

        if not isinstance(payload, dict):
            raise DispatchError(
                "mcp_proxy: response envelope not a JSON-RPC object",
                mcp_code=-32603,
                kind="upstream_error",
            )
        return payload

    def _build_result(self, payload: dict[str, Any]) -> ToolResult:
        error = payload.get("error")
        if isinstance(error, dict):
            code = int(error.get("code", -32603))
            message = str(error.get("message") or "remote mcp error")
            raise DispatchError(
                f"mcp_proxy remote error: {message}",
                mcp_code=code,
                kind="remote_mcp_error",
            )

        if "result" not in payload:
            raise DispatchError(
                "mcp_proxy: response missing result",
                mcp_code=-32603,
                kind="upstream_error",
            )
        result = payload["result"]
        if isinstance(result, dict) and isinstance(result.get("content"), list):
            return ToolResult(
                content=result["content"],
                is_error=bool(result.get("isError")),
            )
        # Fallback: wrap the raw result as a single JSON text block.
        return ToolResult(
            content=[{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
        )


def _parse_sse_envelope(body: str) -> Any:
    """Extract the first complete JSON `data:` block from an SSE body."""
    data_chunks: list[str] = []
    for line in body.splitlines():
        if line.startswith(":") or not line.strip():
            if data_chunks:
                break
            continue
        if line.startswith("data:"):
            data_chunks.append(line[5:].lstrip())
    if not data_chunks:
        raise DispatchError(
            "mcp_proxy: SSE response contained no data frames",
            mcp_code=-32603,
            kind="upstream_error",
        )
    joined = "".join(data_chunks)
    try:
        return json.loads(joined)
    except json.JSONDecodeError as exc:
        raise DispatchError(
            f"mcp_proxy: SSE payload is not JSON: {exc}",
            mcp_code=-32603,
            kind="upstream_error",
        ) from exc
