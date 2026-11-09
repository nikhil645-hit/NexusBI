# 📋 Architecture Decision Records (ADRs)

This document records the architectural and engineering decisions made during the design and development of NexusBI. Each record follows the standard format: **Title**, **Status**, **Context**, **Decision**, and **Consequences**.

---

## ADR-001: SQL AST Validation using `sqlglot` over Regex and Prompt Guardrails

- **Status**: Accepted
- **Date**: 2026-11-05

### Context
When building a Text-to-SQL conversational application, language models can hallucinate destructive queries (`DROP TABLE`, `UPDATE`, `DELETE`) or be tricked via prompt injection into executing arbitrary SQL. We needed a security guardrail to guarantee safety before generated SQL is sent to the warehouse.

Alternatives considered:
1. *Prompt-only instructions* ("Never output DROP or DELETE statements").
2. *Regular expression / string keyword blacklist* (`re.search(r"DROP|DELETE|UPDATE", sql)`).
3. *Abstract Syntax Tree (AST) parsing with `sqlglot`*.

### Decision
Use `sqlglot` to parse generated SQL into an Abstract Syntax Tree (AST) before database execution. Enforce invariants:
- The parsed AST must contain exactly one statement.
- The statement type must be `exp.Select`.
- The expression tree must not contain any forbidden nodes (`exp.Drop`, `exp.Alter`, `exp.Create`, `exp.Insert`, `exp.Update`, `exp.Delete`, `exp.Into`, `exp.Lock`).
- All physical table nodes must belong to `marts` and match `ALLOWED_MART_TABLES`.
- Dangerous system functions (`pg_sleep`, `pg_read_file`, `set_config`, `dblink`, etc.) are explicitly blocked.
- A `LIMIT 1000` clause is automatically injected if omitted or clamped if exceeding 1000.

### Consequences
- **Positive**: Complete protection against regex bypasses (e.g. comments `/* */`, case manipulation, subqueries, multiline whitespace tricks).
- **Positive**: CTEs (`WITH ... AS`) are correctly identified as temporary in-memory aliases rather than unauthorized physical tables.
- **Negative**: Adds a Python runtime dependency on `sqlglot` (~1.5 MB).

---

## ADR-002: ELT Architecture with dbt Core over Custom Python ETL Scripts

- **Status**: Accepted
- **Date**: 2026-11-02

### Context
Raw data from Olist contains transactional timestamps, statuses, and split payments that must be transformed into analytics-ready dimensional models.

Alternatives considered:
1. *Custom Python Pandas/PySpark ETL scripts* reading from raw and writing to destination.
2. *dbt Core (ELT)* transforming data directly within the PostgreSQL warehouse using modular SQL and Jinja.

### Decision
Adopt dbt Core with `dbt-postgres`. Transformations are written in standard SQL with a modular two-tier architecture:
1. Staging (`staging` schema): Views that clean types, cast timestamps, and standardize names without duplicating disk space.
2. Marts (`marts` schema): Aggregated tables optimized for BI query patterns.

### Consequences
- **Positive**: Built-in test framework allows writing declarative data assertions (`unique`, `not_null`, `relationships`, `accepted_values`), resulting in 45 passing automated tests.
- **Positive**: Automatic dependency graph and lineage resolution (`ref()`), plus single-command documentation generation (`dbt docs generate`).
- **Negative**: Requires SQL knowledge and learning Jinja templating.

---

## ADR-003: Cloud LLM via Groq / Gemini over Local Ollama Execution

- **Status**: Accepted
- **Date**: 2026-11-08

### Context
Initially, the text-to-SQL layer ran locally using Ollama (`llama3.2:3b` / `mistral`). However, running a 3-billion to 7-billion parameter language model locally consumed 6 to 8 GB of host RAM, frequently causing memory exhaustion and crashes on student development laptops.

Alternatives considered:
1. *Local Ollama*: Free and offline, but heavy memory consumption and high query latency on non-GPU hardware.
2. *Cloud LLM API via Groq (`openai/gpt-oss-120b`)*: Free tier, ultra-low latency (~0.5s response time), uses 0 MB of local laptop RAM.
3. *Cloud LLM API via Google Gemini (`gemini-1.5-flash`)*: Free tier, high accuracy, lightweight.

### Decision
Provide a unified adapter interface (`BaseLLMAdapter`) that defaults to cloud LLM providers (Groq / Gemini) with an offline mock fallback adapter for testing and CI smoke runs.

### Consequences
- **Positive**: Zero local RAM footprint; instantaneous responses without heating the developer's laptop.
- **Positive**: Significantly higher SQL syntax accuracy and adherence to multi-table joins.
- **Negative**: Requires an internet connection and a free API key for live generation.

---

## ADR-004: Decoupled Cloud Serving Layer from Local Ingestion Pipeline

- **Status**: Accepted
- **Date**: 2026-11-09

### Context
Running an entire data engineering stack (PostgreSQL OLTP, Airbyte OSS, Apache Airflow, dbt, and Streamlit) on cloud instances (e.g. AWS EC2, ECS, or RDS) incurs continuous cloud bills that are unsustainable on a student budget.

Alternatives considered:
1. *Host everything in AWS*: High cloud cost ($50-$100+/month for Airbyte + Airflow + RDS).
2. *Host everything locally*: Inaccessible for live recruiter or portfolio demos.
3. *Decoupled Hybrid Architecture*: Run heavy pipeline components (Airbyte, Airflow, raw and staging schemas) locally on Docker, and export only the lightweight curated data marts (~10 MB) to a cloud database (AWS RDS or free Neon PostgreSQL) connected to Streamlit Community Cloud.

### Decision
Adopt the decoupled hybrid architecture:
- Ingestion, staging, and orchestrations run on local Docker containers.
- The 4 curated marts tables (`mart_daily_sales`, `mart_top_products`, `mart_customer_summary`, `mart_delivery_performance`) are exported via `scripts/export_marts.py` and loaded into the serving database via `scripts/load_marts_to_cloud.py`.
- The Streamlit application connects only to the serving database via the restricted `app_readonly` user.

### Consequences
- **Positive**: 100% free hosting possible using Neon + Streamlit Community Cloud.
- **Positive**: Zero risk of exposing raw transactional data or Airflow infrastructure to the public internet.
- **Negative**: Replicating updates to the cloud serving database requires running the export/load script after local pipeline execution.

---

## ADR-005: Incremental Materialization for `mart_daily_sales` with Lookback Window

- **Status**: Accepted
- **Date**: 2026-11-09

### Context
As transaction volumes grow, rebuilding `mart_daily_sales` as a full refresh table table every day wastes compute cycles by reprocessing historical days that have not changed. However, e-commerce orders occasionally arrive late or get updated days after initial placement.

### Decision
Materialize `mart_daily_sales` as an incremental model in dbt:
```sql
{{ config(materialized='incremental', unique_key='sales_date') }}
```
On incremental runs, filter for records where `order_purchase_date >= (select max(sales_date) - interval '3 days' from {{ this }})`.

### Consequences
- **Positive**: Significantly reduces warehouse transform compute time and I/O during daily Airflow runs.
- **Positive**: The 3-day lookback window prevents data drift caused by late-arriving orders or retrospective status updates.
- **Negative**: Full refresh requires explicit `--full-refresh` flag in dbt.

---

## ADR-006: Host-Independent Database Configuration via Generic Environment Variables

- **Status**: Accepted
- **Date**: 2026-11-09

### Context
Earlier versions of the codebase relied on AWS-specific variable names (`WAREHOUSE_HOST`, `REDSHIFT_HOST`). When migrating to local Docker or serverless PostgreSQL (such as Neon), having cloud-specific naming caused configuration friction.

### Decision
Refactor all connection code in `app/db_helper.py`, `dbt/olist_dbt/profiles.yml`, and utility scripts to support generic environment variables:
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE`.
- Retain backward compatibility fallback to `WAREHOUSE_*` so existing installations never break.
- Provide explicit dbt profile targets: `dev`, `local`, `aws`, `neon`.

### Consequences
- **Positive**: The application and dbt project can seamlessly connect to any PostgreSQL 14+ host (AWS RDS, Neon, Supabase, local Docker) simply by updating `.env`.
- **Positive**: Zero breaking changes for existing developers using `WAREHOUSE_*` variables.

---

## ADR-007: Dual Evaluation Policy (Strict vs. Lenient) for Text-to-SQL Accuracy Benchmarking

- **Status**: Accepted
- **Date**: 2026-11-09

### Context
When evaluating LLM-generated SQL queries against hand-crafted ground truth queries, semantic comparisons can fail for two distinct reasons:
1. Genuine semantic or logic errors (e.g. wrong aggregation formulas, invalid filters, or syntax errors).
2. Harmless projection differences where the LLM includes useful intermediate or component columns (e.g., returning `category_name, total_revenue, units_sold, revenue_per_unit` when the question asks for highest revenue per unit, whereas the ground truth projects only `category_name, revenue_per_unit`).

A rigid shape-matching check flags harmless extra columns as total failures (`Shape mismatch: generated (5, 4) vs expected (5, 2)`). Conversely, ignoring column checks entirely would allow queries with missing metrics to pass.

### Decision
Adopt a dual-reporting comparator policy in `benchmarks/run_benchmark.py`:
1. **Strict Policy**:
   - Requires identical matrix dimensions (`df_gen.shape == df_exp.shape`).
   - Every column in the expected query must align 1:1 with the generated query.
   - Floats compared within relative tolerance `rtol <= 0.05`.
   - Date formats normalized to `YYYY-MM`.
2. **Lenient Policy**:
   - Requires exact row count match (`len(df_gen) == len(df_exp)`).
   - Allows additional generated helper columns (`df_gen.shape[1] >= df_exp.shape[1]`).
   - Every expected column's values must appear as a unique column in the generated result (matched by value equality across all rows, independent of column aliases).
   - Ordering constraints (e.g. `ORDER BY ... LIMIT`) and float tolerances remain strictly enforced.

### Consequences
- **Positive**: Separates LLM hallucinations and SQL syntax errors from harmless auxiliary column projections.
- **Positive**: Provides honest, multi-dimensional visibility for technical interviewers and academic reviewers.
- **Neutral**: Both scores are printed side-by-side in all automated reports and terminal summaries.
