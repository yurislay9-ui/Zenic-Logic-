-- ============================================================
--  TITAN OMNISCALE X v16 - PostgreSQL Init Script
--  Phase 3: VPS Deploy
--
--  This script runs automatically when the PostgreSQL container
--  starts for the first time (via docker-entrypoint-initdb.d).
--
--  It creates extensions, roles, and initial data.
-- ============================================================

-- Enable UUID extension for tenant IDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pgcrypto for hashing
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create a read-only user for monitoring/health checks (optional)
-- Password is sourced from POSTGRES_READONLY_PASSWORD env var, with a random fallback
DO $$
DECLARE
    readonly_pwd text;
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'titan_readonly') THEN
        -- Use environment variable if set, otherwise generate a random password
        SELECT coalesce(
            current_setting('postgres_readonly_password', true),
            encode(gen_random_bytes(24), 'base64')
        ) INTO readonly_pwd;
        EXECUTE format('CREATE ROLE titan_readonly WITH LOGIN PASSWORD %L', readonly_pwd);
        GRANT CONNECT ON DATABASE titan_db TO titan_readonly;
    END IF;
END
$$;

-- Grant read-only access to all tables
DO $$
DECLARE
    tbl text;
BEGIN
    FOR tbl IN SELECT tablename FROM pg_tables WHERE schemaname = 'public'
    LOOP
        EXECUTE format('GRANT SELECT ON %I TO titan_readonly', tbl);
    END LOOP;
END
$$;

-- Create initial admin user (password will be set by the app on first run)
-- This is just a placeholder — AuthService.ensure_admin() handles the real creation

-- Create tenants table (required before INSERT statements below)
CREATE TABLE IF NOT EXISTS tenants (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    plan VARCHAR(50) NOT NULL DEFAULT 'free',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    config JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Grant read-only access to tenants table
GRANT SELECT ON tenants TO titan_readonly;

-- Create default tenant for testing
INSERT INTO tenants (id, name, plan, active, config)
VALUES ('default', 'Default Tenant', 'free', TRUE, '{}')
ON CONFLICT (id) DO NOTHING;

-- Create anonymous tenant for unauthenticated access
INSERT INTO tenants (id, name, plan, active, config)
VALUES ('__anonymous__', 'Anonymous Access', 'free', TRUE, '{}')
ON CONFLICT (id) DO NOTHING;
