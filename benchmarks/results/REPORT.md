# 📊 Text-to-SQL Accuracy & Variance Benchmark Report

- **Timestamp**: `2026-11-09T08:31:11.335129+00:00`
- **Benchmark Mode**: `live`
- **Evaluation Set**: `main`
- **LLM Evaluated**: `GroqCloudAdapter` (Temperature: `0.0`)
- **Runs Evaluated**: `3`
- **Mean Accuracy**: **`81.11%`** (Min: `80.0%`, Max: `83.33%`)
- **Flipping Questions**: `3`
- **Average Query Latency**: `2276.01 ms`

## 📈 Multi-Run Variance Breakdown

| Run Index | Passed Questions | Total Questions | Accuracy % | Avg Latency (ms) |
| :---: | :---: | :---: | :---: | :---: |
| Run 1 | 25 | 30 | **83.33%** | 1966.64 |
| Run 2 | 24 | 30 | **80.0%** | 1998.44 |
| Run 3 | 24 | 30 | **80.0%** | 2276.01 |

## 🔄 Question Stability & Flips Across Runs

The following 3 question(s) flipped between passing and failing across evaluation runs:

| Question ID | Run 1 | Run 2 | Run 3 | Stability Note |
| :--- | :---: | :---: | :---: | :--- |
| `q14` | ❌ FAIL | ✅ PASS | ❌ FAIL | Passed 1/3 runs |
| `q22` | ✅ PASS | ❌ FAIL | ❌ FAIL | Passed 1/3 runs |
| `q30` | ✅ PASS | ❌ FAIL | ✅ PASS | Passed 2/3 runs |

## 🎯 Accuracy by Difficulty (Latest Run)

| Difficulty | Total Questions | Passed | Accuracy % |
| :--- | :---: | :---: | :---: |
| **Easy** | 10 | 9 | 90.0% |
| **Medium** | 12 | 10 | 83.33% |
| **Hard** | 8 | 5 | 62.5% |

## 🔬 Failure Analysis (Latest Run)

| Question ID | Difficulty | Question | Reason |
| :--- | :---: | :--- | :--- |
| `q07` | easy | What was the average delivery time in days across all months? | Value mismatch at row 0, col 0: 12.5 != 14.309130434782608 (tol=0.05) |
| `q14` | medium | Show the top 3 product categories by average unit price with at least 50 units sold. | Shape mismatch: generated (3, 2) vs expected (3, 3) |
| `q22` | medium | Which 5 product categories have the highest total revenue per unit sold? | Shape mismatch: generated (5, 4) vs expected (5, 2) |
| `q23` | hard | What percentage of total revenue came from the top 3 product categories? | SQL Execution Error: column "total.total_revenue" must appear in the GROUP BY clause or be used in an aggregate function
LINE 1: ...UM(CASE WHEN rn <= 3 THEN category_revenue END) / total.tota...
                                                             ^
 |
| `q28` | hard | What was the 7-day rolling average revenue for the last 7 days of recorded daily sales? | Shape mismatch: generated (7, 2) vs expected (7, 3) |
| `q29` | hard | Compare the average spend of single-order buyers versus multi-order repeat buyers. Return one row per buyer type (single-order vs repeat) with the average spend. | String mismatch at row 0, col 0: 'repeat' != 'Repeat Buyer' |

### Detailed Failure Diffs

#### `q07` - What was the average delivery time in days across all months?
- **Failure Reason**: Value mismatch at row 0, col 0: 12.5 != 14.309130434782608 (tol=0.05)
```sql
-- Generated SQL
SELECT ROUND(
         SUM(avg_delivery_days * total_delivered_orders)::NUMERIC /
         NULLIF(SUM(total_delivered_orders), 0),
         2
       ) AS avg_delivery_time_days
FROM marts.mart_delivery_performance;

-- Expected Ground Truth SQL
SELECT AVG(avg_delivery_days) AS avg_delivery_days
FROM marts.mart_delivery_performance;

```

#### `q14` - Show the top 3 product categories by average unit price with at least 50 units sold.
- **Failure Reason**: Shape mismatch: generated (3, 2) vs expected (3, 3)
```sql
-- Generated SQL
SELECT
    category_name,
    AVG(avg_unit_price) AS avg_unit_price
FROM marts.mart_top_products
WHERE units_sold >= 50
GROUP BY category_name
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

#### `q22` - Which 5 product categories have the highest total revenue per unit sold?
- **Failure Reason**: Shape mismatch: generated (5, 4) vs expected (5, 2)
```sql
-- Generated SQL
SELECT
    category_name,
    SUM(total_revenue) AS total_revenue,
    SUM(units_sold) AS total_units_sold,
    SUM(total_revenue) / NULLIF(SUM(units_sold), 0) AS revenue_per_unit
FROM marts.mart_top_products
GROUP BY category_name
ORDER BY revenue_per_unit DESC
LIMIT 5;

-- Expected Ground Truth SQL
SELECT category_name,
       SUM(total_revenue) / SUM(units_sold) AS revenue_per_unit
FROM marts.mart_top_products
GROUP BY category_name
ORDER BY revenue_per_unit DESC
LIMIT 5;

```

#### `q23` - What percentage of total revenue came from the top 3 product categories?
- **Failure Reason**: SQL Execution Error: column "total.total_revenue" must appear in the GROUP BY clause or be used in an aggregate function
LINE 1: ...UM(CASE WHEN rn <= 3 THEN category_revenue END) / total.tota...
                                                             ^

```sql
-- Generated SQL
WITH category_rev AS (
    SELECT
        category_name,
        SUM(total_revenue) AS category_revenue
    FROM marts.mart_top_products
    GROUP BY category_name
),
ranked AS (
    SELECT
        category_name,
        category_revenue,
        ROW_NUMBER() OVER (ORDER BY category_revenue DESC) AS rn
    FROM category_rev
),
total AS (
    SELECT SUM(category_revenue) AS total_revenue
    FROM category_rev
)
SELECT
    ROUND(
        (SUM(CASE WHEN rn <= 3 THEN category_revenue END) / total.total_revenue) * 100,
        2
    ) AS top_3_category_revenue_pct
FROM ranked
CROSS JOIN total;

-- Expected Ground Truth SQL
WITH cat_rev AS (
    SELECT category_name, SUM(total_revenue) AS rev
    FROM marts.mart_top_products
    GROUP BY category_name
),
top3 AS (
    SELECT SUM(rev) AS top3_rev
    FROM (SELECT rev FROM cat_rev ORDER BY rev DESC LIMIT 3) sub
),
total AS (
    SELECT SUM(rev) AS all_rev FROM cat_rev
)
SELECT ROUND((top3.top3_rev / total.all_rev) * 100, 2) AS top3_revenue_pct
FROM top3, total;

```

#### `q28` - What was the 7-day rolling average revenue for the last 7 days of recorded daily sales?
- **Failure Reason**: Shape mismatch: generated (7, 2) vs expected (7, 3)
```sql
-- Generated SQL
WITH ranked AS (
    SELECT
        sales_date,
        total_revenue,
        SUM(total_revenue) OVER (
            ORDER BY sales_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) / 7.0 AS rolling_7day_avg_revenue,
        ROW_NUMBER() OVER (ORDER BY sales_date DESC) AS rn_desc
    FROM marts.mart_daily_sales
)
SELECT
    sales_date,
    rolling_7day_avg_revenue
FROM ranked
WHERE rn_desc <= 7
ORDER BY sales_date ASC;

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

#### `q29` - Compare the average spend of single-order buyers versus multi-order repeat buyers. Return one row per buyer type (single-order vs repeat) with the average spend.
- **Failure Reason**: String mismatch at row 0, col 0: 'repeat' != 'Repeat Buyer'
```sql
-- Generated SQL
SELECT
    CASE
        WHEN total_orders = 1 THEN 'single-order'
        ELSE 'repeat'
    END AS buyer_type,
    AVG(total_spend) AS avg_spend
FROM marts.mart_customer_summary
GROUP BY buyer_type
ORDER BY buyer_type;

-- Expected Ground Truth SQL
SELECT CASE WHEN total_orders = 1 THEN 'Single Order' ELSE 'Repeat Buyer' END AS buyer_type,
       ROUND(AVG(total_spend), 2) AS avg_spend
FROM marts.mart_customer_summary
GROUP BY 1;

```
