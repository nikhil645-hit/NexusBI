-- ==============================================================================
-- 02_users.sql - PostgreSQL Role-Based Access Control (RBAC) & Users
-- Purpose:
--   Creates dedicated PostgreSQL users following the Principle of Least Privilege:
--     1. dbt_user: Full access to staging and marts; read access to raw.
--     2. app_readonly: Read-only access (SELECT) strictly on marts schema only.
--
-- Security Note:
--   Passwords in this file are placeholders. Set them in your local .env and
--   run this script against the local warehouse Postgres (port 5434).
--
-- How to run:
--   docker exec -i olist-warehouse psql -U postgres -d warehouse < sql/02_users.sql
--   or: psql -h localhost -p 5434 -U postgres -d warehouse -f sql/02_users.sql
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Create Users Idempotently
-- ------------------------------------------------------------------------------
DO $$
BEGIN
    -- Create dbt transformation user if not exists
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'dbt_user') THEN
        CREATE USER dbt_user WITH PASSWORD 'REPLACE_WITH_STRONG_DBT_PASSWORD_123!';
    END IF;

    -- Create Streamlit read-only user if not exists
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_readonly') THEN
        CREATE USER app_readonly WITH PASSWORD 'REPLACE_WITH_STRONG_APP_PASSWORD_123!';
    END IF;
END
$$;

-- ------------------------------------------------------------------------------
-- 2. Grants for dbt_user (Full access to staging/marts, Read on raw)
-- ------------------------------------------------------------------------------
GRANT USAGE ON SCHEMA raw TO dbt_user;
GRANT USAGE, CREATE ON SCHEMA staging TO dbt_user;
GRANT USAGE, CREATE ON SCHEMA marts TO dbt_user;

-- Existing objects
GRANT SELECT ON ALL TABLES IN SCHEMA raw TO dbt_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA staging TO dbt_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA marts TO dbt_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA staging TO dbt_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA marts TO dbt_user;

-- Future objects created by Airbyte or dbt
ALTER DEFAULT PRIVILEGES IN SCHEMA raw GRANT SELECT ON TABLES TO dbt_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA staging GRANT ALL PRIVILEGES ON TABLES TO dbt_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT ALL PRIVILEGES ON TABLES TO dbt_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA staging GRANT ALL PRIVILEGES ON SEQUENCES TO dbt_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT ALL PRIVILEGES ON SEQUENCES TO dbt_user;

-- ------------------------------------------------------------------------------
-- 3. Grants for app_readonly (SELECT on marts only, zero access to raw/staging)
-- ------------------------------------------------------------------------------
GRANT USAGE ON SCHEMA marts TO app_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA marts TO app_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT ON TABLES TO app_readonly;

-- Revoke any create/write privileges from public & app_readonly
REVOKE CREATE ON SCHEMA raw FROM app_readonly;
REVOKE CREATE ON SCHEMA staging FROM app_readonly;
REVOKE CREATE ON SCHEMA marts FROM app_readonly;
REVOKE CREATE ON SCHEMA public FROM app_readonly;
