from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AuthContext:
    """Resolved identity for a single request.

    `raw_token` is the original Bearer value — propagated to tools with
    `auth_mode = user_passthrough` (e.g. cloud_cost.*).
    """

    user_id: str
    roles: list[str]
    raw_token: str
    email: str | None = None
    name: str | None = None
    claims: dict = field(default_factory=dict)
