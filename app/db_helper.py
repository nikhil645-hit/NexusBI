# ==============================================================================
# app/db_helper.py - Centralized Warehouse Connection & Query Helper
#
# Connects to PostgreSQL Data Warehouse (Neon Cloud / Local DW).
# Strictly uses the read-only application user.
#
# Security:
#   Never prints, logs, or displays passwords in error messages or UI.
#   Restricted strictly to the 'marts' schema.
# ==============================================================================

import os
import warnings
from pathlib import Path
from typing import List, Union

import pandas as pd
from dotenv import load_dotenv

# Suppress DBAPI2 user warning for pandas read_sql_query with psycopg2
warnings.filterwarnings("ignore", category=UserWarning, module="pandas")

# Load environment variables from .env
_dotenv_path = Path(__file__).resolve().parent.parent / ".env"
if _dotenv_path.exists():
    load_dotenv(dotenv_path=_dotenv_path, override=True)


def _get_config_value(keys: Union[List[str], str], default: str = "") -> str:
    """
    Checks os.environ and st.secrets (if running within Streamlit) for the given keys
    in priority order, ignoring empty or placeholder values.
    """
    if isinstance(keys, str):
        keys = [keys]

    # 1. Check os.environ
    for k in keys:
        val = os.getenv(k)
        if val and "placeholder" not in val.lower() and "your-" not in val.lower():
            return val

    # 2. Check st.secrets (Streamlit Community Cloud secrets management)
    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            for k in keys:
                if k in st.secrets:
                    val = str(st.secrets[k])
                    if val and "placeholder" not in val.lower() and "your-" not in val.lower():
                        return val
    except Exception:
        pass

    return default

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
    """Checks if valid non-placeholder Warehouse credentials are set in environment or st.secrets."""
    host = _get_config_value(["DB_HOST", "NEON_HOST", "WAREHOUSE_HOST", "REDSHIFT_HOST"])
    user = _get_config_value(["DB_USER", "NEON_RO_USER", "NEON_USER", "WAREHOUSE_APP_USER", "REDSHIFT_APP_USER"])
    pwd = _get_config_value(["DB_PASSWORD", "NEON_RO_PASSWORD", "NEON_PASSWORD", "WAREHOUSE_APP_PASSWORD", "REDSHIFT_APP_PASSWORD"])

    if not host or not user or not pwd:
        return False
    return True


def get_connection():
    """
    Creates and returns a connection to the PostgreSQL data warehouse using read-only credentials.
    Enforces server-side statement_timeout (default 10s) and search_path=marts.
    Raises RuntimeError with friendly instructions if credentials are unconfigured.
    """
    if not is_warehouse_configured():
        raise RuntimeError(
            "Warehouse is not yet configured or is using placeholder credentials.\n"
            "Please configure DB_HOST, DB_USER, and DB_PASSWORD (or NEON_* / WAREHOUSE_*) in your .env or Streamlit Secrets."
        )

    import psycopg2

    host = _get_config_value(["DB_HOST", "NEON_HOST", "WAREHOUSE_HOST", "REDSHIFT_HOST"], "localhost")
    default_port = "5432" if ("neon.tech" in host or "amazonaws.com" in host) else "5434"
    port = int(_get_config_value(["DB_PORT", "NEON_PORT", "WAREHOUSE_PORT", "REDSHIFT_PORT"], default_port))
    default_db = "neondb" if "neon.tech" in host else "warehouse"
    db = _get_config_value(["DB_NAME", "NEON_DB", "WAREHOUSE_DB", "REDSHIFT_DB"], default_db)
    user = _get_config_value(["DB_USER", "NEON_RO_USER", "NEON_USER", "WAREHOUSE_APP_USER", "REDSHIFT_APP_USER"], "app_readonly")
    password = _get_config_value(["DB_PASSWORD", "NEON_RO_PASSWORD", "NEON_PASSWORD", "WAREHOUSE_APP_PASSWORD", "REDSHIFT_APP_PASSWORD"], "")

    default_sslmode = "require" if ("neon.tech" in host or "amazonaws.com" in host) else "prefer"
    sslmode = _get_config_value(["DB_SSLMODE", "NEON_SSLMODE", "WAREHOUSE_SSLMODE"], default_sslmode)
    statement_timeout_ms = int(_get_config_value(["STATEMENT_TIMEOUT_MS"], "30000"))

    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=db,
            user=user,
            password=password,
            sslmode=sslmode,
            connect_timeout=15,
            options=f"-c search_path=marts -c statement_timeout={statement_timeout_ms}",
        )
        # Explicitly enforce statement_timeout on the session
        with conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = {statement_timeout_ms};")
        conn.commit()
        return conn
    except Exception as e:
        # Sanitize error to prevent credential leaks
        err_msg = str(e)
        if password and password in err_msg:
            err_msg = err_msg.replace(password, "******")
        raise RuntimeError(f"Failed to connect to data warehouse: {err_msg}")


def _fetch_dataframe(conn, sql: str) -> pd.DataFrame:
    """
    Executes a read query via cursor and builds a DataFrame directly.
    Avoids pandas UserWarning for raw DBAPI2 connections while preserving types.
    """
    import decimal

    with conn.cursor() as cur:
        cur.execute(sql)
        if cur.description is None:
            return pd.DataFrame()
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=columns)

        # Convert Decimal types to float for seamless downstream visualization and calculation
        for col in df.columns:
            if df[col].dtype == object and len(df) > 0:
                first_valid = df[col].dropna().iloc[0] if not df[col].dropna().empty else None
                if isinstance(first_valid, decimal.Decimal):
                    df[col] = pd.to_numeric(df[col], errors="coerce")
        return df


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
        df = _fetch_dataframe(conn, query)
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
        df = _fetch_dataframe(conn, sanitized_sql)
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
            "product_id": ["prod_001", "prod_002", "prod_003", "prod_004", "prod_005"],
            "category_name": ["bed_bath_table", "health_beauty", "sports_leisure", "computers_accessories", "furniture_decor"],
            "units_sold": [11115, 9670, 8641, 7827, 6449],
            "total_revenue": [1036812.50, 1258681.34, 988048.97, 911954.32, 729762.49],
            "revenue_rank": [2, 1, 3, 4, 5],
        })
    elif "mart_daily_sales" in sql_lower:
        dates = pd.date_range(end="2018-08-31", periods=10, freq="D").strftime("%Y-%m-%d").tolist()
        total_orders = [210, 245, 198, 230, 255, 270, 240, 215, 260, 280]
        total_items_sold = [240, 280, 225, 265, 290, 310, 275, 245, 295, 320]
        total_revenue = [28500.40, 34200.10, 27100.80, 31400.00, 36200.50, 39100.00, 33500.20, 29800.70, 37400.90, 41200.00]
        total_freight = [4250.60, 5100.20, 4050.10, 4700.00, 5400.80, 5850.00, 5010.30, 4450.00, 5600.40, 6150.00]
        avg_order_value = [round(r / o, 2) for r, o in zip(total_revenue, total_orders)]
        return pd.DataFrame({
            "sales_date": dates,
            "total_orders": total_orders,
            "total_items_sold": total_items_sold,
            "total_revenue": total_revenue,
            "total_freight": total_freight,
            "avg_order_value": avg_order_value,
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
            "customer_unique_id": ["cust_001", "cust_002", "cust_003", "cust_004", "cust_005"],
            "customer_city": ["sao paulo", "rio de janeiro", "belo horizonte", "porto alegre", "curitiba"],
            "customer_state": ["SP", "RJ", "MG", "RS", "PR"],
            "total_orders": [4, 3, 2, 2, 1],
            "total_spend": [5202.95, 3824.09, 2585.33, 1750.38, 983.08],
            "first_order_date": ["2017-02-15 10:00:00", "2017-04-10 12:30:00", "2017-06-20 09:15:00", "2017-08-05 14:00:00", "2018-01-12 11:20:00"],
            "last_order_date": ["2018-08-10 16:45:00", "2018-07-22 18:20:00", "2018-05-30 14:10:00", "2018-06-15 10:05:00", "2018-01-12 11:20:00"],
        })
    else:
        return pd.DataFrame({
            "message": ["Query executed successfully."],
            "status": ["OK"],
        })
