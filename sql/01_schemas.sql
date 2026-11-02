-- ==============================================================================
-- 01_schemas.sql - PostgreSQL Data Warehouse Schema Initialization
-- Purpose:
--   Creates the three core logical schemas for our local Medallion-style ELT:
--     1. raw     - Landing zone where Airbyte writes untouched source tables.
--     2. staging - Transformation zone where dbt cleans, casts, and filters views.
--     3. marts   - Analytics zone where dbt models dimensional business tables.
--
-- How to run:
--   psql -h localhost -p 5434 -U postgres -d warehouse -f sql/01_schemas.sql
--   (or using docker exec: docker exec -i olist-warehouse psql -U postgres -d warehouse < sql/01_schemas.sql)
-- ==============================================================================

-- 1. Schema for raw ingested data (written by Airbyte)
CREATE SCHEMA IF NOT EXISTS raw;

-- 2. Schema for staging models (managed by dbt)
CREATE SCHEMA IF NOT EXISTS staging;

-- 3. Schema for curated analytical data marts (managed by dbt)
CREATE SCHEMA IF NOT EXISTS marts;
