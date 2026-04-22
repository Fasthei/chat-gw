from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app.auth import AuthContext, authenticate
from app.mcp.handler import McpHandler
from app.mcp.protocol import INTERNAL_ERROR, jsonrpc_error

log = logging.getLogger(__name__)


def _handler(request: Request) -> McpHandler:
    return request.app.state.mcp_handler


def build_streamable_router() -> APIRouter:
    router = APIRouter()

    @router.post("/mcp")
    async def mcp_post(
        request: Request,
        handler: McpHandler = Depends(_handler),
        ctx: AuthContext = Depends(authenticate),
    ) -> Response:
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return JSONResponse(
                status_code=400,
                content=jsonrpc_error(None, INTERNAL_ERROR, "invalid json"),
            )

        if isinstance(body, list):
            results: list[Any] = []
            for item in body:
                resp = await handler.handle(item, ctx)
                if resp is not None:
                    results.append(resp)
            if not results:
                return Response(status_code=204)
            return JSONResponse(content=results)

        resp = await handler.handle(body, ctx)
        if resp is None:
            return Response(status_code=204)
        return JSONResponse(content=resp)

    @router.get("/mcp")
    async def mcp_stream(
        request: Request,
        handler: McpHandler = Depends(_handler),
        ctx: AuthContext = Depends(authenticate),
    ) -> StreamingResponse:
        registry = request.app.state.tool_registry
        queue = registry.subscribe()

        async def events():
            try:
                yield _sse_event(
                    "endpoint",
                    {"method": "notifications/tools/list_changed"},
                )
                while True:
                    event = await queue.get()
                    yield _sse_event(
                        "message",
                        {"jsonrpc": "2.0", "method": "notifications/tools/list_changed"},
                    )
                    if event == "__stop__":
                        break
            except Exception:
                log.debug("mcp stream closed")
            finally:
                registry.unsubscribe(queue)

        return StreamingResponse(events(), media_type="text/event-stream")

    return router


def _sse_event(event: str, data: dict) -> bytes:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")
