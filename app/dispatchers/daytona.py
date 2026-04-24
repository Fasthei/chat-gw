from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from app.dispatchers.base import Dispatcher, DispatchError, ToolInvocation, ToolResult
from app.settings.validation import is_placeholder

log = logging.getLogger(__name__)


class DaytonaAdapter(Dispatcher):
    """Execute `sandbox.run_python` against a real Daytona-managed sandbox.

    Uses the official `daytona-sdk` AsyncDaytona client so the adapter maps
    1:1 onto Daytona's sandbox lifecycle: create a short-lived sandbox,
    run the user-supplied Python code inside it, collect stdout/stderr/exit,
    then delete the sandbox.

    Required env:
        DAYTONA_API_BASE   e.g. https://app.daytona.io/api
        DAYTONA_API_TOKEN  service token (`dtn_*`) — Bearer auth

    `tools.config` (all optional):
        default_timeout_sec   per-call timeout when arguments.timeout_sec missing
        max_timeout_sec       hard upper bound (default 300 — spec §6.3)
        create_timeout_sec    sandbox create timeout (default 120)
        language              sandbox runtime (default "python")

    Errors are normalised through `DispatchError`:
        * missing / placeholder env → kind=config_error, -32603
        * Daytona auth errors       → kind=upstream_denied, -32001
        * Daytona not-found         → kind=upstream_not_found, -32001
        * Daytona validation        → kind=upstream_bad_request, -32602
        * Daytona timeout           → kind=upstream_timeout, -32603
        * anything else from SDK    → kind=upstream_error, -32603

    NEVER retries — sandbox execution is non-idempotent.
    """

    name = "daytona_sandbox"

    DEFAULT_TIMEOUT_SEC = 60.0
    DEFAULT_MAX_TIMEOUT_SEC = 300.0
    DEFAULT_CREATE_TIMEOUT_SEC = 120.0

    def __init__(
        self,
        # `client` kept for signature compatibility with the dispatcher
        # registry; the SDK manages its own transport.
        client: Any = None,
        default_timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        max_timeout_sec: float = DEFAULT_MAX_TIMEOUT_SEC,
    ) -> None:
        self._default_timeout = default_timeout_sec
        self._max_timeout = max_timeout_sec

    async def close(self) -> None:
        return None

    async def invoke(self, inv: ToolInvocation) -> ToolResult:
        base = os.environ.get("DAYTONA_API_BASE", "").rstrip("/")
        token = os.environ.get("DAYTONA_API_TOKEN", "")

        if not base or is_placeholder(base):
            raise DispatchError(
                "daytona: DAYTONA_API_BASE is not configured",
                mcp_code=-32603,
                kind="config_error",
            )
        if not token or is_placeholder(token):
            raise DispatchError(
                "daytona: DAYTONA_API_TOKEN is not configured",
                mcp_code=-32603,
                kind="config_error",
            )

        args = inv.arguments or {}
        code = args.get("code")
        if not isinstance(code, str) or not code.strip():
            raise DispatchError(
                "daytona: arguments.code is required (non-empty string)",
                mcp_code=-32602,
                kind="invalid_params",
            )
        stdin = args.get("stdin")  # not currently forwarded; tracked separately

        cfg = inv.tool.config or {}
        max_timeout = float(cfg.get("max_timeout_sec") or self._max_timeout)
        requested = args.get("timeout_sec") or cfg.get("timeout_sec") or self._default_timeout
        try:
            requested_f = float(requested)
        except (TypeError, ValueError):
            requested_f = self._default_timeout
        exec_timeout = int(min(max(requested_f, 1.0), max_timeout))
        create_timeout = float(cfg.get("create_timeout_sec") or self.DEFAULT_CREATE_TIMEOUT_SEC)
        language = str(cfg.get("language") or "python")

        try:
            payload = await self._run(
                base_url=base,
                token=token,
                code=code,
                stdin=stdin,
                exec_timeout=exec_timeout,
                create_timeout=create_timeout,
                language=language,
            )
        except DispatchError:
            raise
        except Exception as exc:  # Unexpected: keep audit readable.
            log.exception("daytona unexpected failure")
            raise DispatchError(
                f"daytona unexpected error: {exc}",
                mcp_code=-32603,
                kind="upstream_error",
            ) from exc

        return ToolResult(
            content=[{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]
        )

    # ─── SDK plumbing ────────────────────────────────────────────────

    async def _run(
        self,
        *,
        base_url: str,
        token: str,
        code: str,
        stdin: Any,
        exec_timeout: int,
        create_timeout: float,
        language: str,
    ) -> dict[str, Any]:
        daytona_sdk = _require_sdk()
        AsyncDaytona = daytona_sdk.AsyncDaytona
        DaytonaConfig = daytona_sdk.DaytonaConfig
        CreateSandboxFromSnapshotParams = daytona_sdk.CreateSandboxFromSnapshotParams

        config = DaytonaConfig(api_key=token, api_url=base_url)
        client = AsyncDaytona(config)
        sandbox = None
        try:
            try:
                sandbox = await client.create(
                    params=CreateSandboxFromSnapshotParams(language=language),
                    timeout=create_timeout,
                )
            except Exception as exc:
                _map_sdk_error(exc, where="create sandbox")

            try:
                response = await sandbox.process.code_run(code, timeout=exec_timeout)
            except Exception as exc:
                _map_sdk_error(exc, where="code_run")
        finally:
            if sandbox is not None:
                sbid = getattr(sandbox, "id", "<unknown>")
                for attempt in (1, 2):
                    try:
                        await client.delete(sandbox, timeout=30)
                        break
                    except Exception as cleanup_exc:
                        if attempt == 1:
                            log.warning(
                                "daytona delete attempt 1 failed (id=%s): %s",
                                sbid, cleanup_exc,
                            )
                            await asyncio.sleep(1)
                        else:
                            log.error(
                                "daytona delete GIVING UP (id=%s, ORPHANED): %s",
                                sbid, cleanup_exc,
                            )
            try:
                await client.close()
            except Exception:
                pass

        # ExecuteResponse: exit_code, result, artifacts (depending on SDK version)
        payload = {
            "exit_code": getattr(response, "exit_code", None),
            "result": getattr(response, "result", ""),
        }
        artifacts = getattr(response, "artifacts", None)
        if artifacts is not None:
            try:
                payload["artifacts"] = artifacts.model_dump()
            except Exception:
                payload["artifacts"] = str(artifacts)
        return payload


# ─── helpers ─────────────────────────────────────────────────────────

def _require_sdk():
    try:
        import daytona_sdk  # type: ignore[import-untyped]
    except ImportError as exc:
        raise DispatchError(
            "daytona-sdk not installed; add `daytona-sdk` to requirements.txt",
            mcp_code=-32603,
            kind="config_error",
        ) from exc
    return daytona_sdk


def _map_sdk_error(exc: Exception, *, where: str) -> "None":  # type: ignore[return]
    """Translate a daytona_sdk exception into a DispatchError and raise it."""
    # Prefer direct type checks when SDK is importable; fall back to name match.
    try:
        import daytona_sdk as _sdk  # type: ignore[import-untyped]

        if isinstance(exc, _sdk.DaytonaAuthenticationError):
            raise DispatchError(
                f"daytona {where}: auth failed — {exc}",
                mcp_code=-32001, kind="upstream_denied",
            ) from exc
        if isinstance(exc, _sdk.DaytonaAuthorizationError):
            raise DispatchError(
                f"daytona {where}: forbidden — {exc}",
                mcp_code=-32001, kind="upstream_denied",
            ) from exc
        if isinstance(exc, _sdk.DaytonaNotFoundError):
            raise DispatchError(
                f"daytona {where}: not found — {exc}",
                mcp_code=-32001, kind="upstream_not_found",
            ) from exc
        if isinstance(exc, _sdk.DaytonaValidationError):
            raise DispatchError(
                f"daytona {where}: validation — {exc}",
                mcp_code=-32602, kind="upstream_bad_request",
            ) from exc
        if isinstance(exc, _sdk.DaytonaTimeoutError):
            raise DispatchError(
                f"daytona {where}: timed out — {exc}",
                mcp_code=-32603, kind="upstream_timeout",
            ) from exc
        if isinstance(exc, _sdk.DaytonaConnectionError):
            raise DispatchError(
                f"daytona {where}: connection error — {exc}",
                mcp_code=-32603, kind="upstream_error",
            ) from exc
        if isinstance(exc, _sdk.DaytonaRateLimitError):
            raise DispatchError(
                f"daytona {where}: rate limited — {exc}",
                mcp_code=-32603, kind="upstream_error",
            ) from exc
        if isinstance(exc, _sdk.DaytonaError):
            raise DispatchError(
                f"daytona {where}: {exc}",
                mcp_code=-32603, kind="upstream_error",
            ) from exc
    except ImportError:
        pass

    # Catch-all for anything not from the SDK (OSError etc.).
    if isinstance(exc, asyncio.TimeoutError):
        raise DispatchError(
            f"daytona {where}: asyncio timeout",
            mcp_code=-32603, kind="upstream_timeout",
        ) from exc
    raise DispatchError(
        f"daytona {where}: {exc}",
        mcp_code=-32603, kind="upstream_error",
    ) from exc
