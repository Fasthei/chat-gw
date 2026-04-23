# chat-gw 对接手册（给做 chat 的同事）

> 对接方：LobeChat / 任何 MCP client。
> 版本：0.1.0，2026-04-22。
> 状态：本地 Docker 与 Azure Container App 形态一致；本地已用 admin Casdoor 真实 token 跑通 68/69 工具（1 个是 CloudCost 资源表为空）。

---

## 1. 服务地址

| 环境 | Base URL | 认证 |
|---|---|---|
| 本地开发 | `http://localhost:8000` | HS256 dev token（`JWT_DEV_SECRET`）或 prod 模式下的 Casdoor RS256 |
| 生产（Azure） | `https://<chat-gw-host>.azurecontainerapps.io` | Casdoor RS256 强制 |

HTTP/2 可用；生产必须 HTTPS；ARR affinity 关闭。

## 2. 端点列表

| Method | Path | 用途 | 鉴权 |
|---|---|---|---|
| `GET` | `/healthz` | 存活探测（liveness），永远返回 `{"status":"ok"}` | 匿名 |
| `GET` | `/readyz` | 就绪探测（readiness），检查 PG/Redis/JWKS/工具配置 | 匿名 |
| `POST` | `/mcp` | **MCP Streamable HTTP 主入口**，JSON-RPC 2.0，支持 batch | Bearer JWT |
| `GET`  | `/mcp` | MCP Streamable HTTP 事件流（SSE），向 client 推送 `notifications/tools/list_changed` | Bearer JWT |
| `GET`  | `/mcp/sse` | **MCP SSE 传统传输**（LobeChat 1.x 兼容），返回 `event: endpoint` + `event: message` | Bearer JWT |
| `POST` | `/mcp/sse/messages?session_id=<id>` | SSE 会话下 client 推送 JSON-RPC；返回 202，响应通过 SSE 推回 | 依附于 SSE session |
| `GET`  | `/docs`, `/redoc`, `/openapi.json` | FastAPI 自带文档（仅本地 / 非生产） | 匿名 |

MCP 只需要关注 `/mcp`（Streamable）或 `/mcp/sse`（传统）。

## 3. 认证（Authorization）

### 3.1 Bearer JWT

每一个 `/mcp*` 请求必须带：

```
Authorization: Bearer <JWT>
```

**dev 模式（本地）**：HS256，签名密钥 `JWT_DEV_SECRET`。仓库脚本 `scripts/make_dev_token.py` 可以在本地立刻生成。

**prod 模式（生产 / 本地接真 Casdoor）**：RS256，JWKS 来自 Casdoor：

```
https://casdoor.<domain>/.well-known/jwks
```

token claim 最小集：

| claim | 必须 | 说明 |
|---|---|---|
| `sub` | ✅ | 用户 id / M2M 主体 id |
| `iss` | ✅（prod） | 必须匹配 `JWT_ISSUER` |
| `aud` | ✅（prod） | 必须包含 `JWT_AUDIENCE`（对应 Casdoor `clientId`） |
| `exp` | ✅ | `JWT_LEEWAY_SEC=30` 容差 |
| `roles` | 建议 | Casdoor 可能输出 `[{"name":"cloud_admin",...}]`；网关自动展开为扁平字符串数组 |
| `email`, `name` | 可选 | 审计列 |

### 3.2 角色解析顺序（spec §3.3 口径）

1. **token `roles` claim 非空** → 以此为准，**并覆写** Redis `roles:<sub>` 缓存（TTL 60s）。
2. claim 为空 → 读 Redis 缓存。
3. Redis miss + Casdoor 配置齐 → `GET /api/get-account` fallback。
4. 上述均无 → 返回 0 个工具。

同一 `sub` 先 admin 后 viewer，第二次**不会**继承 admin 缓存。

### 3.3 四个角色

`cloud_admin` / `cloud_ops` / `cloud_finance` / `cloud_viewer`（CloudCost RBAC 对齐）。

## 4. MCP JSON-RPC 协议

### 4.1 `initialize`

```http
POST /mcp
Authorization: Bearer <JWT>
Content-Type: application/json
```

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": { "protocolVersion": "2024-11-05" }
}
```

响应：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "serverInfo": { "name": "chat-gw", "version": "0.1.0" },
    "capabilities": { "tools": { "listChanged": true } }
  }
}
```

### 4.2 `tools/list`

返回**仅**调用方角色可见的工具。响应项：`name` / `description` / `inputSchema`（JSON Schema）。

```json
{ "jsonrpc":"2.0", "id":2, "method":"tools/list" }
```

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      { "name": "kb.search", "description": "用途: 搜索内部知识库...", "inputSchema": { "...": "..." } },
      ...
    ]
  }
}
```

当网关侧工具注册表发生变更（上/下架、权限调整等），网关通过已打开的 SSE 通道下推 `notifications/tools/list_changed`，client 应重调 `tools/list` 刷新缓存。

### 4.3 `tools/call`

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "kb.search",
    "arguments": { "query": "重置密码", "top": 3 }
  }
}
```

成功：

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [ { "type": "text", "text": "<原始 JSON 响应文本>" } ]
  }
}
```

工具内部错误（下游可恢复，e.g. jina 远端返回 `isError:true`）：

```json
{ "result": { "content": [...], "isError": true } }
```

### 4.4 通知

- `notifications/initialized`（client → server）：无需回包。
- `notifications/tools/list_changed`（server → client，SSE 推送）。
- `ping` / `pong`：空 `result`。

## 5. 错误码

| code | 场景 | `error.data.kind` 可能值 |
|---|---|---|
| `-32001` | 工具不存在 **或** 角色不足 **或** 上游 401/403/404 | `not_found` / `no_role` / `upstream_denied` / `upstream_not_found` / `remote_mcp_error` |
| `-32602` | JSON Schema 校验失败 / 上游 400 | `invalid_params` / `upstream_bad_request` |
| `-32603` | 内部错误 / 上游 5xx / 超时 / 配置缺失 | `internal_error` / `upstream_error` / `upstream_timeout` / `config_error` / `mcp_proxy_not_ready` |

**注意**：网关故意把"工具不存在"和"无权限"合并为 `-32001`，防角色枚举。

## 6. 工具目录（截至本版本 69 个）

按 category 分组；名字格式 `<domain>.<action>`。可见性列 A=cloud_admin / O=cloud_ops / F=cloud_finance / V=cloud_viewer。详细 input_schema 直接看 `tools/list` 返回。

### 6.1 kb（1）

| 工具 | A O F V | 说明 |
|---|:-:|---|
| `kb.search` | ✅✅✅✅ | 内部知识库搜索，返回命中文档列表 |

### 6.2 web（1）

| 工具 | A O F V | 说明 |
|---|:-:|---|
| `web.search` | ✅✅✅✅ | Serper 真实 Google 搜索 |

### 6.3 ticket（3，Gongdan 工单系统）

| 工具 | A O F V | 说明 |
|---|:-:|---|
| `ticket.list` | ✅✅✅❌ | 工单列表分页 |
| `ticket.get` | ✅✅✅❌ | 单工单详情（需真工单 id） |
| `ticket.list_messages` | ✅✅✅❌ | 工单消息列表（需真工单 id） |

### 6.4 sales（10，SuperOps 销售平台；/api/external/*）

| 工具 | A O F V | 说明 |
|---|:-:|---|
| `sales.list_customers` | ✅✅❌❌ | 客户列表 |
| `sales.get_customer` | ✅✅❌❌ | 客户详情 |
| `sales.list_customer_assignments` | ✅✅❌❌ | 客户分配历史 |
| `sales.list_customer_insight_runs` | ✅✅❌❌ | 客户 AI 洞察运行记录 |
| `sales.list_customer_insight_facts` | ✅✅❌❌ | 客户 AI 洞察事实库（支持 category 过滤） |
| `sales.list_allocations` | ✅✅❌❌ | 分配记录 |
| `sales.get_allocation_history` | ✅✅❌❌ | 分配变更流水 |
| `sales.list_resources` | ✅✅❌❌ | 货源列表 |
| `sales.list_sales_users` | ✅✅❌❌ | 销售成员 |
| `sales.list_sales_rules` | ✅✅❌❌ | 自动分配规则 |

### 6.5 doc（6，doc-creator agent）

| 工具 | A O F V | 说明 |
|---|:-:|---|
| `doc.generate` | ✅✅✅❌ | 统一入口：`prompt + output_type (ppt|word|table)` → 返回文件 url |
| `doc.generate_ppt` | ✅✅✅❌ | 专用 PPT 生成（`num_slides` 控制页数） |
| `doc.generate_word` | ✅✅✅❌ | 专用 Word 生成 |
| `doc.generate_table` | ✅✅✅❌ | 专用 Excel/CSV 生成（`format: xlsx/csv`） |
| `doc.chat` | ✅✅✅❌ | 自然语言意图 → 自动分派 ppt/word/table |
| `doc.list_files` | ✅✅✅❌ | 列出已生成文件（Blob 模式） |

### 6.6 sandbox（1，Daytona SDK）

| 工具 | A O F V | 说明 |
|---|:-:|---|
| `sandbox.run_python` | ✅✅✅✅ | 在短期 Daytona sandbox 里执行 Python，返回 `{exit_code, result, artifacts}`，硬超时 300s |

### 6.7 jina（3，远端 MCP 代理）

| 工具 | A O F V | 说明 |
|---|:-:|---|
| `jina.search` | ✅✅✅✅ | 远端 `search_web`，Jina 全网检索 |
| `jina.read` | ✅✅✅✅ | 远端 `read_url`，URL → Markdown 正文 |
| `jina.search_images` | ✅✅✅✅ | 远端 `search_images`，图片搜索 |

### 6.8 cloud_cost（44，CloudCost AI-BRAIN-API v1.1）

**特殊点**：`auth_mode=user_passthrough`，调用方的 Casdoor JWT 直接透传给 CloudCost，CloudCost 用自己的 JWKS 校验并基于 `users.roles` + `user_cloud_account_grants` 做数据范围控制。

AI-safe 子集，GET-only；禁止集合（由 importer 强制）：credentials / 任何 POST/PUT/PATCH/DELETE / azure-deploy / azure-consent / taiji ingest / admin users / api-keys / sync 写入 / exports / customer-assignments 等。

| 子类别 | 工具数 | A | O | F | V |
|---|:-:|:-:|:-:|:-:|:-:|
| infra：`health`, `auth_me`, `sync_last` | 3 | ✅ | 部分 | 部分 | 部分 |
| dashboard：`bundle/overview/trend/by-*` | 10 | ✅ | ✅ | ✅ | ✅ |
| metering：`summary/daily/by_service/detail/detail_count/products` | 6 | ✅ | ✅ | ✅ | ✅ |
| billing：`detail/detail_count` | 2 | ✅ | ✅ | ✅ | ✅ |
| service_accounts：`list/get/costs/daily_report` | 4 | ✅ | ✅ | ✅ | ✅（只读） |
| projects：`list/get/assignment_logs` | 3 | ✅ | ✅ | ✅ | ✅ |
| bills：`list/get` | 2 | ✅ | ❌ | ✅ | ❌ |
| alerts：`rule_status/rules_list/history/notifications` | 4 | ✅ | ✅ | ✅ | ✅ |
| resources：`list/get` | 2 | ✅ | ✅ | ✅ | ✅ |
| suppliers：`list/supply_sources_all/supplier_supply_sources` | 3 | ✅ | ❌ | ❌ | ❌ |
| categories：`list/get` | 2 | ✅ | ❌ | ❌ | ❌ |
| exchange_rates：`list` | 1 | ✅ | ✅ | ✅ | ✅ |
| data_sources：`list/get` | 2 | ✅ | ❌ | ❌ | ❌ |

**多选 query 参数**：`cloud_cost.metering_*` 的 `account_ids` / `products` 必须用重复 query 语法（`?account_ids=1&account_ids=2`）；input_schema `type: array` 即可，网关 + httpx 自动展开。

## 7. 最小对接示例

```javascript
// pseudo-code (any MCP client)
const base = "https://chat-gw.internal";
const token = /* 从 Casdoor OIDC 登录获得的 access_token */;

async function mcp(method, params = {}) {
  const resp = await fetch(`${base}/mcp`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ jsonrpc: "2.0", id: Date.now(), method, params }),
  });
  if (resp.status === 401) throw new Error("token expired");
  const body = await resp.json();
  if (body.error) throw new Error(`[${body.error.code}] ${body.error.message}`);
  return body.result;
}

await mcp("initialize", { protocolVersion: "2024-11-05" });
const { tools } = await mcp("tools/list");
console.log(`visible tools: ${tools.length}`);

const { content } = await mcp("tools/call", {
  name: "cloud_cost.dashboard_overview",
  arguments: { month: "2026-04" },
});
console.log(content[0].text);  // JSON string of the overview
```

## 8. 对接检查清单

- [ ] 使用 Casdoor OIDC 登录拿 access_token（**不要**再用 X-Api-Key 之类的本地密钥）
- [ ] 每次 MCP 请求把 `Authorization: Bearer <token>` 带上
- [ ] 处理 401 → 刷 token → 重试
- [ ] 处理 `-32001` 的两种情形（权限不够 vs 工具不存在）— 对用户表现都应是"这个工具/数据不可用"
- [ ] 处理 `-32602` → 修正参数；通常是 JSON Schema 校验失败
- [ ] 处理 `-32603` → 展示"系统繁忙/上游异常"并上报 `error.data.kind`
- [ ] 从 `tools/list` 拿到的 `inputSchema` 做前端/agent 参数校验
- [ ] 订阅 SSE (`GET /mcp` 或 `/mcp/sse`) 接收 `notifications/tools/list_changed`，重新拉 `tools/list`
- [ ] 记录每次 `tools/call` 的 `jsonrpc.id` / client-side request id；排障时交给网关侧 SRE 反查即可（审计链路由网关侧负责，对接方不直连后端）

## 9. Admin API（仅 `cloud_admin`）

管理面，供你们实现"工具目录管理 / 角色授权矩阵 / 审计日志"三个页面用。**所有 `/admin/*` 都复用同一套 Bearer JWT 认证**，没有第二套；额外加一道 `cloud_admin` 角色闸门（非 `cloud_admin` 一律 `403`）。

### 9.1 工具注册表 CRUD

#### `GET /admin/tools?include_disabled=true`

```json
{
  "tools": [
    {
      "name": "kb.search",
      "display_name": "KB Search",
      "description": "用途: 搜索内部知识库…",
      "category": "kb",
      "dispatcher": "http_adapter",
      "config": { "base_url_env": "KB_AGENT_URL", "path": "/api/v1/search", "method": "POST", "timeout_sec": 15 },
      "auth_mode": "service_key",
      "secret_env_name": "KB_AGENT_API_KEY",
      "auth_header": "api-key",
      "auth_prefix": "",
      "input_schema": { "...": "..." },
      "output_schema": null,
      "enabled": true,
      "version": 1,
      "created_at": "2026-04-22T03:35:00Z",
      "updated_at": "2026-04-22T03:35:00Z"
    }
  ]
}
```

`include_disabled=false` 时只返回 `enabled=true` 的行。默认按 `category, name` 排序。

#### `POST /admin/tools`（upsert by `name`）

Body = 完整 tool 定义（省略 `id/version/created_at/updated_at` — 这 4 个由后端管理）：

```json
{
  "name": "cloud_cost.dashboard_overview",
  "display_name": "CloudCost Dashboard Overview",
  "description": "…",
  "category": "cloud_cost",
  "dispatcher": "http_adapter",
  "config": {"base_url_env":"CLOUDCOST_API_BASE","method":"GET","path":"/api/v1/dashboard/overview","timeout_sec":45,"retries":0},
  "auth_mode": "user_passthrough",
  "secret_env_name": null,
  "auth_header": "Authorization",
  "auth_prefix": "Bearer ",
  "input_schema": {"type":"object","properties":{"month":{"type":"string","pattern":"^\\d{4}-\\d{2}$"}},"required":["month"]},
  "output_schema": null,
  "enabled": true
}
```

Response：整行新值。首次插入 `version=1`；每次 upsert `version += 1`。

**约束**：
- `dispatcher` ∈ `http_adapter | mcp_proxy | daytona_sandbox`
- `auth_mode` ∈ `service_key | user_passthrough`
- `name` 是主键、幂等键

#### `PATCH /admin/tools/{name}`

任意字段子集（不含 `name`）。空 body 返回 400。不存在返回 404。

```json
// body
{ "enabled": false, "description": "新说明" }
```

Response：整行新值，`version` 自增。

#### `DELETE /admin/tools/{name}?hard=false`

- 默认 `hard=false` → 软删：`enabled=false`，行保留（可还原）
- `hard=true` → 物理删除；`tool_role_grants` 级联清理

返回 `204`。

### 9.2 角色-工具授权 CRUD

#### `GET /admin/tool-role-grants?role=&tool_name=`

```json
{
  "grants": [
    {"role": "cloud_admin",   "tool_name": "cloud_cost.dashboard_overview"},
    {"role": "cloud_ops",     "tool_name": "sales.list_customers"}
  ]
}
```

可选 `role` / `tool_name` 过滤（精确匹配）。当前生产 220 条（admin 69 / ops 60 / finance 51 / viewer 40）。前端可以用它画 4×69 矩阵。

#### `PUT /admin/tool-role-grants`

```json
{ "role": "cloud_ops", "tool_name": "cloud_cost.bills_list", "granted": true }
```

- `granted: true` → INSERT ON CONFLICT DO NOTHING（幂等，可反复调）
- `granted: false` → DELETE（幂等，删不存在的不报错）

Response：回显同 3 个字段，表示当前意愿的最终状态。

**约束**：`role` ∈ `cloud_admin | cloud_ops | cloud_finance | cloud_viewer`；`tool_name` 必须已存在（否则 `404`）。

#### `DELETE /admin/tool-role-grants?role=&tool_name=`

和 `PUT {..., granted:false}` 等价，返回 `204`。

### 9.3 审计日志查询

#### `GET /admin/audit`

Query 参数（都可选）：

| 参数 | 类型 | 说明 |
|---|---|---|
| `user_id` | string | 精确匹配 `AuthContext.user_id`（等于 JWT `sub`） |
| `tool_name` | string | 精确匹配 |
| `outcome` | `allowed\|denied\|error\|ok` | 单值枚举 |
| `from` | ISO 8601 datetime | `started_at >= from`（含） |
| `to` | ISO 8601 datetime | `started_at < to`（不含） |
| `trace_id` | string | 定位单次调用 |
| `cursor` | opaque string | 上一页 response 的 `next_cursor` |
| `limit` | int | 默认 50，最大 500 |

**分页用 keyset cursor，不是 offset**。响应：

```json
{
  "items": [
    {
      "trace_id": "0c4e…",
      "at": "2026-04-23T10:20:30Z",
      "user_id": "0ab89d4c-9741-4edb-…",
      "user_email": "admin@example.com",
      "roles": ["cloud_admin"],
      "tool_name": "cloud_cost.dashboard_overview",
      "tool_id": 42,
      "outcome": "ok",
      "error_code": null,
      "error_kind": null,
      "latency_ms": 1023,
      "deny_reason": null,
      "error_message": null,
      "sensitive_fields_hit": [],
      "arguments": {"month": "2026-04"}
    }
  ],
  "next_cursor": "eyJhdCI6IjIwMjYt…"
}
```

- `error_code` = JSON-RPC error code（`-32001` / `-32602` / `-32603`）
- `error_kind` = 网关侧分类：`not_found_or_no_role` / `schema_validation` / `upstream_denied` / `upstream_error` / `upstream_timeout` / `config_error` / …
- `sensitive_fields_hit` = 敏感字段 key 名，前端渲染 `arguments` 时建议对这些 key 打码（`arguments` 本身原文保留，spec §4.3）
- 按 `(started_at DESC, id DESC)` 排序

**分页使用方式**：第一页传 `?limit=50`；response 里如果 `next_cursor` 非 null，下一页传 `?limit=50&cursor=<上一页 next_cursor>`；直到 `next_cursor` 为 null。

### 9.4 错误

| HTTP | 场景 |
|---|---|
| `401` | 无 Bearer 或 JWT 无效 |
| `403` | JWT 有效但不含 `cloud_admin` |
| `404` | 工具/授权目标不存在 |
| `400` | 空 PATCH / 无效 cursor |
| `422` | Pydantic schema 拒绝（角色枚举、dispatcher 枚举越界等） |

### 9.5 热更新

写操作（POST/PATCH/DELETE tools、PUT/DELETE grants）成功后：
- 本实例立即刷新 30s 内存缓存
- Postgres 触发 `tools_changed` 通知，其它 gateway 实例 30s 内同步
- 对所有打开 SSE 会话的 client 推送 `notifications/tools/list_changed`

## 10. 故障自查 / 反馈

对接方能自己做的两步：

1. **`GET /readyz`**：4 类检查 —— `postgres` / `redis` / `jwks` / `tools` 都 `ok`/`ok 69` 才算网关侧就绪。收到 503 直接告诉我们，不用猜是哪一层。
2. **`error.data.trace_id`**（未来版本加）：每次 `tools/call` 响应里都会带 `trace_id`；遇到 `-32603` 时把这个 id 给网关侧就能反查全链路。当前版本先记 `jsonrpc id` + 你侧的 request id 即可。

**不要**直接连网关的 Postgres / Redis / 下游后端去排障；这些都是网关内部实现，你只需要面向 `/mcp` 这一个端点。工具增删、权限调整、审计查询都由网关侧 SRE 负责。
