# chat-gw 设计文档

> **状态**：Draft（待实现）
> **日期**：2026-04-22
> **作者**：设计会议（Claude + 用户协作完成）
> **关联文档**：`EXTERNAL_SERVICES.md` · `AI-BRAIN-API.md` · `SUPER_OPS_API(1).md` · `工单接口.md`

---

## 0. 摘要

`chat-gw` 是一个**基于 LobeChat 的工具调用网关**（Python + FastAPI，部署于 Azure Web App）。

核心价值：**所有从对话触发的工具调用，都必须先经过 gateway 的 Casdoor 鉴权**，由 gateway 根据用户角色判断是否放行，对 LobeChat UI 表现为"用户只看得到自己有权调用的工具"。

架构骨架：**LobeChat（OIDC 直连 Casdoor）→ MCP 协议 → chat-gw（MCP 聚合/鉴权/分发）→ 各后端工具**。

鉴权模型：**粗粒度在 gateway（tool name × role）+ 细粒度留给工具自己（资源/数据权限不在本网关管）**。

---

## 1. 目标 / 非目标 / v1 范围

### 1.1 目标

1. 为 LobeChat 提供统一的工具调用网关，所有对话触发的 tool 调用都必须经过 gateway。
2. 每次 tool 调用前，gateway 基于用户 Casdoor 身份和角色判断是否允许。
3. `tools/list` 按用户过滤，用户只看到自己有权调用的工具。
4. 把用户真实 Casdoor JWT 原样透传给下游工具（为下游做资源级权限留余地）。
5. 新增/下线工具、调整工具权限不需要改 gateway 代码（走 DB 配置热加载）。

### 1.2 非目标（v1）

- ❌ 不做资源级权限（交给下游工具自己实现）。
- ❌ 不改造 LobeChat UI；LobeChat 只改 Casdoor OIDC + MCP endpoint 配置。
- ❌ 不做 tool 调用计费（预留字段但不实现结算）。
- ❌ 不做多租户；v1 仅一个 Casdoor organization。
- ❌ 不做工具运行结果的二次加工/脱敏（透传）。
- ❌ 不做后台管理 UI；v1 通过 DB SQL 维护注册表。

### 1.3 v1 工具清单（8 类）

| 工具（命名规范 `<domain>.<action>`）| 后端协议 | 认证方式 |
|---|---|---|
| `kb.search` | HTTP POST | service key `api-key` header |
| `jina.search` / `jina.read`（从远程 MCP 动态上架） | MCP（远程 SSE） | jina token |
| `sandbox.run_python` | Daytona HTTP/SDK | service `dtn_...` token |
| `doc.generate` | doc-creator-agent HTTP | service `sk-...` |
| `ticket.list` / `ticket.get` / `ticket.list_messages` | gongdan HTTP | service `gd_live_...`（`allowedModules=["ticket"]`）|
| `web.search` | Serper.dev HTTP | service API key |
| `sales.*`（11 个 1:1 接口） | super-ops HTTP | service `X-Api-Key` |
| `cloud_cost.*`（**全量路由**） | CloudCost HTTP | **user_passthrough**（用户原始 Casdoor JWT） |

`cloud_cost.*` 是唯一 `user_passthrough` 的工具族 —— 利用它自身已有的 Casdoor 数据权限机制。

### 1.4 角色矩阵（v1）

使用现有 4 个 Casdoor 角色：`cloud_admin` / `cloud_ops` / `cloud_finance` / `cloud_viewer`。

| 工具 | admin | ops | finance | viewer |
|---|:-:|:-:|:-:|:-:|
| `kb.search` | ✅ | ✅ | ✅ | ✅ |
| `jina.*` / `web.search` | ✅ | ✅ | ✅ | ✅ |
| `doc.generate` | ✅ | ✅ | ✅ | ❌ |
| `ticket.*` | ✅ | ✅ | ✅ | ❌ |
| `sandbox.run_python` | ✅ | ✅ | ✅ | ✅ |
| `sales.*` | ✅ | ✅ | ❌ | ❌ |
| `cloud_cost.*` | ✅ | ✅ | ✅ | ❌ |

---

## 2. 架构总览

### 2.1 组件拓扑

```
                   ┌─────────────────────────────┐
                   │  Casdoor (OIDC provider)    │
                   │  - /oauth/authorize         │
                   │  - /oauth/token             │
                   │  - /.well-known/jwks.json   │
                   └──────────────┬──────────────┘
                                  │ (1) OIDC login
                                  │ (2) access_token (JWT w/ roles)
                                  ▼
 ┌────────────────────────────┐        ┌───────────────────────────────────┐
 │ LobeChat                   │        │ chat-gw  (Azure Web App, Python)  │
 │ (Azure Container Apps)     │  MCP   │                                   │
 │                            │───────▶│  ┌─────────────────────────────┐  │
 │  - OIDC client (Casdoor)   │ SSE /  │  │ Transport: SSE + Streamable │  │
 │  - MCP client (/sse, /mcp) │ HTTP   │  │   (FastAPI + python-mcp)    │  │
 │  - Bearer: access_token    │        │  └──────────────┬──────────────┘  │
 └────────────────────────────┘        │                 ▼                 │
                                       │  ┌─────────────────────────────┐  │
                                       │  │ Auth Middleware             │  │
                   ┌───────────────────┼──┤  - JWKS verify (local)      │  │
                   │ Redis (roles      │  │  - Redis cache (TTL 60s)    │  │
                   │  cache, 60s TTL)  │  └──────────────┬──────────────┘  │
                   └───────────────────┤                 ▼                 │
                                       │  ┌─────────────────────────────┐  │
                   ┌───────────────────┼──┤ Tool Registry (Postgres)    │  │
                   │ Postgres chat_gw  │  │  - tools / tool_role_grants │  │
                   │  - tools          │  │  - filter tools/list        │  │
                   │  - tool_role_grants│ │  - authorize tools/call     │  │
                   │  - tool_audit_log │  └──────────────┬──────────────┘  │
                   └───────────────────┤                 ▼                 │
                                       │  ┌─────────────────────────────┐  │
                                       │  │ Dispatch Layer              │  │
                                       │  │  ┌──────────┐  ┌─────────┐  │  │
                                       │  │  │ Adapter  │  │  MCP    │  │  │
                                       │  │  │ (HTTP)   │  │  Proxy  │  │  │
                                       │  │  └────┬─────┘  └────┬────┘  │  │
                                       │  └───────┼─────────────┼───────┘  │
                                       └──────────┼─────────────┼──────────┘
                                                  │             │
      ┌────────────┬──────────┬────────────┬──────▼──┬──────────▼────────┐
      ▼            ▼          ▼            ▼         ▼                   ▼
  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌──────────────┐
  │   KB    │ │ Daytona │ │ doc-    │ │ gongdan │ │ xiaoshou │ │ Jina MCP     │
  │ (HTTP)  │ │ (HTTP)  │ │ creator │ │ (HTTP)  │ │ (HTTP)   │ │ (remote MCP) │
  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └──────────┘ └──────────────┘

                   ┌─────────────────────┐
                   │ CloudCost (云管)    │
                   │  Casdoor Bearer     │
                   │  (用户 token 透传)  │
                   └─────────────────────┘
                          ▲
                          │ user token passthrough
                       [Dispatch Layer]
```

### 2.2 组件职责

| 组件 | 职责 | 技术 |
|---|---|---|
| **LobeChat** | 前端对话、MCP client、Casdoor OIDC 登录 | 自托管 Container Apps |
| **Casdoor** | OIDC IdP、发 JWT、角色管理 | 已有 |
| **Gateway Transport** | MCP `/sse` + `/mcp` 两个端点，处理 `initialize`、`tools/list`、`tools/call` | FastAPI + `mcp` (Python SDK) |
| **Gateway Auth** | 本地 JWKS 验签 JWT → user_id；Redis 查/缓存 roles；fallback 回源 Casdoor | `python-jose` + `redis` |
| **Gateway Registry** | 从 Postgres 读 `tools` / `tool_role_grants`，30s TTL + LISTEN/NOTIFY 热失效 | SQLAlchemy + asyncpg |
| **Gateway Dispatch** | 两种 dispatcher：`GenericHttpAdapter`（配置驱动）和 `McpProxy`（远程 MCP 聚合） | `httpx` + `mcp` client |
| **Redis** | roles 缓存 60s TTL | Azure Cache for Redis（现有 `oper.redis`） |
| **Postgres** | `tools` / `tool_role_grants` / `tool_audit_log` | Azure Postgres（新建独立 `chat_gw` 库） |
| **Key Vault** | 所有 secret 的唯一持久位置 | 新建 `chat-gw-kv` |

### 2.3 进程模型

- Gateway 是单个 FastAPI 应用，`uvicorn` on Azure Web App Python 3.12 runtime
- **无状态**，可多实例 scale-out（ARR affinity 关闭，允许 LobeChat 重连到任一实例）
- MCP session 在单一实例内内存中维护，连接断开 LobeChat 会自动重连
- 冷启动 < 3s；`tools/list` < 50ms（Redis 热路径）；`tools/call` overhead（不含下游）< 30ms P95

---

## 3. 请求链路 & 认证

### 3.1 端到端时序

```
User → LobeChat → Casdoor          (OIDC login → access_token JWT)
User → LobeChat → chat-gw           (MCP tools/list, Bearer JWT)
                     │ 1. JWKS verify (local)
                     │ 2. Redis GET roles:<sub> (hit 60s)
                     │ 3. SELECT tools WHERE role ∈ user.roles
                     └──▶ filtered tools[] ← LobeChat 展示

User → LobeChat → chat-gw           (MCP tools/call <name>, Bearer JWT)
                     │ 1-2 同上
                     │ 3. registry.find_authorized(name, roles)
                     │ 4. jsonschema validate
                     │ 5. scan_sensitive_fields(arguments)
                     │ 6. dispatch → Adapter or McpProxy
                     │    - service_key: 读 env → header
                     │    - user_passthrough: inv.auth.raw_token → Authorization
                     │    - 注入 X-Gateway-* headers (informational)
                     │ 7. tool_audit_log INSERT
                     └──▶ result ← LobeChat 回显
```

### 3.2 Casdoor JWT 期望结构

```json
{
  "sub": "user_id_or_name",
  "aud": "chat-gw",
  "iss": "https://casdoor.<domain>/",
  "exp": 1712345678,
  "roles": ["cloud_finance"],
  "owner": "<org-name>",
  "email": "xxx@xxx.com",
  "name": "张三"
}
```

**实际 `roles` claim 名由实现期确认**：通过查询 CloudCost（已使用 Casdoor）的真实 token 样本或 Casdoor application 配置获得，写入 `CASDOOR_ROLES_CLAIM` 环境变量（默认 `roles`）。

### 3.3 认证伪代码

```python
class AuthContext(BaseModel):
    user_id: str
    roles: list[str]
    raw_token: str          # 透传给 cloud_cost.* 用
    email: str | None
    name: str | None

async def authenticate(request: Request) -> AuthContext:
    token = extract_bearer(request)
    if not token:
        raise Unauthorized("missing bearer")

    # 1. 本地 JWKS 验签（启动拉一次，按 kid 查；失败时刷新一次 JWKS）
    claims = jwt_verify(token, jwks_cache.get())
    user_id = claims["sub"]

    # 2. Redis 读 roles
    cached = await redis.get(f"roles:{user_id}")
    if cached:
        roles = json.loads(cached)
    else:
        # 3. 主路径：token claim
        roles = claims.get(settings.CASDOOR_ROLES_CLAIM, [])
        # 4. 空则 fallback Casdoor /api/get-account
        if not roles:
            roles = await casdoor.get_user_roles(user_id)
        await redis.setex(f"roles:{user_id}", 60, json.dumps(roles))

    return AuthContext(user_id=user_id, roles=roles, raw_token=token,
                       email=claims.get("email"), name=claims.get("name"))
```

### 3.4 下游凭证选择

| 工具族 | Gateway → 下游认证 | 理由 |
|---|---|---|
| `cloud_cost.*` | `Authorization: Bearer <用户原始 JWT>` | 下游自行做 per-user 数据权限 |
| `kb.*` | `api-key: <KB_AGENT_API_KEY>` | 服务账号 |
| `ticket.*` | `X-Api-Key: gd_live_...` | 服务账号 |
| `sales.*` | `X-Api-Key: <SUPER_OPS_API_KEY>` | 服务账号 |
| `sandbox.*` | Daytona token | 服务账号 |
| `doc.*` | `sk-...` | 服务账号 |
| `web.*` | Serper key | 服务账号 |
| `jina.*` | Jina token（挂 MCP client config） | 服务账号 |

### 3.5 信息性 Header 注入

每次调用给下游附加：

```
X-Gateway-User-Id:     <casdoor user_id>
X-Gateway-User-Roles:  cloud_finance,cloud_viewer
X-Gateway-Trace-Id:    <uuid>
X-Gateway-Tool-Name:   <tool.name>
```

下游 MAY 消费；不识别直接忽略（HTTP 未知请求头静默放行）。

### 3.6 Secret 管理

- 全部 secret 存 Azure Key Vault（新建 `chat-gw-kv`）
- Web App Application Settings 用 `@Microsoft.KeyVault(SecretUri=...)` 引用
- Azure 启动时解析为明文 env var；gateway 代码只 `os.getenv(...)`，零改动
- DB 中 `tools.secret_env_name` 只存 env var 名，永不存明文

---

## 4. 授权模型 & 数据库 Schema

### 4.1 授权判定

```
SELECT 1 FROM chat_gw.tools t
    JOIN chat_gw.tool_role_grants g ON g.tool_id = t.id
WHERE t.name = :name
  AND t.enabled = true
  AND g.role = ANY(:roles)
LIMIT 1;

miss → 返回 MCP 错误 -32001 "tool 'X' not found"（合并 "不存在" 和 "无权限"，防角色枚举）
hit  → 放行，dispatch
```

### 4.2 Postgres Schema（独立库 `chat_gw`）

```sql
-- 工具定义
CREATE TABLE chat_gw.tools (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(128) UNIQUE NOT NULL,    -- "cloud_cost.dashboard_overview"
    display_name    VARCHAR(255) NOT NULL,
    description     TEXT NOT NULL,                    -- LLM 可见
    category        VARCHAR(64),                      -- "kb"/"sales"/"cloud_cost"/...
    enabled         BOOLEAN NOT NULL DEFAULT true,

    dispatcher      VARCHAR(32) NOT NULL,             -- "http_adapter" | "daytona_sandbox" | "mcp_proxy"
    config          JSONB NOT NULL DEFAULT '{}'::jsonb, -- dispatcher 特定配置

    auth_mode       VARCHAR(32) NOT NULL,             -- "service_key" | "user_passthrough"
    secret_env_name VARCHAR(128),
    auth_header     VARCHAR(128),
    auth_prefix     VARCHAR(32) DEFAULT '',

    input_schema    JSONB NOT NULL,                   -- 暴露给 MCP tools/list
    output_schema   JSONB,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      VARCHAR(128),
    version         INT NOT NULL DEFAULT 1            -- 乐观锁
);
CREATE INDEX idx_tools_enabled ON chat_gw.tools(enabled) WHERE enabled = true;

-- 角色授权
CREATE TABLE chat_gw.tool_role_grants (
    tool_id         BIGINT REFERENCES chat_gw.tools(id) ON DELETE CASCADE,
    role            VARCHAR(64) NOT NULL,
    granted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    granted_by      VARCHAR(128),
    PRIMARY KEY (tool_id, role)
);
CREATE INDEX idx_grants_role ON chat_gw.tool_role_grants(role);

-- 调用审计
CREATE TABLE chat_gw.tool_audit_log (
    id                     BIGSERIAL PRIMARY KEY,
    trace_id               UUID NOT NULL,
    user_id                VARCHAR(128) NOT NULL,
    user_email             VARCHAR(255),
    roles                  TEXT[] NOT NULL,
    tool_name              VARCHAR(128) NOT NULL,
    tool_id                BIGINT,
    arguments              JSONB,                    -- 全量原文，不脱敏
    sensitive_fields_hit   TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    status                 VARCHAR(16) NOT NULL,     -- allowed|denied|error|ok
    deny_reason            VARCHAR(255),
    error_message          TEXT,
    latency_ms             INT,
    started_at             TIMESTAMPTZ NOT NULL,
    finished_at            TIMESTAMPTZ
);
CREATE INDEX idx_audit_user_time ON chat_gw.tool_audit_log(user_id, started_at DESC);
CREATE INDEX idx_audit_tool_time ON chat_gw.tool_audit_log(tool_name, started_at DESC);
```

### 4.3 敏感字段扫描

`arguments` 存全量原文，**不脱敏**。同时记录 `sensitive_fields_hit` 为所有（递归）命中以下正则的 JSON key：

```
/(password|token|secret|api[_-]?key|authorization|credential)/i
```

含义：
- `arguments` 原始审计价值保留
- `sensitive_fields_hit` 让 SRE grep "哪些调用带了敏感字段" 不需要再扫 JSONB
- **审计表访问权限必须严格收敛**（只授给 SRE 读角色）

### 4.4 `tools/listChanged` 热更新

```sql
CREATE FUNCTION chat_gw.notify_tools_changed() RETURNS trigger AS $$
BEGIN
  PERFORM pg_notify('tools_changed', COALESCE(NEW.id, OLD.id)::text);
  RETURN COALESCE(NEW, OLD);
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tools_changed
AFTER INSERT OR UPDATE OR DELETE ON chat_gw.tools
FOR EACH ROW EXECUTE FUNCTION chat_gw.notify_tools_changed();

-- tool_role_grants 同理
```

Gateway 启动后台 task `LISTEN tools_changed`，收到通知：
1. invalidate registry in-memory cache
2. 向所有活跃 MCP session 发 `notifications/tools/list_changed`
3. LobeChat 重调 `tools/list`

### 4.5 配置管理（v1）

- 所有变更走 Alembic 迁移 + SQL 种子文件（`migrations/seeds/tools.sql` 等）
- 运维临时调权限直接 SQL 改表 → Postgres trigger 通知 → gateway 30s 内或立即生效
- v2 再考虑管理 UI

---

## 5. MCP 协议契约

### 5.1 暴露端点

```
https://chat-gw.<domain>/mcp/sse     ← MCP SSE（LobeChat 1.x 主用）
https://chat-gw.<domain>/mcp         ← Streamable HTTP（新版 LobeChat）
https://chat-gw.<domain>/healthz     ← liveness（免鉴权）
https://chat-gw.<domain>/readyz      ← readiness（验 Postgres/Redis/JWKS）
```

### 5.2 方法处理

**`initialize`**：标准 MCP 握手。**在 `initialize` 之前强制 Bearer token 校验**，无/失效 token 直接 close 连接并返回 `401`。认证上下文在 session 存活期间复用。

```json
{
  "protocolVersion": "2024-11-05",
  "serverInfo": {"name": "chat-gw", "version": "0.1.0"},
  "capabilities": {"tools": {"listChanged": true}}
}
```

**`tools/list`**：按 session.auth_context.roles 过滤 → 返回用户可见工具列表。

**`tools/call`**：参见 3.1 时序；伪代码：

```python
async def call_tool(session, name, arguments) -> ToolResult:
    ctx = session.auth_context
    trace_id = uuid.uuid4()
    started = time.time()

    tool = await registry.find_authorized(name, ctx.roles)
    if tool is None:
        await audit.log(trace_id, ctx, name, arguments,
                        status="denied", reason="not_found_or_no_role")
        raise McpError(-32001, f"tool '{name}' not found")

    try:
        jsonschema.validate(arguments, tool.input_schema)
    except ValidationError as e:
        await audit.log(..., status="error", error=str(e))
        raise McpError(-32602, f"invalid params: {e.message}")

    sensitive_hit = scan_sensitive(arguments)
    dispatcher = get_dispatcher(tool.dispatcher)
    try:
        result = await dispatcher.invoke(
            ToolInvocation(tool=tool, arguments=arguments,
                           auth=ctx, trace_id=trace_id))
        status, err = "ok", None
    except ToolError as e:
        status, err, result = "error", str(e), None
    finally:
        await audit.log(trace_id, ctx, name, arguments,
                        status=status, sensitive_fields_hit=sensitive_hit,
                        latency_ms=int((time.time()-started)*1000),
                        error_message=err)
    return result
```

### 5.3 错误码

| code | 含义 | 场景 |
|---|---|---|
| `-32001` | `tool_not_found` | 工具不存在**或**无权限（合并防枚举） |
| `-32602` | `invalid_params` | jsonschema 校验失败 |
| `-32603` | `internal_error` | 下游 5xx / 网络错误 / timeout / adapter bug |
| `-32001` + data | `upstream_denied` | 下游自己返回 403（如 CloudCost 资源权限）原样包装 |

### 5.4 Tool description 模板

```
用途: <一句话>
何时使用: <1-2 条触发场景>
参数说明: <关键参数语义，非 schema 能表达的>
```

示例：
```
用途: 查询超级运营中心的客户列表（只读）。
何时使用: 用户问"某行业的客户"、"未分配的客户"、"最近更新的客户"时。
注意: 结果按更新时间倒序；默认 50 条；用 updated_since 做增量。
```

---

## 6. Tool Adapter 抽象

### 6.1 Dispatcher 接口

```python
# gateway/dispatch/base.py

class ToolInvocation(BaseModel):
    tool: ToolRow
    arguments: dict
    auth: AuthContext
    trace_id: UUID

class Dispatcher(Protocol):
    async def invoke(self, inv: ToolInvocation) -> ToolResult: ...

DISPATCHERS: dict[str, Dispatcher] = {
    "http_adapter":     GenericHttpAdapter(),       # 7 类 HTTP 工具共用单例，靠 tools.config 驱动
    "daytona_sandbox":  DaytonaAdapter(),           # sandbox 专用，使用 Daytona Python SDK
    "mcp_proxy":        McpProxyManager(),          # 聚合多个远程 MCP server，按 config.remote_url 内部路由
}

# tools 行通过 dispatcher 列查上表得到 Dispatcher 实例；所有工具定制化配置 100% 落在 tools.config JSONB 中，不需要额外注册表。
```

### 6.2 通用 HTTP Adapter

```python
class GenericHttpAdapter(Dispatcher):
    """从 tools.config 驱动：URL 模板、method、header、参数映射"""

    async def invoke(self, inv: ToolInvocation) -> ToolResult:
        cfg = inv.tool.config
        base_url = os.environ[cfg["base_url_env"]]
        path = render_template(cfg["path"], inv.arguments)  # /customers/{id}

        if inv.tool.auth_mode == "service_key":
            token = os.environ[inv.tool.secret_env_name]
        else:  # user_passthrough
            token = inv.auth.raw_token

        headers = {
            inv.tool.auth_header: inv.tool.auth_prefix + token,
            "X-Gateway-User-Id":    inv.auth.user_id,
            "X-Gateway-User-Roles": ",".join(inv.auth.roles),
            "X-Gateway-Trace-Id":   str(inv.trace_id),
            "X-Gateway-Tool-Name":  inv.tool.name,
        }

        query, body = split_params(cfg.get("param_map", {}), inv.arguments)

        async with httpx.AsyncClient(timeout=cfg.get("timeout_sec", 30)) as c:
            resp = await c.request(
                cfg["method"], f"{base_url}{path}",
                params=query, json=body, headers=headers,
            )
            resp.raise_for_status()
            return ToolResult(content=[TextContent(text=resp.text)])
```

### 6.3 各工具接入

#### `kb.search`
- dispatcher: `http_adapter`
- config: `{"base_url_env":"KB_AGENT_URL","path":"/api/v1/search","method":"POST","param_in":"body","timeout_sec":15}`
- auth: `service_key`, header=`api-key`, secret=`KB_AGENT_API_KEY`
- input_schema: `{query: string, top?: int, search_mode?: string}`

#### `jina.*`（动态上架）
- dispatcher: `mcp_proxy`, config: `{"remote_url":"https://mcp.jina.ai/sse","auth_env":"JINA_API_KEY","prefix":"jina."}`
- Gateway 启动时作为 MCP **client** 连接远程 Jina，拉 `tools/list` → 按 `jina.<name>` 前缀 **upsert** 到 `chat_gw.tools`，默认授权 4 个角色
- 重连策略：指数退避，最大 60s
- 若远程不可达：标记该工具 `enabled=false`，恢复后自动重置

#### `sandbox.run_python`
- dispatcher: `daytona_sandbox`（使用 Daytona Python SDK 的专用 adapter）
- auth: `service_key`, `secret_env_name=DAYTONA_API_TOKEN`
- input_schema: `{code: string, timeout_sec?: int ≤ 300, stdin?: string}`
- 超时硬上限 300s（Web App 240s HTTP timeout 留余量）；超出 → `-32603 upstream_timeout`

#### `doc.generate`
- dispatcher: `http_adapter`
- config: `{"base_url_env":"DOC_CREATOR_BASE","path":"<TBD>","method":"POST"}`（path + schema 待实现期向 doc-creator 方确认，见 Section 8 #4）
- auth: `service_key`, header=`Authorization`, prefix=`Bearer `, secret=`DOC_CREATOR_API_KEY`
- **依赖**：具体 endpoint + request schema 实现期向 doc-creator 方确认

#### `ticket.list` / `ticket.get` / `ticket.list_messages`
- dispatcher: `http_adapter`
- base: `GONGDAN_API_BASE`
- 3 个独立 tool（1:1 到接口）
- auth: `service_key`, header=`X-Api-Key`, secret=`GONGDAN_API_KEY`
- **依赖**：运维申请专用 `gd_live_...` key，`allowedModules=["ticket"]`

#### `web.search` (Serper)
- dispatcher: `http_adapter`
- config: `{"base_url_env":"SERPER_BASE","path":"/search","method":"POST"}` (base=`https://google.serper.dev`)
- auth: `service_key`, header=`X-API-KEY`, secret=`SERPER_API_KEY`
- input_schema: `{q: string, num?: int}`

#### `sales.*`（11 个 1:1 工具）
- dispatcher: `http_adapter`
- base: `SUPER_OPS_API_BASE` = `https://xiaoshou-api.braveglacier-e1a32a70.eastasia.azurecontainerapps.io/api/external`
- auth: `service_key`, header=`X-Api-Key`, secret=`SUPER_OPS_API_KEY`
- 11 个：
  - `sales.list_customers` → `GET /customers`
  - `sales.get_customer` → `GET /customers/{id}`
  - `sales.list_customer_assignments` → `GET /customers/{id}/assignment-log`
  - `sales.list_customer_insight_runs` → `GET /customers/{id}/insight/runs`
  - `sales.list_customer_insight_facts` → `GET /customers/{id}/insight/facts`
  - `sales.list_allocations` → `GET /allocations`
  - `sales.get_allocation_history` → `GET /allocations/{id}/history`
  - `sales.list_resources` → `GET /resources`
  - `sales.list_sales_users` → `GET /sales/users`
  - `sales.list_sales_rules` → `GET /sales/rules`
  - （`/meta/ping` 不上架）

#### `cloud_cost.*`（**全量路由**）
- dispatcher: `http_adapter`
- auth: **`user_passthrough`**, header=`Authorization`, prefix=`Bearer `
- 路由清单：**实现期从 CloudCost 拿到 `API.md` 全量路由，逐条上架**
- 其自身 Casdoor 鉴权 + `cloud_account_grant` 数据权限保留生效

### 6.4 通用能力

- **HTTP client 池**：`httpx.AsyncClient` 单例、连接复用、TCP keep-alive、HTTP/2
- **超时与重试**：service_key 工具默认 `timeout=30s, retry=2 (502/503/504)`；`user_passthrough`（cloud_cost.*）不重试，避免用户看到重复调用
- **Tracing**：每次调用 `trace_id` + OpenTelemetry span → Azure Application Insights
- **错误归一化**：
  - 下游 401/403 → `-32001 upstream_denied`
  - 下游 404 → `-32001 upstream_not_found`
  - 下游 400 → `-32602 upstream_bad_request`
  - 5xx / timeout → `-32603 upstream_error`

### 6.5 Split-ready 路径

当某个工具要拆成独立 MCP server：

1. 新写独立 `xxx-mcp-server`
2. 改该 tool 的 `dispatcher` 从 `http_adapter` / `daytona_sandbox` → `mcp_proxy`，`config` 改 `{"remote_url":"https://xxx.internal/sse"}`
3. Gateway 零代码改动，注册表 LISTEN/NOTIFY 触发 session 重拉 → 自动切换

`McpProxy` 在 v1 即落地（Jina 使用），这是未来扩展的 escape hatch。

---

## 7. 部署 / 运维 / 可观测 / 测试

### 7.1 Azure 资源

| 资源 | SKU | 用途 |
|---|---|---|
| Azure Web App (Linux, Python 3.12) | **P3v3**（Always On）| Gateway |
| Azure Postgres Flexible Server | 新建 **独立库 `chat_gw`**（可复用实例 `dataope.postgres.database.azure.com`），Burstable B1ms 起步 | registry + audit |
| Azure Cache for Redis | 复用现有 `oper.redis` | roles cache |
| Azure Key Vault | 新建 `chat-gw-kv` | 全部 secret |
| Azure Application Insights | 按量 | logs / trace / metric |
| Casdoor 现有实例 | — | IdP（新建 application） |
| LobeChat Container App | 现有 | 改 2 处配置 |

**网络**：Web App + Container App 同区域公网互通（TLS）。Postgres/Redis 用 firewall rule 放行 Web App outbound IP。

**扩展**：Web App auto-scale 1→3（CPU/内存触发）。Gateway 进程无状态，MCP session 粘在发起实例内存；scale-out 时 ARR affinity 关闭，容忍偶发重连（重连成本低）。

### 7.2 环境变量（全部 Key Vault reference）

```bash
# ─── Casdoor ───
CASDOOR_ENDPOINT=https://casdoor.<domain>
CASDOOR_CLIENT_ID=chat-gw
CASDOOR_CLIENT_SECRET=<kv>
CASDOOR_ORG=<org>
CASDOOR_APP_NAME=chat-gw
CASDOOR_JWKS_URL=https://casdoor.../.well-known/jwks.json
CASDOOR_ROLES_CLAIM=roles          # 实际 key 启动前确认
CASDOOR_ISSUER=https://casdoor.<domain>/
CASDOOR_AUDIENCE=chat-gw

# ─── Storage ───
DATABASE_URL=postgresql+asyncpg://...@dataope.postgres.database.azure.com:5432/chat_gw?sslmode=require
REDIS_URL=rediss://:<pwd>@oper.redis.cache.windows.net:6380/0

# ─── Service secrets (全走 KV ref) ───
KB_AGENT_URL=...
KB_AGENT_API_KEY=<kv>
DAYTONA_API_BASE=https://app.daytona.io/api
DAYTONA_API_TOKEN=<kv>
DOC_CREATOR_BASE=http://doc-creator-agent-b0d02105-a557fe.taijiagnet.com
DOC_CREATOR_API_KEY=<kv>
GONGDAN_API_BASE=https://gongdan-b5fzbtgteqd5gzfb.eastasia-01.azurewebsites.net
GONGDAN_API_KEY=<kv>                # allowedModules=["ticket"] 专用
SERPER_BASE=https://google.serper.dev
SERPER_API_KEY=<kv>
SUPER_OPS_API_BASE=https://xiaoshou-api.braveglacier-e1a32a70.eastasia.azurecontainerapps.io/api/external
SUPER_OPS_API_KEY=<kv>
JINA_API_KEY=<kv>
JINA_MCP_URL=https://mcp.jina.ai/sse

# ─── CloudCost (user passthrough) ───
CLOUDCOST_API_BASE=https://<cloudcost-host>

# ─── Self ───
LOG_LEVEL=INFO
REGISTRY_CACHE_TTL_SEC=30
ROLE_CACHE_TTL_SEC=60
```

### 7.3 Casdoor 配置清单（实现期由 Claude 自行完成，用户提供访问权限）

1. 新建 Application `chat-gw`：
   - Organization: 现有 org
   - Redirect URI: `https://lobechat.<domain>/api/auth/callback/casdoor`
   - Token format: JWT
   - Grant types: `authorization_code`, `refresh_token`, `client_credentials`
2. 确认 JWT claim 包含 `roles`（或记下实际 key 填 `CASDOOR_ROLES_CLAIM`）
3. 确认/创建 4 个角色：`cloud_admin` / `cloud_ops` / `cloud_finance` / `cloud_viewer`
4. 给测试用户每种角色至少 1 人（用于回归 matrix）
5. 拿 `client_id` / `client_secret` / JWKS URL → 存 Key Vault

详细步骤 → `docs/superpowers/runbooks/casdoor-setup.md`（实现期产出）。

### 7.4 LobeChat 侧改动（零源码改动）

1. Container App 环境变量：
   ```bash
   NEXT_AUTH_SSO_PROVIDERS=casdoor
   AUTH_CASDOOR_ISSUER=https://casdoor.<domain>
   AUTH_CASDOOR_ID=chat-gw
   AUTH_CASDOOR_SECRET=<kv>
   ```
2. Admin panel：添加 MCP server 指向 `https://chat-gw.<domain>/mcp/sse`，Authorization 带 OIDC access_token（具体变量名以 LobeChat 实际版本为准，实现期验证）。

### 7.5 可观测

- **日志**：stdout → App Insights。字段：`trace_id` / `user_id` / `tool_name` / `status` / `latency_ms`
- **Metrics**：
  - `chat_gw.tool_calls_total{tool, status}`
  - `chat_gw.tool_latency_ms{tool}` histogram
  - `chat_gw.active_mcp_sessions` gauge
  - `chat_gw.auth_cache_hit_ratio`
- **Trace**：OpenTelemetry（FastAPI + httpx + asyncpg + redis 自动插桩）
- **告警**：
  - `tool_calls_total{status=error}` 5min > 10%
  - P95 latency > 10s 持续 5min
  - `authn_failures` 1min > 20（爆破检测）

### 7.6 测试策略

| 层 | 范围 | 工具 |
|---|---|---|
| **单元** | Auth（JWKS、Redis cache）、Registry 查询、adapter param/header 构造、敏感扫描 | `pytest` + `pytest-asyncio` + `respx` |
| **集成** | MCP 握手、`tools/list` 过滤、`tools/call` 端到端、listChanged、LISTEN/NOTIFY | `pytest` + 真 Postgres + 真 Redis（docker-compose） |
| **契约** | 各下游工具真实调用（测试账号） | `make smoke` 按需跑 |
| **回归** | 4 roles × 全部 tools 的 matrix | `pytest parametrize` |
| **负载** | MCP SSE 长连 + 并发 tools/call（100 并发 / 5min） | `locust` 或 `vegeta` |

**验收基线**：
- 单测 + 集成覆盖率 ≥ 80%
- 回归 matrix 100% pass
- P95 tools/call overhead（不含下游）< 30ms
- 冷启动 < 3s

### 7.7 上线计划

| 阶段 | 时长 | 内容 |
|---|---|---|
| 1 | 1d | Casdoor application + Key Vault + Postgres DB + Web App 基础设施 ready |
| 2 | ~1w | Gateway 代码、集成测试、smoke 打通 |
| 3 | 1d | 灰度：1 个测试 LobeChat 实例 + 2 个测试用户 × 4 角色 |
| 4 | 1d | 正式 LobeChat 切 MCP endpoint，开放给真实用户 |

---

## 8. 依赖与未决项（Open Questions）

| # | 项 | 阻塞等级 | 获取方式 |
|---|---|---|---|
| 1 | CloudCost 完整路由清单（`API.md`）| BLOCKER（v1 要求全量上架） | 实现期向 CloudCost 索取 |
| 2 | Casdoor JWT `roles` claim 实际 key 名 | BLOCKER | 实现期用 CloudCost 样本 token 自查 |
| 3 | Casdoor admin 权限 | BLOCKER（Section 7.3 需要） | 用户提供 |
| 4 | doc-creator-agent 的 endpoint + request schema | HIGH | 实现期向 doc-creator 方确认 |
| 5 | 工单专用 `gd_live_...` key（`allowedModules=["ticket"]`） | HIGH | 用户申请 |
| 6 | LobeChat 版本 & MCP Authorization header 变量名 | MEDIUM | 实现期验证 |
| 7 | Azure Key Vault 是否新建 `chat-gw-kv` | LOW | 实现期决定（默认新建） |

---

## 9. 关键设计决策记录

| # | 决策 | 理由 |
|---|---|---|
| 1 | **架构形态 = B（LobeChat 前端 + 独立 Gateway）+ MCP 作为一等公民** | 覆盖所有工具（非 MCP HTTP 占多数）+ 拥抱 MCP 标准 |
| 2 | **权限模型 = D（粗粒度在 Gateway + 细粒度在工具）** | 职责清晰；复用下游已有数据权限（如 CloudCost `cloud_account_grant`） |
| 3 | **身份传递 = A（LobeChat 直连 Casdoor OIDC）** | 端到端一套身份；token 可无损透传 CloudCost |
| 4 | **语言 = Python + FastAPI** | 与现有后端栈一致；MCP Python SDK 成熟 |
| 5 | **部署 = Azure Web App P3v3** | SSE 长连接友好；Always On；与 LobeChat（Container Apps）公网互通 |
| 6 | **工具注册表 = DB（独立 `chat_gw` 库）** | 增改工具/权限无需发版；SQL 可视可审 |
| 7 | **`tools/list` 按用户过滤** | UI 干净；避免用户看到无权工具 |
| 8 | **MCP 传输 = SSE + Streamable HTTP 双端点** | 兼容新老 LobeChat |
| 9 | **Token 校验 = 本地 JWKS + Redis 60s 缓存** | 性能 + 权限变更 1 分钟内生效 |
| 10 | **工具粒度 = 1 tool : 1 接口** | LLM 在 function calling 中 tool 越明确越好 |
| 11 | **Adapter 策略 = Adapter 单体 + McpProxy 预留，split-ready** | v1 快；未来按需拆独立 MCP server 零成本 |
| 12 | **认证失败 = `-32001 tool_not_found`（合并不存在/无权限）** | 防角色枚举 |
| 13 | **审计 = 全量原文 + sensitive_fields_hit 标记** | 不脱敏保留原始；列名标记方便 SRE grep；审计表访问严格收敛 |
| 14 | **Secret = Azure Key Vault + App Settings KV 引用** | 原生、零代码改动 |
| 15 | **`tools/listChanged` 通知 = Postgres LISTEN/NOTIFY + MCP notifications/tools/list_changed** | 权限调整近实时生效 |
| 16 | **下游注入 X-Gateway-\* header（informational）** | 下游审计支撑；不识别静默放行 |

---

## 10. 不在 v1 的后续项（Parking Lot）

- 管理 UI（增删改工具、查看审计、调权限）
- 工具调用计费 / 配额 / 速率限制
- 多租户 / 多 organization
- 工具结果后处理（二次加工、脱敏、摘要）
- Sandbox 异步长任务执行（>300s）
- 远程 MCP server 拆分（先从 sandbox / jina 以外工具按热点决定）
- OIDC BFF 模式（如未来 LobeChat 不想持有 token）
- 针对数据敏感角色的可疑调用识别（例如 `cloud_finance` 一分钟内批量查 100 账号 → 告警）
