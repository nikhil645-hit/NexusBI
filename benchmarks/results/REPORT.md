# 📊 Text-to-SQL Accuracy & Variance Benchmark Report

- **Timestamp**: `2026-11-09T09:24:03.418323+00:00`
- **Benchmark Mode**: `live`
- **Evaluation Set**: `main`
- **LLM Evaluated**: `GroqCloudAdapter` (Temperature: `0.0`)
- **Runs Evaluated**: `3`
- **Strict Mean Accuracy**: **`83.33%`** (Min: `83.33%`, Max: `83.33%`)
- **Lenient Mean Accuracy**: **`87.78%`** (Min: `86.67%`, Max: `90.0%`)
- **Strict Flipping Questions**: `2`
- **Average Query Latency**: `1983.39 ms`

> [!NOTE]
> **Strict scoring** requires exact matrix shape match (1:1 column projection).
> **Lenient scoring** requires matching row count and all expected column values, but permits harmless extra helper columns.

## 📈 Multi-Run Variance Breakdown

| Run Index | Strict Passed | Strict % | Lenient Passed | Lenient % | Total Qs | Avg Latency (ms) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Run 1 | 25 | **83.33%** | 26 | **86.67%** | 30 | 2030.67 |
| Run 2 | 25 | **83.33%** | 26 | **86.67%** | 30 | 2170.87 |
| Run 3 | 25 | **83.33%** | 27 | **90.0%** | 30 | 1983.39 |

## 🔄 Question Stability & Flips Across Runs

The following 2 question(s) flipped under strict scoring across evaluation runs:

| Question ID | Run 1 (Strict) | Run 2 (Strict) | Run 3 (Strict) | Lenient Outcome |
| :--- | :---: | :---: | :---: | :--- |
| `q14` | ✅ PASS | ✅ PASS | ❌ FAIL | 100% Pass |
| `q23` | ❌ FAIL | ❌ FAIL | ✅ PASS | 1/3 Pass |

## 🎯 Accuracy by Difficulty (Latest Run)

| Difficulty | Total Questions | Strict Passed | Strict % | Lenient Passed | Lenient % |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Easy** | 10 | 10 | 100.0% | 10 | 100.0% |
| **Medium** | 12 | 10 | 83.33% | 12 | 100.0% |
| **Hard** | 8 | 5 | 62.5% | 5 | 62.5% |

## 🔬 Failure Analysis (Latest Run - Strict Scoring)

| Question ID | Difficulty | Question | Reason (Strict) | Passed Lenient? |
| :--- | :---: | :--- | :--- | :---: |
| `q14` | medium | Show the top 3 product categories by average unit price with at least 50 units sold. | Value mismatch at row 0, col 1: 203.0 != 1098.3405418719212 (tol=0.05) | ✅ Yes |
| `q22` | medium | Which 5 product categories have the highest total revenue per unit sold? | Shape mismatch: generated (5, 4) vs expected (5, 2) | ✅ Yes |
| `q28` | hard | What was the 7-day rolling average revenue for the last 7 days of recorded daily sales? | Shape mismatch: generated (7, 2) vs expected (7, 3) | ❌ No |
| `q29` | hard | Compare the average spend of single-order buyers versus multi-order repeat buyers. Return one row per buyer type (single-order vs repeat) with the average spend. | String mismatch at row 0, col 0: 'repeat' != 'Repeat Buyer' | ❌ No |
| `q30` | hard | Identify months in 2018 where the late delivery rate was above 5 percent. | Shape mismatch: generated (8, 1) vs expected (6, 2) | ❌ No |

### Detailed Failure Diffs

#### `q14` - Show the top 3 product categories by average unit price with at least 50 units sold.
- **Strict Failure Reason**: Value mismatch at row 0, col 1: 203.0 != 1098.3405418719212 (tol=0.05)
- **Lenient Outcome**: PASSED (Contains all expected columns; extra columns present)
```sql
-- Generated SQL
WITH category_stats AS (
    SELECT
        category_name,
        SUM(units_sold) AS total_units_sold,
        SUM(avg_unit_price * units_sold)::NUMERIC / NULLIF(SUM(units_sold), 0) AS avg_unit_price
    FROM marts.mart_top_products
    GROUP BY category_name
    HAVING SUM(units_sold) >= 50
)
SELECT
    category_name,
    total_units_sold,
    avg_unit_price
FROM category_stats
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
- **Strict Failure Reason**: Shape mismatch: generated (5, 4) vs expected (5, 2)
- **Lenient Outcome**: PASSED (Contains all expected columns; extra columns present)
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

#### `q28` - What was the 7-day rolling average revenue for the last 7 days of recorded daily sales?
- **Strict Failure Reason**: Shape mismatch: generated (7, 2) vs expected (7, 3)
- **Lenient Outcome**: FAILED (Fewer columns in generated (2) than expected (3))
```sql
-- Generated SQL
WITH daily AS (
    SELECT
        sales_date,
        total_revenue,
        SUM(total_revenue) OVER (
            ORDER BY sales_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) / 7.0 AS rolling_7day_avg_revenue
    FROM marts.mart_daily_sales
),
ranked AS (
    SELECT
        sales_date,
        rolling_7day_avg_revenue,
        ROW_NUMBER() OVER (ORDER BY sales_date DESC) AS rn
    FROM daily
)
SELECT
    sales_date,
    ROUND(rolling_7day_avg_revenue, 2) AS rolling_7day_avg_revenue
FROM ranked
WHERE rn <= 7
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
- **Strict Failure Reason**: String mismatch at row 0, col 0: 'repeat' != 'Repeat Buyer'
- **Lenient Outcome**: FAILED (Expected column(s) [0] not found among generated columns)
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

#### `q30` - Identify months in 2018 where the late delivery rate was above 5 percent.
- **Strict Failure Reason**: Shape mismatch: generated (8, 1) vs expected (6, 2)
- **Lenient Outcome**: FAILED (Row count mismatch: generated 8 vs expected 6)
```sql
-- Generated SQL
SELECT year_month
FROM marts.mart_delivery_performance
WHERE EXTRACT(YEAR FROM order_month) = 2018
  AND pct_late_vs_estimated > 0.05
ORDER BY year_month;

-- Expected Ground Truth SQL
SELECT year_month, pct_late_vs_estimated
FROM marts.mart_delivery_performance
WHERE year_month LIKE '2018-%' AND pct_late_vs_estimated > 5.0
ORDER BY pct_late_vs_estimated DESC;

```
