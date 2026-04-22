# chat-gw — MCP tool gateway

Python 3.12 / FastAPI gateway implementing the MCP protocol with Casdoor
role-based tool authorization. Runs locally via Docker; migrates to Azure
Web App (see `docs/superpowers/specs/2026-04-22-chat-gw-design.md` and
`docs/deployment/azure-runbook.md`).

## Architecture at a glance

```
LobeChat ─(Bearer JWT, MCP Streamable HTTP / SSE)─▶ chat-gw ─┬─▶ http_adapter  (kb / ticket / sales / web / doc)
                                                             ├─▶ daytona_sandbox (sandbox.run_python)
                                                             ├─▶ mcp_proxy   (jina.*  — remote MCP server)
                                                             └─▶ cloud_cost.*  (user_passthrough Bearer JWT)
```

Every tool call flows through: **JWT verify → role resolve → registry
authorize → JSON-schema validate → sensitive scan → dispatcher → audit**.

## Layout

```
app/
├── settings/     Pydantic Settings + placeholder/production validators
├── db/           SQLAlchemy async engine + ORM + LISTEN/NOTIFY
├── auth/         JWKS cache, JWT verify (HS256 dev / RS256 prod),
│                 Redis roles cache, Casdoor /api/get-account fallback
├── registry/     30s in-memory tool cache + role-filtered lookup + listChanged broadcast
├── dispatchers/  Dispatcher Protocol
│                 · GenericHttpAdapter (param/path/query/body/header mapping)
│                 · McpProxyAdapter    (remote MCP Streamable HTTP / SSE)
│                 · DaytonaAdapter     (sandbox.run_python, 300s hard cap)
├── mcp/          JSON-RPC handler + /mcp Streamable HTTP + /mcp/sse compat
├── audit/        tool_audit_log writer (allowed|denied|error|ok)
├── api/          health + exception handlers
└── sensitive.py  key-name sensitive field scanner (password|token|secret|api_key|authorization|credential)
```

## Role resolution (authoritative order)

Per spec §3.3 — **token claim always wins over the Redis cache.** The cache
is a fallback for tokens that carry no roles, never an override of fresh
claims.

1. If `claims[CASDOOR_ROLES_CLAIM]` (default `roles`) is non-empty, use
   those roles and overwrite the Redis `roles:<sub>` entry (TTL =
   `ROLE_CACHE_TTL_SEC`, default 60s).
2. If the claim is empty, try the Redis cache.
3. If the cache is empty and Casdoor is configured, fall back to
   `/api/get-account`; otherwise return empty roles (→ 0 tools visible).

A unit test covers the same-`sub` admin→viewer transition; see
`tests/test_auth.py::test_claim_change_same_user_does_not_reuse_old_cache`.

## Quickstart (local Docker)

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps        # app / postgres / redis must all be `healthy`
```

Services (host ports chosen to avoid collisions with common local dev
stacks; adjust in `docker-compose.yml` if needed):

| Service  | In-container | Host |
|----------|:------------:|:----:|
| gateway  | 8000         | 8000 |
| postgres | 5432         | 15432 |
| redis    | 6379         | 16379 |

### Health

```bash
curl -s http://localhost:8000/healthz
curl -s http://localhost:8000/readyz | jq
```

`/readyz` checks Postgres, Redis, JWKS (prod only), production env
presence, and — per tool — whether each referenced env var is present and
not a placeholder.

### Mint a dev JWT

Development mode uses HS256 + `JWT_DEV_SECRET`. Production mode (`APP_ENV=
production`) **refuses to start** if `JWT_DEV_SECRET` is set; it must use
Casdoor JWKS (RS256).

```bash
pip install -r requirements.txt
python scripts/make_dev_token.py                 # cloud_admin
ROLES=cloud_viewer python scripts/make_dev_token.py
SUB=alice ROLES=cloud_ops,cloud_finance python scripts/make_dev_token.py
```

### MCP calls

```bash
TOKEN=$(python scripts/make_dev_token.py)

# initialize
curl -sS -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}' | jq

# tools/list — filtered by the token's roles
curl -sS -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | jq

# tools/call — JSON-schema validated + audited (allowed|denied|error|ok)
curl -sS -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call",
       "params":{"name":"kb.search","arguments":{"query":"reset password","top":3}}}' | jq
```

Legacy SSE endpoint pair (for LobeChat 1.x):
`GET /mcp/sse` opens the stream; `POST /mcp/sse/messages?session_id=…`
sends JSON-RPC; responses arrive on the SSE stream as `event: message`.

## Seeded tools

| Tool                     | Dispatcher       | Auth mode         | Role grants |
|--------------------------|------------------|-------------------|-------------|
| `kb.search`              | http_adapter     | service_key       | all 4 |
| `web.search`             | http_adapter     | service_key       | all 4 |
| `ticket.list`            | http_adapter     | service_key       | admin/ops/finance |
| `ticket.get`             | http_adapter     | service_key       | admin/ops/finance |
| `ticket.list_messages`   | http_adapter     | service_key       | admin/ops/finance |
| `sales.list_customers`   | http_adapter     | service_key       | admin/ops |
| `sales.get_customer`     | http_adapter     | service_key       | admin/ops |
| `sales.list_allocations` | http_adapter     | service_key       | admin/ops |
| `doc.generate`           | http_adapter     | service_key       | admin/ops/finance |
| `sandbox.run_python`     | daytona_sandbox  | service_key       | all 4 |
| `jina.search`            | mcp_proxy        | service_key       | all 4 |
| `jina.read`              | mcp_proxy        | service_key       | all 4 |
| `cloud_cost.*` (44 tools)| http_adapter     | **user_passthrough** | see CloudCost section |

Every row is upserted idempotently by `migrations/002_seeds.sql`.

### CloudCost (`cloud_cost.*`) — real AI-safe surface, 44 tools

CloudCost routes are now registered from
[`migrations/seeds/cloud_cost_spec.json`](migrations/seeds/cloud_cost_spec.json)
(derived from CloudCost's AI-BRAIN-API v1.1 and integrator handoff).
The committed SQL seed [`migrations/003_cloud_cost_tools.sql`](migrations/003_cloud_cost_tools.sql)
is mounted into Postgres at container init and rebuilt deterministically by:

```bash
python scripts/import_cloudcost_tools.py \
  migrations/seeds/cloud_cost_spec.json \
  > migrations/003_cloud_cost_tools.sql
# apply to an already-running DB:
psql "$DATABASE_URL_SYNC" -v ON_ERROR_STOP=1 -f migrations/003_cloud_cost_tools.sql
```

Every `cloud_cost.*` row is forced to:
- `dispatcher = http_adapter`, `base_url_env = CLOUDCOST_API_BASE`
- `auth_mode = user_passthrough`, `auth_header = Authorization`,
  `auth_prefix = 'Bearer '`, `secret_env_name = NULL`
- `retries = 0` (user-passthrough must never replay a user action)
- `method = GET` (importer rejects anything else)

The importer also enforces a **path blocklist** so the following CloudCost
surfaces can never reach LobeChat through this gateway:

- `/credentials` (secret decryption)
- any `POST / PUT / PATCH / DELETE`
- `/azure-deploy/*`, `/azure-consent/*` (ARM writes)
- `POST /api/metering/taiji/ingest` (service-only push)
- `/admin/users*`, `/api-keys*`, `/api-permissions*`
- `/sync/*` except `GET /api/sync/last`
- `/export` streams (CSV/XLSX unsuitable for model context)
- `/customer-assignments*`, `/discover-gcp-projects`, `/hard/`,
  `/suspend`, `/activate`, `/mark-paid`, `/confirm`, `/adjust`,
  `/generate`, `/regenerate`

Role grants mirror CloudCost's own RBAC (AI-BRAIN-API §1.2 and §10):

| CloudCost module | Roles granted |
|---|---|
| dashboard, metering, billing, alerts, resources, projects (read), service_accounts (read), exchange_rates | cloud_admin + cloud_ops + cloud_finance + cloud_viewer |
| bills | cloud_admin + cloud_finance |
| sync_last | cloud_admin + cloud_ops |
| suppliers, categories, data_sources | cloud_admin only |

Multi-valued query filters (`account_ids`, `products`) are passed as
**repeated query keys** — `?account_ids=1&account_ids=2` — matching
CloudCost v1.1. Verified by `tests/test_array_query_params.py`.

### doc.generate

The gateway side is production-ready and will forward to `DOC_CREATOR_BASE
+ /api/v1/documents/generate`. When doc-creator's real contract diverges,
only `tools.config` + `input_schema` need updating — no code change. Until
the contract lands, calls surface as `-32603 upstream_error` with a
structured audit row.

### jina.*

Proxied to `$JINA_MCP_URL` (default `https://mcp.jina.ai/sse`). The
dispatcher performs the MCP `initialize` handshake once per (remote, auth)
pair, caches `Mcp-Session-Id`, and reuses it for subsequent `tools/call`
requests. Remote's `content[]` is passed through; remote JSON-RPC errors
are mapped to the upstream MCP code so LobeChat sees a proper error.

### sandbox.run_python

`DaytonaAdapter` posts to `DAYTONA_API_BASE + /sandbox/python/run` with a
hard 300s timeout cap. Missing or placeholder `DAYTONA_API_BASE` /
`DAYTONA_API_TOKEN` returns `-32603 config_error` — never a fake success.

## JWT modes

| Mode | Trigger | Signing | Required settings |
|------|---------|---------|-------------------|
| dev  | `JWT_DEV_SECRET` set, `APP_ENV != production` | HS256 | `JWT_DEV_SECRET` |
| prod | `APP_ENV=production` | RS256 via Casdoor JWKS | `JWKS_URL`, `JWT_ISSUER`, `JWT_AUDIENCE` |

`Settings.jwt_mode()` raises at startup when the combination is invalid
(e.g. `JWT_DEV_SECRET` is present in production).

## Tests

```bash
pip install -r requirements.txt
pytest -q                    # full suite; no network, no Postgres, no Redis
```

Coverage includes: JWT HS256/RS256, JWKS kid/cooldown, role resolver
(claim-wins over cache), 30s registry cache + listChanged broadcast,
http/daytona/mcp_proxy dispatchers (param mapping, auth, retries, SSE
parsing, error normalization), audit (allowed/denied/error/ok),
placeholder detection, production fail-closed Settings, CloudCost spec
importer, and ASGI smoke for `/healthz` / `/mcp` / role filtering.

## Production deployment (Azure)

See [`docs/deployment/azure-runbook.md`](docs/deployment/azure-runbook.md)
for:
- Azure Web App / Postgres / Redis / Key Vault / App Insights provisioning
- App Settings (Key Vault reference format)
- `APP_ENV=production` hard-fail matrix
- OpenTelemetry wiring

The Docker image is the same bits across local and Azure. Azure provides
secrets via `@Microsoft.KeyVault(SecretUri=…)` references; the gateway
code only reads `os.environ[...]`.

## What's still expected from upstream providers

| Item | Gateway side | External input needed |
|------|--------------|-----------------------|
| **CloudCost `CLOUDCOST_API_BASE`** | 44 AI-safe tools seeded, user_passthrough bearer wiring verified | Production URL and Casdoor RS256 issuer/audience for prod deploys |
| **Casdoor app** | JWKS/RS256 verifier, roles claim resolver, `/api/get-account` fallback ready | Application registration + role assignments; `CASDOOR_ROLES_CLAIM` override if not `roles` |
| **doc-creator contract** | `doc.generate` wired and schema-validated | Concrete endpoint + payload from doc-creator team |
| **Gongdan ticket key** | Adapter + seed ready | Operations to issue the scoped `gd_live_*` key |
| **Daytona sandbox** | `sandbox.run_python` adapter, 300s cap, fail-closed config check | Real `DAYTONA_API_BASE` + `DAYTONA_API_TOKEN` |
| **Jina MCP** | `jina.search` / `jina.read` mcp_proxy wired with initialize handshake + session caching | Real `JINA_API_KEY` |
| **LobeChat endpoint** | `/mcp` (Streamable HTTP) + `/mcp/sse` both live | LobeChat admin config change to point at gateway |

None of these block local Docker validation — every tool's gateway-side
path is production-grade, fail-closed, and audited.
