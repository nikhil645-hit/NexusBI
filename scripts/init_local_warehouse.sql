-- ==============================================================================
-- scripts/init_local_warehouse.sql - Local Docker Postgres Initialization
--
-- Initializes warehouse database schemas, service users, and sample marts data
-- for reviewers testing NexusBI with zero external cloud dependencies.
-- ==============================================================================

-- 1. Create Roles
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'dbt_user') THEN
        CREATE ROLE dbt_user WITH LOGIN PASSWORD 'dbt_user_password';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_readonly') THEN
        CREATE ROLE app_readonly WITH LOGIN PASSWORD 'readonly_local_pass';
    END IF;
END
$$;

-- 2. Create Schemas
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;

GRANT ALL ON SCHEMA raw TO dbt_user;
GRANT ALL ON SCHEMA staging TO dbt_user;
GRANT ALL ON SCHEMA marts TO dbt_user;

GRANT USAGE ON SCHEMA marts TO app_readonly;

-- 3. Create Curated Marts Tables
CREATE TABLE IF NOT EXISTS marts.mart_daily_sales (
    sales_date DATE PRIMARY KEY,
    total_orders INTEGER,
    total_items_sold INTEGER,
    total_revenue NUMERIC(12, 2),
    total_freight NUMERIC(12, 2),
    avg_order_value NUMERIC(12, 2)
);

CREATE TABLE IF NOT EXISTS marts.mart_top_products (
    product_id VARCHAR(64) PRIMARY KEY,
    category_name VARCHAR(64),
    units_sold INTEGER,
    total_revenue NUMERIC(12, 2),
    avg_unit_price NUMERIC(12, 2),
    revenue_rank INTEGER,
    units_sold_rank INTEGER
);

CREATE TABLE IF NOT EXISTS marts.mart_customer_summary (
    customer_unique_id VARCHAR(64) PRIMARY KEY,
    customer_city VARCHAR(64),
    customer_state VARCHAR(2),
    total_orders INTEGER,
    total_spend NUMERIC(12, 2),
    first_order_date TIMESTAMP,
    last_order_date TIMESTAMP
);

CREATE TABLE IF NOT EXISTS marts.mart_delivery_performance (
    order_month DATE PRIMARY KEY,
    year_month VARCHAR(7),
    total_delivered_orders INTEGER,
    avg_delivery_days NUMERIC(8, 2),
    avg_estimated_delivery_days NUMERIC(8, 2),
    late_orders_count INTEGER,
    pct_late_vs_estimated NUMERIC(8, 2)
);

-- 4. Seed Representative Sample Data
INSERT INTO marts.mart_daily_sales VALUES
('2018-08-25', 240, 290, 31200.50, 4200.10, 130.00),
('2018-08-26', 265, 310, 35400.00, 4800.50, 133.58),
('2018-08-27', 280, 340, 38900.20, 5100.00, 138.93),
('2018-08-28', 295, 360, 41200.80, 5450.20, 139.66),
('2018-08-29', 270, 325, 36800.00, 4900.00, 136.30)
ON CONFLICT (sales_date) DO NOTHING;

INSERT INTO marts.mart_top_products VALUES
('prod_001', 'health_beauty', 9670, 1258681.34, 130.16, 1, 2),
('prod_002', 'bed_bath_table', 11115, 1036812.50, 93.28, 2, 1),
('prod_003', 'sports_leisure', 8641, 988048.97, 114.34, 3, 3),
('prod_004', 'computers_accessories', 7827, 911954.32, 116.51, 4, 4),
('prod_005', 'furniture_decor', 6449, 729762.49, 113.16, 5, 5)
ON CONFLICT (product_id) DO NOTHING;

INSERT INTO marts.mart_customer_summary VALUES
('cust_001', 'sao paulo', 'SP', 3, 450.80, '2017-02-14 10:00:00', '2018-08-10 14:30:00'),
('cust_002', 'rio de janeiro', 'RJ', 2, 280.40, '2017-06-20 12:00:00', '2018-05-18 09:15:00'),
('cust_003', 'belo horizonte', 'MG', 1, 145.20, '2018-03-01 16:45:00', '2018-03-01 16:45:00'),
('cust_004', 'curitiba', 'PR', 2, 310.00, '2017-11-12 11:30:00', '2018-07-22 18:20:00'),
('cust_005', 'porto alegre', 'RS', 1, 89.90, '2018-04-10 08:20:00', '2018-04-10 08:20:00')
ON CONFLICT (customer_unique_id) DO NOTHING;

INSERT INTO marts.mart_delivery_performance VALUES
('2018-05-01', '2018-05', 6873, 11.20, 23.40, 412, 6.00),
('2018-06-01', '2018-06', 6099, 10.80, 22.90, 365, 5.98),
('2018-07-01', '2018-07', 6159, 10.50, 23.10, 308, 5.00),
('2018-08-01', '2018-08', 6351, 10.10, 22.50, 285, 4.49)
ON CONFLICT (order_month) DO NOTHING;

-- 5. Grant Permissions
GRANT SELECT ON ALL TABLES IN SCHEMA marts TO app_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT ON TABLES TO app_readonly;
