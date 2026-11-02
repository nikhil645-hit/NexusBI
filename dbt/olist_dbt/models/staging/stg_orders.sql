-- ==============================================================================
-- stg_orders.sql - Cleansed Orders Staging View
-- Purpose:
--   Casts order status, standardizes timestamps, and extracts the purchase date.
--   Drops all Airbyte ingestion metadata.
-- ==============================================================================

with source as (
    select * from {{ source('raw', 'orders') }}
),

cleaned as (
    select
        cast(order_id as varchar(64)) as order_id,
        cast(customer_id as varchar(64)) as customer_id,
        lower(trim(cast(order_status as varchar(30)))) as order_status,
        cast(order_purchase_timestamp as timestamp) as order_purchase_timestamp,
        cast(order_purchase_timestamp as date) as order_purchase_date,
        cast(order_approved_at as timestamp) as order_approved_at,
        cast(order_delivered_carrier_date as timestamp) as order_delivered_carrier_date,
        cast(order_delivered_customer_date as timestamp) as order_delivered_customer_date,
        cast(order_estimated_delivery_date as timestamp) as order_estimated_delivery_date
    from source
)

select * from cleaned
