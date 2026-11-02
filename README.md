# End-to-End Data Pipeline with Conversational BI (Olist E-Commerce)

[![Architecture](https://img.shields.io/badge/Architecture-ELT%20%2B%20dbt%20%2B%20Airflow%20%2B%20Streamlit-blue.svg)](docs/architecture.md)
[![Database](https://img.shields.io/badge/Warehouse-Amazon%20Redshift%20Serverless-red.svg)](docs/aws_setup.md)
[![Orchestrator](https://img.shields.io/badge/Orchestrator-Apache%20Airflow%20(LocalExecutor)-017CEE.svg)](airflow/)

A modern, production-grade Data Engineering microproject built for college demonstration and viva defense. It extracts real-world e-commerce data from a local transactional database, loads it to an Amazon Redshift Serverless data warehouse using Airbyte, models star-schema analytics marts with dbt, orchestrates the entire workflow with Apache Airflow, and exposes a secure Conversational BI chat interface powered by an LLM (Gemini / Anthropic) with strict SQL safety validation.

---

## 🏗️ Architecture Overview

```text
[Postgres 16 (Local OLTP)] 
       │
       ▼ (Airbyte OSS via S3 Staging)
[Amazon Redshift Serverless: raw schema]
       │
       ▼ (dbt transformations: views)
[Amazon Redshift Serverless: staging schema]
       │
       ▼ (dbt transformations: analytical tables & tests)
[Amazon Redshift Serverless: marts schema]
       │
       ├─────────────────────────────────────────┐
       ▼                                         ▼
[Streamlit Conversational BI]          [Airflow Orchestrator]
(LLM Text-to-SQL + sqlglot guardrail)    (Triggers Airbyte -> dbt run -> dbt test)
```

See [docs/architecture.md](docs/architecture.md) for full architectural details and the interactive Mermaid diagram.

---

## 📁 Repository Directory Structure

```text
de-project/
├── PROJECT.md               # Project requirements & viva specifications
├── README.md                # Master setup and execution guide (this file)
├── Makefile                 # Convenient CLI shortcut commands
├── .env.example             # Master environment template (placeholders)
├── .gitignore               # Strict ignore rules (no secrets, data, venvs)
├── source/                  # Local transactional database setup
│   ├── docker-compose.yml   # Postgres 16 container (port 5433)
│   └── load_olist.py        # Python ingestion script loading Olist CSVs
├── docs/                    # Complete project documentation
│   ├── architecture.md      # Pipeline architecture and component breakdown
│   ├── aws_setup.md         # Redshift Serverless & S3 cost-effective guide (Phase 1)
│   ├── airbyte_setup.md     # Airbyte connection & API instructions (Phase 1)
│   ├── data_dictionary.md   # Schema reference for raw, staging, and marts (Phase 5)
│   ├── runbook.md           # Step-by-step production runbook & teardown (Phase 5)
│   ├── testing.md           # Test cases & validation verification (Phase 5)
│   └── screenshots_checklist.md # Report and viva submission checklist (Phase 5)
├── sql/                     # Warehouse initialization scripts (Phase 1)
│   ├── 01_schemas.sql       # Creates schemas: raw, staging, marts
│   └── 02_users.sql         # Creates dbt and app_readonly users with RBAC
├── dbt/olist_dbt/           # dbt Transformation Project (Phase 2)
│   ├── models/staging/      # Cleansed views (stg_orders, stg_customers, etc.)
│   ├── models/marts/        # Star-schema tables (sales, products, delivery)
│   ├── tests/               # Schema tests and custom business assertions
│   └── profiles.yml         # Redshift connection profile using env vars
├── airflow/                 # Apache Airflow Orchestration (Phase 3)
│   ├── Dockerfile           # Airflow image with isolated dbt virtualenv
│   ├── docker-compose.yml   # Lightweight LocalExecutor setup (under 10 GB RAM)
│   └── dags/                # olist_daily_pipeline DAG
└── app/                     # Conversational BI Interface (Phase 4)
    ├── streamlit_app.py     # Streamlit web application
    ├── llm_helper.py        # Adapter for Gemini & Anthropic LLMs
    ├── sql_validator.py     # Deterministic SQLGlot safety guardrail
    └── test_sql_validator.py# Pytest suite for SQL injection & security
```

---

## 🚀 Execution Order (End-to-End Walkthrough)

Follow these phases sequentially to stand up and demonstrate the pipeline:

### Step 1: Environment Configuration
Copy `.env.example` to `.env` and fill in your actual values:
```bash
cp .env.example .env
```
*(All components read from environment variables to keep credentials out of code).*

### Step 2: Start Local Source Database
1. Launch the Postgres container on port `5433`:
   ```bash
   make source-up
   ```
2. Ingest the Olist e-commerce dataset (~100k rows):
   ```bash
   make source-load
   ```

### Step 3: Setup AWS Redshift & S3 (Phase 1)
1. Follow the step-by-step instructions in [docs/aws_setup.md](docs/aws_setup.md) to launch Redshift Serverless with minimal Base Capacity (Base RPU) and budget alerts.
2. Run the initialization SQL scripts to provision schemas and role-based access:
   - `sql/01_schemas.sql`
   - `sql/02_users.sql`

### Step 4: Configure Airbyte Replication (Phase 1)
1. Open the Airbyte UI at `http://localhost:8000`.
2. Follow [docs/airbyte_setup.md](docs/airbyte_setup.md) to connect the local Postgres source to Redshift destination (`raw` schema).
3. Generate Airbyte API credentials (Settings -> Applications) and store the Client ID, Secret, and Connection ID in `.env`.

### Step 5: dbt Transformations & Testing (Phase 2)
1. Test connectivity to Redshift:
   ```bash
   make dbt-debug
   ```
2. Build the staging views and marts analytical tables:
   ```bash
   make dbt-run
   ```
3. Run data quality tests (uniqueness, referential integrity, non-null, business rules):
   ```bash
   make dbt-test
   ```

### Step 6: Orchestrate with Apache Airflow (Phase 3)
1. Start the Airflow stack:
   ```bash
   make airflow-up
   ```
2. Open the Airflow Web UI at `http://localhost:8080`.
3. Unpause and trigger the DAG `olist_daily_pipeline`:
   - Task 1: Triggers Airbyte sync via REST API.
   - Task 2: Executes `dbt run` inside the isolated virtualenv.
   - Task 3: Executes `dbt test` to guarantee data quality.
   - Task 4: Emits pipeline execution status summary.

### Step 7: Launch Conversational BI (Phase 4)
1. Start the Streamlit application:
   ```bash
   make app-run
   ```
2. Open `http://localhost:8501` to query the data marts using natural language questions. All queries are verified through `sqlglot` before running against Redshift.

---

## 🛡️ Viva & Defense Key Talking Points

1. **Why ELT instead of ETL?**
   - We extract and load raw data directly into Redshift (`raw` schema) via Airbyte, letting Redshift's distributed columnar engine perform transformations via dbt. This avoids transforming data on a bottleneck ingestion server.
2. **Why LocalExecutor instead of CeleryExecutor for Airflow?**
   - The project runs on a workstation with 16 GB RAM with Docker. CeleryExecutor requires Redis and Flower workers which consume excessive RAM. LocalExecutor runs tasks in worker processes within the scheduler container, staying strictly within the 10 GB Docker memory budget.
3. **How is SQL Injection prevented in the Conversational BI app?**
   - We implement a multi-layered defense:
     1. The app connects using `app_readonly`, which only has `SELECT` privileges on the `marts` schema.
     2. An AST parser (`sqlglot`) guarantees exactly one `SELECT` statement, enforces `marts` schema access only, forbids DDL/DML, and caps the result set to `LIMIT 1000`.
4. **How portable is this architecture?**
   - Warehouse-specific logic is strictly isolated in `dbt/olist_dbt/profiles.yml`, SQL user provisioning scripts, and database helpers. Migrating to Snowflake or BigQuery requires modifying only the connection profile and target dialect without rewriting business models.
