"""Gongdan ticket-system client.

Only the minimal surface needed by chat-gw is implemented: resolving the
``customer_code`` carried in a LobeChat JWT to a real customer record.

Design notes
------------

* **Real-time**: every call hits the upstream API. No process cache.
* **Authentication**: the ``X-Api-Key`` header is required by the gongdan
  gateway (see ``docs/工单接口.md``). Missing key → client is disabled and
  ``get_by_code`` returns ``None`` so dev environments can skip integration.
* **Lookup strategy**: the upstream API exposes ``GET /api/customers`` and
  ``GET /api/customers/:id`` (UUID) but **no** ``?code=`` filter. So we fetch
  the list once per request and match on ``customerCode`` client-side. The
  list is small (tens of rows in practice) and the call is already
  short-lived, but if the catalogue ever grows we should add a server-side
  filter rather than cache client-side.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger(__name__)


class GongdanError(Exception):
    """Base exception for gongdan client failures."""


class GongdanUpstreamError(GongdanError):
    """Upstream returned a non-2xx / unparsable response."""


@dataclass(frozen=True, slots=True)
class Customer:
    id: str
    customer_code: str
    name: str
    tier: str | None
    queue_type: str | None
    bound_engineer_id: str | None

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "Customer":
        return cls(
            id=str(payload.get("id") or ""),
            customer_code=str(payload.get("customerCode") or ""),
            name=str(payload.get("name") or ""),
            tier=payload.get("tier"),
            queue_type=payload.get("queueType"),
            bound_engineer_id=payload.get("boundEngineerId"),
        )


class GongdanClient:
    """Thin async client for the gongdan ticket system.

    The caller owns the ``httpx.AsyncClient`` lifetime via :py:meth:`close`.
    """

    def __init__(
        self,
        *,
        base_url: str | None,
        api_key: str | None,
        timeout_sec: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (base_url or "").rstrip("/")
        self._api_key = api_key or ""
        self._timeout = timeout_sec
        # Owned client unless an external one is injected (tests / shared pool).
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_sec)

    def configured(self) -> bool:
        return bool(self._base_url and self._api_key)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_by_id(self, customer_id: str) -> Customer | None:
        """Fetch a single customer by gongdan UUID."""
        if not self.configured() or not customer_id:
            return None
        url = f"{self._base_url}/api/customers/{customer_id}"
        resp = await self._get(url)
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise GongdanUpstreamError(
                f"gongdan get_by_id failed: {resp.status_code} {resp.text[:200]}"
            )
        return Customer.from_api(_parse_json(resp))

    async def get_by_code(self, customer_code: str) -> Customer | None:
        """Resolve ``customer_code`` (``CUST-XXXX``) to a :class:`Customer`.

        Returns ``None`` when the client is not configured, the code is empty,
        or no customer matches. Raises :class:`GongdanUpstreamError` on
        upstream failure so callers can distinguish "missing" from "broken".
        """
        if not self.configured() or not customer_code:
            return None
        url = f"{self._base_url}/api/customers"
        resp = await self._get(url)
        if resp.status_code >= 400:
            raise GongdanUpstreamError(
                f"gongdan list failed: {resp.status_code} {resp.text[:200]}"
            )
        rows = _parse_json(resp)
        if not isinstance(rows, list):
            raise GongdanUpstreamError("gongdan list: expected JSON array")
        target = customer_code.strip()
        for row in rows:
            if isinstance(row, dict) and row.get("customerCode") == target:
                return Customer.from_api(row)
        return None

    async def _get(self, url: str) -> httpx.Response:
        try:
            return await self._client.get(
                url,
                headers={"X-Api-Key": self._api_key},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise GongdanUpstreamError(f"gongdan HTTP error: {exc}") from exc


def _parse_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError as exc:
        raise GongdanUpstreamError(f"gongdan: invalid JSON body: {exc}") from exc
