from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app.auth import AuthContext, authenticate
from app.mcp.handler import McpHandler
from app.mcp.protocol import INTERNAL_ERROR, jsonrpc_error

log = logging.getLogger(__name__)


class _SseSession:
    __slots__ = ("id", "ctx", "queue")

    def __init__(self, session_id: str, ctx: AuthContext) -> None:
        self.id = session_id
        self.ctx = ctx
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=64)

    async def push(self, message: dict[str, Any]) -> None:
        await self.queue.put(json.dumps(message, ensure_ascii=False))


def _sessions(request: Request) -> dict[str, _SseSession]:
    store = getattr(request.app.state, "sse_sessions", None)
    if store is None:
        store = {}
        request.app.state.sse_sessions = store
    return store


def _handler(request: Request) -> McpHandler:
    return request.app.state.mcp_handler


def build_sse_router() -> APIRouter:
    """Legacy MCP SSE transport retained for LobeChat 1.x compatibility."""
    router = APIRouter()

    @router.get("/mcp/sse")
    async def sse_open(
        request: Request,
        ctx: AuthContext = Depends(authenticate),
    ) -> StreamingResponse:
        sid = uuid.uuid4().hex
        sessions = _sessions(request)
        session = _SseSession(sid, ctx)
        sessions[sid] = session

        async def events():
            try:
                endpoint = f"/mcp/sse/messages?session_id={sid}"
                yield f"event: endpoint\ndata: {endpoint}\n\n".encode("utf-8")
                while True:
                    data = await session.queue.get()
                    yield f"event: message\ndata: {data}\n\n".encode("utf-8")
            except asyncio.CancelledError:
                raise
            finally:
                sessions.pop(sid, None)

        return StreamingResponse(events(), media_type="text/event-stream")

    @router.post("/mcp/sse/messages")
    async def sse_post(
        request: Request,
        handler: McpHandler = Depends(_handler),
    ) -> Response:
        sid = request.query_params.get("session_id") or ""
        sessions = _sessions(request)
        session = sessions.get(sid)
        if session is None:
            return JSONResponse(
                status_code=404,
                content=jsonrpc_error(None, INTERNAL_ERROR, "unknown session"),
            )
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return JSONResponse(
                status_code=400,
                content=jsonrpc_error(None, INTERNAL_ERROR, "invalid json"),
            )
        resp = await handler.handle(body, session.ctx)
        if resp is not None:
            await session.push(resp)
        return Response(status_code=202)

    return router
