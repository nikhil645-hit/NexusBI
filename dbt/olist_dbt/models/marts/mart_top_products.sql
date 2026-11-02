-- ==============================================================================
-- mart_top_products.sql - Top Performing Products and Categories
-- Purpose:
--   Aggregates sales by product, calculating total revenue, units sold,
--   and ranking products across the entire catalog.
-- ==============================================================================

with valid_orders as (
    select order_id from {{ ref('stg_orders') }}
    where order_status != 'canceled'
),

order_items as (
    select * from {{ ref('stg_order_items') }}
),

products as (
    select * from {{ ref('stg_products') }}
),

product_sales as (
    select
        p.product_id,
        p.category_name,
        count(i.order_item_id) as units_sold,
        round(coalesce(sum(i.price), 0.00), 2) as total_revenue,
        round(coalesce(avg(i.price), 0.00), 2) as avg_unit_price
    from order_items i
    inner join valid_orders o
        on i.order_id = o.order_id
    left join products p
        on i.product_id = p.product_id
    group by p.product_id, p.category_name
),

ranked_products as (
    select
        product_id,
        category_name,
        units_sold,
        total_revenue,
        avg_unit_price,
        dense_rank() over (order by total_revenue desc) as revenue_rank,
        dense_rank() over (order by units_sold desc) as units_sold_rank
    from product_sales
)

select * from ranked_products
order by revenue_rank asc

