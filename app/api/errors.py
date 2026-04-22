from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.auth.errors import AuthError
from app.mcp.protocol import jsonrpc_error


async def auth_error_handler(_request: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content=jsonrpc_error(None, -32001, str(exc) or "unauthorized"),
        headers={"WWW-Authenticate": 'Bearer realm="chat-gw"'},
    )
