# ==============================================================================
# app/test_sql_validator.py - Pytest Unit Test Suite for SQL Safety Validator
# ==============================================================================

import pytest
from app.sql_validator import validate_and_sanitize_sql, MAX_ALLOWED_LIMIT


class TestSQLValidator:
    """Test suite verifying deterministic SQL security invariants."""

    # --------------------------------------------------------------------------
    # 1. Valid Query Tests
    # --------------------------------------------------------------------------
    def test_valid_simple_select(self):
        sql = "SELECT sales_date, total_revenue FROM mart_daily_sales ORDER BY sales_date DESC"
        is_valid, sanitized_sql, err = validate_and_sanitize_sql(sql)
        assert is_valid is True
        assert err == ""
        assert "marts.mart_daily_sales" in sanitized_sql.lower()
        assert f"LIMIT {MAX_ALLOWED_LIMIT}" in sanitized_sql

    def test_valid_select_with_existing_reasonable_limit(self):
        sql = "SELECT product_id, total_revenue FROM marts.mart_top_products LIMIT 10"
        is_valid, sanitized_sql, err = validate_and_sanitize_sql(sql)
        assert is_valid is True
        assert "LIMIT 10" in sanitized_sql

    def test_valid_aggregation_and_grouping(self):
        sql = """
        SELECT customer_state, COUNT(*) as buyers, SUM(total_spend) as revenue
        FROM marts.mart_customer_summary
        GROUP BY customer_state
        ORDER BY revenue DESC
        """
        is_valid, sanitized_sql, err = validate_and_sanitize_sql(sql)
        assert is_valid is True
        assert "GROUP BY customer_state" in sanitized_sql

    def test_valid_strips_markdown_fences(self):
        sql = "```sql\nSELECT * FROM mart_delivery_performance\n```"
        is_valid, sanitized_sql, err = validate_and_sanitize_sql(sql)
        assert is_valid is True
        assert "marts.mart_delivery_performance" in sanitized_sql.lower()

    # --------------------------------------------------------------------------
    # 2. Limit Clamping Tests
    # --------------------------------------------------------------------------
    def test_excessive_limit_clamped(self):
        sql = "SELECT * FROM mart_daily_sales LIMIT 50000"
        is_valid, sanitized_sql, err = validate_and_sanitize_sql(sql)
        assert is_valid is True
        assert f"LIMIT {MAX_ALLOWED_LIMIT}" in sanitized_sql
        assert "50000" not in sanitized_sql

    # --------------------------------------------------------------------------
    # 3. Security Rejection Tests: DDL & DML
    # --------------------------------------------------------------------------
    @pytest.mark.parametrize(
        "destructive_sql,expected_keyword",
        [
            ("DROP TABLE marts.mart_daily_sales", "DROP"),
            ("DELETE FROM marts.mart_daily_sales WHERE 1=1", "DELETE"),
            ("UPDATE marts.mart_top_products SET total_revenue = 0", "UPDATE"),
            ("INSERT INTO marts.mart_daily_sales (sales_date) VALUES ('2024-01-01')", "INSERT"),
            ("TRUNCATE TABLE marts.mart_customer_summary", "TRUNCATE"),
            ("ALTER TABLE marts.mart_delivery_performance DROP COLUMN is_late", "ALTER"),
        ],
    )
    def test_reject_destructive_operations(self, destructive_sql, expected_keyword):
        is_valid, _, err = validate_and_sanitize_sql(destructive_sql)
        assert is_valid is False
        assert "Security Violation" in err

    # --------------------------------------------------------------------------
    # 4. Security Rejection Tests: Multi-Statement Chaining (SQL Injection)
    # --------------------------------------------------------------------------
    def test_reject_chained_queries(self):
        sql = "SELECT * FROM marts.mart_daily_sales; DROP TABLE marts.mart_top_products;"
        is_valid, _, err = validate_and_sanitize_sql(sql)
        assert is_valid is False
        assert "Chained queries detected" in err

    # --------------------------------------------------------------------------
    # 5. Schema and Table Isolation Tests
    # --------------------------------------------------------------------------
    def test_reject_unauthorized_raw_schema(self):
        sql = "SELECT * FROM raw.customers"
        is_valid, _, err = validate_and_sanitize_sql(sql)
        assert is_valid is False
        assert "Access to schema 'raw' is forbidden" in err

    def test_reject_unauthorized_staging_schema(self):
        sql = "SELECT * FROM staging.stg_orders"
        is_valid, _, err = validate_and_sanitize_sql(sql)
        assert is_valid is False
        assert "Access to schema 'staging' is forbidden" in err

    def test_reject_unauthorized_system_catalog(self):
        sql = "SELECT * FROM pg_catalog.pg_tables"
        is_valid, _, err = validate_and_sanitize_sql(sql)
        assert is_valid is False
        assert "Access to schema 'pg_catalog' is forbidden" in err

    def test_reject_unknown_table(self):
        sql = "SELECT * FROM marts.secret_passwords_table"
        is_valid, _, err = validate_and_sanitize_sql(sql)
        assert is_valid is False
        assert "Access to table 'secret_passwords_table' is forbidden" in err

    # --------------------------------------------------------------------------
    # 6. CTE (Common Table Expression) Isolation Tests
    # --------------------------------------------------------------------------
    def test_valid_cte_with_marts(self):
        sql = """
        WITH latest_month AS (
            SELECT DATE_TRUNC('month', sales_date) AS month, SUM(total_revenue) AS rev
            FROM mart_daily_sales
            GROUP BY 1
            ORDER BY 1 DESC
            LIMIT 1
        )
        SELECT * FROM latest_month
        """
        is_valid, sanitized_sql, err = validate_and_sanitize_sql(sql)
        assert is_valid is True
        assert err == ""
        assert "marts.mart_daily_sales" in sanitized_sql.lower()
        assert "latest_month" in sanitized_sql

    def test_reject_unauthorized_table_inside_cte(self):
        sql = """
        WITH hacked_cte AS (
            SELECT * FROM raw.customers
        )
        SELECT * FROM hacked_cte
        """
        is_valid, _, err = validate_and_sanitize_sql(sql)
        assert is_valid is False
        assert "Access to schema 'raw' is forbidden" in err

