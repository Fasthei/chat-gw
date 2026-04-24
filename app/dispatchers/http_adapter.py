from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any
from urllib.parse import quote

import httpx

from app.dispatchers.base import Dispatcher, DispatchError, ToolInvocation, ToolResult

log = logging.getLogger(__name__)

_RETRYABLE_STATUS = {502, 503, 504}
_PATH_VAR_RE = re.compile(r"\{(\w+)\}")


class GenericHttpAdapter(Dispatcher):
    """Config-driven HTTP tool dispatcher.

    `tool.config` keys:
      base_url_env       env var holding base URL (e.g. `KB_AGENT_URL`)
      path               path template; `{var}` substitutes from arguments
      method             HTTP method (default `GET`)
      param_map          dict of `{arg_name: "path"|"query"|"body"|"header:<Name>"}`
                         — unmapped args default to `query` for GET, `body` otherwise
      body_wrap          wrap body args under this key (e.g. `"data"`)
      timeout_sec        request timeout (default from settings)
      retries            max retries on 502/503/504 (default 2; 0 for user_passthrough)

    Auth:
      auth_mode == service_key       → header = prefix + os.environ[secret_env_name]
      auth_mode == user_passthrough  → header = prefix + auth.raw_token
    """

    name = "http_adapter"

    def __init__(
        self,
        client: httpx.AsyncClient,
        default_timeout_sec: float = 30.0,
        default_retries: int = 2,
        retry_backoff_base_sec: float = 0.25,
    ) -> None:
        self._client = client
        self._default_timeout = default_timeout_sec
        self._default_retries = default_retries
        self._backoff = retry_backoff_base_sec

    async def close(self) -> None:
        # Shared client closed by the app lifespan.
        return None

    async def invoke(self, inv: ToolInvocation) -> ToolResult:
        cfg = inv.tool.config or {}

        base_url = _env_required(cfg.get("base_url_env"), "base_url_env")
        method = str(cfg.get("method", "GET")).upper()
        timeout = float(cfg.get("timeout_sec") or self._default_timeout)
        retries = self._retries_for(inv, cfg)

        mapped = map_params(
            arguments=inv.arguments,
            path_template=str(cfg.get("path") or ""),
            param_map=cfg.get("param_map") or {},
            method=method,
            body_wrap=cfg.get("body_wrap"),
        )

        headers = _build_headers(inv, extra=mapped["header"])
        url = base_url.rstrip("/") + mapped["path"]

        return await self._send(
            method=method,
            url=url,
            params=mapped["query"] or None,
            json_body=mapped["body"] if mapped["body"] else None,
            headers=headers,
            timeout=timeout,
            retries=retries,
        )

    def _retries_for(self, inv: ToolInvocation, cfg: dict[str, Any]) -> int:
        if inv.tool.auth_mode == "user_passthrough":
            return 0
        value = cfg.get("retries")
        if value is None:
            return self._default_retries
        return max(0, int(value))

    async def _send(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None,
        json_body: dict[str, Any] | None,
        headers: dict[str, str],
        timeout: float,
        retries: int,
    ) -> ToolResult:
        attempt = 0
        last_exc: Exception | None = None
        while True:
            try:
                resp = await self._client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=headers,
                    timeout=timeout,
                )
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt >= retries:
                    raise DispatchError(
                        f"upstream timeout after {timeout}s",
                        mcp_code=-32603,
                        kind="upstream_timeout",
                    ) from exc
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt >= retries:
                    raise DispatchError(
                        f"upstream connection error: {exc}",
                        mcp_code=-32603,
                        kind="upstream_error",
                    ) from exc
            else:
                if resp.status_code in _RETRYABLE_STATUS and attempt < retries:
                    attempt += 1
                    await asyncio.sleep(self._backoff * (2 ** (attempt - 1)))
                    continue
                return _interpret(resp)

            attempt += 1
            await asyncio.sleep(self._backoff * (2 ** (attempt - 1)))
            if attempt > retries and last_exc is not None:
                raise DispatchError(
                    f"upstream error: {last_exc}",
                    mcp_code=-32603,
                    kind="upstream_error",
                ) from last_exc


def _env_required(name: str | None, what: str) -> str:
    if not name:
        raise DispatchError(
            f"tool config missing {what}",
            mcp_code=-32603,
            kind="config_error",
        )
    value = os.environ.get(name)
    if not value:
        raise DispatchError(
            f"missing env var: {name}",
            mcp_code=-32603,
            kind="config_error",
        )
    return value


def _build_headers(inv: ToolInvocation, extra: dict[str, str]) -> dict[str, str]:
    headers: dict[str, str] = {
        "X-Gateway-User-Id": inv.auth.user_id,
        "X-Gateway-User-Roles": ",".join(inv.auth.roles),
        "X-Gateway-Trace-Id": str(inv.trace_id),
        "X-Gateway-Tool-Name": inv.tool.name,
    }
    auth_header = inv.tool.auth_header
    if auth_header:
        if inv.tool.auth_mode == "user_passthrough":
            token = inv.auth.raw_token
        else:
            env_name = inv.tool.secret_env_name or ""
            token = os.environ.get(env_name, "")
            if not token:
                raise DispatchError(
                    f"missing secret env var: {env_name}",
                    mcp_code=-32603,
                    kind="config_error",
                )
        headers[auth_header] = (inv.tool.auth_prefix or "") + token
    # Forward the resolved customer_code so downstream services (notably
    # gongdan) can re-scope ADMIN-looking service-key requests back to the
    # originating customer. Without this, a customer-authenticated call
    # that fans out through a service_key tool is indistinguishable from
    # a real internal ADMIN call — which is the越权 we are fixing here.
    # The corresponding gongdan-side enforcement is in a sibling PR.
    customer_code = inv.auth.customer_code
    if customer_code:
        headers["X-Customer-Code"] = customer_code
    headers.update(extra)
    return headers


def _interpret(resp: httpx.Response) -> ToolResult:
    status = resp.status_code
    if 200 <= status < 300:
        text = resp.text
        return ToolResult(content=[{"type": "text", "text": text}])

    snippet = resp.text[:2000] if resp.text else ""
    if status in (401, 403):
        raise DispatchError(
            f"upstream denied: {status}",
            mcp_code=-32001,
            kind="upstream_denied",
            upstream_status=status,
        )
    if status == 404:
        raise DispatchError(
            "upstream not found",
            mcp_code=-32001,
            kind="upstream_not_found",
            upstream_status=status,
        )
    if status == 400:
        raise DispatchError(
            f"upstream bad request: {snippet}",
            mcp_code=-32602,
            kind="upstream_bad_request",
            upstream_status=status,
        )
    raise DispatchError(
        f"upstream error {status}: {snippet}",
        mcp_code=-32603,
        kind="upstream_error",
        upstream_status=status,
    )


def map_params(
    *,
    arguments: dict[str, Any],
    path_template: str,
    param_map: dict[str, str],
    method: str,
    body_wrap: str | None = None,
) -> dict[str, Any]:
    """Split `arguments` into path/query/body/header buckets.

    Precedence order:
      1. explicit `param_map` entries
      2. path template variables (auto-consumed, even if not mapped)
      3. default bucket: `query` for GET/DELETE, `body` otherwise
    """
    path_vars = set(_PATH_VAR_RE.findall(path_template))
    default_bucket = "query" if method in ("GET", "DELETE", "HEAD") else "body"

    path_args: dict[str, Any] = {}
    query: dict[str, Any] = {}
    body: dict[str, Any] = {}
    header: dict[str, str] = {}

    for key, value in arguments.items():
        target = param_map.get(key)
        if target is None:
            if key in path_vars:
                target = "path"
            else:
                target = default_bucket

        if target == "path":
            path_args[key] = value
        elif target == "query":
            query[key] = value
        elif target == "body":
            body[key] = value
        elif target.startswith("header:"):
            header[target.split(":", 1)[1]] = "" if value is None else str(value)
        else:
            raise DispatchError(
                f"unknown param_map target: {target}",
                mcp_code=-32603,
                kind="config_error",
            )

    rendered_path = _render_path(path_template, path_args)

    wrapped_body: dict[str, Any] = {}
    if body:
        wrapped_body = {body_wrap: body} if body_wrap else body

    return {
        "path": rendered_path,
        "query": query,
        "body": wrapped_body,
        "header": header,
    }


def _render_path(template: str, values: dict[str, Any]) -> str:
    def replace(m: re.Match) -> str:
        key = m.group(1)
        if key not in values:
            raise DispatchError(
                f"missing path argument: {key}",
                mcp_code=-32602,
                kind="invalid_params",
            )
        return quote(str(values[key]), safe="")

    return _PATH_VAR_RE.sub(replace, template)
