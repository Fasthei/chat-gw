-- chat_gw schema + triggers. Idempotent: safe to re-run.
--
-- Apply via:
--   psql -v ON_ERROR_STOP=1 -f migrations/001_schema.sql
-- or Docker entrypoint (mounted in docker-entrypoint-initdb.d).

CREATE SCHEMA IF NOT EXISTS chat_gw;

-- ─── Tools ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_gw.tools (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(128) UNIQUE NOT NULL,
    display_name    VARCHAR(255) NOT NULL,
    description     TEXT NOT NULL,
    category        VARCHAR(64),
    enabled         BOOLEAN NOT NULL DEFAULT true,

    dispatcher      VARCHAR(32) NOT NULL,
    config          JSONB NOT NULL DEFAULT '{}'::jsonb,

    auth_mode       VARCHAR(32) NOT NULL,
    secret_env_name VARCHAR(128),
    auth_header     VARCHAR(128),
    auth_prefix     VARCHAR(32) NOT NULL DEFAULT '',

    input_schema    JSONB NOT NULL,
    output_schema   JSONB,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      VARCHAR(128),
    version         INT NOT NULL DEFAULT 1,

    CONSTRAINT tools_auth_mode_ck CHECK (auth_mode IN ('service_key','user_passthrough')),
    CONSTRAINT tools_dispatcher_ck CHECK (dispatcher IN ('http_adapter','mcp_proxy','daytona_sandbox'))
);

CREATE INDEX IF NOT EXISTS idx_tools_enabled
    ON chat_gw.tools(enabled) WHERE enabled = true;

-- ─── Role grants ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_gw.tool_role_grants (
    tool_id         BIGINT NOT NULL REFERENCES chat_gw.tools(id) ON DELETE CASCADE,
    role            VARCHAR(64) NOT NULL,
    granted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    granted_by      VARCHAR(128),
    PRIMARY KEY (tool_id, role)
);

CREATE INDEX IF NOT EXISTS idx_grants_role ON chat_gw.tool_role_grants(role);

-- ─── Audit log ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_gw.tool_audit_log (
    id                     BIGSERIAL PRIMARY KEY,
    trace_id               UUID NOT NULL,
    user_id                VARCHAR(128) NOT NULL,
    user_email             VARCHAR(255),
    roles                  TEXT[] NOT NULL,
    tool_name              VARCHAR(128) NOT NULL,
    tool_id                BIGINT,
    arguments              JSONB,
    sensitive_fields_hit   TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    status                 VARCHAR(16) NOT NULL,
    deny_reason            VARCHAR(255),
    error_message          TEXT,
    latency_ms             INT,
    started_at             TIMESTAMPTZ NOT NULL,
    finished_at            TIMESTAMPTZ,

    CONSTRAINT audit_status_ck CHECK (status IN ('allowed','denied','error','ok'))
);

CREATE INDEX IF NOT EXISTS idx_audit_user_time
    ON chat_gw.tool_audit_log(user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_tool_time
    ON chat_gw.tool_audit_log(tool_name, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_trace_id
    ON chat_gw.tool_audit_log(trace_id);

-- ─── Triggers ─────────────────────────────────────────────────────────

-- updated_at auto-bump
CREATE OR REPLACE FUNCTION chat_gw.set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tools_set_updated_at ON chat_gw.tools;
CREATE TRIGGER trg_tools_set_updated_at
    BEFORE UPDATE ON chat_gw.tools
    FOR EACH ROW EXECUTE FUNCTION chat_gw.set_updated_at();

-- LISTEN/NOTIFY on tools + tool_role_grants
CREATE OR REPLACE FUNCTION chat_gw.notify_tools_changed() RETURNS trigger AS $$
DECLARE
    payload TEXT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        payload := COALESCE(OLD.id::text, '');
    ELSE
        payload := COALESCE(NEW.id::text, '');
    END IF;
    PERFORM pg_notify('tools_changed', payload);
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tools_notify ON chat_gw.tools;
CREATE TRIGGER trg_tools_notify
    AFTER INSERT OR UPDATE OR DELETE ON chat_gw.tools
    FOR EACH ROW EXECUTE FUNCTION chat_gw.notify_tools_changed();

CREATE OR REPLACE FUNCTION chat_gw.notify_grants_changed() RETURNS trigger AS $$
DECLARE
    payload TEXT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        payload := COALESCE(OLD.tool_id::text, '');
    ELSE
        payload := COALESCE(NEW.tool_id::text, '');
    END IF;
    PERFORM pg_notify('tools_changed', payload);
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_grants_notify ON chat_gw.tool_role_grants;
CREATE TRIGGER trg_grants_notify
    AFTER INSERT OR UPDATE OR DELETE ON chat_gw.tool_role_grants
    FOR EACH ROW EXECUTE FUNCTION chat_gw.notify_grants_changed();
