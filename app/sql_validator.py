# ==============================================================================
# app/sql_validator.py - Deterministic SQL Safety Validator
#
# In a viva: Explain that relying solely on LLM prompt instructions ("do not delete
# tables") is dangerously vulnerable to prompt injection. This validator uses an
# Abstract Syntax Tree (AST) parser (sqlglot) to enforce strict safety invariants
# before any query ever reaches the data warehouse.
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

MAX_ALLOWED_LIMIT = 1000


def validate_and_sanitize_sql(
    raw_sql: str,
    allowed_schema: str = "marts",
    max_limit: int = MAX_ALLOWED_LIMIT,
) -> Tuple[bool, str, str]:
    """
    Validates and sanitizes an LLM-generated SQL query.

    Enforces 5 Golden Safety Invariants:
      1. Single Statement: Disallow batch queries or command chaining.
      2. SELECT Only: Disallow DDL (DROP, CREATE, ALTER) and DML (INSERT, UPDATE, DELETE).
      3. Schema Containment: Tables must belong strictly to the 'marts' schema.
      4. Disallowed Schemas: Explicitly reject references to 'raw', 'staging', or system catalogs.
      5. Forced Limit: Guarantee a LIMIT of at most max_limit (1000 rows).

    Returns:
      (is_valid: bool, sanitized_sql_or_error: str, failure_reason: str)
    """
    cleaned_sql = raw_sql.strip()

    # 0. Clean markdown code fences if LLM wrapped SQL in ```sql ... ```
    cleaned_sql = re.sub(r"^```(?:sql)?\s*", "", cleaned_sql, flags=re.IGNORECASE)
    cleaned_sql = re.sub(r"\s*```$", "", cleaned_sql)
    cleaned_sql = cleaned_sql.strip()

    if not cleaned_sql:
        return False, "", "Empty SQL query provided."

    # Parse SQL into AST expressions using sqlglot (Postgres/Redshift dialect)
    try:
        parsed_statements = sqlglot.parse(cleaned_sql, read="redshift")
    except Exception as e:
        return False, "", f"SQL Syntax Error: Unable to parse SQL query ({str(e)})."

    # Rule 1: Exactly one statement allowed
    if len(parsed_statements) == 0:
        return False, "", "No valid SQL statement detected."
    if len(parsed_statements) > 1:
        return False, "", f"Security Violation: Chained queries detected ({len(parsed_statements)} statements). Only single statements are permitted."

    expression = parsed_statements[0]
    if expression is None:
        return False, "", "Invalid SQL statement."

    # Rule 2: SELECT statement only (no DDL/DML)
    if not isinstance(expression, exp.Select):
        stmt_type = expression.key.upper() if hasattr(expression, "key") else "NON-SELECT"
        return False, "", f"Security Violation: Forbidden statement type '{stmt_type}'. Only read-only SELECT queries are permitted."

    # Check for forbidden AST nodes anywhere in the expression tree
    forbidden_types = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Create,
        exp.Alter,
        exp.Command,
    )
    for node in expression.find_all(forbidden_types):
        return False, "", f"Security Violation: Forbidden operation '{type(node).__name__}' found in query tree."

    # Rule 3 & 4: Table and Schema Isolation
    # Traverse all Table references in AST
    tables_found = list(expression.find_all(exp.Table))
    if not tables_found:
        # Some queries might select literals like 'SELECT 1'; allowable but warn if no table
        pass

    for table_node in tables_found:
        table_name = table_node.name.lower()
        schema_name = table_node.db.lower() if table_node.db else ""

        # Explicitly reject references to sensitive schemas
        if schema_name in ("raw", "staging", "pg_catalog", "information_schema"):
            return False, "", f"Security Violation: Access to schema '{schema_name}' is forbidden. You may only query the '{allowed_schema}' schema."

        # Verify table belongs to allowed marts tables
        if table_name not in ALLOWED_MART_TABLES:
            return False, "", (
                f"Security Violation: Access to table '{table_name}' is forbidden. "
                f"Only curated marts tables may be queried: {', '.join(sorted(ALLOWED_MART_TABLES))}."
            )

        # Enforce qualification with allowed_schema (e.g. marts.mart_daily_sales)
        if not schema_name:
            table_node.set("db", exp.Identifier(this=allowed_schema))
        elif schema_name != allowed_schema:
            return False, "", f"Security Violation: Table '{table_name}' referenced under unapproved schema '{schema_name}'."

    # Rule 5: Force LIMIT of at most max_limit
    existing_limit = expression.find(exp.Limit)
    if existing_limit is None:
        expression = expression.limit(max_limit)
    else:
        # Check current limit value
        try:
            current_limit_val = int(existing_limit.expression.this)
            if current_limit_val > max_limit or current_limit_val <= 0:
                existing_limit.expression.set("this", str(max_limit))
        except (ValueError, TypeError, AttributeError):
            existing_limit.expression.set("this", str(max_limit))

    # Generate sanitized SQL string
    sanitized_sql = expression.sql(dialect="redshift")
    return True, sanitized_sql, ""

