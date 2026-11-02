-- ==============================================================================
-- mart_daily_sales.sql - Daily E-Commerce Sales Performance
-- Purpose:
--   Aggregates sales metrics at the daily grain: order volume, units sold,
--   total merchandise revenue, freight revenue, and average order value (AOV).
-- ==============================================================================

with orders as (
    select * from {{ ref('stg_orders') }}
    where order_status != 'canceled'
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

