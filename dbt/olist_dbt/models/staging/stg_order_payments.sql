-- ==============================================================================
-- stg_order_payments.sql - Cleansed Order Payments Staging View
-- Purpose:
--   Standardizes payment methods, installment numbers, and monetary amounts.
--   Drops Airbyte metadata columns.
-- ==============================================================================

with source as (
    select * from {{ source('raw', 'order_payments') }}
),

cleaned as (
    select
        cast(order_id as varchar(64)) as order_id,
        cast(payment_sequential as integer) as payment_sequential,
        lower(trim(cast(payment_type as varchar(30)))) as payment_type,
        cast(payment_installments as integer) as payment_installments,
        cast(payment_value as numeric(10,2)) as payment_value
    from source
)

select * from cleaned

