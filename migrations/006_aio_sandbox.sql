-- Swap sandbox.run_python: Daytona → AIO MCP proxy.
--
-- AIO MCP at http://172.188.1.66:8080/mcp exposes `sandbox_execute_code`
-- (python + javascript). AIO nginx currently has JWT auth disabled — we
-- still route through mcp_proxy in service_key mode so flipping back to
-- JWT-protected is a 1-env-var change (set AIO_SANDBOX_SERVICE_JWT to the
-- real bearer). While AIO is open, AIO_SANDBOX_SERVICE_JWT must still be
-- set to any non-empty value (mcp_proxy refuses empty secret_env) — AIO
-- just ignores the header today.
--
-- Network boundary: inbound to 172.188.1.66:8080 should be restricted at
-- the VM NSG to chat-gw's App Service outbound IP pool (separate op).
--
-- Daytona adapter code (app/dispatchers/daytona.py) is intentionally left
-- intact — rollback is `UPDATE ... SET dispatcher='daytona_sandbox' ...`.
--
-- Apply:  psql -v ON_ERROR_STOP=1 -f migrations/006_aio_sandbox.sql

UPDATE chat_gw.tools SET
    display_name    = 'Python Sandbox (AIO)',
    description     = $$用途: 在 AIO 受限沙箱中执行 Python / JavaScript 代码，
返回 {status, stdout, stderr, exit_code}。
何时使用: 需要跑小段脚本辅助回答（计算、数据转换、简易数据分析）。
参数说明: code 必填；language 默认 python (可选 javascript)；timeout 秒（可选）。
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 sandbox_execute_code 工具，
service_key 模式 (Authorization: Bearer AIO_SANDBOX_SERVICE_JWT)，不透传用户 token。$$,
    dispatcher      = 'mcp_proxy',
    config          = '{
        "remote_url": "http://172.188.1.66:8080/mcp",
        "remote_tool_name": "sandbox_execute_code",
        "timeout_sec": 120,
        "protocol_version": "2024-11-05"
    }'::jsonb,
    auth_mode       = 'service_key',
    secret_env_name = 'AIO_SANDBOX_SERVICE_JWT',
    auth_header     = 'Authorization',
    auth_prefix     = 'Bearer ',
    input_schema    = '{
        "type": "object",
        "additionalProperties": false,
        "required": ["code"],
        "properties": {
            "code":     {"type": "string", "minLength": 1},
            "language": {"type": "string", "enum": ["python", "javascript"], "default": "python"},
            "timeout":  {"type": "integer", "minimum": 1, "maximum": 300}
        }
    }'::jsonb
WHERE name = 'sandbox.run_python';
