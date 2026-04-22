"""Unit tests for DaytonaAdapter.

Focus on the production fail-closed paths that don't need a real Daytona
sandbox:

* missing / placeholder env → config_error before any network I/O
* missing / non-string `code` argument → invalid_params before any I/O
* SDK-level exceptions → normalised DispatchError (upstream_denied /
  upstream_not_found / upstream_bad_request / upstream_timeout /
  upstream_error) via `_map_sdk_error`

A live Daytona integration test lives in `scripts/smoke_integrations.py`;
running it requires a real `DAYTONA_API_TOKEN`.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.dispatchers.base import DispatchError, ToolInvocation
from app.dispatchers.daytona import DaytonaAdapter, _map_sdk_error
from tests.factories import make_auth_ctx, make_tool_view


def _sandbox_tool(**overrides):
    defaults = dict(
        name="sandbox.run_python",
        dispatcher="daytona_sandbox",
        auth_mode="service_key",
        secret_env_name="DAYTONA_API_TOKEN",
        auth_header="Authorization",
        auth_prefix="Bearer ",
        input_schema={
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
        roles=frozenset({"cloud_admin"}),
        config={"language": "python", "create_timeout_sec": 60, "max_timeout_sec": 30},
    )
    defaults.update(overrides)
    return make_tool_view(**defaults)


def _adapter() -> DaytonaAdapter:
    return DaytonaAdapter(default_timeout_sec=5, max_timeout_sec=30)


# ─── Config guards ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_base_is_config_error(monkeypatch):
    monkeypatch.delenv("DAYTONA_API_BASE", raising=False)
    monkeypatch.setenv("DAYTONA_API_TOKEN", "dtn_live_abc")

    inv = ToolInvocation(
        tool=_sandbox_tool(), arguments={"code": "print(1)"},
        auth=make_auth_ctx(), trace_id=uuid4(),
    )
    with pytest.raises(DispatchError) as exc:
        await _adapter().invoke(inv)
    assert exc.value.kind == "config_error"


@pytest.mark.asyncio
async def test_placeholder_token_is_config_error(monkeypatch):
    monkeypatch.setenv("DAYTONA_API_BASE", "https://sandbox.test")
    monkeypatch.setenv("DAYTONA_API_TOKEN", "REPLACE_ME")
    inv = ToolInvocation(
        tool=_sandbox_tool(), arguments={"code": "print(1)"},
        auth=make_auth_ctx(), trace_id=uuid4(),
    )
    with pytest.raises(DispatchError) as exc:
        await _adapter().invoke(inv)
    assert exc.value.kind == "config_error"


@pytest.mark.asyncio
async def test_placeholder_base_is_config_error(monkeypatch):
    monkeypatch.setenv("DAYTONA_API_BASE", "https://example.com/api")
    monkeypatch.setenv("DAYTONA_API_TOKEN", "dtn_live_abc")
    inv = ToolInvocation(
        tool=_sandbox_tool(), arguments={"code": "print(1)"},
        auth=make_auth_ctx(), trace_id=uuid4(),
    )
    with pytest.raises(DispatchError) as exc:
        await _adapter().invoke(inv)
    assert exc.value.kind == "config_error"


# ─── Argument guard ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_code_is_invalid_params(monkeypatch):
    monkeypatch.setenv("DAYTONA_API_BASE", "https://real.daytona/api")
    monkeypatch.setenv("DAYTONA_API_TOKEN", "dtn_live_real")
    inv = ToolInvocation(
        tool=_sandbox_tool(), arguments={"stdin": "ignore me"},
        auth=make_auth_ctx(), trace_id=uuid4(),
    )
    with pytest.raises(DispatchError) as exc:
        await _adapter().invoke(inv)
    assert exc.value.kind == "invalid_params"
    assert exc.value.mcp_code == -32602


# ─── End-to-end via mocked SDK ───────────────────────────────────────

@pytest.mark.asyncio
async def test_successful_run_returns_exit_code_and_result(monkeypatch):
    monkeypatch.setenv("DAYTONA_API_BASE", "https://real.daytona/api")
    monkeypatch.setenv("DAYTONA_API_TOKEN", "dtn_live_real")

    # Build a mock AsyncDaytona surface the adapter will touch.
    exec_response = MagicMock(exit_code=0, result="42\n", artifacts=None)
    mock_process = MagicMock()
    mock_process.code_run = AsyncMock(return_value=exec_response)
    mock_sandbox = MagicMock(process=mock_process)

    mock_client = MagicMock()
    mock_client.create = AsyncMock(return_value=mock_sandbox)
    mock_client.delete = AsyncMock(return_value=None)
    mock_client.close = AsyncMock(return_value=None)

    with patch("app.dispatchers.daytona._require_sdk") as sdk_getter:
        sdk_module = MagicMock()
        sdk_module.AsyncDaytona = MagicMock(return_value=mock_client)
        sdk_module.DaytonaConfig = MagicMock()
        sdk_module.CreateSandboxFromSnapshotParams = MagicMock()
        sdk_getter.return_value = sdk_module

        inv = ToolInvocation(
            tool=_sandbox_tool(),
            arguments={"code": "print(40 + 2)", "timeout_sec": 10},
            auth=make_auth_ctx(), trace_id=uuid4(),
        )
        result = await _adapter().invoke(inv)

    assert mock_client.create.await_count == 1
    assert mock_process.code_run.await_count == 1
    # Exec timeout is clamped to max_timeout_sec=30 in the tool config.
    _, kwargs = mock_process.code_run.call_args
    assert kwargs["timeout"] == 10
    # Sandbox is cleaned up regardless of outcome.
    assert mock_client.delete.await_count == 1

    text = result.content[0]["text"]
    assert '"exit_code": 0' in text
    assert "42" in text


@pytest.mark.asyncio
async def test_auth_error_maps_to_upstream_denied(monkeypatch):
    monkeypatch.setenv("DAYTONA_API_BASE", "https://real.daytona/api")
    monkeypatch.setenv("DAYTONA_API_TOKEN", "dtn_live_real")

    import daytona_sdk

    class _Auth(daytona_sdk.DaytonaAuthenticationError):
        pass

    mock_client = MagicMock()
    mock_client.create = AsyncMock(side_effect=_Auth("bad token"))
    mock_client.delete = AsyncMock(return_value=None)
    mock_client.close = AsyncMock(return_value=None)

    with patch("app.dispatchers.daytona._require_sdk") as sdk_getter:
        sdk_module = MagicMock(wraps=daytona_sdk)
        sdk_module.AsyncDaytona = MagicMock(return_value=mock_client)
        sdk_module.DaytonaAuthenticationError = daytona_sdk.DaytonaAuthenticationError
        sdk_module.DaytonaAuthorizationError = daytona_sdk.DaytonaAuthorizationError
        sdk_module.DaytonaNotFoundError = daytona_sdk.DaytonaNotFoundError
        sdk_module.DaytonaValidationError = daytona_sdk.DaytonaValidationError
        sdk_module.DaytonaTimeoutError = daytona_sdk.DaytonaTimeoutError
        sdk_module.DaytonaConnectionError = daytona_sdk.DaytonaConnectionError
        sdk_module.DaytonaRateLimitError = daytona_sdk.DaytonaRateLimitError
        sdk_module.DaytonaError = daytona_sdk.DaytonaError
        sdk_module.DaytonaConfig = MagicMock()
        sdk_module.CreateSandboxFromSnapshotParams = MagicMock()
        sdk_getter.return_value = sdk_module

        inv = ToolInvocation(
            tool=_sandbox_tool(), arguments={"code": "print(1)"},
            auth=make_auth_ctx(), trace_id=uuid4(),
        )
        with pytest.raises(DispatchError) as exc:
            await _adapter().invoke(inv)
    assert exc.value.kind == "upstream_denied"
    assert exc.value.mcp_code == -32001


# ─── _map_sdk_error direct coverage ──────────────────────────────────

def test_map_sdk_error_wraps_unrelated_exc():
    with pytest.raises(DispatchError) as exc:
        _map_sdk_error(OSError("socket closed"), where="code_run")
    assert exc.value.kind == "upstream_error"


def test_map_sdk_error_maps_timeout():
    import daytona_sdk
    with pytest.raises(DispatchError) as exc:
        _map_sdk_error(daytona_sdk.DaytonaTimeoutError("boom"), where="code_run")
    assert exc.value.kind == "upstream_timeout"


def test_map_sdk_error_maps_validation():
    import daytona_sdk
    with pytest.raises(DispatchError) as exc:
        _map_sdk_error(daytona_sdk.DaytonaValidationError("bad"), where="create")
    assert exc.value.mcp_code == -32602
    assert exc.value.kind == "upstream_bad_request"
