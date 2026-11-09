# 📊 Text-to-SQL Accuracy Benchmark Report

- **Timestamp**: `2026-11-09T06:06:27.579108+00:00`
- **Benchmark Mode**: `live`
- **LLM Evaluated**: `GroqCloudAdapter`
- **Total Test Questions**: `30`
- **Overall Accuracy**: **`73.33%`** (22/30)
- **Average Query Latency**: `1821.55 ms`

## 🎯 Accuracy by Difficulty

| Difficulty | Total Questions | Passed | Accuracy % |
| :--- | :---: | :---: | :---: |
| **Easy** | 10 | 10 | 100.0% |
| **Medium** | 12 | 9 | 75.0% |
| **Hard** | 8 | 3 | 37.5% |

## 🔬 Failure Analysis

| Question ID | Difficulty | Question | Reason |
| :--- | :---: | :--- | :--- |
| `q14` | medium | Show the top 3 product categories by average unit price with at least 50 units sold. | Value mismatch at row 0, col 1: 1368.067 != 1098.3405418719212 (tol=0.05) |
| `q19` | medium | Show the top 5 days with the highest daily revenue in 2018. | Shape mismatch: generated (5, 2) vs expected (5, 3) |
| `q21` | medium | Show the monthly average delivery days compared to estimated delivery days for 2018. | String mismatch at row 0, col 0: '2018-01-01' != '2018-01' |
| `q25` | hard | Identify months where average delivery days exceeded 15 days along with total delivered orders. | Shape mismatch: generated (7, 2) vs expected (7, 4) |
| `q26` | hard | Combine monthly total revenue from daily sales with monthly late delivery percentage for 2018. | Shape mismatch: generated (9, 3) vs expected (8, 3) |
| `q28` | hard | What was the 7-day rolling average revenue for the last 7 days of recorded daily sales? | Shape mismatch: generated (3, 2) vs expected (7, 3) |
| `q29` | hard | Compare the average spend of single-order buyers versus multi-order repeat buyers. | Shape mismatch: generated (1, 2) vs expected (2, 3) |
| `q30` | hard | Identify months in 2018 where the late delivery rate was above 5 percent. | Shape mismatch: generated (6, 2) vs expected (6, 4) |

### Detailed Failure Diffs

#### `q14` - Show the top 3 product categories by average unit price with at least 50 units sold.
- **Failure Reason**: Value mismatch at row 0, col 1: 1368.067 != 1098.3405418719212 (tol=0.05)
```sql
-- Generated SQL
SELECT
    category_name,
    AVG(avg_unit_price) AS avg_unit_price,
    SUM(units_sold) AS total_units_sold
FROM marts.mart_top_products
GROUP BY category_name
HAVING SUM(units_sold) >= 50
ORDER BY avg_unit_price DESC
LIMIT 3;

-- Expected Ground Truth SQL
SELECT category_name,
       SUM(total_revenue) / SUM(units_sold) AS avg_unit_price,
       SUM(units_sold) AS total_units
FROM marts.mart_top_products
GROUP BY category_name
HAVING SUM(units_sold) >= 50
ORDER BY avg_unit_price DESC
LIMIT 3;

```

#### `q19` - Show the top 5 days with the highest daily revenue in 2018.
- **Failure Reason**: Shape mismatch: generated (5, 2) vs expected (5, 3)
```sql
-- Generated SQL
SELECT sales_date,
       total_revenue
FROM marts.mart_daily_sales
WHERE EXTRACT(YEAR FROM sales_date) = 2018
ORDER BY total_revenue DESC
LIMIT 5;

-- Expected Ground Truth SQL
SELECT sales_date, total_revenue, total_orders
FROM marts.mart_daily_sales
WHERE EXTRACT(YEAR FROM sales_date) = 2018
ORDER BY total_revenue DESC
LIMIT 5;

```

#### `q21` - Show the monthly average delivery days compared to estimated delivery days for 2018.
- **Failure Reason**: String mismatch at row 0, col 0: '2018-01-01' != '2018-01'
```sql
-- Generated SQL
SELECT DATE_TRUNC('month', order_month)::date AS month,
       AVG(avg_delivery_days)        AS avg_delivery_days,
       AVG(avg_estimated_delivery_days) AS avg_estimated_delivery_days
FROM   marts.mart_delivery_performance
WHERE  EXTRACT(YEAR FROM order_month) = 2018
GROUP BY 1
ORDER BY 1;

-- Expected Ground Truth SQL
SELECT year_month, avg_delivery_days, avg_estimated_delivery_days
FROM marts.mart_delivery_performance
WHERE year_month LIKE '2018-%'
ORDER BY year_month ASC;

```

#### `q25` - Identify months where average delivery days exceeded 15 days along with total delivered orders.
- **Failure Reason**: Shape mismatch: generated (7, 2) vs expected (7, 4)
```sql
-- Generated SQL
SELECT DATE_TRUNC('month', order_month)::date AS month,
       total_delivered_orders
FROM marts.mart_delivery_performance
WHERE avg_delivery_days > 15
ORDER BY month;

-- Expected Ground Truth SQL
SELECT year_month, total_delivered_orders, avg_delivery_days, pct_late_vs_estimated
FROM marts.mart_delivery_performance
WHERE avg_delivery_days > 15.0
ORDER BY avg_delivery_days DESC;

```

#### `q26` - Combine monthly total revenue from daily sales with monthly late delivery percentage for 2018.
- **Failure Reason**: Shape mismatch: generated (9, 3) vs expected (8, 3)
```sql
-- Generated SQL
WITH revenue_monthly AS (
    SELECT DATE_TRUNC('month', sales_date)::DATE AS month,
           SUM(total_revenue) AS monthly_revenue
    FROM marts.mart_daily_sales
    WHERE EXTRACT(YEAR FROM sales_date) = 2018
    GROUP BY month
),
delivery_monthly AS (
    SELECT DATE_TRUNC('month', order_month)::DATE AS month,
           ROUND(
               (SUM(late_orders_count)::NUMERIC / NULLIF(SUM(total_delivered_orders), 0)) * 100,
               2
           ) AS late_delivery_pct
    FROM marts.mart_delivery_performance
    WHERE EXTRACT(YEAR FROM order_month) = 2018
    GROUP BY month
)
SELECT r.month,
       r.monthly_revenue,
       d.late_delivery_pct
FROM revenue_monthly r
FULL OUTER JOIN delivery_monthly d
    ON r.month = d.month
ORDER BY r.month;

-- Expected Ground Truth SQL
SELECT d.sales_month, d.total_revenue, p.pct_late_vs_estimated
FROM (
    SELECT DATE_TRUNC('month', sales_date)::DATE AS sales_month,
           TO_CHAR(sales_date, 'YYYY-MM') AS ym,
           SUM(total_revenue) AS total_revenue
    FROM marts.mart_daily_sales
    WHERE EXTRACT(YEAR FROM sales_date) = 2018
    GROUP BY 1, 2
) d
JOIN marts.mart_delivery_performance p ON d.ym = p.year_month
ORDER BY d.sales_month ASC;

```

#### `q28` - What was the 7-day rolling average revenue for the last 7 days of recorded daily sales?
- **Failure Reason**: Shape mismatch: generated (3, 2) vs expected (7, 3)
```sql
-- Generated SQL
WITH max_date AS (
    SELECT MAX(sales_date) AS max_sales_date
    FROM marts.mart_daily_sales
)
SELECT
    sales_date,
    AVG(total_revenue) OVER (
        ORDER BY sales_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS rolling_7day_avg_revenue
FROM marts.mart_daily_sales
CROSS JOIN max_date
WHERE sales_date BETWEEN max_date.max_sales_date - INTERVAL '6 days'
                      AND max_date.max_sales_date
ORDER BY sales_date;

-- Expected Ground Truth SQL
WITH rolling AS (
    SELECT sales_date, total_revenue,
           AVG(total_revenue) OVER (ORDER BY sales_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS rolling_7d_avg
    FROM marts.mart_daily_sales
)
SELECT sales_date, total_revenue, ROUND(rolling_7d_avg, 2) AS rolling_7d_avg
FROM rolling
ORDER BY sales_date DESC
LIMIT 7;

```

#### `q29` - Compare the average spend of single-order buyers versus multi-order repeat buyers.
- **Failure Reason**: Shape mismatch: generated (1, 2) vs expected (2, 3)
```sql
-- Generated SQL
SELECT 
    AVG(CASE WHEN total_orders = 1 THEN total_spend END) AS avg_spend_single_order,
    AVG(CASE WHEN total_orders > 1 THEN total_spend END) AS avg_spend_multi_order
FROM marts.mart_customer_summary;

-- Expected Ground Truth SQL
SELECT CASE WHEN total_orders = 1 THEN 'Single Order' ELSE 'Repeat Buyer' END AS buyer_type,
       COUNT(*) AS buyer_count,
       ROUND(AVG(total_spend), 2) AS avg_spend
FROM marts.mart_customer_summary
GROUP BY 1;

```

#### `q30` - Identify months in 2018 where the late delivery rate was above 5 percent.
- **Failure Reason**: Shape mismatch: generated (6, 2) vs expected (6, 4)
```sql
-- Generated SQL
SELECT DATE_TRUNC('month', order_month)::date AS delivery_month,
       ROUND((late_orders_count::numeric / total_delivered_orders) * 100, 2) AS late_delivery_rate_pct
FROM marts.mart_delivery_performance
WHERE EXTRACT(YEAR FROM order_month) = 2018
  AND total_delivered_orders > 0
  AND (late_orders_count::numeric / total_delivered_orders) * 100 > 5
ORDER BY delivery_month;

-- Expected Ground Truth SQL
SELECT year_month, total_delivered_orders, late_orders_count, pct_late_vs_estimated
FROM marts.mart_delivery_performance
WHERE year_month LIKE '2018-%' AND pct_late_vs_estimated > 5.0
ORDER BY pct_late_vs_estimated DESC;

```
