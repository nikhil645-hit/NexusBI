-- ==============================================================================
-- mart_customer_summary.sql - Customer Lifetime and Geographic Profile
-- Purpose:
--   Aggregates purchasing behavior by unique customer: order count,
--   lifetime spend (merchandise + freight), geography, and first/last order dates.
-- ==============================================================================

with customers as (
    select * from {{ ref('stg_customers') }}
),

orders as (
    select * from {{ ref('stg_orders') }}
    where order_status != 'canceled'
),

order_items as (
    select * from {{ ref('stg_order_items') }}
),

customer_orders as (
    select
        c.customer_unique_id,
        max(c.customer_city) as customer_city,
        max(c.customer_state) as customer_state,
        count(distinct o.order_id) as total_orders,
        round(coalesce(sum(i.price + i.freight_value), 0.00), 2) as total_spend,
        min(o.order_purchase_timestamp) as first_order_date,
        max(o.order_purchase_timestamp) as last_order_date
    from customers c
    inner join orders o
        on c.customer_id = o.customer_id
    inner join order_items i
        on o.order_id = i.order_id
    group by c.customer_unique_id
)

select * from customer_orders
order by total_spend desc
