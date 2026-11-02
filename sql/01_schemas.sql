-- ==============================================================================
-- 01_schemas.sql - Redshift Serverless Schema Initialization
-- Purpose:
--   Creates the three core logical schemas required for our Medallion-style ELT:
--     1. raw     - Landing zone where Airbyte writes untouched source tables.
--     2. staging - Transformation zone where dbt cleans, casts, and filters views.
--     3. marts   - Analytics zone where dbt models dimensional business tables.
--
-- How to run:
--   Execute this script as the Redshift admin user using the AWS Redshift Query
--   Editor v2 or via psql:
--   psql -h $REDSHIFT_HOST -p $REDSHIFT_PORT -U $REDSHIFT_ADMIN_USER -d $REDSHIFT_DB -f sql/01_schemas.sql
-- ==============================================================================

-- 1. Schema for raw ingested data (written by Airbyte)
-- In a viva: Explain that raw tables preserve the exact schema and data from the
-- transactional system without modification, enabling auditability and re-processing.
CREATE SCHEMA IF NOT EXISTS raw;

-- 2. Schema for staging models (managed by dbt)
-- In a viva: Explain that staging models are lightweight SQL views that rename columns,
-- cast data types, standardize timestamps, and join basic dimensional lookup tables.
CREATE SCHEMA IF NOT EXISTS staging;

-- 3. Schema for curated analytical data marts (managed by dbt)
-- In a viva: Explain that marts are optimized physical tables (star/snowflake schema)
-- designed for high-performance reporting, BI tools, and LLM text-to-SQL querying.
CREATE SCHEMA IF NOT EXISTS marts;

