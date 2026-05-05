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
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'titan_readonly') THEN
        CREATE ROLE titan_readonly WITH LOGIN PASSWORD 'titan_readonly_change_me';
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

-- Create default tenant for testing
INSERT INTO tenants (id, name, plan, active, config)
VALUES ('default', 'Default Tenant', 'free', TRUE, '{}')
ON CONFLICT (id) DO NOTHING;

-- Create anonymous tenant for unauthenticated access
INSERT INTO tenants (id, name, plan, active, config)
VALUES ('__anonymous__', 'Anonymous Access', 'free', TRUE, '{}')
ON CONFLICT (id) DO NOTHING;
