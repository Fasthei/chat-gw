#!/usr/bin/env python3
"""Emit SQL to register CloudCost routes as `cloud_cost.*` MCP tools.

AI-safety rules (enforced by this importer; failures abort with non-zero exit):

  * Only `GET` methods are allowed. Any `POST/PUT/PATCH/DELETE` → rejected.
  * Path blocklist (substring match, case-insensitive):
      - `/credentials`            secret decryption
      - `/azure-deploy/`          ARM tokens + resource creation
      - `/azure-consent/`         tenant auth grants
      - `/taiji/ingest`           Taiji push channel (service-only)
      - `/admin/users`            user management
      - `/api-keys`               API key management
      - `/api-permissions`        module kill-switches
      - `/customer-assignments`   sales-only writes
      - `/export`                 CSV/XLSX streams — do not fit MCP context
      - `/sync/all`               write / Celery dispatch
      - `/sync/refresh-summary`   write / Celery dispatch
      - `/sync/status/`           Celery status tracking
      - `/sync/logs`              sync log browsing (internal ops)
      - `/discover-gcp-projects`  write / schema mutation
      - `/hard/`                  hard delete
      - `/suspend`                state mutation
      - `/activate`               state mutation
      - `/mark-paid`              bill state mutation
      - `/confirm`                bill state mutation
      - `/adjust`                 bill mutation
      - `/generate`               bill generation
      - `/regenerate`             bill mutation

  * Only `sync/last` is allowed under the `sync` module.
  * `cloud_cost.*` name prefix required.
  * All auth flags forced: `auth_mode='user_passthrough'`,
    `auth_header='Authorization'`, `auth_prefix='Bearer '`,
    `secret_env_name=NULL`. `retries=0` (user_passthrough MUST NOT retry).

Spec (JSON) top-level shape:

    {
      "base_url_env": "CLOUDCOST_API_BASE",
      "timeout_sec": 45,                         # optional, per-tool override wins
      "roles": ["cloud_admin", "cloud_ops",      # default role grants
                "cloud_finance", "cloud_viewer"],
      "tools": [
        {
          "name": "cloud_cost.dashboard_bundle",
          "display_name": "...",
          "description": "...",
          "method": "GET",
          "path": "/api/dashboard/bundle",
          "timeout_sec": 30,                     # optional
          "param_map": {"month": "query"},       # optional
          "body_wrap": null,                     # optional
          "input_schema": {...},
          "output_schema": null,
          "roles": ["cloud_admin", ...]          # optional, overrides default
        }
      ]
    }

Usage:
    python scripts/import_cloudcost_tools.py migrations/seeds/cloud_cost_spec.json \
        > migrations/003_cloud_cost_tools.sql
    psql "$DATABASE_URL_SYNC" -v ON_ERROR_STOP=1 -f migrations/003_cloud_cost_tools.sql

The emitted SQL is transactional and idempotent:
  BEGIN; upsert tool rows; clear stale grants; re-insert grants; COMMIT;
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = {"name", "method", "path"}
NAME_PREFIX = "cloud_cost."
ALLOWED_METHOD = "GET"

# Any path whose *lowercased* form contains one of these substrings is rejected.
PATH_BLOCKLIST: tuple[str, ...] = (
    "/credentials",
    "/azure-deploy/",
    "/azure-consent/",
    "/taiji/ingest",
    "/admin/users",
    "/api-keys",
    "/api-permissions",
    "/customer-assignments",
    "/export",
    "/sync/all",
    "/sync/refresh-summary",
    "/sync/status/",
    "/sync/logs",
    "/discover-gcp-projects",
    "/hard/",
    "/suspend",
    "/activate",
    "/mark-paid",
    "/confirm",
    "/adjust",
    "/generate",
    "/regenerate",
    "/read-all",
    "/unread-count",  # harmless but kept off AI surface; re-add if requested
)

# These paths pass the generic blocklist but we still forbid them because they
# belong to sync write surface or unused AI endpoints.
SYNC_ALLOWED_PATHS = {"/api/sync/last"}


class SpecError(ValueError):
    """Raised when a spec fails validation."""


def _psql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
        return "'" + encoded.replace("'", "''") + "'::jsonb"
    return "'" + str(value).replace("'", "''") + "'"


def _dollar_quote(text: str) -> str:
    """Safe $$...$$ quoting for description blocks; escalates tag on collision."""
    tag = ""
    while f"${tag}$" in text:
        tag = (tag or "x") + "x"
    return f"${tag}${text}${tag}$"


def _assert_not_blocked(name: str, path: str) -> None:
    lower = path.lower()
    for blocked in PATH_BLOCKLIST:
        if blocked in lower:
            raise SpecError(
                f"tool {name!r}: path {path!r} matches forbidden substring {blocked!r}"
            )
    if lower.startswith("/api/sync/") and path not in SYNC_ALLOWED_PATHS:
        raise SpecError(
            f"tool {name!r}: only GET /api/sync/last is allowed in the sync module"
        )


def _assert_method(name: str, method: str) -> None:
    if method.upper() != ALLOWED_METHOD:
        raise SpecError(
            f"tool {name!r}: method {method!r} not allowed (GET only for AI-safe surface)"
        )


def _validate_roles(names: list[str], *, what: str) -> list[str]:
    if not isinstance(names, list) or not names:
        raise SpecError(f"{what} must be a non-empty list of role names")
    allowed = {"cloud_admin", "cloud_ops", "cloud_finance", "cloud_viewer"}
    bad = [r for r in names if not isinstance(r, str) or r not in allowed]
    if bad:
        raise SpecError(f"{what} contains unknown roles: {bad}")
    # Preserve order but de-dup
    seen: set[str] = set()
    out: list[str] = []
    for r in names:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _validate_spec(spec: dict[str, Any]) -> None:
    if not spec.get("base_url_env"):
        raise SpecError("spec.base_url_env is required")
    if spec["base_url_env"] != "CLOUDCOST_API_BASE":
        raise SpecError(
            f"spec.base_url_env must be 'CLOUDCOST_API_BASE' (got {spec['base_url_env']!r})"
        )
    tools = spec.get("tools")
    if not isinstance(tools, list) or not tools:
        raise SpecError("spec.tools must be a non-empty list")
    _validate_roles(spec.get("roles") or [], what="spec.roles")

    seen_names: set[str] = set()
    for i, t in enumerate(tools):
        if not isinstance(t, dict):
            raise SpecError(f"tools[{i}] must be a mapping")
        missing = REQUIRED_FIELDS - t.keys()
        if missing:
            raise SpecError(f"tools[{i}] missing keys: {sorted(missing)}")
        name = str(t["name"])
        if not name.startswith(NAME_PREFIX):
            raise SpecError(
                f"tools[{i}].name must start with {NAME_PREFIX!r} (got {name!r})"
            )
        if name in seen_names:
            raise SpecError(f"duplicate tool name: {name}")
        seen_names.add(name)

        _assert_method(name, str(t["method"]))
        _assert_not_blocked(name, str(t["path"]))

        if "roles" in t:
            _validate_roles(t["roles"], what=f"tools[{i}].roles ({name})")

        param_map = t.get("param_map") or {}
        if not isinstance(param_map, dict):
            raise SpecError(f"tools[{i}].param_map must be a mapping")
        for key, target in param_map.items():
            if not isinstance(target, str) or target not in ("path", "query", "body"):
                raise SpecError(
                    f"tools[{i}].param_map[{key!r}] must be one of "
                    f"'path'|'query'|'body' (got {target!r}); AI-safe tools "
                    "cannot set arbitrary headers"
                )


def _render_insert(tool: dict[str, Any], *, base_url_env: str, timeout_sec: int) -> str:
    config: dict[str, Any] = {
        "base_url_env": base_url_env,
        "method": tool["method"].upper(),
        "path": tool["path"],
        "timeout_sec": int(tool.get("timeout_sec") or timeout_sec),
        "retries": 0,  # user_passthrough MUST NOT retry
    }
    if "param_map" in tool and tool["param_map"]:
        config["param_map"] = tool["param_map"]
    if tool.get("body_wrap"):
        config["body_wrap"] = tool["body_wrap"]

    description = tool.get("description") or f"CloudCost route {tool['path']}"
    display_name = tool.get("display_name") or tool["name"]

    return (
        "INSERT INTO chat_gw.tools\n"
        "    (name, display_name, description, category, dispatcher, config,\n"
        "     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema, output_schema)\n"
        "VALUES (\n"
        f"    {_psql_literal(tool['name'])},\n"
        f"    {_psql_literal(display_name)},\n"
        f"    {_dollar_quote(description)},\n"
        f"    {_psql_literal('cloud_cost')},\n"
        f"    {_psql_literal('http_adapter')},\n"
        f"    {_psql_literal(config)},\n"
        f"    {_psql_literal('user_passthrough')},\n"
        "    NULL,\n"
        f"    {_psql_literal('Authorization')},\n"
        f"    {_psql_literal('Bearer ')},\n"
        f"    {_psql_literal(tool.get('input_schema') or {'type': 'object'})},\n"
        f"    {_psql_literal(tool.get('output_schema'))}\n"
        ")\n"
        "ON CONFLICT (name) DO UPDATE SET\n"
        "    display_name = EXCLUDED.display_name,\n"
        "    description = EXCLUDED.description,\n"
        "    category = EXCLUDED.category,\n"
        "    dispatcher = EXCLUDED.dispatcher,\n"
        "    config = EXCLUDED.config,\n"
        "    auth_mode = EXCLUDED.auth_mode,\n"
        "    secret_env_name = EXCLUDED.secret_env_name,\n"
        "    auth_header = EXCLUDED.auth_header,\n"
        "    auth_prefix = EXCLUDED.auth_prefix,\n"
        "    input_schema = EXCLUDED.input_schema,\n"
        "    output_schema = EXCLUDED.output_schema;"
    )


def _render_grants(tool_name: str, roles: list[str]) -> str:
    roles_sql = ", ".join(_psql_literal(r) for r in roles)
    return (
        f"INSERT INTO chat_gw.tool_role_grants (tool_id, role)\n"
        f"SELECT id, r FROM chat_gw.tools, unnest(ARRAY[{roles_sql}]) AS r\n"
        f"WHERE chat_gw.tools.name = {_psql_literal(tool_name)}\n"
        f"ON CONFLICT DO NOTHING;"
    )


def _render_clear_grants(tool_names: list[str]) -> str:
    names_sql = ", ".join(_psql_literal(n) for n in tool_names)
    return (
        "DELETE FROM chat_gw.tool_role_grants\n"
        f"WHERE tool_id IN (SELECT id FROM chat_gw.tools WHERE name IN ({names_sql}));"
    )


def render_sql(spec: dict[str, Any]) -> str:
    _validate_spec(spec)
    base_url_env = spec["base_url_env"]
    default_timeout = int(spec.get("timeout_sec") or 45)
    default_roles = _validate_roles(spec["roles"], what="spec.roles")

    tool_names = [t["name"] for t in spec["tools"]]

    parts: list[str] = [
        "-- Generated by scripts/import_cloudcost_tools.py — DO NOT HAND-EDIT.",
        "-- Source spec: migrations/seeds/cloud_cost_spec.json",
        "-- AI-safe: GET-only + path blocklist; auth=user_passthrough; retries=0.",
        "BEGIN;",
    ]

    for tool in spec["tools"]:
        parts.append(_render_insert(tool, base_url_env=base_url_env,
                                    timeout_sec=default_timeout))

    # Rebuild grants authoritatively: drop all cloud_cost.* grants we own, re-grant.
    parts.append(_render_clear_grants(tool_names))
    for tool in spec["tools"]:
        roles = tool.get("roles") or default_roles
        roles = _validate_roles(roles, what=f"tools[{tool['name']}].roles")
        parts.append(_render_grants(tool["name"], roles))

    parts.append("COMMIT;")
    return "\n\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CloudCost tool-spec → SQL")
    parser.add_argument("spec_path", type=Path, help="Path to JSON spec")
    args = parser.parse_args(argv)

    try:
        spec = json.loads(args.spec_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"spec file not found: {args.spec_path}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"invalid JSON: {exc}", file=sys.stderr)
        return 2

    try:
        sys.stdout.write(render_sql(spec))
    except SpecError as exc:
        print(f"spec validation error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
