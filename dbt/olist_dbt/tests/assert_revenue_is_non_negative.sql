-- ==============================================================================
-- assert_revenue_is_non_negative.sql - Singular Data Quality Test
-- Purpose:
--   In dbt, a singular test asserts that NO records meet a failure condition.
--   This test verifies that calculated monetary values in the daily sales mart
--   are never negative. If this query returns ANY rows, dbt test fails.
-- ==============================================================================

select
    sales_date,
    total_revenue,
    avg_order_value
from {{ ref('mart_daily_sales') }}
where total_revenue < 0
   or avg_order_value < 0
