-- Customer-scoped tool grants. Parallel to chat_gw.tool_role_grants; OR-merged
-- with role grants at read time. Intended for LobeChat-style customers that
-- log in with a customerCode (from the gongdan ticket system) and need a
-- curated, customer-specific tool set.
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS chat_gw.tool_customer_grants (
    tool_id         BIGINT NOT NULL REFERENCES chat_gw.tools(id) ON DELETE CASCADE,
    customer_code   VARCHAR(32) NOT NULL,
    granted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    granted_by      VARCHAR(128),
    PRIMARY KEY (tool_id, customer_code)
);

CREATE INDEX IF NOT EXISTS idx_customer_grants_code
    ON chat_gw.tool_customer_grants(customer_code);

-- Re-use the existing notify_grants_changed() payload convention: emit
-- tools_changed with tool_id so ToolRegistry refreshes on any mutation.
DROP TRIGGER IF EXISTS trg_customer_grants_notify ON chat_gw.tool_customer_grants;
CREATE TRIGGER trg_customer_grants_notify
    AFTER INSERT OR UPDATE OR DELETE ON chat_gw.tool_customer_grants
    FOR EACH ROW EXECUTE FUNCTION chat_gw.notify_grants_changed();
