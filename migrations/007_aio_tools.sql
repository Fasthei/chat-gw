-- Register remaining AIO MCP tools (bulk).
--
-- Source: http://172.188.1.66:8080/mcp tools/list (33 tools).
-- Mapping:
--   sandbox_* (AIO) -> sandbox.* (chat-gw)   category=sandbox
--   browser_*  (AIO) -> browser.* (chat-gw)  category=browser
-- Skipped: sandbox_execute_code (already mapped as sandbox.run_python).
--
-- All tools share dispatcher=mcp_proxy, auth_mode=service_key,
-- secret_env_name=AIO_SANDBOX_SERVICE_JWT (placeholder while AIO nginx
-- JWT is disabled). Grants mirror sandbox.run_python (cloud_admin /
-- cloud_finance / cloud_ops / cloud_viewer).
--
-- Re-runnable: ON CONFLICT (name) DO UPDATE ensures idempotent.

BEGIN;

-- sandbox_get_browser_info -> sandbox.get_browser_info
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sandbox.get_browser_info',
    'AIO Get Info',
    $T$用途: AIO 远端 MCP 工具 `sandbox_get_browser_info`。
原始描述:
Get information about browser, like cdp url, viewport size, etc.

    Args:
        request (Dict): The incoming request context.
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 sandbox_get_browser_info，service_key 模式 (placeholder JWT)。$T$,
    'sandbox',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "sandbox_get_browser_info", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {}, "title": "get_browser_infoArguments"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- sandbox_browser_screenshot -> sandbox.browser_screenshot
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sandbox.browser_screenshot',
    'AIO Screenshot',
    $T$用途: AIO 远端 MCP 工具 `sandbox_browser_screenshot`。
原始描述:
Take a screenshot of the current display.

    Returns:
        Image: A screenshot of the current display in JPEG format with metadata.
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 sandbox_browser_screenshot，service_key 模式 (placeholder JWT)。$T$,
    'sandbox',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "sandbox_browser_screenshot", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {}, "title": "browser_screenshotArguments"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- sandbox_browser_execute_action -> sandbox.browser_execute_action
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sandbox.browser_execute_action',
    'AIO Execute Action',
    $T$用途: AIO 远端 MCP 工具 `sandbox_browser_execute_action`。
原始描述:
Execute a browser action on the current display.

Args:
    `action`: Dictionary containing `action_type` and relevant parameters.
            The `action_type` determines which parameters are required.

Action types and their parameters (auto-generated from models):
    - CLICK: {action_type: 'CLICK', x: Optional?, y: Optional?, button: Literal?, num_clicks: Literal?}
    - DOUBLE_CLICK: {action_type: 'DOUBLE_CLICK', x: Optional?, y: Optional?}
    - DRAG_REL: {action_type: 'DRAG_REL', x_offset: float, y_offset: float}
    - DRAG_TO: {action_type: 'DRAG_TO', x: float, y: float}
    - HOTKEY: {action_type: 'HOTKEY', keys: List}
    - KEY_DOWN: {action_type: 'KEY_DOWN', key: str}
    - KEY_UP: {action_type: 'KEY_UP', key: str}
    - MOUSE_DOWN: {action_type: 'MOUSE_DOWN', button: Literal?}
    - MOUSE_UP: {action_type: 'MOUSE_UP', button: Literal?}
    - MOVE_REL: {action_type: 'MOVE_REL', x_offset: float, y_offset: float}
    - MOVE_TO: {action_type: 'MOVE_TO', x: float, y: float}
    - PRESS: {action_type: 'PRESS', key: str}
    - RIGHT_CLICK: {action_type: 'RIGHT_CLICK', x: Optional?, y: Optional?}
    - SCROLL: {action_type: 'SCROLL', dx: int?, dy: int?}
    - TYPING: {action_type: 'TYPING', text: str, use_clipboard: Optional?}
    - WAIT: {action_type: 'WAIT', duration: float}

Returns:
    Dict containing `status` and `action_performed`

Raises:
    ValueError: If `action_type` is invalid or required parameters are missing
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 sandbox_browser_execute_action，service_key 模式 (placeholder JWT)。$T$,
    'sandbox',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "sandbox_browser_execute_action", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {"action": {"additionalProperties": true, "title": "Action", "type": "object"}}, "required": ["action"], "title": "browser_execute_actionArguments"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- sandbox_file_operations -> sandbox.file_operations
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sandbox.file_operations',
    'AIO File Operations',
    $T$用途: AIO 远端 MCP 工具 `sandbox_file_operations`。
原始描述:
Unified file system operations tool for agents. `/tmp` and `/home/$USER` are fully accessible.

    Args:
        action: Operation type - "read", "write", "replace", "search", "find", "list"
        path: File or directory path
        content: Content for write/replace operations (or regex for search)
        target: Target string for replace operations (new_str)
        pattern: Pattern for find operations (glob syntax)
        encoding: File encoding (utf-8, base64, raw)
        start_line: Starting line for read operations (0-based)
        end_line: Ending line for read operations (not included)
        append: Append mode for write operations
        recursive: Recursive mode for find/list operations
        show_hidden: Show hidden files in list operations
        file_types: Filter by file extensions for list operations
        sudo: Use sudo privileges

    Returns:
        Dict containing operation result and relevant data
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 sandbox_file_operations，service_key 模式 (placeholder JWT)。$T$,
    'sandbox',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "sandbox_file_operations", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {"action": {"title": "Action", "type": "string"}, "path": {"title": "Path", "type": "string"}, "content": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": null, "title": "Content"}, "target": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": null, "title": "Target"}, "pattern": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": null, "title": "Pattern"}, "encoding": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": "utf-8", "title": "Encoding"}, "start_line": {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": null, "title": "Start Line"}, "end_line": {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": null, "title": "End Line"}, "append": {"default": false, "title": "Append", "type": "boolean"}, "recursive": {"default": false, "title": "Recursive", "type": "boolean"}, "show_hidden": {"default": false, "title": "Show Hidden", "type": "boolean"}, "file_types": {"anyOf": [{"items": {"type": "string"}, "type": "array"}, {"type": "null"}], "default": null, "title": "File Types"}, "sudo": {"default": false, "title": "Sudo", "type": "boolean"}}, "required": ["action", "path"], "title": "file_operationsArguments"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- sandbox_str_replace_editor -> sandbox.str_replace_editor
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sandbox.str_replace_editor',
    'AIO Str Replace Editor',
    $T$用途: AIO 远端 MCP 工具 `sandbox_str_replace_editor`。
原始描述:
Professional file editor tool using openhands_aci editor.

    This tool provides advanced file editing capabilities compatible with Anthropic's
    str_replace_editor interface. Parameters and behavior match the standard interface.

    Args:
        command: Command to execute ("view", "create", "str_replace", "insert", "undo_edit")
        path: File path to operate on
        file_text: File content for create command
        old_str: Original string to replace (for str_replace command)
        new_str: New string to replace with (for str_replace and insert commands)
        insert_line: Line number to insert at (for insert command)
        view_range: Line range for view command [start, end]

    Returns:
        Dict containing editor operation result
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 sandbox_str_replace_editor，service_key 模式 (placeholder JWT)。$T$,
    'sandbox',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "sandbox_str_replace_editor", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {"command": {"title": "Command", "type": "string"}, "path": {"title": "Path", "type": "string"}, "file_text": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": null, "title": "File Text"}, "old_str": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": null, "title": "Old Str"}, "new_str": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": null, "title": "New Str"}, "insert_line": {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": null, "title": "Insert Line"}, "view_range": {"anyOf": [{"items": {"type": "integer"}, "type": "array"}, {"type": "null"}], "default": null, "title": "View Range"}}, "required": ["command", "path"], "title": "str_replace_editorArguments"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- sandbox_get_context -> sandbox.get_context
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sandbox.get_context',
    'AIO Get Context',
    $T$用途: AIO 远端 MCP 工具 `sandbox_get_context`。
原始描述:
Get sandbox environment information. aio system's version.

    Returns:
        Dict containing aio sandbox's environment info, version, and home directory
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 sandbox_get_context，service_key 模式 (placeholder JWT)。$T$,
    'sandbox',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "sandbox_get_context", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {}, "title": "get_contextArguments"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- sandbox_get_packages -> sandbox.get_packages
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sandbox.get_packages',
    'AIO Get Packages',
    $T$用途: AIO 远端 MCP 工具 `sandbox_get_packages`。
原始描述:
Get installed packages by language.

    Args:
        language: Optional language filter ('python' or 'nodejs')

    Returns: String listing installed packages
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 sandbox_get_packages，service_key 模式 (placeholder JWT)。$T$,
    'sandbox',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "sandbox_get_packages", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {"language": {"default": null, "enum": ["python", "nodejs"], "title": "Language", "type": "string"}}, "title": "get_packagesArguments"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- sandbox_execute_bash -> sandbox.execute_bash
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sandbox.execute_bash',
    'AIO Execute Bash',
    $T$用途: AIO 远端 MCP 工具 `sandbox_execute_bash`。
原始描述:
Execute a shell command. Sessions are managed automatically.

    Args:
        cmd: Shell command to execute
        cwd: Optional working directory (absolute path), default to '/tmp'
        new_session: If True, creates a new session instead of using the default
        timeout: Optional timeout in seconds for command execution (default: 30)

    Returns:
        Dict containing command, status, output, and exit_code
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 sandbox_execute_bash，service_key 模式 (placeholder JWT)。$T$,
    'sandbox',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "sandbox_execute_bash", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {"cmd": {"title": "Cmd", "type": "string"}, "cwd": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": null, "title": "Cwd"}, "new_session": {"default": false, "title": "New Session", "type": "boolean"}, "timeout": {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": 30, "title": "Timeout"}}, "required": ["cmd"], "title": "execute_bashArguments"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- sandbox_convert_to_markdown -> sandbox.convert_to_markdown
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'sandbox.convert_to_markdown',
    'AIO Convert To Markdown',
    $T$用途: AIO 远端 MCP 工具 `sandbox_convert_to_markdown`。
原始描述:
Convert a resource described by an http:, https:, file: or data: URI to markdown
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 sandbox_convert_to_markdown，service_key 模式 (placeholder JWT)。$T$,
    'sandbox',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "sandbox_convert_to_markdown", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {"uri": {"title": "Uri", "type": "string"}}, "required": ["uri"], "title": "convert_to_markdownArguments"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_navigate -> browser.navigate
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.navigate',
    'AIO Navigate',
    $T$用途: AIO 远端 MCP 工具 `browser_navigate`。
原始描述:
Navigate to a URL
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_navigate，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_navigate", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"], "additionalProperties": false, "$schema": "http://json-schema.org/draft-07/schema#"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_go_back -> browser.go_back
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.go_back',
    'AIO Go Back',
    $T$用途: AIO 远端 MCP 工具 `browser_go_back`。
原始描述:
Go back to the previous page
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_go_back，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_go_back", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {}}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_go_forward -> browser.go_forward
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.go_forward',
    'AIO Go Forward',
    $T$用途: AIO 远端 MCP 工具 `browser_go_forward`。
原始描述:
Go forward to the next page
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_go_forward，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_go_forward", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {}}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_form_input_fill -> browser.form_input_fill
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.form_input_fill',
    'AIO Form Input Fill',
    $T$用途: AIO 远端 MCP 工具 `browser_form_input_fill`。
原始描述:
Fill out an input field, before using the tool, Either 'index' or 'selector' must be provided
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_form_input_fill，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_form_input_fill", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {"selector": {"type": "string", "description": "CSS selector for input field, priority use index, if index is not provided, use selector"}, "index": {"type": "number", "description": "Index of the element to fill"}, "value": {"type": "string", "description": "Value to fill"}, "clear": {"type": "boolean", "default": false, "description": "Whether to clear existing text before filling"}}, "required": ["value"], "additionalProperties": false, "$schema": "http://json-schema.org/draft-07/schema#"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_get_markdown -> browser.get_markdown
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.get_markdown',
    'AIO Get Markdown',
    $T$用途: AIO 远端 MCP 工具 `browser_get_markdown`。
原始描述:
Get the markdown content of the current page
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_get_markdown，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_get_markdown", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {}, "additionalProperties": false, "$schema": "http://json-schema.org/draft-07/schema#"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_get_text -> browser.get_text
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.get_text',
    'AIO Get Text',
    $T$用途: AIO 远端 MCP 工具 `browser_get_text`。
原始描述:
Get the text content of the current page
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_get_text，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_get_text", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {}, "additionalProperties": false, "$schema": "http://json-schema.org/draft-07/schema#"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_read_links -> browser.read_links
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.read_links',
    'AIO Read Links',
    $T$用途: AIO 远端 MCP 工具 `browser_read_links`。
原始描述:
Get all links on the current page
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_read_links，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_read_links", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {}}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_new_tab -> browser.new_tab
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.new_tab',
    'AIO New Tab',
    $T$用途: AIO 远端 MCP 工具 `browser_new_tab`。
原始描述:
Open a new tab
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_new_tab，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_new_tab", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {"url": {"type": "string", "description": "URL to open in the new tab"}}, "required": ["url"], "additionalProperties": false, "$schema": "http://json-schema.org/draft-07/schema#"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_tab_list -> browser.tab_list
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.tab_list',
    'AIO Tab List',
    $T$用途: AIO 远端 MCP 工具 `browser_tab_list`。
原始描述:
Get the list of tabs
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_tab_list，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_tab_list", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {}}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_switch_tab -> browser.switch_tab
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.switch_tab',
    'AIO Switch Tab',
    $T$用途: AIO 远端 MCP 工具 `browser_switch_tab`。
原始描述:
Switch to a specific tab
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_switch_tab，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_switch_tab", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {"index": {"type": "number", "description": "Tab index to switch to"}}, "required": ["index"], "additionalProperties": false, "$schema": "http://json-schema.org/draft-07/schema#"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_close_tab -> browser.close_tab
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.close_tab',
    'AIO Close Tab',
    $T$用途: AIO 远端 MCP 工具 `browser_close_tab`。
原始描述:
Close the current tab
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_close_tab，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_close_tab", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {}}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_evaluate -> browser.evaluate
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.evaluate',
    'AIO Evaluate',
    $T$用途: AIO 远端 MCP 工具 `browser_evaluate`。
原始描述:
Execute JavaScript in the browser console
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_evaluate，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_evaluate", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {"script": {"type": "string", "description": "JavaScript code to execute, () => { /* code */ }"}}, "required": ["script"], "additionalProperties": false, "$schema": "http://json-schema.org/draft-07/schema#"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_vision_screen_capture -> browser.vision_screen_capture
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.vision_screen_capture',
    'AIO Vision Screen Capture',
    $T$用途: AIO 远端 MCP 工具 `browser_vision_screen_capture`。
原始描述:
Take a screenshot of the current page for vision mode
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_vision_screen_capture，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_vision_screen_capture", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {}, "additionalProperties": false, "$schema": "http://json-schema.org/draft-07/schema#"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_vision_screen_click -> browser.vision_screen_click
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.vision_screen_click',
    'AIO Vision Screen Click',
    $T$用途: AIO 远端 MCP 工具 `browser_vision_screen_click`。
原始描述:
Click left mouse button on the page with vision and snapshot, before calling this tool, you should call `browser_vision_screen_capture` first only once, fallback to `browser_click` if failed
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_vision_screen_click，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_vision_screen_click", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {"factors": {"type": "array", "items": {"type": "number"}, "description": "Vision model coordinate system scaling factors [width_factor, height_factor] for coordinate space normalization. Transformation formula: x = (x_model * screen_width * width_factor) / width_factor y = (y_model * screen_height * height_factor) / height_factor where x_model, y_model are normalized model output coordinates (0-1), screen_width/height are screen dimensions, width_factor/height_factor are quantization factors, If the factors are unknown, leave it blank. Most models do not require this parameter."}, "x": {"type": "number", "description": "X pixel coordinate"}, "y": {"type": "number", "description": "Y pixel coordinate"}}, "required": ["x", "y"], "additionalProperties": false, "$schema": "http://json-schema.org/draft-07/schema#"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_get_download_list -> browser.get_download_list
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.get_download_list',
    'AIO Get Download List',
    $T$用途: AIO 远端 MCP 工具 `browser_get_download_list`。
原始描述:
Get the list of downloaded files
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_get_download_list，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_get_download_list", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {}}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_screenshot -> browser.screenshot
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.screenshot',
    'AIO Screenshot',
    $T$用途: AIO 远端 MCP 工具 `browser_screenshot`。
原始描述:
Take a screenshot of the current page or a specific element
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_screenshot，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_screenshot", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {"name": {"type": "string", "description": "Name for the screenshot"}, "selector": {"type": "string", "description": "CSS selector for element to screenshot"}, "index": {"type": "number", "description": "index of the element to screenshot"}, "width": {"type": "number", "description": "Width in pixels (default: viewport width)"}, "height": {"type": "number", "description": "Height in pixels (default: viewport height)"}, "fullPage": {"type": "boolean", "description": "Full page screenshot (default: false)"}, "highlight": {"type": "boolean", "default": false, "description": "Highlight the element"}}, "additionalProperties": false, "$schema": "http://json-schema.org/draft-07/schema#"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_click -> browser.click
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.click',
    'AIO Click',
    $T$用途: AIO 远端 MCP 工具 `browser_click`。
原始描述:
Click an element on the page, before using the tool, use `browser_get_clickable_elements` to get the index of the element, but not call `browser_get_clickable_elements` multiple times
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_click，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_click", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {"index": {"type": "number", "description": "Index of the element to click"}}, "additionalProperties": false, "$schema": "http://json-schema.org/draft-07/schema#"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_select -> browser.select
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.select',
    'AIO Select',
    $T$用途: AIO 远端 MCP 工具 `browser_select`。
原始描述:
Select an element on the page with index, Either 'index' or 'selector' must be provided
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_select，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_select", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {"index": {"type": "number", "description": "Index of the element to select"}, "selector": {"type": "string", "description": "CSS selector for element to select"}, "value": {"type": "string", "description": "Value to select"}}, "required": ["value"], "additionalProperties": false, "$schema": "http://json-schema.org/draft-07/schema#"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_hover -> browser.hover
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.hover',
    'AIO Hover',
    $T$用途: AIO 远端 MCP 工具 `browser_hover`。
原始描述:
Hover an element on the page, Either 'index' or 'selector' must be provided
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_hover，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_hover", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {"index": {"type": "number", "description": "Index of the element to hover"}, "selector": {"type": "string", "description": "CSS selector for element to hover"}}, "additionalProperties": false, "$schema": "http://json-schema.org/draft-07/schema#"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_get_clickable_elements -> browser.get_clickable_elements
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.get_clickable_elements',
    'AIO Get Clickable Elements',
    $T$用途: AIO 远端 MCP 工具 `browser_get_clickable_elements`。
原始描述:
Get the clickable or hoverable or selectable elements on the current page, don't call this tool multiple times
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_get_clickable_elements，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_get_clickable_elements", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {}}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_scroll -> browser.scroll
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.scroll',
    'AIO Scroll',
    $T$用途: AIO 远端 MCP 工具 `browser_scroll`。
原始描述:
Scroll the page
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_scroll，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_scroll", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {"amount": {"type": "number", "description": "Pixels to scroll (positive for down, negative for up), if the amount is not provided, scroll to the bottom of the page"}}, "additionalProperties": false, "$schema": "http://json-schema.org/draft-07/schema#"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_close -> browser.close
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.close',
    'AIO Close',
    $T$用途: AIO 远端 MCP 工具 `browser_close`。
原始描述:
Close the browser when the task is done and the browser is not needed anymore
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_close，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_close", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {}}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- browser_press_key -> browser.press_key
INSERT INTO chat_gw.tools
    (name, display_name, description, category, dispatcher, config,
     auth_mode, secret_env_name, auth_header, auth_prefix, input_schema)
VALUES (
    'browser.press_key',
    'AIO Press Key',
    $T$用途: AIO 远端 MCP 工具 `browser_press_key`。
原始描述:
Press a key on the keyboard
实现: 远端 MCP (http://172.188.1.66:8080/mcp) 的 browser_press_key，service_key 模式 (placeholder JWT)。$T$,
    'browser',
    'mcp_proxy',
    $T${"remote_url": "http://172.188.1.66:8080/mcp", "remote_tool_name": "browser_press_key", "timeout_sec": 120, "protocol_version": "2024-11-05"}$T$::jsonb,
    'service_key', 'AIO_SANDBOX_SERVICE_JWT', 'Authorization', 'Bearer ',
    $T${"type": "object", "properties": {"key": {"type": "string", "enum": ["Enter", "Tab", "Escape", "Backspace", "Delete", "Insert", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", "ShiftLeft", "ShiftRight", "ControlLeft", "ControlRight", "AltLeft", "AltRight", "MetaLeft", "MetaRight", "CapsLock", "PrintScreen", "ScrollLock", "Pause", "ContextMenu"], "description": "Name of the key to press or a character to generate, such as Enter, Tab, Escape, Backspace, Delete, Insert, F1, F2, F3, F4, F5, F6, F7, F8, F9, F10, F11, F12, ArrowLeft, ArrowRight, ArrowUp, ArrowDown, PageUp, PageDown, Home, End, ShiftLeft, ShiftRight, ControlLeft, ControlRight, AltLeft, AltRight, MetaLeft, MetaRight, CapsLock, PrintScreen, ScrollLock, Pause, ContextMenu"}}, "required": ["key"], "additionalProperties": false, "$schema": "http://json-schema.org/draft-07/schema#"}$T$::jsonb
)
ON CONFLICT (name) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    category        = EXCLUDED.category,
    dispatcher      = EXCLUDED.dispatcher,
    config          = EXCLUDED.config,
    auth_mode       = EXCLUDED.auth_mode,
    secret_env_name = EXCLUDED.secret_env_name,
    auth_header     = EXCLUDED.auth_header,
    auth_prefix     = EXCLUDED.auth_prefix,
    input_schema    = EXCLUDED.input_schema,
    updated_at      = now(),
    version         = chat_gw.tools.version + 1;

-- ── role grants (mirror sandbox.run_python: 4 roles) ────────────────

WITH t AS (
    SELECT id FROM chat_gw.tools WHERE name IN ('sandbox.get_browser_info','sandbox.browser_screenshot','sandbox.browser_execute_action','sandbox.file_operations','sandbox.str_replace_editor','sandbox.get_context','sandbox.get_packages','sandbox.execute_bash','sandbox.convert_to_markdown','browser.navigate','browser.go_back','browser.go_forward','browser.form_input_fill','browser.get_markdown','browser.get_text','browser.read_links','browser.new_tab','browser.tab_list','browser.switch_tab','browser.close_tab','browser.evaluate','browser.vision_screen_capture','browser.vision_screen_click','browser.get_download_list','browser.screenshot','browser.click','browser.select','browser.hover','browser.get_clickable_elements','browser.scroll','browser.close','browser.press_key')
), r AS (
    SELECT unnest(ARRAY['cloud_admin','cloud_finance','cloud_ops','cloud_viewer']) AS role
)
INSERT INTO chat_gw.tool_role_grants (tool_id, role)
SELECT t.id, r.role FROM t CROSS JOIN r
ON CONFLICT DO NOTHING;

COMMIT;
