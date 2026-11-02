-- ==============================================================================
-- mart_delivery_performance.sql - Monthly Delivery & Fulfillment Performance
-- Purpose:
--   Measures shipping lead times, carrier efficiency, and SLA compliance:
--   average delivery days, estimated days, and percentage of late deliveries.
-- ==============================================================================

with delivered_orders as (
    select
        order_id,
        order_purchase_timestamp,
        order_delivered_customer_date,
        order_estimated_delivery_date,
        date_trunc('month', order_purchase_timestamp) as order_month,
        to_char(order_purchase_timestamp, 'YYYY-MM') as year_month,
        (cast(order_delivered_customer_date as date) - cast(order_purchase_timestamp as date)) as actual_delivery_days,
        (cast(order_estimated_delivery_date as date) - cast(order_purchase_timestamp as date)) as estimated_delivery_days,
        case
            when order_delivered_customer_date > order_estimated_delivery_date then 1
            else 0
        end as is_late
    from {{ ref('stg_orders') }}
    where order_status = 'delivered'
      and order_delivered_customer_date is not null
)

select
    order_month,
    year_month,
    count(order_id) as total_delivered_orders,
    round(avg(actual_delivery_days), 2) as avg_delivery_days,
    round(avg(estimated_delivery_days), 2) as avg_estimated_delivery_days,
    sum(is_late) as late_orders_count,
    round(100.0 * sum(is_late) / nullif(count(order_id), 0), 2) as pct_late_vs_estimated
from delivered_orders
group by order_month, year_month
order by order_month desc
