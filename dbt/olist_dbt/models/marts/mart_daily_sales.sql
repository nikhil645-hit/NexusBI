-- ==============================================================================
-- mart_daily_sales.sql - Daily E-Commerce Sales Performance (Incremental)
--
-- Materialization: Incremental with unique_key='sales_date'.
-- On full refresh, processes entire transaction history.
-- On incremental runs, looks back 3 days to capture late-arriving orders.
-- ==============================================================================

{{
    config(
        materialized='incremental',
        unique_key='sales_date',
        on_schema_change='sync_all_columns'
    )
}}

with orders as (
    select * from {{ ref('stg_orders') }}
    where order_status != 'canceled'
    {% if is_incremental() %}
        and order_purchase_date >= (
            select coalesce(max(sales_date) - interval '3 days', '2016-01-01'::date)
            from {{ this }}
        )
    {% endif %}
),

order_items as (
    select * from {{ ref('stg_order_items') }}
),

daily_metrics as (
    select
        o.order_purchase_date as sales_date,
        count(distinct o.order_id) as total_orders,
        count(i.order_item_id) as total_items_sold,
        round(coalesce(sum(i.price), 0.00), 2) as total_revenue,
        round(coalesce(sum(i.freight_value), 0.00), 2) as total_freight,
        round(
            coalesce(sum(i.price), 0.00) / nullif(count(distinct o.order_id), 0),
            2
        ) as avg_order_value
    from orders o
    inner join order_items i
        on o.order_id = i.order_id
    group by o.order_purchase_date
)

select * from daily_metrics
order by sales_date desc
