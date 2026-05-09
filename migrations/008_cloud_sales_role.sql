-- Add cloud_sales role grants. Mirrors cloud_ops' tool set today; the role
-- exists as a separate identity so future authz tweaks (e.g. revoking ticket
-- write access) don't disturb ops.
--
-- Casdoor side: a `cloud_sales` role must be created and assigned to sales
-- staff for these grants to take effect — chat-gw reads roles from the JWT
-- `roles` claim verbatim.
--
-- Idempotent: ON CONFLICT DO NOTHING. Safe to re-run.

BEGIN;

-- kb.search / web.search
WITH t AS (SELECT id FROM chat_gw.tools WHERE name IN ('kb.search','web.search'))
INSERT INTO chat_gw.tool_role_grants (tool_id, role)
SELECT t.id, 'cloud_sales' FROM t
ON CONFLICT DO NOTHING;

-- ticket.*
WITH t AS (SELECT id FROM chat_gw.tools WHERE name LIKE 'ticket.%')
INSERT INTO chat_gw.tool_role_grants (tool_id, role)
SELECT t.id, 'cloud_sales' FROM t
ON CONFLICT DO NOTHING;

-- sales.*
WITH t AS (SELECT id FROM chat_gw.tools WHERE name LIKE 'sales.%')
INSERT INTO chat_gw.tool_role_grants (tool_id, role)
SELECT t.id, 'cloud_sales' FROM t
ON CONFLICT DO NOTHING;

-- doc.*
WITH t AS (SELECT id FROM chat_gw.tools WHERE name LIKE 'doc.%')
INSERT INTO chat_gw.tool_role_grants (tool_id, role)
SELECT t.id, 'cloud_sales' FROM t
ON CONFLICT DO NOTHING;

-- sandbox.run_python
WITH t AS (SELECT id FROM chat_gw.tools WHERE name = 'sandbox.run_python')
INSERT INTO chat_gw.tool_role_grants (tool_id, role)
SELECT t.id, 'cloud_sales' FROM t
ON CONFLICT DO NOTHING;

-- jina.*
WITH t AS (SELECT id FROM chat_gw.tools WHERE name LIKE 'jina.%')
INSERT INTO chat_gw.tool_role_grants (tool_id, role)
SELECT t.id, 'cloud_sales' FROM t
ON CONFLICT DO NOTHING;

COMMIT;
