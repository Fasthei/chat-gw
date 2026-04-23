from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ─── /admin/tools ────────────────────────────────────────────────────

AuthMode = Literal["service_key", "user_passthrough"]
Dispatcher = Literal["http_adapter", "mcp_proxy", "daytona_sandbox"]


class ToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    display_name: str
    description: str
    category: str | None
    dispatcher: Dispatcher
    config: dict[str, Any]
    auth_mode: AuthMode
    secret_env_name: str | None
    auth_header: str | None
    auth_prefix: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    enabled: bool
    version: int
    created_at: datetime
    updated_at: datetime


class ToolsListResponse(BaseModel):
    tools: list[ToolOut]


class ToolUpsertIn(BaseModel):
    """Full definition used by POST /admin/tools (upsert by `name`)."""

    name: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    category: str | None = Field(default=None, max_length=64)
    dispatcher: Dispatcher
    config: dict[str, Any] = Field(default_factory=dict)
    auth_mode: AuthMode
    secret_env_name: str | None = Field(default=None, max_length=128)
    auth_header: str | None = Field(default=None, max_length=128)
    auth_prefix: str = Field(default="", max_length=32)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    enabled: bool = True


class ToolPatchIn(BaseModel):
    """Partial update for PATCH /admin/tools/{name}."""

    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    category: str | None = Field(default=None, max_length=64)
    dispatcher: Dispatcher | None = None
    config: dict[str, Any] | None = None
    auth_mode: AuthMode | None = None
    secret_env_name: str | None = None
    auth_header: str | None = None
    auth_prefix: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    enabled: bool | None = None


# ─── /admin/tool-role-grants ─────────────────────────────────────────

Role = Literal["cloud_admin", "cloud_ops", "cloud_finance", "cloud_viewer"]


class GrantPair(BaseModel):
    role: Role
    tool_name: str


class GrantsListResponse(BaseModel):
    grants: list[GrantPair]


class GrantPutIn(BaseModel):
    role: Role
    tool_name: str = Field(min_length=1, max_length=128)
    granted: bool


class GrantPutOut(BaseModel):
    role: Role
    tool_name: str
    granted: bool


# ─── /admin/audit ────────────────────────────────────────────────────

Outcome = Literal["allowed", "denied", "error", "ok"]


class AuditItem(BaseModel):
    trace_id: str
    at: datetime
    user_id: str
    user_email: str | None
    roles: list[str]
    tool_name: str
    tool_id: int | None
    outcome: Outcome
    error_code: int | None
    error_kind: str | None
    latency_ms: int | None
    deny_reason: str | None
    error_message: str | None
    sensitive_fields_hit: list[str]
    arguments: dict[str, Any] | None


class AuditResponse(BaseModel):
    items: list[AuditItem]
    next_cursor: str | None = None
