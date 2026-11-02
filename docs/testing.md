# Testing Matrix & Verification Checklist

This document contains the verification test cases covering every layer of the data pipeline. Use this checklist during your development checkpoints and before college demo presentations.

> [!NOTE]
> The **Result (Pass / Fail)** column is deliberately left blank for you to check off during your live evaluation and project demonstration.

---

## Comprehensive Test Case Matrix

| Test ID | Category | Test Description | Execution Method | Expected Result | Result (Pass / Fail) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-01** | Source DB | Local Postgres container initialization and port binding | `docker ps --filter "name=olist-postgres"` | Container is healthy and listening on host port `5433`. | |
| **TC-02** | Source Data | Initial Olist CSV ingestion into Postgres | `SELECT count(*) FROM orders;` in Postgres | Order count equals `99,441` rows with zero corruption. | |
| **TC-03** | Warehouse | Redshift Serverless connectivity and credentials | `make dbt-debug` (or `dbt debug`) | All connection checks pass (`Connection test: [OK]`). | |
| **TC-04** | Security | Redshift RBAC: `app_readonly` user cannot write to warehouse | `CREATE TABLE marts.test_table (id int);` logged in as `app_readonly` | Query fails with permission denied error. | |
| **TC-05** | Ingestion | Airbyte replication from Postgres to Redshift | Trigger sync in Airbyte UI (`http://localhost:8000`) | All 6 tables sync with status `Succeeded` (Full Refresh \| Overwrite). | |
| **TC-06** | Transformation | Staging models compilation and materialization | `dbt run --select staging` | 5 staging views (`stg_customers`, `stg_orders`, etc.) compiled successfully. | |
| **TC-07** | Transformation | Dimensional analytical marts materialization | `dbt run --select marts` | 4 marts physical tables (`mart_daily_sales`, `mart_top_products`, etc.) built. | |
| **TC-08** | Data Quality | Primary key uniqueness and non-null integrity | `dbt test --select "stg_customers stg_orders"` | Zero test failures for unique and not-null constraints. | |
| **TC-09** | Data Quality | Foreign key referential integrity checks | `dbt test --select "test_type:relationships"` | Referential integrity between items, orders, and products passes. | |
| **TC-10** | Data Quality | Business logic assertion: Non-negative revenue | `dbt test --select assert_revenue_is_non_negative` | Singular test passes with 0 failing rows. | |
| **TC-11** | Orchestrator | Airflow Docker stack health and LocalExecutor | `docker compose -f airflow/docker-compose.yml ps` | Postgres, webserver, and scheduler running healthy within memory limit. | |
| **TC-12** | Orchestrator | End-to-end DAG execution (`olist_daily_pipeline`) | Trigger DAG in Airflow Web UI (`http://localhost:8080`) | All 5 task nodes turn dark green (`success`). | |
| **TC-13** | Security AST | SQL safety validator: Rejection of destructive DDL/DML | `pytest app/test_sql_validator.py` | 16 unit tests pass, blocking DROP, DELETE, and stacked queries. | |
| **TC-14** | Security AST | Enforced query row limit | Execute SQL without LIMIT through validator | Validator appends `LIMIT 1000` to prevent excessive cloud egress. | |
| **TC-15** | App / BI | Streamlit conversational question answering | Click sample question in Streamlit chat UI (`http://localhost:8501`) | LLM returns safe SQL, displays data table, and renders visualization. | |
| **TC-16** | App / BI | Single-turn automatic self-correction on syntax error | Submit prompt with ambiguous column or intentional syntax error | App re-prompts LLM with database error, self-corrects, and executes. | |
