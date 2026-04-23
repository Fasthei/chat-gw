-- 004_admin_fields.sql — idempotent, adds structured error columns the
-- Admin audit query relies on for filtering. Safe to run against an already-
-- populated tool_audit_log table: existing rows get NULL for the new fields.

ALTER TABLE chat_gw.tool_audit_log
    ADD COLUMN IF NOT EXISTS error_code INT,
    ADD COLUMN IF NOT EXISTS error_kind VARCHAR(64);

-- New filter path: GET /admin/audit?outcome=error — supporting index.
CREATE INDEX IF NOT EXISTS idx_audit_status_time
    ON chat_gw.tool_audit_log(status, started_at DESC);

-- Keyset pagination for the admin audit query.
-- Existing idx_audit_user_time / idx_audit_tool_time cover the two common
-- single-field filters; this composite covers the empty-filter case.
CREATE INDEX IF NOT EXISTS idx_audit_started_at_id
    ON chat_gw.tool_audit_log(started_at DESC, id DESC);
