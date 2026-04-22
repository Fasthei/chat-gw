from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import import_cloudcost_tools as importer


# ─── Happy-path SQL rendering ────────────────────────────────────────

def test_render_sql_emits_insert_and_grants():
    spec = {
        "base_url_env": "CLOUDCOST_API_BASE",
        "timeout_sec": 45,
        "roles": ["cloud_admin", "cloud_ops"],
        "tools": [
            {
                "name": "cloud_cost.dashboard_overview",
                "display_name": "Overview",
                "description": "Account-level summary.",
                "method": "GET",
                "path": "/api/dashboard/overview",
                "param_map": {"month": "query"},
                "input_schema": {"type": "object", "properties": {"month": {"type": "string"}}},
            }
        ],
    }
    sql = importer.render_sql(spec)
    assert "INSERT INTO chat_gw.tools" in sql
    assert "cloud_cost.dashboard_overview" in sql
    assert "'user_passthrough'" in sql
    assert "'Authorization'" in sql
    assert "'Bearer '" in sql
    assert '"retries": 0' in sql
    # Grants are cleared then re-inserted atomically.
    assert "DELETE FROM chat_gw.tool_role_grants" in sql
    assert "INSERT INTO chat_gw.tool_role_grants" in sql
    assert "'cloud_admin'" in sql and "'cloud_ops'" in sql
    assert "cloud_viewer" not in sql


def test_render_sql_honours_per_tool_role_override():
    spec = {
        "base_url_env": "CLOUDCOST_API_BASE",
        "roles": ["cloud_admin", "cloud_ops", "cloud_finance", "cloud_viewer"],
        "tools": [
            {"name": "cloud_cost.dashboard_bundle", "method": "GET",
             "path": "/api/dashboard/bundle"},
            {"name": "cloud_cost.bills_list", "method": "GET", "path": "/api/bills/",
             "roles": ["cloud_admin", "cloud_finance"]},
        ],
    }
    sql = importer.render_sql(spec)
    # The second tool's grant block must not include ops/viewer.
    bills_grant = _extract_grant_block(sql, "cloud_cost.bills_list")
    assert "'cloud_admin'" in bills_grant
    assert "'cloud_finance'" in bills_grant
    assert "'cloud_ops'" not in bills_grant
    assert "'cloud_viewer'" not in bills_grant
    # The first tool gets the default.
    bundle_grant = _extract_grant_block(sql, "cloud_cost.dashboard_bundle")
    for r in ("cloud_admin", "cloud_ops", "cloud_finance", "cloud_viewer"):
        assert f"'{r}'" in bundle_grant


def _extract_grant_block(sql: str, tool_name: str) -> str:
    anchor = f"WHERE chat_gw.tools.name = '{tool_name}'"
    idx = sql.index(anchor)
    start = sql.rfind("INSERT INTO chat_gw.tool_role_grants", 0, idx)
    end = sql.find(";", idx)
    return sql[start : end + 1]


# ─── Validation errors ───────────────────────────────────────────────

def test_render_sql_rejects_non_cloud_cost_name():
    spec = {"base_url_env": "CLOUDCOST_API_BASE",
            "roles": ["cloud_admin"],
            "tools": [{"name": "kb.search", "method": "GET", "path": "/x"}]}
    with pytest.raises(importer.SpecError):
        importer.render_sql(spec)


def test_render_sql_rejects_duplicate_names():
    spec = {
        "base_url_env": "CLOUDCOST_API_BASE",
        "roles": ["cloud_admin"],
        "tools": [
            {"name": "cloud_cost.x", "method": "GET", "path": "/a"},
            {"name": "cloud_cost.x", "method": "GET", "path": "/b"},
        ],
    }
    with pytest.raises(importer.SpecError):
        importer.render_sql(spec)


def test_render_sql_rejects_wrong_base_url_env():
    spec = {
        "base_url_env": "KB_AGENT_URL",
        "roles": ["cloud_admin"],
        "tools": [{"name": "cloud_cost.x", "method": "GET", "path": "/"}],
    }
    with pytest.raises(importer.SpecError):
        importer.render_sql(spec)


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_render_sql_rejects_non_get_method(method):
    spec = {
        "base_url_env": "CLOUDCOST_API_BASE",
        "roles": ["cloud_admin"],
        "tools": [{"name": "cloud_cost.write", "method": method, "path": "/api/bills/"}],
    }
    with pytest.raises(importer.SpecError, match="method"):
        importer.render_sql(spec)


@pytest.mark.parametrize("forbidden_path", [
    "/api/service-accounts/42/credentials",
    "/api/azure-deploy/subscriptions",
    "/api/azure-consent/grant",
    "/api/metering/taiji/ingest",
    "/api/admin/users/1",
    "/api/api-keys/",
    "/api/api-permissions/billing",
    "/api/service-accounts/customer-assignments/sync",
    "/api/billing/export",
    "/api/metering/export",
    "/api/service-accounts/daily-report/export",
    "/api/service-accounts/42/costs/export",
    "/api/sync/all",
    "/api/sync/refresh-summary",
    "/api/sync/status/abc123",
    "/api/sync/logs",
    "/api/service-accounts/discover-gcp-projects",
    "/api/service-accounts/hard/42",
    "/api/service-accounts/42/suspend",
    "/api/service-accounts/42/activate",
    "/api/bills/42/mark-paid",
    "/api/bills/42/confirm",
    "/api/bills/42/adjust",
    "/api/bills/generate",
    "/api/bills/regenerate",
])
def test_render_sql_rejects_blocked_paths(forbidden_path):
    spec = {
        "base_url_env": "CLOUDCOST_API_BASE",
        "roles": ["cloud_admin"],
        "tools": [{"name": "cloud_cost.blocked", "method": "GET", "path": forbidden_path}],
    }
    with pytest.raises(importer.SpecError, match="forbidden|sync"):
        importer.render_sql(spec)


def test_render_sql_rejects_non_last_sync_path():
    spec = {
        "base_url_env": "CLOUDCOST_API_BASE",
        "roles": ["cloud_admin"],
        "tools": [{"name": "cloud_cost.sync_status",
                   "method": "GET",
                   "path": "/api/sync/some-other"}],
    }
    with pytest.raises(importer.SpecError, match="sync"):
        importer.render_sql(spec)


def test_render_sql_accepts_sync_last():
    spec = {
        "base_url_env": "CLOUDCOST_API_BASE",
        "roles": ["cloud_admin", "cloud_ops"],
        "tools": [{"name": "cloud_cost.sync_last", "method": "GET",
                   "path": "/api/sync/last"}],
    }
    sql = importer.render_sql(spec)
    assert "cloud_cost.sync_last" in sql


def test_render_sql_rejects_unknown_role():
    spec = {
        "base_url_env": "CLOUDCOST_API_BASE",
        "roles": ["cloud_admin", "superuser"],
        "tools": [{"name": "cloud_cost.x", "method": "GET", "path": "/api/dashboard/overview"}],
    }
    with pytest.raises(importer.SpecError, match="unknown roles"):
        importer.render_sql(spec)


def test_render_sql_rejects_header_param_map():
    spec = {
        "base_url_env": "CLOUDCOST_API_BASE",
        "roles": ["cloud_admin"],
        "tools": [{"name": "cloud_cost.x", "method": "GET",
                   "path": "/api/dashboard/overview",
                   "param_map": {"foo": "header:X-Injected"}}],
    }
    with pytest.raises(importer.SpecError, match="path|query|body"):
        importer.render_sql(spec)


# ─── Real spec ───────────────────────────────────────────────────────

def _load_real_spec() -> dict:
    path = (
        Path(__file__).resolve().parent.parent
        / "migrations" / "seeds" / "cloud_cost_spec.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_real_spec_renders_and_is_ai_safe():
    spec = _load_real_spec()
    sql = importer.render_sql(spec)

    # Every cloud_cost.* tool must be user_passthrough with retries=0.
    assert "'service_key'" not in sql  # no service_key anywhere in cloud_cost surface
    # Every tool upsert includes the forced auth headers.
    tool_count = sql.count("INSERT INTO chat_gw.tools\n")
    assert tool_count == len(spec["tools"])
    assert sql.count("'user_passthrough'") == tool_count
    # retries:0 appears once per tool config block (sorted JSON).
    assert sql.count('"retries": 0') == tool_count

    # Tool-name cardinality check — must match spec.
    for tool in spec["tools"]:
        assert tool["name"] in sql


def test_real_spec_has_no_forbidden_paths():
    spec = _load_real_spec()
    forbidden_substrings = (
        "/credentials", "/azure-deploy", "/azure-consent", "/taiji/ingest",
        "/admin/users", "/api-keys", "/api-permissions", "/customer-assignments",
        "/export", "/sync/all", "/sync/refresh-summary", "/sync/status",
        "/sync/logs", "/discover-gcp-projects", "/hard/",
        "/suspend", "/activate", "/mark-paid", "/confirm", "/adjust",
        "/generate", "/regenerate",
    )
    for tool in spec["tools"]:
        path = tool["path"].lower()
        for bad in forbidden_substrings:
            assert bad not in path, (
                f"tool {tool['name']} path {path!r} contains forbidden {bad!r}"
            )
        assert tool["method"].upper() == "GET", tool


def test_real_spec_bills_and_categories_are_role_scoped():
    spec = _load_real_spec()
    by_name = {t["name"]: t for t in spec["tools"]}

    # bills.* is cloud_finance + cloud_admin only.
    for n in ("cloud_cost.bills_list", "cloud_cost.bill_get"):
        assert set(by_name[n]["roles"]) == {"cloud_admin", "cloud_finance"}, n

    # admin-only modules:
    for n in (
        "cloud_cost.suppliers_list",
        "cloud_cost.suppliers_supply_sources_all",
        "cloud_cost.supplier_supply_sources",
        "cloud_cost.categories_list",
        "cloud_cost.category_get",
        "cloud_cost.data_sources_list",
        "cloud_cost.data_source_get",
    ):
        assert by_name[n]["roles"] == ["cloud_admin"], n

    # sync_last: admin + ops only.
    assert set(by_name["cloud_cost.sync_last"]["roles"]) == {"cloud_admin", "cloud_ops"}


def test_real_spec_supports_array_query_params():
    spec = _load_real_spec()
    by_name = {t["name"]: t for t in spec["tools"]}
    meter = by_name["cloud_cost.metering_summary"]
    assert meter["param_map"]["account_ids"] == "query"
    assert meter["param_map"]["products"] == "query"
    props = meter["input_schema"]["properties"]
    assert props["account_ids"]["type"] == "array"
    assert props["products"]["type"] == "array"


def test_real_spec_covers_required_endpoints():
    spec = _load_real_spec()
    names = {t["name"] for t in spec["tools"]}
    must_have = {
        # infra
        "cloud_cost.health", "cloud_cost.auth_me", "cloud_cost.sync_last",
        # dashboard
        "cloud_cost.dashboard_bundle", "cloud_cost.dashboard_overview",
        "cloud_cost.dashboard_trend", "cloud_cost.dashboard_by_provider",
        "cloud_cost.dashboard_by_category", "cloud_cost.dashboard_by_project",
        "cloud_cost.dashboard_by_service", "cloud_cost.dashboard_by_region",
        "cloud_cost.dashboard_top_growth", "cloud_cost.dashboard_unassigned",
        # metering
        "cloud_cost.metering_summary", "cloud_cost.metering_daily",
        "cloud_cost.metering_by_service", "cloud_cost.metering_detail",
        "cloud_cost.metering_detail_count", "cloud_cost.metering_products",
        # billing
        "cloud_cost.billing_detail", "cloud_cost.billing_detail_count",
        # service accounts
        "cloud_cost.service_accounts_list", "cloud_cost.service_account_get",
        "cloud_cost.service_account_costs",
        "cloud_cost.service_accounts_daily_report",
        # projects
        "cloud_cost.projects_list", "cloud_cost.project_get",
        # bills (finance)
        "cloud_cost.bills_list", "cloud_cost.bill_get",
        # alerts
        "cloud_cost.alerts_rule_status",
        # suppliers
        "cloud_cost.suppliers_list", "cloud_cost.suppliers_supply_sources_all",
        # categories / exchange_rates / data_sources / resources
        "cloud_cost.categories_list", "cloud_cost.exchange_rates_list",
        "cloud_cost.data_sources_list", "cloud_cost.resources_list",
    }
    missing = must_have - names
    assert not missing, f"spec missing required tools: {missing}"


def test_real_spec_tool_count_matches_generated_sql():
    spec = _load_real_spec()
    sql = importer.render_sql(spec)
    tool_count = sql.count("INSERT INTO chat_gw.tools\n")
    assert tool_count == len(spec["tools"])
    # Must also match the committed SQL file (importer is deterministic).
    committed = (
        Path(__file__).resolve().parent.parent
        / "migrations" / "003_cloud_cost_tools.sql"
    ).read_text(encoding="utf-8")
    assert committed.count("INSERT INTO chat_gw.tools\n") == tool_count


def test_dollar_quote_handles_dollar_text():
    sql = importer._dollar_quote("text with $$ inside")
    assert sql.startswith("$xx$") and sql.endswith("$xx$")
    assert "text with $$ inside" in sql
    assert sql.count("$xx$") == 2
