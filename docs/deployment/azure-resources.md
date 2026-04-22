# chat-gw 生产部署所需 Azure 资源清单

> 目的：告诉基础设施同事"要开哪些 Azure 资源 + 开通哪些网络策略"。
> 价格档位是 v1 最小可生产值，后续可按流量上调。所有真实 secret 走 Key Vault，禁止硬编码。

## 1. 核心资源

| 资源类型 | 推荐名 | SKU / 规格 | 说明 |
|---|---|---|---|
| Resource Group | `rg-chat-gw-prod` | — | 统一租户 |
| **Container Apps Environment** 或 **App Service Plan** | `cae-chat-gw` / `asp-chat-gw-P3v3` | Consumption + workload profiles，或 Linux **P3v3** (**Always On** 打开) | 两种都可以；Container Apps 对 SSE 长连接友好，Web App 有更完整的槽位管理。团队熟哪个选哪个 |
| **Container App** / **Web App** | `ca-chat-gw` / `app-chat-gw` | 1 replica 起步，autoscale 到 3（CPU > 70% 触发） | 跑 `chat-gw:<git-sha>` 镜像；HTTP ingress; TLS enforced; ARR affinity OFF |
| **Azure Database for PostgreSQL Flexible Server** | 复用 `dataope.postgres.database.azure.com` | **独立数据库 `chat_gw`**；Burstable `B2s` 起步 | schema 由 `migrations/001_schema.sql` + `002_seeds.sql` + `003_cloud_cost_tools.sql` 初始化；开启 `CREATE EXTENSION`/trigger 权限（LISTEN/NOTIFY 默认可用） |
| **Azure Cache for Redis** | 复用 `oper.redis.cache.windows.net` | **Standard C1** 以上；TLS-only port 6380 | 仅用作 60s 角色缓存；无持久化要求 |
| **Azure Key Vault** | `chat-gw-kv`（或复用统一 KV） | Standard | 下列所有 secret 集中存放；Web App/Container App 用 Managed Identity 读 |
| **Application Insights** | `appi-chat-gw` | 按量 | `APPLICATIONINSIGHTS_CONNECTION_STRING` 用于日志/trace |
| **Log Analytics Workspace** | 复用区域统一 workspace | 按量 | App Insights 底座 + Container App 日志默认发送 |

## 2. Managed Identity + RBAC

1. 给 Container App / Web App 分配 **system-assigned managed identity**。
2. 在 Key Vault 上赋予该 identity：
   - `get` / `list` Secrets（`Key Vault Secrets User` 角色就够）
3. 如果 Postgres 想走 AAD 鉴权（推荐），给 identity 分配 `postgres_aad_role`；否则 `DATABASE_URL` 用 user:password 方式放在 KV 里也行。

## 3. Key Vault 必须放的 secret

只列名字；值由 ops 填入。

| Key Vault secret name | 对应 App Setting 环境变量 | 用途 |
|---|---|---|
| `database-url-asyncpg` | `DATABASE_URL` | Postgres 连接串（`postgresql+asyncpg://...sslmode=require`） |
| `database-url-sync` | `DATABASE_URL_SYNC` | 执行 `psql` 迁移时用（可选） |
| `redis-url` | `REDIS_URL` | `rediss://:<key>@oper.redis.cache.windows.net:6380/0` |
| `kb-agent-api-key` | `KB_AGENT_API_KEY` | 内部 KB agent `api-key` header |
| `gongdan-api-key` | `GONGDAN_API_KEY` | 工单 `X-Api-Key`（`gd_live_...`，`allowedModules=["ticket"]`） |
| `super-ops-api-key` | `SUPER_OPS_API_KEY` | SuperOps `/api/external` 的 `X-Api-Key` |
| `serper-api-key` | `SERPER_API_KEY` | serper.dev |
| `doc-creator-api-key` | `DOC_CREATOR_API_KEY` | doc-creator `Authorization: Bearer` |
| `daytona-api-token` | `DAYTONA_API_TOKEN` | Daytona `dtn_...` |
| `jina-api-key` | `JINA_API_KEY` | Jina MCP `Authorization: Bearer` |
| `casdoor-client-id` | `CASDOOR_CLIENT_ID` | Casdoor M2M fallback（可选） |
| `casdoor-client-secret` | `CASDOOR_CLIENT_SECRET` | 同上 |

> `SUPER_OPS_API_KEY` 和 `GONGDAN_API_KEY` 是**独立密钥**，与 Casdoor 体系分开轮换。对应的下游服务 `/api/external/*` 或 gongdan `X-Api-Key` 都不认 Casdoor token。

## 4. App Settings（非 secret 类）

直接写明文：

```
APP_ENV=production
LOG_LEVEL=INFO
SERVER_NAME=chat-gw
SERVER_VERSION=<git-sha>

JWT_DEV_SECRET=
JWKS_URL=https://casdoor.ashyglacier-8207efd2.eastasia.azurecontainerapps.io/.well-known/jwks
JWT_ISSUER=https://casdoor.ashyglacier-8207efd2.eastasia.azurecontainerapps.io
JWT_AUDIENCE=<Casdoor 的 clientId，例如使用 LobeChat 自己的 app id>
JWT_LEEWAY_SEC=30
JWKS_CACHE_TTL_SEC=3600
JWKS_REFRESH_COOLDOWN_SEC=30

CASDOOR_ENDPOINT=https://casdoor.ashyglacier-8207efd2.eastasia.azurecontainerapps.io
CASDOOR_ORG=built-in
CASDOOR_APP_NAME=chat-gw
CASDOOR_ROLES_CLAIM=roles

ROLE_CACHE_TTL_SEC=60
REGISTRY_CACHE_TTL_SEC=30
HTTP_DEFAULT_TIMEOUT_SEC=30
HTTP_DEFAULT_RETRIES=2
HTTP_RETRY_BACKOFF_BASE_SEC=0.25
MCP_PROXY_DEFAULT_TIMEOUT_SEC=60
DAYTONA_DEFAULT_TIMEOUT_SEC=60
DAYTONA_MAX_TIMEOUT_SEC=300
ENABLE_MCP_SSE=true

KB_AGENT_URL=https://agnetdoc-cve0guf5h8eggmej.southeastasia-01.azurewebsites.net
GONGDAN_API_BASE=https://gongdan-b5fzbtgteqd5gzfb.eastasia-01.azurewebsites.net
SUPER_OPS_API_BASE=https://xiaoshou-api.braveglacier-e1a32a70.eastasia.azurecontainerapps.io/api/external
SERPER_BASE=https://google.serper.dev
DOC_CREATOR_BASE=http://doc-creator-agent-b0d02105-a557fe.taijiagnet.com
DAYTONA_API_BASE=https://app.daytona.io/api
JINA_MCP_URL=https://mcp.jina.ai/sse
CLOUDCOST_API_BASE=https://cloudcost-brank.yellowground-bf760827.southeastasia.azurecontainerapps.io

APPLICATIONINSIGHTS_CONNECTION_STRING=<App Insights 连接串>
```

secret 用 `@Microsoft.KeyVault(SecretUri=...)` 引用，例如：

```
KB_AGENT_API_KEY=@Microsoft.KeyVault(SecretUri=https://chat-gw-kv.vault.azure.net/secrets/kb-agent-api-key/)
```

## 5. 出站网络白名单

Container App / Web App 需要出站访问：

| 目的 | 协议 / Port |
|---|---|
| `casdoor.ashyglacier-…azurecontainerapps.io` | HTTPS 443 |
| `cloudcost-brank.yellowground-…azurecontainerapps.io` | HTTPS 443 |
| `xiaoshou-api.braveglacier-…azurecontainerapps.io` | HTTPS 443 |
| `gongdan-…azurewebsites.net` | HTTPS 443 |
| `agnetdoc-…azurewebsites.net` | HTTPS 443 |
| `google.serper.dev` | HTTPS 443 |
| `doc-creator-agent-…taijiagnet.com` | HTTP 80 + HTTPS 443（doc-creator 目前是 http）|
| `app.daytona.io` / `*.daytona.io` + `proxy.app.daytona.io` | HTTPS 443 |
| `mcp.jina.ai` | HTTPS 443 |
| Postgres Flexible Server | 5432（私网 / 公网 firewall rule 加网关 outbound IP） |
| Redis Cache | 6380 TLS |
| Key Vault | 443 |
| Application Insights | 443 |

如果用 VNet 集成，给上述 FQDN 开 DNS 私有解析或允许出站。

## 6. 入站与 Ingress

- 只需一个公共 FQDN（例如 `chat-gw.<domain>`）
- TLS：要么用 Container App 自带证书，要么 App Service 绑定自有 CNAME+SNI
- 允许路径：`/healthz` 和 `/readyz` 给平台探针（匿名），`/mcp` 和 `/mcp/sse*` 业务
- **关闭**：`/docs`、`/redoc`、`/openapi.json`（通过 `APP_ENV=production` 也可以手动禁，或 WAF 黑名单）

## 7. 可观测性告警（Application Insights 规则）

| 告警 | 阈值 |
|---|---|
| `requests/failed` 占比 | 5min > 10% → Sev3 |
| `requests/duration` p95 | 5min > 10s → Sev3 |
| `customEvents` name=`authn_failures` | 1min > 20 → Sev2（爆破检测） |
| Container App replica count | 长期 == max_replicas → 扩容 |

## 8. Casdoor 侧依赖（由 Casdoor 管理员执行）

1. 为 chat-gw 创建/确认 application（若与 LobeChat 共用则复用 LobeChat 那个 clientId，把 `JWT_AUDIENCE` 对齐）。
2. 4 个角色存在：`cloud_admin` / `cloud_ops` / `cloud_finance` / `cloud_viewer`。
3. 如果使用 M2M fallback，给 chat-gw 的 M2M account 至少赋一个查询权限角色（默认不用）。

## 9. 一次性资源 provision 脚本骨架（参考）

```bash
az group create -n rg-chat-gw-prod -l eastasia

az keyvault create -n chat-gw-kv -g rg-chat-gw-prod -l eastasia

# （略：Postgres、Redis、Container App Environment、App Insights 按公司模板）

# 发布镜像后
az containerapp create \
  --name ca-chat-gw \
  --resource-group rg-chat-gw-prod \
  --environment cae-chat-gw \
  --image <acr>.azurecr.io/chat-gw:<git-sha> \
  --target-port 8000 --ingress external \
  --min-replicas 1 --max-replicas 3 \
  --env-vars APP_ENV=production LOG_LEVEL=INFO ... \
  --secrets kb-agent-api-key=@Microsoft.KeyVault(...)

az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee $(az containerapp show -n ca-chat-gw -g rg-chat-gw-prod --query identity.principalId -o tsv) \
  --scope $(az keyvault show -n chat-gw-kv --query id -o tsv)
```

## 10. 回滚

镜像级回滚：

```bash
az containerapp update -n ca-chat-gw -g rg-chat-gw-prod \
  --image <acr>.azurecr.io/chat-gw:<prev-git-sha>
```

schema 级：所有迁移都是 `ADD`/幂等，无需回滚 DB。
