-- ==============================================================================
-- stg_order_items.sql - Cleansed Order Line Items Staging View
-- Purpose:
--   Casts item numbers, prices, and freight values to numeric decimals.
--   Computes total item line cost (price + freight). Drops Airbyte metadata.
-- ==============================================================================

with source as (
    select * from {{ source('raw', 'order_items') }}
),

cleaned as (
    select
        cast(order_id as varchar(64)) as order_id,
        cast(order_item_id as integer) as order_item_id,
        cast(product_id as varchar(64)) as product_id,
        cast(seller_id as varchar(64)) as seller_id,
        cast(shipping_limit_date as timestamp) as shipping_limit_date,
        cast(price as numeric(10,2)) as price,
        cast(freight_value as numeric(10,2)) as freight_value,
        cast(price + freight_value as numeric(10,2)) as total_item_cost
    from source
)

select * from cleaned

