from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


class CasdoorClient:
    """Minimal Casdoor admin-API client for `get-account` role fallback.

    Only invoked when a verified JWT has an empty `roles` claim. Structure
    is complete but responses are conservatively parsed — if the deployment
    has custom claim shapes, the caller records empty roles and gateway
    returns 0 authorized tools rather than failing open.
    """

    def __init__(
        self,
        endpoint: str | None,
        client_id: str | None,
        client_secret: str | None,
        http_client: httpx.AsyncClient | None = None,
        timeout_sec: float = 5.0,
    ) -> None:
        self._endpoint = endpoint.rstrip("/") if endpoint else None
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = timeout_sec
        self._client = http_client
        self._owns_client = http_client is None

    def configured(self) -> bool:
        return bool(self._endpoint and self._client_id and self._client_secret)

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_user_roles(self, user_id: str, bearer_token: str | None = None) -> list[str]:
        """Fetch role names for `user_id` via Casdoor admin API.

        Returns empty list on any error — authz then denies the call.
        """
        if not self.configured():
            log.debug("casdoor not configured; fallback disabled")
            return []
        assert self._endpoint and self._client_id and self._client_secret

        url = f"{self._endpoint}/api/get-account"
        params: dict[str, Any] = {"userId": user_id}
        headers: dict[str, str] = {}
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        else:
            params["clientId"] = self._client_id
            params["clientSecret"] = self._client_secret

        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns_temp = self._client is None
        try:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            log.warning("casdoor get-account failed for %s: %s", user_id, exc)
            return []
        finally:
            if owns_temp:
                await client.aclose()

        return _extract_role_names(body)


def _extract_role_names(body: Any) -> list[str]:
    if not isinstance(body, dict):
        return []
    data = body.get("data")
    if not isinstance(data, dict):
        return []
    roles = data.get("roles") or []
    names: list[str] = []
    for entry in roles:
        if isinstance(entry, str):
            names.append(entry)
        elif isinstance(entry, dict):
            name = entry.get("name") or entry.get("displayName")
            if name:
                names.append(str(name))
    return names
