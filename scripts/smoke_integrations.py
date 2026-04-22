#!/usr/bin/env python3
"""Per-tool smoke test against a locally running gateway.

Iterates through every tool the caller's dev token can see (admin role by
default), runs a minimal MCP `tools/call` against each one, and classifies
the response:

    ok              tool returned a result
    denied          -32001 / tool not found or no role
    invalid_params  -32602 / schema / param mapping bug
    config_error    -32603 kind=config_error (missing env var, placeholder …)
    upstream_denied -32001 kind=upstream_denied / remote_mcp_error (4xx auth)
    upstream_error  -32603 kind=upstream_error / upstream_timeout (DNS / 5xx)

Cloud_cost.* tools are skipped by default because they need a real Casdoor
token (user_passthrough) — run with `--include cloud_cost` and pass a
Casdoor bearer via `--token` or the `CLOUD_COST_TEST_TOKEN` env var to
exercise them.

Usage:
    python scripts/smoke_integrations.py
    python scripts/smoke_integrations.py --base http://localhost:8000
    python scripts/smoke_integrations.py --only kb.search,web.search
    python scripts/smoke_integrations.py --include cloud_cost \
        --cloud-cost-token $CASDOOR_TOKEN
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

try:
    import httpx
    from jose import jwt
except ImportError as exc:
    sys.stderr.write(f"missing dependency: {exc}\n")
    sys.stderr.write("run: pip install -r requirements.txt\n")
    raise SystemExit(2)


DEFAULT_BASE = "http://localhost:8000"
DEFAULT_TIMEOUT = 30.0


# ─── Dev token minting ────────────────────────────────────────────────

def mint_dev_token(
    *,
    secret: str,
    roles: list[str],
    subject: str,
    audience: str = "chat-gw",
    issuer: str | None = None,
    ttl_sec: int = 600,
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": subject,
        "roles": roles,
        "email": f"{subject}@smoke.local",
        "name": subject,
        "iat": now,
        "exp": now + ttl_sec,
    }
    if audience:
        payload["aud"] = audience
    if issuer:
        payload["iss"] = issuer
    return jwt.encode(payload, secret, algorithm="HS256")


# ─── Minimal-argument generator ───────────────────────────────────────

# Tool-specific required payload overrides (used when auto-derivation would
# pick values the upstream rejects, e.g. bogus IDs).
_OVERRIDES: dict[str, dict[str, Any]] = {
    "kb.search": {"query": "chat-gw smoke", "top": 1},
    "web.search": {"q": "chat-gw smoke", "num": 1},
    "ticket.list": {"page": 1, "page_size": 1},
    "sales.list_customers": {"page": 1, "page_size": 1},
    "sales.list_allocations": {"page": 1, "page_size": 1},
    "sandbox.run_python": {"code": "print('ok')", "timeout_sec": 5},
    "doc.generate": {"template": "smoke", "context": {"note": "smoke"}, "format": "md"},
    "jina.search": {"query": "chat-gw"},
    "jina.read": {"url": "https://example.com/"},
    "doc.generate": {"prompt": "chat-gw smoke: one-line hello", "output_type": "word"},
    "doc.chat": {"message": "给我一个单页 smoke 测试 word"},
    "doc.generate_ppt": {"prompt": "chat-gw smoke deck", "num_slides": 3},
    "doc.generate_word": {"prompt": "chat-gw smoke word"},
    "doc.generate_table": {"prompt": "chat-gw smoke table", "format": "xlsx"},
    # By-id tools: override with real IDs from the corresponding list endpoints
    # so smoke reflects real backend behaviour rather than 404 for id=1.
    #
    # The list-first approach (smoke resolves IDs dynamically on every run) is
    # intentionally NOT used here: it would double request volume and couple
    # smoke to list response shapes that vary per backend.  Static overrides
    # are fine because the goal of smoke is "every adapter reaches a real
    # backend and returns 2xx / mapped error correctly", not data coverage.
    "ticket.get": {"id": "d0c186cf-0a2b-485f-b9ff-5fa5f89eb2cd"},
    "ticket.list_messages": {"ticket_id": "d0c186cf-0a2b-485f-b9ff-5fa5f89eb2cd"},
    "sales.get_customer": {"id": 2},
    "cloud_cost.service_account_get": {"account_id": 7},
    "cloud_cost.service_account_costs": {
        "account_id": 7, "start_date": "2026-04-01", "end_date": "2026-04-22",
    },
    "cloud_cost.project_get": {"project_id": 7},
    "cloud_cost.project_assignment_logs": {"project_id": 7},
    # bill_get / resource_get: the upstream DB may have no row with these IDs;
    # returning 404 is correct upstream behaviour. Use list endpoints first
    # (cloud_cost.bills_list / resources_list) to decide whether to run them.
    # For smoke we pass id=3 (seen in bills_list) and skip resource_get.
    "cloud_cost.bill_get": {"bill_id": 3},
    # resource_get left to default id=1 — may 404 if table empty, which is OK.
}


def _current_month_placeholder() -> str:
    today = _dt.date.today()
    return today.strftime("%Y-%m")


def _current_date_placeholder() -> str:
    today = _dt.date.today()
    return today.strftime("%Y-%m-%d")


def _fill_required(schema: dict[str, Any]) -> dict[str, Any]:
    """Generate minimum-viable args satisfying `required` fields in a schema."""
    if not schema or schema.get("type") != "object":
        return {}
    required = schema.get("required") or []
    properties = schema.get("properties") or {}
    out: dict[str, Any] = {}
    for key in required:
        spec = properties.get(key) or {}
        out[key] = _value_for(spec, key)
    return out


def _value_for(spec: dict[str, Any], key: str) -> Any:
    if "default" in spec:
        return spec["default"]
    if "enum" in spec and spec["enum"]:
        return spec["enum"][0]
    typ = spec.get("type")
    fmt = spec.get("format")
    pattern = spec.get("pattern")

    if typ == "string":
        if fmt == "date" or "date" in key:
            return _current_date_placeholder()
        if pattern == r"^\d{4}-\d{2}$" or "month" in key:
            return _current_month_placeholder()
        if fmt == "uri":
            return "https://example.com/"
        return "smoke"
    if typ == "integer":
        return int(spec.get("minimum") or 1)
    if typ == "number":
        return float(spec.get("minimum") or 1)
    if typ == "boolean":
        return False
    if typ == "array":
        return []
    if typ == "object":
        return {}
    return None


def build_args(tool_name: str, input_schema: dict[str, Any]) -> dict[str, Any]:
    if tool_name in _OVERRIDES:
        base = dict(_OVERRIDES[tool_name])
    else:
        base = _fill_required(input_schema)
    # Tool-specific adjustments:
    if tool_name in ("cloud_cost.dashboard_bundle", "cloud_cost.dashboard_overview",
                     "cloud_cost.dashboard_by_provider", "cloud_cost.dashboard_by_category",
                     "cloud_cost.dashboard_by_project", "cloud_cost.dashboard_by_service",
                     "cloud_cost.dashboard_by_region", "cloud_cost.dashboard_unassigned",
                     "cloud_cost.bills_list", "cloud_cost.alerts_rule_status"):
        base.setdefault("month", _current_month_placeholder())
    if tool_name in ("cloud_cost.service_account_costs",
                     "cloud_cost.service_accounts_daily_report"):
        base.setdefault("start_date", _current_date_placeholder())
        base.setdefault("end_date", _current_date_placeholder())
    return base


# ─── Result classification ────────────────────────────────────────────

@dataclass
class Outcome:
    tool: str
    status: str
    latency_ms: int
    detail: str = ""


def classify(tool_name: str, args: dict[str, Any], response: dict[str, Any],
             elapsed_ms: int) -> Outcome:
    if "result" in response:
        return Outcome(tool_name, "ok", elapsed_ms, _short_result(response["result"]))
    err = response.get("error") or {}
    code = err.get("code")
    message = err.get("message") or ""
    kind = (err.get("data") or {}).get("kind") or ""
    if code == -32001 and kind == "":
        return Outcome(tool_name, "denied", elapsed_ms, message)
    if code == -32602:
        if kind == "upstream_bad_request":
            return Outcome(tool_name, "upstream_400", elapsed_ms, _trim(message))
        return Outcome(tool_name, "invalid_params", elapsed_ms, _trim(message))
    if kind == "config_error":
        return Outcome(tool_name, "config_error", elapsed_ms, _trim(message))
    if kind in ("upstream_denied", "upstream_not_found", "remote_mcp_error"):
        return Outcome(tool_name, "upstream_denied", elapsed_ms, _trim(message))
    if kind in ("upstream_timeout", "upstream_error", "mcp_proxy_not_ready"):
        return Outcome(tool_name, "upstream_error", elapsed_ms, _trim(message))
    return Outcome(tool_name, "unknown", elapsed_ms, f"code={code} msg={_trim(message)}")


def _short_result(result: Any) -> str:
    try:
        content = result.get("content") if isinstance(result, dict) else None
        if isinstance(content, list) and content:
            text = content[0].get("text", "")
            return _trim(text)
    except Exception:
        pass
    return _trim(json.dumps(result, ensure_ascii=False))


def _trim(text: str, n: int = 110) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


# ─── Driver ───────────────────────────────────────────────────────────

def list_tools(client: httpx.Client, base: str, token: str) -> list[dict[str, Any]]:
    resp = client.post(
        f"{base}/mcp",
        headers={"Authorization": f"Bearer {token}"},
        json={"jsonrpc": "2.0", "id": "list", "method": "tools/list"},
    )
    resp.raise_for_status()
    body = resp.json()
    if "error" in body:
        raise RuntimeError(f"tools/list failed: {body['error']}")
    return body["result"]["tools"]


def call_tool(client: httpx.Client, base: str, token: str,
              name: str, args: dict[str, Any]) -> tuple[dict[str, Any], int]:
    started = time.perf_counter()
    resp = client.post(
        f"{base}/mcp",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "jsonrpc": "2.0",
            "id": uuid4().hex,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        },
    )
    elapsed = int((time.perf_counter() - started) * 1000)
    resp.raise_for_status()
    return resp.json(), elapsed


def print_table(outcomes: list[Outcome]) -> None:
    headers = ("STATUS", "LATENCY", "TOOL", "DETAIL")
    rows = [
        (o.status.upper(), f"{o.latency_ms}ms", o.tool, o.detail)
        for o in outcomes
    ]
    widths = [
        max(len(headers[i]), *(len(r[i]) for r in rows))
        for i in range(len(headers))
    ]
    sep = "  "
    print(sep.join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print(sep.join("-" * widths[i] for i in range(len(headers))))
    for r in rows:
        print(sep.join(r[i].ljust(widths[i]) for i in range(len(headers))))


def summarize(outcomes: list[Outcome]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for o in outcomes:
        counts[o.status] = counts.get(o.status, 0) + 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--base", default=os.environ.get("CHAT_GW_BASE", DEFAULT_BASE))
    parser.add_argument("--secret", default=os.environ.get("JWT_DEV_SECRET",
                                                           "dev-secret-change-me-in-production"))
    parser.add_argument("--audience", default=os.environ.get("JWT_AUDIENCE", "chat-gw"))
    parser.add_argument("--issuer", default=os.environ.get("JWT_ISSUER") or None)
    parser.add_argument("--roles", default="cloud_admin",
                        help="comma-separated role list for the dev token")
    parser.add_argument("--subject", default="smoke-admin")
    parser.add_argument("--only", help="comma-separated tool name filter")
    parser.add_argument(
        "--include", default="",
        help="comma-separated categories to include beyond the default set "
             "(e.g. 'cloud_cost')"
    )
    parser.add_argument("--bearer", default=os.environ.get("CHAT_GW_BEARER"),
                        help="Override caller-side bearer for every tool "
                             "(skips dev-token minting; used when gateway is "
                             "in prod/JWKS mode with a real Casdoor token).")
    parser.add_argument("--cloud-cost-token", default=os.environ.get("CLOUD_COST_TEST_TOKEN"),
                        help="Casdoor bearer for cloud_cost.* user_passthrough")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)

    if args.bearer:
        caller_token = args.bearer
    else:
        roles = [r.strip() for r in args.roles.split(",") if r.strip()]
        caller_token = mint_dev_token(
            secret=args.secret, roles=roles, subject=args.subject,
            audience=args.audience, issuer=args.issuer,
        )
    dev_token = caller_token  # alias used below

    include = {s.strip() for s in args.include.split(",") if s.strip()}
    only_filter = {s.strip() for s in args.only.split(",")} if args.only else None

    with httpx.Client(timeout=args.timeout) as client:
        try:
            tools = list_tools(client, args.base, dev_token)
        except Exception as exc:
            print(f"gateway unreachable at {args.base}: {exc}", file=sys.stderr)
            return 2

        if not tools:
            print("no tools visible to the supplied role(s).", file=sys.stderr)
            return 1

        outcomes: list[Outcome] = []
        for tool in tools:
            name = tool["name"]
            if only_filter and name not in only_filter:
                continue
            category = name.split(".", 1)[0]
            if category == "cloud_cost" and "cloud_cost" not in include:
                continue

            token_for_call = dev_token
            if category == "cloud_cost":
                # cloud_cost.* is user_passthrough: CloudCost itself verifies
                # the forwarded bearer. If a dedicated --cloud-cost-token is
                # supplied use that; else fall back to the general --bearer.
                if args.cloud_cost_token:
                    token_for_call = args.cloud_cost_token
                elif args.bearer:
                    token_for_call = args.bearer
                else:
                    outcomes.append(Outcome(
                        name, "skipped", 0,
                        "cloud_cost.* needs --cloud-cost-token or --bearer",
                    ))
                    continue

            payload = build_args(name, tool.get("inputSchema") or {})
            try:
                body, elapsed = call_tool(client, args.base, token_for_call, name, payload)
            except Exception as exc:
                outcomes.append(Outcome(name, "request_error", 0, _trim(str(exc))))
                continue
            outcomes.append(classify(name, payload, body, elapsed))

    outcomes.sort(key=lambda o: (o.status, o.tool))
    print_table(outcomes)
    summary = summarize(outcomes)
    print()
    print("summary:", ", ".join(f"{k}={v}" for k, v in sorted(summary.items())))
    # Exit non-zero if any hard failure — caller decides what to do about
    # upstream_error / upstream_denied (those are environmental).
    hard_fail_statuses = {"invalid_params", "unknown", "request_error"}
    return 1 if any(o.status in hard_fail_statuses for o in outcomes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
