-- Seed tools. Idempotent via ON CONFLICT (name).
-- Adding real tool coverage: kb.search, web.search, ticket.*, sales.* subset.
-- Reserved structural TODOs (no wiring): cloud_cost.*, jina.*, sandbox.run_python,
-- doc.generate — explicitly disabled until their real adapters/configs land.

BEGIN;

-- ─── kb.search ────────────────────────────────────────────────────────
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'kb.search',
    'KB Search',
    $$用途: 搜索内部知识库。
何时使用: 用户询问内部文档、流程、规范时。
参数说明: query 为搜索词；top 限制返回条数；search_mode 可选 "hybrid"/"semantic"/"keyword"。$$,
    'kb',
    'http_adapter',
    '{"base_url_env":"KB_AGENT_URL","path":"/api/v1/search","method":"POST","timeout_sec":15}'::jsonb,
    'service_key', 'KB_AGENT_API_KEY', 'api-key', '',
    '{"type":"object","additionalProperties":false,"properties":{"query":{"type":"string","minLength":1},"top":{"type":"integer","minimum":1,"maximum":50,"default":5},"search_mode":{"type":"string","enum":["hybrid","semantic","keyword"],"default":"hybrid"}},"required":["query"]}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

-- ─── web.search (Serper) ──────────────────────────────────────────────
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'web.search',
    'Web Search',
    $$用途: 搜索互联网公开内容。
何时使用: 用户需要查询外部新闻、技术文档、通用信息时。
参数说明: q 为搜索词；num 返回条数 (默认 10)。$$,
    'web',
    'http_adapter',
    '{"base_url_env":"SERPER_BASE","path":"/search","method":"POST","timeout_sec":15}'::jsonb,
    'service_key', 'SERPER_API_KEY', 'X-API-KEY', '',
    '{"type":"object","additionalProperties":false,"properties":{"q":{"type":"string","minLength":1},"num":{"type":"integer","minimum":1,"maximum":100,"default":10}},"required":["q"]}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

-- ─── ticket.list ──────────────────────────────────────────────────────
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'ticket.list',
    'Ticket List',
    $$用途: 查询工单列表。
何时使用: 用户询问工单总览、未处理工单、按状态过滤时。
参数说明: page 从 1 开始；page_size 默认 20；status 可选过滤。$$,
    'ticket',
    'http_adapter',
    '{"base_url_env":"GONGDAN_API_BASE","path":"/api/tickets","method":"GET","timeout_sec":15}'::jsonb,
    'service_key', 'GONGDAN_API_KEY', 'X-Api-Key', '',
    '{"type":"object","additionalProperties":false,"properties":{"page":{"type":"integer","minimum":1,"default":1},"page_size":{"type":"integer","minimum":1,"maximum":100,"default":20},"status":{"type":"string"}}}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

-- ─── ticket.get ───────────────────────────────────────────────────────
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'ticket.get',
    'Ticket Detail',
    $$用途: 查询单个工单详情。
何时使用: 用户提到特定工单 ID，需要查看详细信息时。
参数说明: id 为工单 ID，必填。$$,
    'ticket',
    'http_adapter',
    '{"base_url_env":"GONGDAN_API_BASE","path":"/api/tickets/{id}","method":"GET","timeout_sec":15}'::jsonb,
    'service_key', 'GONGDAN_API_KEY', 'X-Api-Key', '',
    '{"type":"object","additionalProperties":false,"properties":{"id":{"type":"string","minLength":1}},"required":["id"]}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

-- ─── ticket.list_messages ─────────────────────────────────────────────
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'ticket.list_messages',
    'Ticket Messages',
    $$用途: 查询单个工单的对话消息。
何时使用: 用户需要查看工单处理过程中的对话记录时。
参数说明: ticket_id 必填；page/page_size 用于分页。$$,
    'ticket',
    'http_adapter',
    '{"base_url_env":"GONGDAN_API_BASE","path":"/api/tickets/{ticket_id}/messages","method":"GET","timeout_sec":15,"param_map":{"ticket_id":"path","page":"query","page_size":"query"}}'::jsonb,
    'service_key', 'GONGDAN_API_KEY', 'X-Api-Key', '',
    '{"type":"object","additionalProperties":false,"properties":{"ticket_id":{"type":"string","minLength":1},"page":{"type":"integer","minimum":1,"default":1},"page_size":{"type":"integer","minimum":1,"maximum":100,"default":20}},"required":["ticket_id"]}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

-- ─── sales.list_customers ─────────────────────────────────────────────
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sales.list_customers',
    'Sales Customer List',
    $$用途: 查询超级运营中心的客户列表（只读）。
何时使用: 用户问某行业的客户、未分配客户、最近更新客户等。
参数说明: 结果按更新时间倒序；updated_since 用 ISO8601 做增量。$$,
    'sales',
    'http_adapter',
    '{"base_url_env":"SUPER_OPS_API_BASE","path":"/customers","method":"GET","timeout_sec":30}'::jsonb,
    'service_key', 'SUPER_OPS_API_KEY', 'X-Api-Key', '',
    '{"type":"object","additionalProperties":false,"properties":{"page":{"type":"integer","minimum":1,"default":1},"page_size":{"type":"integer","minimum":1,"maximum":200,"default":50},"industry":{"type":"string"},"updated_since":{"type":"string","format":"date-time"},"is_assigned":{"type":"boolean"}}}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

-- ─── sales.get_customer ───────────────────────────────────────────────
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sales.get_customer',
    'Sales Customer Detail',
    $$用途: 查询单个客户详情。
何时使用: 用户提到具体客户 ID 需要详细信息时。
参数说明: id 必填（客户 UUID/主键）。$$,
    'sales',
    'http_adapter',
    '{"base_url_env":"SUPER_OPS_API_BASE","path":"/customers/{id}","method":"GET","timeout_sec":30,"param_map":{"id":"path"}}'::jsonb,
    'service_key', 'SUPER_OPS_API_KEY', 'X-Api-Key', '',
    '{"type":"object","additionalProperties":false,"properties":{"id":{"type":"integer","minimum":1}},"required":["id"]}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

-- ─── sales.list_customer_assignments ─────────────────────────────────
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sales.list_customer_assignments',
    'Sales Customer Assignment Log',
    $$用途: 查询单个客户的商机分配 / 再分配 / 回收历史 (按 id 升序)。
何时使用: 回答"这个客户为什么归了某销售"、"销售变更记录"时。
参数说明: id 必填 (customer_id); trigger 枚举 manual/auto/recycle/import。$$,
    'sales',
    'http_adapter',
    '{"base_url_env":"SUPER_OPS_API_BASE","path":"/customers/{id}/assignment-log","method":"GET","timeout_sec":30,"param_map":{"id":"path"}}'::jsonb,
    'service_key', 'SUPER_OPS_API_KEY', 'X-Api-Key', '',
    '{"type":"object","additionalProperties":false,"properties":{"id":{"type":"integer","minimum":1}},"required":["id"]}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

-- ─── sales.list_customer_insight_runs ─────────────────────────────────
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sales.list_customer_insight_runs',
    'Sales Customer Insight Runs',
    $$用途: 查询客户 AI 洞察 agent 运行列表 (按时间降序)。
何时使用: 需要看某客户最近 N 次 AI 洞察的 summary 和步骤进展。
参数说明: id 必填 (customer_id)。$$,
    'sales',
    'http_adapter',
    '{"base_url_env":"SUPER_OPS_API_BASE","path":"/customers/{id}/insight/runs","method":"GET","timeout_sec":30,"param_map":{"id":"path"}}'::jsonb,
    'service_key', 'SUPER_OPS_API_KEY', 'X-Api-Key', '',
    '{"type":"object","additionalProperties":false,"properties":{"id":{"type":"integer","minimum":1}},"required":["id"]}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

-- ─── sales.list_customer_insight_facts ────────────────────────────────
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sales.list_customer_insight_facts',
    'Sales Customer Insight Facts',
    $$用途: 查询客户事实库 (agent 抓取的结构化事实).
何时使用: 回答客户背景 (basic/people/tech/news/event) 类问题。
参数说明: id 必填; category 可选 (basic|people|tech|news|event|other)。$$,
    'sales',
    'http_adapter',
    '{"base_url_env":"SUPER_OPS_API_BASE","path":"/customers/{id}/insight/facts","method":"GET","timeout_sec":30,"param_map":{"id":"path","category":"query"}}'::jsonb,
    'service_key', 'SUPER_OPS_API_KEY', 'X-Api-Key', '',
    '{"type":"object","additionalProperties":false,"properties":{"id":{"type":"integer","minimum":1},"category":{"type":"string","enum":["basic","people","tech","news","event","other"]}},"required":["id"]}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

-- ─── sales.list_allocations ───────────────────────────────────────────
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sales.list_allocations',
    'Sales Allocations',
    $$用途: 查询销售分配 (客户 → 货源) 列表 (分页 + 增量)。
何时使用: "最近分配"、"按客户看分配"、"含已取消" 等。
参数说明: page/page_size; include_cancelled 含已取消; customer_id 过滤; updated_since ISO8601 增量。$$,
    'sales',
    'http_adapter',
    '{"base_url_env":"SUPER_OPS_API_BASE","path":"/allocations","method":"GET","timeout_sec":30}'::jsonb,
    'service_key', 'SUPER_OPS_API_KEY', 'X-Api-Key', '',
    '{"type":"object","additionalProperties":false,"properties":{"page":{"type":"integer","minimum":1,"default":1},"page_size":{"type":"integer","minimum":1,"maximum":500,"default":50},"include_cancelled":{"type":"boolean","default":false},"customer_id":{"type":"integer","minimum":1},"updated_since":{"type":"string","format":"date-time"}}}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

-- ─── sales.get_allocation_history ─────────────────────────────────────
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sales.get_allocation_history',
    'Sales Allocation History',
    $$用途: 查询某一条分配记录的字段级变更流水。
何时使用: 审计分配金额 / 状态 / 数量变更。
参数说明: id 必填 (allocation_id)。$$,
    'sales',
    'http_adapter',
    '{"base_url_env":"SUPER_OPS_API_BASE","path":"/allocations/{id}/history","method":"GET","timeout_sec":30,"param_map":{"id":"path"}}'::jsonb,
    'service_key', 'SUPER_OPS_API_KEY', 'X-Api-Key', '',
    '{"type":"object","additionalProperties":false,"properties":{"id":{"type":"integer","minimum":1}},"required":["id"]}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

-- ─── sales.list_resources ─────────────────────────────────────────────
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sales.list_resources',
    'Sales Resources (货源)',
    $$用途: 超运货源列表 (可分配的云 / 产品资源池)。
何时使用: 查看可售卖的货源库存、单价。
参数说明: page / page_size 分页。$$,
    'sales',
    'http_adapter',
    '{"base_url_env":"SUPER_OPS_API_BASE","path":"/resources","method":"GET","timeout_sec":30}'::jsonb,
    'service_key', 'SUPER_OPS_API_KEY', 'X-Api-Key', '',
    '{"type":"object","additionalProperties":false,"properties":{"page":{"type":"integer","minimum":1,"default":1},"page_size":{"type":"integer","minimum":1,"maximum":500,"default":50}}}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

-- ─── sales.list_sales_users ───────────────────────────────────────────
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sales.list_sales_users',
    'Sales Team Members',
    $$用途: 销售成员列表。
何时使用: 查销售人员信息、按销售 id 查客户归属等。
参数说明: active_only 默认 true，false 返回含停用成员。$$,
    'sales',
    'http_adapter',
    '{"base_url_env":"SUPER_OPS_API_BASE","path":"/sales/users","method":"GET","timeout_sec":30}'::jsonb,
    'service_key', 'SUPER_OPS_API_KEY', 'X-Api-Key', '',
    '{"type":"object","additionalProperties":false,"properties":{"active_only":{"type":"boolean","default":true}}}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

-- ─── sales.list_sales_rules ───────────────────────────────────────────
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sales.list_sales_rules',
    'Sales Allocation Rules',
    $$用途: 客户自动分配规则 (按 priority 升序)。
何时使用: 理解为什么某客户被分给某销售 / 轮询组。
参数说明: 无。$$,
    'sales',
    'http_adapter',
    '{"base_url_env":"SUPER_OPS_API_BASE","path":"/sales/rules","method":"GET","timeout_sec":30}'::jsonb,
    'service_key', 'SUPER_OPS_API_KEY', 'X-Api-Key', '',
    '{"type":"object","additionalProperties":false,"properties":{}}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

-- ─── doc.* (doc-creator agent, real contract) ─────────────────────────
-- Base: DOC_CREATOR_BASE. Auth: Authorization: Bearer <DOC_CREATOR_API_KEY>.
-- Unified generate endpoint + type-specific endpoints + NL chat + listing.
-- File download endpoint is intentionally NOT surfaced (returns binary/CSV
-- stream; URL already returned in the generate response is sufficient).
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'doc.generate',
    'Document Generator (unified)',
    $$用途: 统一生成 PPT / Word / Excel-CSV 文档。
何时使用: 用户要求生成报告、总结、方案、表格等任意文档。
参数说明: prompt 自然语言描述; output_type ∈ ppt|word|table; title 可选。
返回: {success, filename, url (Blob URL 或 /api/v1/files/{filename}), output_type}。$$,
    'doc',
    'http_adapter',
    '{"base_url_env":"DOC_CREATOR_BASE","path":"/api/v1/generate","method":"POST","timeout_sec":180}'::jsonb,
    'service_key', 'DOC_CREATOR_API_KEY', 'Authorization', 'Bearer ',
    '{"type":"object","additionalProperties":false,"properties":{"prompt":{"type":"string","minLength":1},"output_type":{"type":"string","enum":["ppt","word","table"]},"title":{"type":"string"}},"required":["prompt","output_type"]}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

-- doc.generate_ppt — POST /api/v1/generate-ppt
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'doc.generate_ppt',
    'Document Generator (PPT)',
    $$用途: 直接生成 .pptx。
参数说明: prompt 自然语言; title 可选; num_slides 页数 1-50。$$,
    'doc',
    'http_adapter',
    '{"base_url_env":"DOC_CREATOR_BASE","path":"/api/v1/generate-ppt","method":"POST","timeout_sec":180}'::jsonb,
    'service_key', 'DOC_CREATOR_API_KEY', 'Authorization', 'Bearer ',
    '{"type":"object","additionalProperties":false,"properties":{"prompt":{"type":"string","minLength":1},"title":{"type":"string"},"num_slides":{"type":"integer","minimum":1,"maximum":50,"default":5}},"required":["prompt"]}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name, description = EXCLUDED.description,
    category = EXCLUDED.category, dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config, auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name, auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix, input_schema = EXCLUDED.input_schema;

-- doc.generate_word — POST /api/v1/generate-word
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'doc.generate_word',
    'Document Generator (Word)',
    $$用途: 直接生成 .docx。
参数说明: prompt 自然语言; title 可选。$$,
    'doc',
    'http_adapter',
    '{"base_url_env":"DOC_CREATOR_BASE","path":"/api/v1/generate-word","method":"POST","timeout_sec":180}'::jsonb,
    'service_key', 'DOC_CREATOR_API_KEY', 'Authorization', 'Bearer ',
    '{"type":"object","additionalProperties":false,"properties":{"prompt":{"type":"string","minLength":1},"title":{"type":"string"}},"required":["prompt"]}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name, description = EXCLUDED.description,
    category = EXCLUDED.category, dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config, auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name, auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix, input_schema = EXCLUDED.input_schema;

-- doc.generate_table — POST /api/v1/generate-table
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'doc.generate_table',
    'Document Generator (Excel/CSV)',
    $$用途: 直接生成表格 (.xlsx 或 .csv)。
参数说明: prompt 自然语言; title 可选; format xlsx|csv 默认 xlsx。$$,
    'doc',
    'http_adapter',
    '{"base_url_env":"DOC_CREATOR_BASE","path":"/api/v1/generate-table","method":"POST","timeout_sec":180}'::jsonb,
    'service_key', 'DOC_CREATOR_API_KEY', 'Authorization', 'Bearer ',
    '{"type":"object","additionalProperties":false,"properties":{"prompt":{"type":"string","minLength":1},"title":{"type":"string"},"format":{"type":"string","enum":["xlsx","csv"],"default":"xlsx"}},"required":["prompt"]}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name, description = EXCLUDED.description,
    category = EXCLUDED.category, dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config, auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name, auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix, input_schema = EXCLUDED.input_schema;

-- doc.chat — POST /chat (NL → auto-detect PPT/Word/Table)
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'doc.chat',
    'Document Generator (NL auto-detect)',
    $$用途: 一句话自然语言指令，由 Agent 自动决定 PPT/Word/Table 并生成。
参数说明: message 必填。
返回: {response, generated:{success,filename,url,output_type}, timestamp}。$$,
    'doc',
    'http_adapter',
    '{"base_url_env":"DOC_CREATOR_BASE","path":"/chat","method":"POST","timeout_sec":180}'::jsonb,
    'service_key', 'DOC_CREATOR_API_KEY', 'Authorization', 'Bearer ',
    '{"type":"object","additionalProperties":false,"properties":{"message":{"type":"string","minLength":1}},"required":["message"]}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name, description = EXCLUDED.description,
    category = EXCLUDED.category, dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config, auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name, auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix, input_schema = EXCLUDED.input_schema;

-- doc.list_files — GET /api/v1/list-files
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'doc.list_files',
    'Document Generator (list files)',
    $$用途: 列出 doc-creator 已生成的文件 (Blob 模式下有效)。
参数说明: 无。$$,
    'doc',
    'http_adapter',
    '{"base_url_env":"DOC_CREATOR_BASE","path":"/api/v1/list-files","method":"GET","timeout_sec":30}'::jsonb,
    'service_key', 'DOC_CREATOR_API_KEY', 'Authorization', 'Bearer ',
    '{"type":"object","additionalProperties":false,"properties":{}}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name, description = EXCLUDED.description,
    category = EXCLUDED.category, dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config, auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name, auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix, input_schema = EXCLUDED.input_schema;

-- ─── sandbox.run_python (Daytona SDK-backed) ─────────────────────────
-- The daytona_sandbox dispatcher uses daytona-sdk to create a short-lived
-- sandbox, run the code, and delete the sandbox. config.language picks the
-- Daytona snapshot language; create_timeout_sec bounds sandbox provisioning.
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sandbox.run_python',
    'Python Sandbox (Daytona)',
    $$用途: 在受限 Python 沙箱中执行代码，返回 {exit_code, result, artifacts}。
何时使用: 需要跑小段脚本辅助回答 (计算、数据转换、绘图 API 调用等)。
参数说明: code 必填；timeout_sec 秒，硬上限 300。
实现: daytona-sdk AsyncDaytona，每次调用创建短期 sandbox 并回收。
注意: 冷启动 ~30s 属正常；长任务请走独立批量工具。$$,
    'sandbox',
    'daytona_sandbox',
    '{"language":"python","create_timeout_sec":120,"max_timeout_sec":300}'::jsonb,
    'service_key', 'DAYTONA_API_TOKEN', 'Authorization', 'Bearer ',
    '{"type":"object","additionalProperties":false,"properties":{"code":{"type":"string","minLength":1},"stdin":{"type":"string"},"timeout_sec":{"type":"integer","minimum":1,"maximum":300,"default":60}},"required":["code"]}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

-- ─── jina.* (remote MCP proxy; real tool names verified against mcp.jina.ai) ──
-- Local tool names use `jina.` prefix; `remote_tool_name` is sent upstream.
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'jina.search',
    'Jina Web Search (remote MCP search_web)',
    $$用途: Jina 托管 MCP 的全网检索 (search_web)。
何时使用: 需要高质量语义化的网页检索 (相较 serper 更偏语义)。
参数说明: query 必填；其他字段透传给远端 MCP。$$,
    'jina',
    'mcp_proxy',
    '{"remote_url":"https://mcp.jina.ai/sse","remote_tool_name":"search_web","timeout_sec":60,"skip_initialize":true}'::jsonb,
    'service_key', 'JINA_API_KEY', 'Authorization', 'Bearer ',
    '{"type":"object","additionalProperties":true,"properties":{"query":{"type":"string","minLength":1}},"required":["query"]}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'jina.read',
    'Jina URL Reader (remote MCP read_url)',
    $$用途: 读取单个 URL 的主要正文 (read_url)。
何时使用: 已有具体 URL，需要其 Markdown 化正文。
参数说明: url 必填。$$,
    'jina',
    'mcp_proxy',
    '{"remote_url":"https://mcp.jina.ai/sse","remote_tool_name":"read_url","timeout_sec":60,"skip_initialize":true}'::jsonb,
    'service_key', 'JINA_API_KEY', 'Authorization', 'Bearer ',
    '{"type":"object","additionalProperties":true,"properties":{"url":{"type":"string","format":"uri"}},"required":["url"]}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'jina.search_images',
    'Jina Image Search',
    $$用途: Jina search_images — 图片检索。
何时使用: 需要图片素材/可视化参考。
参数说明: query 必填，返回图片 URL 列表。$$,
    'jina',
    'mcp_proxy',
    '{"remote_url":"https://mcp.jina.ai/sse","remote_tool_name":"search_images","timeout_sec":60,"skip_initialize":true}'::jsonb,
    'service_key', 'JINA_API_KEY', 'Authorization', 'Bearer ',
    '{"type":"object","additionalProperties":true,"properties":{"query":{"type":"string","minLength":1}},"required":["query"]}'::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    dispatcher = EXCLUDED.dispatcher,
    config = EXCLUDED.config,
    auth_mode = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header = EXCLUDED.auth_header,
    auth_prefix = EXCLUDED.auth_prefix,
    input_schema = EXCLUDED.input_schema;

-- ─── cloud_cost.* are registered via scripts/import_cloudcost_tools.py
-- (auth_mode='user_passthrough', Authorization: Bearer <user JWT>, retries=0).
-- Run it once the CloudCost API spec is available.

-- ─── Role grants ──────────────────────────────────────────────────────
-- kb.search / web.search: all 4 roles
WITH t AS (SELECT id FROM chat_gw.tools WHERE name IN ('kb.search','web.search'))
INSERT INTO chat_gw.tool_role_grants (tool_id, role)
SELECT t.id, r
FROM t,
     unnest(ARRAY['cloud_admin','cloud_ops','cloud_finance','cloud_viewer']) AS r
ON CONFLICT DO NOTHING;

-- ticket.*: admin / ops / finance
WITH t AS (SELECT id FROM chat_gw.tools WHERE name LIKE 'ticket.%')
INSERT INTO chat_gw.tool_role_grants (tool_id, role)
SELECT t.id, r
FROM t,
     unnest(ARRAY['cloud_admin','cloud_ops','cloud_finance']) AS r
ON CONFLICT DO NOTHING;

-- sales.*: admin / ops
WITH t AS (SELECT id FROM chat_gw.tools WHERE name LIKE 'sales.%')
INSERT INTO chat_gw.tool_role_grants (tool_id, role)
SELECT t.id, r
FROM t,
     unnest(ARRAY['cloud_admin','cloud_ops']) AS r
ON CONFLICT DO NOTHING;

-- doc.*: admin / ops / finance (matches spec §1.4)
WITH t AS (SELECT id FROM chat_gw.tools WHERE name LIKE 'doc.%')
INSERT INTO chat_gw.tool_role_grants (tool_id, role)
SELECT t.id, r
FROM t,
     unnest(ARRAY['cloud_admin','cloud_ops','cloud_finance']) AS r
ON CONFLICT DO NOTHING;

-- sandbox.run_python: all 4 roles (spec §1.4)
WITH t AS (SELECT id FROM chat_gw.tools WHERE name = 'sandbox.run_python')
INSERT INTO chat_gw.tool_role_grants (tool_id, role)
SELECT t.id, r
FROM t,
     unnest(ARRAY['cloud_admin','cloud_ops','cloud_finance','cloud_viewer']) AS r
ON CONFLICT DO NOTHING;

-- jina.*: all 4 roles (spec §1.4)
WITH t AS (SELECT id FROM chat_gw.tools WHERE name LIKE 'jina.%')
INSERT INTO chat_gw.tool_role_grants (tool_id, role)
SELECT t.id, r
FROM t,
     unnest(ARRAY['cloud_admin','cloud_ops','cloud_finance','cloud_viewer']) AS r
ON CONFLICT DO NOTHING;

-- Reconcile: some seed evolutions removed `remote_tool_name` variants we
-- no longer ship (e.g. literal `jina.jina.search`). Dropping any stale
-- jina.* rows not in the canonical set avoids ghost tools after DB upgrades.
DELETE FROM chat_gw.tools
WHERE name LIKE 'jina.%'
  AND name NOT IN ('jina.search', 'jina.read', 'jina.search_images');

COMMIT;
