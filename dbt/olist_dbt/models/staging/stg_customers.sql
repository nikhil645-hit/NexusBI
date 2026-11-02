-- ==============================================================================
-- stg_customers.sql - Cleansed Customer Staging View
-- Purpose:
--   Renames and standardizes customer identifiers, geographical cities, and states.
--   Drops all Airbyte ingestion metadata.
-- ==============================================================================

with source as (
    select * from {{ source('raw', 'customers') }}
),

cleaned as (
    select
        cast(customer_id as varchar(64)) as customer_id,
        cast(customer_unique_id as varchar(64)) as customer_unique_id,
        cast(customer_zip_code_prefix as varchar(10)) as customer_zip_code_prefix,
        trim(lower(cast(customer_city as varchar(100)))) as customer_city,
        upper(trim(cast(customer_state as varchar(10)))) as customer_state
    from source
)

select * from cleaned

