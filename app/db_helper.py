# ==============================================================================
# app/db_helper.py - Centralized Warehouse Connection & Query Helper
#
# Connects to the local PostgreSQL 16 Data Warehouse (port 5434).
# Strictly uses the read-only application user (WAREHOUSE_APP_USER = app_readonly).
#
# Security:
#   Never prints, logs, or displays passwords in error messages or UI.
#   Restricted strictly to the 'marts' schema.
# ==============================================================================

import os
from typing import Optional, Dict, Any, List
import pandas as pd

# Fallback schema metadata if warehouse is offline or during offline demo
STATIC_MARTS_SCHEMA = """
Schema: marts

Table: marts.mart_daily_sales
Columns:
  - sales_date (DATE): Calendar date of purchase
  - total_orders (INTEGER): Count of distinct non-canceled orders
  - total_items_sold (INTEGER): Total items ordered
  - total_revenue (NUMERIC): Gross merchandise revenue
  - total_freight (NUMERIC): Total freight charges collected
  - avg_order_value (NUMERIC): Average order revenue (total_revenue / total_orders)

Table: marts.mart_top_products
Columns:
  - product_id (VARCHAR): Unique product identifier
  - category_name (VARCHAR): Translated English product category name
  - units_sold (INTEGER): Total units sold
  - total_revenue (NUMERIC): Total revenue generated
  - avg_unit_price (NUMERIC): Average price per item
  - revenue_rank (INTEGER): Dense rank by total revenue (1 = top seller)
  - units_sold_rank (INTEGER): Dense rank by units sold

Table: marts.mart_customer_summary
Columns:
  - customer_unique_id (VARCHAR): Unique buyer identifier across all orders
  - customer_city (VARCHAR): Customer home city
  - customer_state (VARCHAR): Brazilian state abbreviation (e.g., SP, RJ, MG)
  - total_orders (INTEGER): Lifetime count of non-canceled orders
  - total_spend (NUMERIC): Total lifetime spend (price + freight)
  - first_order_date (TIMESTAMP): Timestamp of earliest purchase
  - last_order_date (TIMESTAMP): Timestamp of most recent purchase

Table: marts.mart_delivery_performance
Columns:
  - order_month (DATE): First day of purchase month
  - year_month (VARCHAR): Year and month formatted as YYYY-MM
  - total_delivered_orders (INTEGER): Count of delivered orders
  - avg_delivery_days (NUMERIC): Average days from purchase to delivery
  - avg_estimated_delivery_days (NUMERIC): Average estimated delivery days promised
  - late_orders_count (INTEGER): Delivered orders where delivery date > estimated date
  - pct_late_vs_estimated (NUMERIC): Percentage of delivered orders that were late
"""


def is_warehouse_configured() -> bool:
    """Checks if valid non-placeholder Warehouse credentials are set in environment."""
    host = os.getenv("WAREHOUSE_HOST") or os.getenv("REDSHIFT_HOST", "")
    user = os.getenv("WAREHOUSE_APP_USER") or os.getenv("REDSHIFT_APP_USER", "")
    pwd = os.getenv("WAREHOUSE_APP_PASSWORD") or os.getenv("REDSHIFT_APP_PASSWORD", "")

    if not host or "placeholder" in host or "your-" in host:
        return False
    if not user or not pwd or "placeholder" in pwd:
        return False
    return True


def get_connection():
    """
    Creates and returns a connection to the PostgreSQL data warehouse using read-only credentials.
    Raises RuntimeError with friendly instructions if credentials are unconfigured.
    """
    if not is_warehouse_configured():
        raise RuntimeError(
            "Warehouse is not yet configured or is using placeholder credentials.\n"
            "Please configure WAREHOUSE_HOST, WAREHOUSE_APP_USER, and WAREHOUSE_APP_PASSWORD in your .env file."
        )

    import psycopg2

    host = os.getenv("WAREHOUSE_HOST") or os.getenv("REDSHIFT_HOST", "localhost")
    port = int(os.getenv("WAREHOUSE_PORT") or os.getenv("REDSHIFT_PORT", "5434"))
    db = os.getenv("WAREHOUSE_DB") or os.getenv("REDSHIFT_DB", "warehouse")
    user = os.getenv("WAREHOUSE_APP_USER") or os.getenv("REDSHIFT_APP_USER", "app_readonly")
    password = os.getenv("WAREHOUSE_APP_PASSWORD") or os.getenv("REDSHIFT_APP_PASSWORD", "")

    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=db,
            user=user,
            password=password,
            connect_timeout=15,
            options="-c search_path=marts",
        )
        return conn
    except Exception as e:
        # Sanitize error to prevent credential leaks
        err_msg = str(e)
        if password and password in err_msg:
            err_msg = err_msg.replace(password, "******")
        raise RuntimeError(f"Failed to connect to data warehouse: {err_msg}")


def get_marts_schema_text() -> str:
    """
    Returns the schema definitions of the marts tables to feed into the LLM context.
    Fetches dynamically from information_schema if connected, else falls back to static schema.
    """
    if not is_warehouse_configured():
        return STATIC_MARTS_SCHEMA

    try:
        conn = get_connection()
        query = """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'marts'
        ORDER BY table_name, ordinal_position;
        """
        df = pd.read_sql_query(query, conn)
        conn.close()

        if df.empty:
            return STATIC_MARTS_SCHEMA

        lines = ["Schema: marts\n"]
        for table, group in df.groupby("table_name"):
            lines.append(f"Table: marts.{table}")
            lines.append("Columns:")
            for _, row in group.iterrows():
                lines.append(f"  - {row['column_name']} ({row['data_type']})")
            lines.append("")
        return "\n".join(lines)
    except Exception:
        return STATIC_MARTS_SCHEMA


def execute_marts_query(sanitized_sql: str) -> pd.DataFrame:
    """
    Executes a sanitized read-only query against the data warehouse.
    If warehouse is not connected, provides simulated sample data for testing.
    """
    if not is_warehouse_configured():
        return _generate_mock_results(sanitized_sql)

    conn = get_connection()
    try:
        df = pd.read_sql_query(sanitized_sql, conn)
        return df
    except Exception as e:
        err_str = str(e)
        # Never leak passwords
        pwd = os.getenv("WAREHOUSE_APP_PASSWORD") or os.getenv("REDSHIFT_APP_PASSWORD", "")
        if pwd and pwd in err_str:
            err_str = err_str.replace(pwd, "******")
        raise RuntimeError(err_str)
    finally:
        conn.close()


def _generate_mock_results(sql: str) -> pd.DataFrame:
    """
    Generates realistic synthetic results for testing when warehouse is offline.
    Allows testing UI layout, charts, and table rendering with zero setup.
    """
    sql_lower = sql.lower()
    if "mart_top_products" in sql_lower:
        return pd.DataFrame({
            "category_name": ["bed_bath_table", "health_beauty", "sports_leisure", "computers_accessories", "furniture_decor"],
            "units_sold": [11115, 9670, 8641, 7827, 6449],
            "total_revenue": [1036812.50, 1258681.34, 988048.97, 911954.32, 729762.49],
            "revenue_rank": [2, 1, 3, 4, 5],
        })
    elif "mart_daily_sales" in sql_lower:
        dates = pd.date_range(end="2018-08-31", periods=10, freq="D").strftime("%Y-%m-%d")
        return pd.DataFrame({
            "sales_date": dates,
            "total_orders": [210, 245, 198, 230, 255, 270, 240, 215, 260, 280],
            "total_revenue": [28500.40, 34200.10, 27100.80, 31400.00, 36200.50, 39100.00, 33500.20, 29800.70, 37400.90, 41200.00],
            "avg_order_value": [135.71, 139.59, 136.87, 136.52, 141.96, 144.81, 139.58, 138.60, 143.85, 147.14],
        })
    elif "mart_delivery_performance" in sql_lower:
        return pd.DataFrame({
            "year_month": ["2018-05", "2018-06", "2018-07", "2018-08"],
            "total_delivered_orders": [6873, 6099, 6159, 6351],
            "avg_delivery_days": [11.2, 10.8, 10.5, 10.1],
            "avg_estimated_delivery_days": [23.4, 22.9, 23.1, 22.5],
            "late_orders_count": [412, 365, 308, 285],
            "pct_late_vs_estimated": [6.00, 5.98, 5.00, 4.49],
        })
    elif "mart_customer_summary" in sql_lower:
        return pd.DataFrame({
            "customer_state": ["SP", "RJ", "MG", "RS", "PR"],
            "total_buyers": [41746, 12852, 11635, 5466, 5045],
            "total_spend": [5202955.05, 1824093.15, 1585330.45, 750384.10, 683083.76],
        })
    else:
        return pd.DataFrame({
            "message": ["Query executed successfully."],
            "status": ["OK"],
        })
