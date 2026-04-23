from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AuthContext:
    """Resolved identity for a single request.

    ``raw_token`` is the original Bearer value — propagated to tools with
    ``auth_mode = user_passthrough`` (e.g. cloud_cost.*).

    Customer fields (``customer_code`` / ``customer_id`` / ``customer_tier``
    / ``customer_queue_type``) are populated when the JWT carries a
    ``customer_code`` claim that successfully resolves against the gongdan
    ticket system. They are orthogonal to ``roles``: tool authorization
    takes the OR of role grants and customer-code grants.
    """

    user_id: str
    roles: list[str]
    raw_token: str
    email: str | None = None
    name: str | None = None
    customer_code: str | None = None
    customer_id: str | None = None
    customer_tier: str | None = None
    customer_queue_type: str | None = None
    claims: dict = field(default_factory=dict)
