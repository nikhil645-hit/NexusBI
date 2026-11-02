-- ==============================================================================
-- 02_users.sql - Role-Based Access Control (RBAC) & User Provisioning
-- Purpose:
--   Creates dedicated database users adhering to the Principle of Least Privilege:
--     1. dbt_user: Used by dbt in transformations (Read raw, Full staging & marts).
--     2. app_readonly: Used by Streamlit conversational BI (Read-only on marts only).
--
-- Security Note:
--   Passwords in this file are PLACEHOLDERS. Replace them with strong, unique
--   passwords before executing, and update your local .env accordingly.
--   NEVER commit actual production passwords.
--
-- How to run:
--   psql -h $REDSHIFT_HOST -p $REDSHIFT_PORT -U $REDSHIFT_ADMIN_USER -d $REDSHIFT_DB -f sql/02_users.sql
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Create dbt Transformation User
-- ------------------------------------------------------------------------------
-- In a viva: dbt needs to read raw landing tables and build/drop tables and views
-- inside the staging and marts schemas. It should NEVER have write access to raw.

CREATE USER dbt_user WITH PASSWORD 'REPLACE_WITH_STRONG_DBT_PASSWORD_123!';

-- Grant usage on schemas
GRANT USAGE ON SCHEMA raw TO dbt_user;
GRANT ALL ON SCHEMA staging TO dbt_user;
GRANT ALL ON SCHEMA marts TO dbt_user;

-- Grant permissions on existing tables
GRANT SELECT ON ALL TABLES IN SCHEMA raw TO dbt_user;
GRANT ALL ON ALL TABLES IN SCHEMA staging TO dbt_user;
GRANT ALL ON ALL TABLES IN SCHEMA marts TO dbt_user;

-- Ensure dbt_user has access to future tables created by Airbyte or dbt
ALTER DEFAULT PRIVILEGES IN SCHEMA raw GRANT SELECT ON TABLES TO dbt_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA staging GRANT ALL ON TABLES TO dbt_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT ALL ON TABLES TO dbt_user;


-- ------------------------------------------------------------------------------
-- 2. Create Application Read-Only User (Streamlit / LLM Conversational BI)
-- ------------------------------------------------------------------------------
-- In a viva: Defense in depth! Even if an LLM is tricked into generating 'DROP TABLE'
-- or 'DELETE FROM', this database user physically cannot execute destructive DDL/DML.
-- It is strictly locked to SELECT operations on the curated marts schema only.

CREATE USER app_readonly WITH PASSWORD 'REPLACE_WITH_STRONG_APP_PASSWORD_123!';

-- Grant USAGE only on the marts schema (cannot see raw or staging schemas)
GRANT USAGE ON SCHEMA marts TO app_readonly;

-- Grant SELECT only on existing marts tables
GRANT SELECT ON ALL TABLES IN SCHEMA marts TO app_readonly;

-- Grant SELECT on future tables created in marts by dbt runs
ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT ON TABLES TO app_readonly;

-- Explicitly revoke any public create permissions (safety guard)
REVOKE CREATE ON SCHEMA raw FROM app_readonly;
REVOKE CREATE ON SCHEMA staging FROM app_readonly;
REVOKE CREATE ON SCHEMA marts FROM app_readonly;
