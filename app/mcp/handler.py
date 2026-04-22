from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import jsonschema

from app.audit import AuditWriter
from app.auth import AuthContext
from app.dispatchers.base import Dispatcher, DispatchError, ToolInvocation
from app.mcp.protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    SERVER_CAPABILITIES,
    SUPPORTED_PROTOCOL_VERSION,
    TOOL_NOT_FOUND,
    jsonrpc_error,
    jsonrpc_result,
)
from app.registry import ToolRegistry
from app.registry.cache import ToolView
from app.sensitive import scan_sensitive_fields
from app.settings import Settings

log = logging.getLogger(__name__)


class McpHandler:
    """Dispatches MCP JSON-RPC methods shared by /mcp and /mcp/sse."""

    def __init__(
        self,
        *,
        settings: Settings,
        registry: ToolRegistry,
        dispatchers: dict[str, Dispatcher],
        audit: AuditWriter,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._dispatchers = dispatchers
        self._audit = audit

    async def handle(self, msg: dict[str, Any], ctx: AuthContext) -> dict[str, Any] | None:
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return jsonrpc_error(msg.get("id") if isinstance(msg, dict) else None,
                                 INVALID_PARAMS, "invalid JSON-RPC envelope")

        method = msg.get("method")
        req_id = msg.get("id")
        params = msg.get("params") or {}

        if method is None:
            return jsonrpc_error(req_id, INVALID_PARAMS, "missing method")

        if req_id is None and method.startswith("notifications/"):
            return None

        try:
            if method == "initialize":
                return await self._initialize(req_id, params)
            if method in ("notifications/initialized", "initialized"):
                return None
            if method == "ping":
                return jsonrpc_result(req_id, {})
            if method == "tools/list":
                return await self._tools_list(req_id, ctx)
            if method == "tools/call":
                return await self._tools_call(req_id, params, ctx)
            return jsonrpc_error(req_id, METHOD_NOT_FOUND, f"method not found: {method}")
        except Exception as exc:
            log.exception("mcp handler error: method=%s", method)
            return jsonrpc_error(req_id, INTERNAL_ERROR, f"internal error: {exc}")

    async def _initialize(self, req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        client_version = params.get("protocolVersion")
        negotiated = client_version if isinstance(client_version, str) else SUPPORTED_PROTOCOL_VERSION
        return jsonrpc_result(
            req_id,
            {
                "protocolVersion": negotiated,
                "serverInfo": {
                    "name": self._settings.server_name,
                    "version": self._settings.server_version,
                },
                "capabilities": SERVER_CAPABILITIES,
            },
        )

    async def _tools_list(self, req_id: Any, ctx: AuthContext) -> dict[str, Any]:
        views = await self._registry.list_for_roles(ctx.roles)
        payload = [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.input_schema,
            }
            for t in views
        ]
        return jsonrpc_result(req_id, {"tools": payload})

    async def _tools_call(
        self, req_id: Any, params: dict[str, Any], ctx: AuthContext
    ) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not name:
            return jsonrpc_error(req_id, INVALID_PARAMS, "missing tool name")
        if not isinstance(arguments, dict):
            return jsonrpc_error(req_id, INVALID_PARAMS, "arguments must be object")

        trace_id = uuid.uuid4()
        started = time.monotonic()

        tool = await self._registry.find_authorized(name, ctx.roles)
        if tool is None:
            await self._audit.log(
                trace_id=trace_id,
                ctx=ctx,
                tool_name=name,
                arguments=arguments,
                status="denied",
                deny_reason="not_found_or_no_role",
            )
            return jsonrpc_error(req_id, TOOL_NOT_FOUND, f"tool '{name}' not found")

        try:
            jsonschema.validate(instance=arguments, schema=tool.input_schema)
        except jsonschema.ValidationError as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            await self._audit.log(
                trace_id=trace_id,
                ctx=ctx,
                tool_name=name,
                arguments=arguments,
                status="error",
                tool_id=tool.id,
                sensitive_fields_hit=scan_sensitive_fields(arguments),
                error_message=f"schema: {exc.message}",
                latency_ms=latency_ms,
            )
            return jsonrpc_error(req_id, INVALID_PARAMS, f"invalid params: {exc.message}")

        sensitive_hit = scan_sensitive_fields(arguments)
        dispatcher = self._dispatchers.get(tool.dispatcher)
        if dispatcher is None:
            latency_ms = int((time.monotonic() - started) * 1000)
            await self._audit.log(
                trace_id=trace_id,
                ctx=ctx,
                tool_name=name,
                arguments=arguments,
                status="error",
                tool_id=tool.id,
                sensitive_fields_hit=sensitive_hit,
                error_message=f"unknown dispatcher: {tool.dispatcher}",
                latency_ms=latency_ms,
            )
            return jsonrpc_error(req_id, INTERNAL_ERROR, f"unknown dispatcher: {tool.dispatcher}")

        inv = ToolInvocation(tool=tool, arguments=arguments, auth=ctx, trace_id=trace_id)
        try:
            result = await dispatcher.invoke(inv)
        except DispatchError as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            await self._audit.log(
                trace_id=trace_id,
                ctx=ctx,
                tool_name=name,
                arguments=arguments,
                status="error",
                tool_id=tool.id,
                sensitive_fields_hit=sensitive_hit,
                error_message=f"{exc.kind}: {exc.message}",
                latency_ms=latency_ms,
            )
            data: dict[str, Any] = {"kind": exc.kind}
            if exc.upstream_status is not None:
                data["upstreamStatus"] = exc.upstream_status
            return jsonrpc_error(req_id, exc.mcp_code, exc.message, data=data)
        except Exception as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            log.exception("dispatcher raised for tool=%s", name)
            await self._audit.log(
                trace_id=trace_id,
                ctx=ctx,
                tool_name=name,
                arguments=arguments,
                status="error",
                tool_id=tool.id,
                sensitive_fields_hit=sensitive_hit,
                error_message=str(exc),
                latency_ms=latency_ms,
            )
            return jsonrpc_error(req_id, INTERNAL_ERROR, f"internal error: {exc}")

        latency_ms = int((time.monotonic() - started) * 1000)
        await self._audit.log(
            trace_id=trace_id,
            ctx=ctx,
            tool_name=name,
            arguments=arguments,
            status="ok",
            tool_id=tool.id,
            sensitive_fields_hit=sensitive_hit,
            latency_ms=latency_ms,
        )
        return jsonrpc_result(req_id, result.to_mcp())


def view_to_mcp(view: ToolView) -> dict[str, Any]:
    return {
        "name": view.name,
        "description": view.description,
        "inputSchema": view.input_schema,
    }
