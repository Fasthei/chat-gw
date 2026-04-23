"""Test factories: build ToolView / AuthContext without ORM or Redis."""
from __future__ import annotations

from typing import Any

from app.auth import AuthContext
from app.registry.cache import ToolView


def make_auth_ctx(
    *,
    user_id: str = "test-user",
    roles: list[str] | None = None,
    token: str = "raw-bearer",
    email: str | None = "test@example.com",
    name: str | None = "Test User",
    customer_code: str | None = None,
    customer_id: str | None = None,
    customer_tier: str | None = None,
    customer_queue_type: str | None = None,
) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        roles=roles if roles is not None else ["cloud_admin"],
        raw_token=token,
        email=email,
        name=name,
        customer_code=customer_code,
        customer_id=customer_id,
        customer_tier=customer_tier,
        customer_queue_type=customer_queue_type,
    )


def make_tool_view(
    *,
    id: int = 1,
    name: str = "kb.search",
    display_name: str = "KB Search",
    description: str = "Search the knowledge base.",
    category: str | None = "kb",
    dispatcher: str = "http_adapter",
    config: dict[str, Any] | None = None,
    auth_mode: str = "service_key",
    secret_env_name: str | None = "KB_AGENT_API_KEY",
    auth_header: str | None = "api-key",
    auth_prefix: str = "",
    input_schema: dict[str, Any] | None = None,
    roles: frozenset[str] | None = None,
    customer_codes: frozenset[str] | None = None,
) -> ToolView:
    return ToolView(
        id=id,
        name=name,
        display_name=display_name,
        description=description,
        category=category,
        dispatcher=dispatcher,
        config=config or {
            "base_url_env": "KB_AGENT_URL",
            "path": "/api/v1/search",
            "method": "POST",
        },
        auth_mode=auth_mode,
        secret_env_name=secret_env_name,
        auth_header=auth_header,
        auth_prefix=auth_prefix,
        input_schema=input_schema or {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "top": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
        roles=roles if roles is not None else frozenset({"cloud_admin", "cloud_ops", "cloud_finance", "cloud_viewer"}),
        customer_codes=customer_codes if customer_codes is not None else frozenset(),
    )
