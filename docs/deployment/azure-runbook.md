# chat-gw — Azure production deployment runbook

> Target: **Azure Web App for Containers** (P3v3 Linux), backed by Azure
> Database for PostgreSQL Flexible Server, Azure Cache for Redis, Azure
> Key Vault, Azure Monitor / Application Insights, and Casdoor (self-hosted).
>
> Every real secret below is a **placeholder** — substitute values in
> Azure itself (Key Vault + App Settings). Do not commit real values to
> this repository.

## 0. Prerequisites

| Item | Value |
|------|-------|
| Resource group | `rg-chat-gw-prod` |
| Region | e.g. `eastasia` (match LobeChat / Casdoor) |
| Docker image | `chat-gw:<git-sha>` (built via CI from this repo) |
| Python runtime in image | 3.12 (Dockerfile base image) |
| Casdoor | existing tenant; one application `chat-gw` created beforehand |

## 1. Azure resources

Create (or reuse) once:

1. **Azure Key Vault** `chat-gw-kv`
   - Enable "Azure role-based access control".
   - Create access policies for the Web App's managed identity (get/list
     secrets) and for the CI service principal (set secret).
2. **Azure Database for PostgreSQL Flexible Server**
   - Burstable `B2s` is sufficient for v1.
   - Create database `chat_gw` inside.
   - Enable firewall rule for the Web App outbound IPs (or use VNet
     integration).
3. **Azure Cache for Redis**
   - Reuse existing `oper.redis` (Standard C1). TLS-only, port 6380.
4. **Azure Application Insights** `appi-chat-gw`
   - Web application type. Note the connection string.
5. **Azure Web App for Containers** `app-chat-gw`
   - Plan: Linux P3v3, **Always On** enabled, HTTP/2 on.
   - ARR affinity: **off** (MCP sessions reconnect on restart; stateless).
   - Enable managed identity → grant Key Vault access policy.

## 2. Casdoor application

Create `chat-gw` application under the existing organization:

- Redirect URI: `https://lobechat.<domain>/api/auth/callback/casdoor`
- Token format: **JWT**
- Grant types: `authorization_code`, `refresh_token`, `client_credentials`
- Verify the JWT `roles` claim shape with a sample token and record the
  actual key in `CASDOOR_ROLES_CLAIM` (usually `roles`).
- Ensure the 4 roles exist: `cloud_admin` / `cloud_ops` /
  `cloud_finance` / `cloud_viewer`.

Store `client_id`, `client_secret`, and JWKS URL in Key Vault:

```
chat-gw-kv / casdoor-client-id
chat-gw-kv / casdoor-client-secret
```

`jwks_url` typically doesn't need Key Vault — it is a public URL.

## 3. Key Vault secrets

Populate (names are examples; the gateway only reads env var names from
`tools.*.secret_env_name`):

| Key Vault name | Env var (App Setting) consumer |
|----------------|--------------------------------|
| `kb-agent-api-key` | `KB_AGENT_API_KEY` |
| `gongdan-api-key` | `GONGDAN_API_KEY` (scoped `allowedModules=["ticket"]`) |
| `super-ops-api-key` | `SUPER_OPS_API_KEY` |
| `serper-api-key` | `SERPER_API_KEY` |
| `doc-creator-api-key` | `DOC_CREATOR_API_KEY` |
| `daytona-api-token` | `DAYTONA_API_TOKEN` |
| `jina-api-key` | `JINA_API_KEY` |
| `database-url-asyncpg` | `DATABASE_URL` |
| `database-url-sync` | `DATABASE_URL_SYNC` (importer only) |
| `redis-url` | `REDIS_URL` |
| `casdoor-client-id` | `CASDOOR_CLIENT_ID` |
| `casdoor-client-secret` | `CASDOOR_CLIENT_SECRET` |

No real secret values appear in this repository.

## 4. App Settings (environment variables)

Paste into the Web App **Configuration → Application settings**. Values
shown as `@Microsoft.KeyVault(...)` are resolved by Azure at container
start:

```
# Mode
APP_ENV=production
LOG_LEVEL=INFO
SERVER_NAME=chat-gw
SERVER_VERSION=<git-sha>

# JWT — prod mode requires JWKS
JWT_DEV_SECRET=                        # must be empty
JWKS_URL=https://casdoor.<domain>/.well-known/jwks.json
JWT_ISSUER=https://casdoor.<domain>/
JWT_AUDIENCE=chat-gw
JWT_LEEWAY_SEC=30
JWKS_CACHE_TTL_SEC=3600
JWKS_REFRESH_COOLDOWN_SEC=30

# Casdoor fallback for tokens without roles claim
CASDOOR_ENDPOINT=https://casdoor.<domain>
CASDOOR_CLIENT_ID=@Microsoft.KeyVault(SecretUri=https://chat-gw-kv.vault.azure.net/secrets/casdoor-client-id/)
CASDOOR_CLIENT_SECRET=@Microsoft.KeyVault(SecretUri=https://chat-gw-kv.vault.azure.net/secrets/casdoor-client-secret/)
CASDOOR_ORG=<casdoor-org>
CASDOOR_APP_NAME=chat-gw
CASDOOR_ROLES_CLAIM=roles

# Data
DATABASE_URL=@Microsoft.KeyVault(SecretUri=https://chat-gw-kv.vault.azure.net/secrets/database-url-asyncpg/)
REDIS_URL=@Microsoft.KeyVault(SecretUri=https://chat-gw-kv.vault.azure.net/secrets/redis-url/)
ROLE_CACHE_TTL_SEC=60
REGISTRY_CACHE_TTL_SEC=30

# HTTP dispatcher
HTTP_DEFAULT_TIMEOUT_SEC=30
HTTP_DEFAULT_RETRIES=2
HTTP_RETRY_BACKOFF_BASE_SEC=0.25
MCP_PROXY_DEFAULT_TIMEOUT_SEC=60
DAYTONA_DEFAULT_TIMEOUT_SEC=60
DAYTONA_MAX_TIMEOUT_SEC=300

# Transports
ENABLE_MCP_SSE=true

# Downstream service secrets (every one via KV reference)
KB_AGENT_URL=https://kb-agent.<domain>
KB_AGENT_API_KEY=@Microsoft.KeyVault(SecretUri=https://chat-gw-kv.vault.azure.net/secrets/kb-agent-api-key/)
GONGDAN_API_BASE=https://gongdan.<domain>
GONGDAN_API_KEY=@Microsoft.KeyVault(SecretUri=https://chat-gw-kv.vault.azure.net/secrets/gongdan-api-key/)
SUPER_OPS_API_BASE=https://xiaoshou-api.<domain>/api/external
SUPER_OPS_API_KEY=@Microsoft.KeyVault(SecretUri=https://chat-gw-kv.vault.azure.net/secrets/super-ops-api-key/)
SERPER_BASE=https://google.serper.dev
SERPER_API_KEY=@Microsoft.KeyVault(SecretUri=https://chat-gw-kv.vault.azure.net/secrets/serper-api-key/)
DOC_CREATOR_BASE=https://doc-creator.<domain>
DOC_CREATOR_API_KEY=@Microsoft.KeyVault(SecretUri=https://chat-gw-kv.vault.azure.net/secrets/doc-creator-api-key/)
DAYTONA_API_BASE=https://app.daytona.io/api
DAYTONA_API_TOKEN=@Microsoft.KeyVault(SecretUri=https://chat-gw-kv.vault.azure.net/secrets/daytona-api-token/)
JINA_MCP_URL=https://mcp.jina.ai/sse
JINA_API_KEY=@Microsoft.KeyVault(SecretUri=https://chat-gw-kv.vault.azure.net/secrets/jina-api-key/)
CLOUDCOST_API_BASE=https://cloudcost.<domain>

# Observability (enables autoinstrumentation through the official extension)
APPLICATIONINSIGHTS_CONNECTION_STRING=<copy-from-appi-chat-gw>
OTEL_RESOURCE_ATTRIBUTES=service.name=chat-gw,service.version=<git-sha>
```

### Production hard-fail matrix

The gateway refuses to start if any of the following is true with
`APP_ENV=production`:

- `JWT_DEV_SECRET` is set (must be empty)
- `JWKS_URL`, `JWT_ISSUER`, `JWT_AUDIENCE`, `DATABASE_URL`, or
  `REDIS_URL` is empty or looks like a placeholder (`example.com`,
  `REPLACE_ME`, `dev-secret`, …)
- `DATABASE_URL` is not a Postgres URL

Source: `app/settings/validation.py::validate_production_settings`
and `app/main.py::_assert_production_ready`. `/readyz` surfaces the same
checks for operator inspection.

## 5. Database setup

Apply the idempotent migration once (and re-run any time the schema
changes):

```bash
psql "$DATABASE_URL_SYNC" -v ON_ERROR_STOP=1 \
  -f migrations/001_schema.sql \
  -f migrations/002_seeds.sql
```

Access: restrict `chat_gw.tool_audit_log` read access to an SRE role —
arguments are logged verbatim and may contain sensitive fields.

## 6. CloudCost import

44 AI-safe `cloud_cost.*` tools are already registered from
`migrations/seeds/cloud_cost_spec.json` (authored against CloudCost's
AI-BRAIN-API v1.1). The committed SQL seed `migrations/003_cloud_cost_tools.sql`
is the artefact applied to Postgres.

### Regenerating the seed

Every time CloudCost ships a new AI-safe endpoint or role shape:

1. Edit `migrations/seeds/cloud_cost_spec.json`.
2. Regenerate:

    ```bash
    python scripts/import_cloudcost_tools.py \
      migrations/seeds/cloud_cost_spec.json \
      > migrations/003_cloud_cost_tools.sql
    ```

3. Apply to the live Postgres:

    ```bash
    psql "$DATABASE_URL_SYNC" -v ON_ERROR_STOP=1 \
      -f migrations/003_cloud_cost_tools.sql
    ```

The importer refuses non-GET methods and any path on the forbidden list
(credentials, `/azure-deploy/*`, `/azure-consent/*`,
`POST /api/metering/taiji/ingest`, sync triggers, exports, admin writes,
etc.). Attempting to slip one through fails the script with a non-zero
exit before any SQL is emitted.

Because every `cloud_cost.*` tool uses `auth_mode=user_passthrough`, the
gateway never stores a CloudCost service key — the caller's Casdoor JWT is
forwarded verbatim. Postgres `LISTEN / NOTIFY` notifies the running
gateway, which refreshes its 30s tool cache and pushes
`notifications/tools/list_changed` to every open MCP session.

### CloudCost specific env vars

```
CLOUDCOST_API_BASE=https://cloudcost-brank.yellowground-bf760827.southeastasia.azurecontainerapps.io
```

No `CLOUDCOST_API_KEY` / token env var is consumed by the gateway — this
is intentional. If an operator sees a `config_error` audit row for
`cloud_cost.*`, check `CLOUDCOST_API_BASE` rather than looking for a
missing service key.

## 7. LobeChat wiring

In LobeChat Container App settings:

```
NEXT_AUTH_SSO_PROVIDERS=casdoor
AUTH_CASDOOR_ISSUER=https://casdoor.<domain>
AUTH_CASDOOR_ID=chat-gw
AUTH_CASDOOR_SECRET=@Microsoft.KeyVault(SecretUri=.../secrets/casdoor-client-secret/)
```

Admin panel → MCP servers → add endpoint
`https://app-chat-gw.azurewebsites.net/mcp/sse` (or `/mcp` for newer
LobeChat builds using Streamable HTTP). Authorization header flows from
OIDC access_token automatically.

## 8. Observability

- Logs / stdout → Log Analytics via the Web App's container log stream.
- Traces / metrics → Application Insights using the connection string in
  `APPLICATIONINSIGHTS_CONNECTION_STRING`. To add OpenTelemetry exporters
  install `azure-monitor-opentelemetry` in the image (pin in
  `requirements.txt`) and call `configure_azure_monitor()` once in
  `app/main.py::lifespan`. Until then App Insights ingests standard
  Web App request telemetry only.
- Alerts (Application Insights → Metric alerts):
  - `chat_gw.tool_audit_log WHERE status='error'` rate > 10% over 5m
  - p95 `request duration` > 10s over 5m
  - `authn_failures` counter > 20 per minute (abuse detection)
- Dashboard:
  - tool_calls_total grouped by `tool_name`, `status`
  - tool_latency_ms histogram
  - auth cache hit ratio

## 9. Smoke test after deployment

```bash
APP=https://app-chat-gw.azurewebsites.net
curl -fsS $APP/healthz
curl -fsS $APP/readyz | jq .status
# Expect "ready" and every check OK.

# LobeChat admin → send one "hello" through MCP; verify a row lands in
# chat_gw.tool_audit_log with status=ok.
```

## 10. Rollback

```bash
az webapp config container set --name app-chat-gw \
  --resource-group rg-chat-gw-prod \
  --docker-custom-image-name chat-gw:<previous-git-sha>
az webapp restart --name app-chat-gw --resource-group rg-chat-gw-prod
```

Schema changes are additive and idempotent; a rollback of the image does
not require a database rollback in v1.
