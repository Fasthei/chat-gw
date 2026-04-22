from __future__ import annotations

import asyncio

import pytest

from app.registry.cache import ToolCache
from app.registry.service import ToolRegistry
from tests.factories import make_tool_view


@pytest.mark.asyncio
async def test_cache_filters_by_role():
    cache = ToolCache(ttl_sec=60)
    tools = [
        make_tool_view(id=1, name="kb.search", roles=frozenset({"cloud_admin", "cloud_viewer"})),
        make_tool_view(
            id=2, name="sales.list_customers", category="sales",
            roles=frozenset({"cloud_admin", "cloud_ops"}),
        ),
    ]

    async def loader():
        return _FakeRows(tools)

    registry = ToolRegistry(cache)
    registry._load = lambda: _fake_awaitable(tools)  # type: ignore[attr-defined]

    viewer_tools = await registry.list_for_roles(["cloud_viewer"])
    assert [t.name for t in viewer_tools] == ["kb.search"]

    admin_tools = await registry.list_for_roles(["cloud_admin"])
    assert {t.name for t in admin_tools} == {"kb.search", "sales.list_customers"}

    none = await registry.list_for_roles([])
    assert none == []


@pytest.mark.asyncio
async def test_find_authorized_denies_when_role_mismatch():
    cache = ToolCache(ttl_sec=60)
    tools = [
        make_tool_view(id=1, name="sales.x", roles=frozenset({"cloud_admin"})),
    ]
    registry = ToolRegistry(cache)
    registry._load = lambda: _fake_awaitable(tools)  # type: ignore[attr-defined]

    found = await registry.find_authorized("sales.x", ["cloud_admin"])
    assert found is not None
    denied = await registry.find_authorized("sales.x", ["cloud_viewer"])
    assert denied is None
    missing = await registry.find_authorized("does.not.exist", ["cloud_admin"])
    assert missing is None


@pytest.mark.asyncio
async def test_list_changed_broadcast_on_force_refresh():
    cache = ToolCache(ttl_sec=60)
    registry = ToolRegistry(cache)
    registry._load = lambda: _fake_awaitable([make_tool_view()])  # type: ignore[attr-defined]

    q = registry.subscribe()
    await registry.force_refresh()
    assert q.get_nowait() == "tools_changed"


# ─── helpers ──────────────────────────────────────────────────────────

class _FakeRows(list):
    pass


async def _fake_awaitable(value):
    await asyncio.sleep(0)
    # Accept ToolView instances as already-materialized rows; the registry's
    # `_load` hook expects ORM rows, so craft a minimal duck-typed facade.
    class _FakeTool:
        def __init__(self, view):
            self.id = view.id
            self.name = view.name
            self.display_name = view.display_name
            self.description = view.description
            self.category = view.category
            self.dispatcher = view.dispatcher
            self.config = view.config
            self.auth_mode = view.auth_mode
            self.secret_env_name = view.secret_env_name
            self.auth_header = view.auth_header
            self.auth_prefix = view.auth_prefix
            self.input_schema = view.input_schema
            self.output_schema = view.output_schema
            self.grants = [_FakeGrant(r) for r in view.roles]

    class _FakeGrant:
        def __init__(self, role):
            self.role = role

    return [_FakeTool(v) for v in value]
