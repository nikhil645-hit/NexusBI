# ==============================================================================
# app/sql_validator.py - Deterministic SQL Safety Validator
#
# Relying solely on LLM prompt instructions ("do not delete tables") is
# dangerously vulnerable to prompt injection and jailbreaks. This validator uses
# an Abstract Syntax Tree (AST) parser (sqlglot) to enforce strict safety
# invariants before any query ever reaches the data warehouse.
# ==============================================================================

import re
from typing import Tuple, Set
import sqlglot
from sqlglot import exp

# Whitelist of tables in the curated marts schema
ALLOWED_MART_TABLES: Set[str] = {
    "mart_daily_sales",
    "mart_top_products",
    "mart_customer_summary",
    "mart_delivery_performance",
}

# Dangerous PostgreSQL functions and extensions that could facilitate denial-of-service,
# remote code execution, file reads, or configuration tampering.
DANGEROUS_FUNCTIONS: Set[str] = {
    "pg_sleep",
    "pg_sleep_for",
    "pg_sleep_until",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "lo_import",
    "lo_export",
    "lo_get",
    "lo_put",
    "lo_unlink",
    "dblink",
    "dblink_exec",
    "dblink_connect",
    "dblink_disconnect",
    "copy",
    "set_config",
    "current_setting",
    "query_to_xml",
    "inet_client_addr",
    "inet_server_addr",
    "version",
}

MAX_ALLOWED_LIMIT = 1000
MAX_QUERY_LENGTH = 4000


def validate_and_sanitize_sql(
    raw_sql: str,
    allowed_schema: str = "marts",
    max_limit: int = MAX_ALLOWED_LIMIT,
) -> Tuple[bool, str, str]:
    """
    Validates and sanitizes an LLM-generated SQL query using sqlglot AST parsing.

    Enforces Golden Safety Invariants:
      1. Length & Format: Rejects empty or oversized queries (> 4000 chars).
      2. Single Statement: Disallow batch queries or semicolon chaining.
      3. SELECT Only: Disallow DDL, DML, SELECT INTO, and lock queries (FOR UPDATE/SHARE).
      4. Function Blacklist: Disallow dangerous functions (pg_sleep, file I/O, set_config, etc.)
         and any pg_* or information_schema function calls.
      5. Schema & Table Containment: Tables must belong strictly to the 'marts' schema.
         Disallows 'raw', 'staging', 'pg_catalog', 'information_schema', and non-mart tables.
      6. Forced Limit: Guarantee a LIMIT of at most max_limit (1000 rows).

    Returns:
      (is_valid: bool, sanitized_sql_or_error: str, failure_reason: str)
    """
    if raw_sql is None:
        return False, "", "Empty SQL query provided."

    cleaned_sql = raw_sql.strip()

    # 0. Clean markdown code fences if LLM wrapped SQL in ```sql ... ```
    cleaned_sql = re.sub(r"^```(?:sql)?\s*", "", cleaned_sql, flags=re.IGNORECASE)
    cleaned_sql = re.sub(r"\s*```$", "", cleaned_sql)
    cleaned_sql = cleaned_sql.strip()

    if not cleaned_sql:
        return False, "", "Empty SQL query provided."

    # 1. Enforce maximum input length to prevent denial-of-service / memory exhaustion
    if len(cleaned_sql) > MAX_QUERY_LENGTH:
        return (
            False,
            "",
            f"Security Violation: Query exceeds maximum allowed length of {MAX_QUERY_LENGTH} characters (received {len(cleaned_sql)}).",
        )

    # 2. Parse SQL into AST expressions using sqlglot (Postgres dialect)
    try:
        raw_statements = sqlglot.parse(cleaned_sql, read="postgres")
    except Exception as e:
        return False, "", f"SQL Syntax Error: Unable to parse SQL query ({str(e)})."

    # Filter out empty statements or bare semicolons
    parsed_statements = [
        s for s in raw_statements if s is not None and not isinstance(s, exp.Semicolon)
    ]

    # Rule 1: Exactly one statement allowed
    if len(parsed_statements) == 0:
        return False, "", "No valid SQL statement detected."
    if len(parsed_statements) > 1:
        return (
            False,
            "",
            f"Security Violation: Chained queries detected ({len(parsed_statements)} statements). Semicolon statement chaining is forbidden.",
        )

    expression = parsed_statements[0]
    if expression is None:
        return False, "", "Invalid SQL statement."

    # Rule 2: SELECT statement only (no DDL/DML)
    if not isinstance(expression, exp.Select):
        stmt_type = expression.key.upper() if hasattr(expression, "key") else "NON-SELECT"
        return (
            False,
            "",
            f"Security Violation: Forbidden statement type '{stmt_type}'. Only read-only SELECT queries are permitted.",
        )

    # Check for forbidden AST nodes anywhere in the expression tree
    forbidden_types = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Create,
        exp.Alter,
        exp.Command,
        exp.Into,          # SELECT ... INTO table
        exp.Lock,          # SELECT ... FOR UPDATE / FOR SHARE
        exp.Set,           # SET config / search_path
        exp.TruncateTable, # TRUNCATE TABLE
        exp.Grant,
        exp.Revoke,
    )
    for node in expression.find_all(forbidden_types):
        node_name = type(node).__name__
        if isinstance(node, exp.Into):
            return False, "", "Security Violation: 'SELECT ... INTO' is forbidden as it creates warehouse tables."
        if isinstance(node, exp.Lock):
            return False, "", "Security Violation: Locking reads ('FOR UPDATE' / 'FOR SHARE') are forbidden."
        return False, "", f"Security Violation: Forbidden operation '{node_name}' found in query tree."

    # Rule 3: Function security inspection (block pg_sleep, lo_import, set_config, etc.)
    for func_node in expression.find_all((exp.Func, exp.Anonymous)):
        func_name = (func_node.name or "").lower()
        if not func_name:
            continue

        if func_name.startswith("pg_") or func_name in DANGEROUS_FUNCTIONS:
            return (
                False,
                "",
                f"Security Violation: Call to dangerous system function '{func_name}' is forbidden.",
            )

        # Disallow functions referencing information_schema
        if "information_schema" in func_name:
            return (
                False,
                "",
                f"Security Violation: Access to system schema via function '{func_name}' is forbidden.",
            )

    # Rule 4: Table and Schema Isolation
    # Collect CTE (Common Table Expression / WITH ... AS) aliases
    cte_aliases = {
        cte.alias_or_name.lower()
        for cte in expression.find_all(exp.CTE)
        if cte.alias_or_name
    }

    # Traverse all Table references in AST
    tables_found = list(expression.find_all(exp.Table))

    for table_node in tables_found:
        raw_name = table_node.name or ""
        raw_db = table_node.db or ""
        table_name = raw_name.strip('"').lower()
        schema_name = raw_db.strip('"').lower()

        # Skip CTE temporary result sets (they are internal aliases, not physical database tables)
        if table_name in cte_aliases and not schema_name:
            continue

        # Explicitly reject references to sensitive schemas and system catalogs
        if schema_name in ("raw", "staging", "pg_catalog", "information_schema", "public"):
            if schema_name != allowed_schema.lower():
                return (
                    False,
                    "",
                    f"Security Violation: Access to schema '{schema_name}' is forbidden. You may only query the '{allowed_schema}' schema.",
                )

        if table_name.startswith("pg_") or schema_name.startswith("pg_"):
            return (
                False,
                "",
                f"Security Violation: Access to internal system catalog '{table_name}' is forbidden.",
            )

        if schema_name == "information_schema" or table_name == "information_schema":
            return (
                False,
                "",
                "Security Violation: Direct queries against 'information_schema' are forbidden.",
            )

        # Verify table belongs to allowed marts tables
        if table_name not in ALLOWED_MART_TABLES:
            return (
                False,
                "",
                f"Security Violation: Access to table '{table_name}' is forbidden. "
                f"Only curated marts tables may be queried: {', '.join(sorted(ALLOWED_MART_TABLES))}.",
            )

        # Enforce qualification with allowed_schema (e.g. marts.mart_daily_sales)
        if not schema_name:
            table_node.set("this", exp.to_identifier(table_name))
            table_node.set("db", exp.to_identifier(allowed_schema.lower()))
        elif schema_name != allowed_schema.lower():
            return (
                False,
                "",
                f"Security Violation: Table '{table_name}' referenced under unapproved schema '{schema_name}'.",
            )
        else:
            table_node.set("this", exp.to_identifier(table_name))
            table_node.set("db", exp.to_identifier(allowed_schema.lower()))

    # Rule 5: Force LIMIT of at most max_limit
    existing_limit = expression.find(exp.Limit)
    if existing_limit is None:
        expression = expression.limit(max_limit)
    else:
        try:
            current_limit_val = int(existing_limit.expression.this)
            if current_limit_val > max_limit or current_limit_val <= 0:
                existing_limit.expression.set("this", str(max_limit))
        except (ValueError, TypeError, AttributeError):
            existing_limit.expression.set("this", str(max_limit))

    # Generate sanitized SQL string in Postgres dialect
    sanitized_sql = expression.sql(dialect="postgres")
    return True, sanitized_sql, ""
