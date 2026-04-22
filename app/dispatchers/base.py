from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.auth import AuthContext
from app.registry.cache import ToolView


@dataclass
class ToolInvocation:
    tool: ToolView
    arguments: dict[str, Any]
    auth: AuthContext
    trace_id: UUID


@dataclass
class ToolResult:
    """MCP tools/call result content — list of content blocks."""

    content: list[dict[str, Any]]
    is_error: bool = False

    def to_mcp(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"content": self.content}
        if self.is_error:
            payload["isError"] = True
        return payload


class DispatchError(Exception):
    """Normalized dispatcher error.

    `mcp_code` maps to JSON-RPC error codes (see MCP spec §5.3).
    `kind` is a short stable tag for audit (e.g. `upstream_timeout`).
    """

    def __init__(
        self,
        message: str,
        *,
        mcp_code: int = -32603,
        kind: str = "internal_error",
        upstream_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.mcp_code = mcp_code
        self.kind = kind
        self.upstream_status = upstream_status


class Dispatcher(Protocol):
    name: str

    async def invoke(self, inv: ToolInvocation) -> ToolResult: ...

    async def close(self) -> None: ...
