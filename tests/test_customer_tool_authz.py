"""Tests for the principal-based (role OR customer_code) authorization merge."""
from __future__ import annotations

import pytest

from app.registry.cache import ToolCache
from app.registry.service import ToolRegistry
from tests.factories import make_tool_view


pytestmark = pytest.mark.asyncio


def _registry_with_views(views):
    cache = ToolCache(ttl_sec=60)

    async def loader():
        # `_load` in ToolCache maps ToolView.from_model over loader()'s rows.
        # Here we're injecting already-built ToolViews, so we bypass
        # `from_model` by stubbing `_load` on the cache instance.
        return []

    async def _load_stub(_loader):
        cache._tools = list(views)
        cache._by_name = {v.name: v for v in views}
        import time as _t
        cache._loaded_at = _t.monotonic()

    cache.ensure_fresh = _load_stub  # type: ignore[assignment]
    cache.invalidate_and_reload = _load_stub  # type: ignore[assignment]
    return ToolRegistry(cache)


async def test_role_only_grant_visible_to_role_principal() -> None:
    v = make_tool_view(
        name="kb.search",
        roles=frozenset({"cloud_ops"}),
        customer_codes=frozenset(),
    )
    reg = _registry_with_views([v])
    out = await reg.list_for_principal(["cloud_ops"], customer_code=None)
    assert [t.name for t in out] == ["kb.search"]


async def test_customer_only_grant_visible_to_customer_principal() -> None:
    v = make_tool_view(
        name="kb.search",
        roles=frozenset(),
        customer_codes=frozenset({"CUST-AAA"}),
    )
    reg = _registry_with_views([v])

    out = await reg.list_for_principal(roles=[], customer_code="CUST-AAA")
    assert [t.name for t in out] == ["kb.search"]

    out_none = await reg.list_for_principal(roles=[], customer_code=None)
    assert out_none == []

    out_wrong = await reg.list_for_principal(roles=[], customer_code="CUST-ZZZ")
    assert out_wrong == []


async def test_or_union_role_and_customer() -> None:
    role_tool = make_tool_view(
        id=1, name="ops.tool", roles=frozenset({"cloud_ops"}),
        customer_codes=frozenset(),
    )
    cust_tool = make_tool_view(
        id=2, name="cust.tool", roles=frozenset(),
        customer_codes=frozenset({"CUST-AAA"}),
    )
    both_tool = make_tool_view(
        id=3, name="shared.tool", roles=frozenset({"cloud_ops"}),
        customer_codes=frozenset({"CUST-AAA"}),
    )
    reg = _registry_with_views([role_tool, cust_tool, both_tool])

    out = await reg.list_for_principal(["cloud_ops"], "CUST-AAA")
    assert sorted(t.name for t in out) == ["cust.tool", "ops.tool", "shared.tool"]


async def test_find_authorized_for_principal_rejects_unknown_code() -> None:
    v = make_tool_view(
        name="kb.search",
        roles=frozenset(),
        customer_codes=frozenset({"CUST-AAA"}),
    )
    reg = _registry_with_views([v])

    hit = await reg.find_authorized_for_principal("kb.search", [], "CUST-AAA")
    assert hit is not None and hit.name == "kb.search"

    miss = await reg.find_authorized_for_principal("kb.search", [], "CUST-ZZZ")
    assert miss is None

    miss2 = await reg.find_authorized_for_principal("kb.search", [], None)
    assert miss2 is None


async def test_legacy_list_for_roles_preserved() -> None:
    v = make_tool_view(name="kb.search", roles=frozenset({"cloud_ops"}))
    reg = _registry_with_views([v])
    out = await reg.list_for_roles(["cloud_ops"])
    assert [t.name for t in out] == ["kb.search"]
