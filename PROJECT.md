# PROJECT: End-to-End Data Pipeline with Conversational BI (DE Microproject)

## Who I am and what this is
I am a Computer Engineering student, a beginner at data engineering. This is a college
micro project, demoed in about 2 weeks. Keep everything simple, readable, well commented, and
explain each file you create in plain language. I must be able to defend every line in a viva.

## Architecture (fixed, do not change tools)
Local Postgres (Olist e-commerce data) -> Airbyte OSS -> Amazon Redshift Serverless (schema raw)
-> dbt (staging -> marts) -> Streamlit chat app (LLM text-to-SQL on marts).
Airflow (Docker Compose) orchestrates: Airbyte sync -> dbt run -> dbt test.
Cloud: AWS (Redshift Serverless, S3 for Airbyte staging if required). Region: ap-south-1 (Mumbai).
Keep ALL warehouse-specific code in: dbt profiles.yml, one db helper module, and docs/aws_setup.md,
so the warehouse can be swapped (e.g. to Snowflake) later with minimal changes.

## What already exists (do NOT modify or recreate)
- Project root: ~/de-project (WSL Ubuntu, Windows 11, 16 GB RAM, Docker Desktop with WSL integration)
- source/docker-compose.yml: Postgres 16 container "olist-postgres", host port 5433, db olist, user olist,
  password in source/.env (PG_PASSWORD). Tables loaded in schema public: customers, orders, order_items,
  order_payments, products, category_translation (Olist dataset; orders has 99,441 rows).
- source/load_olist.py, data/ (CSVs), .venv, .gitignore, secrets/ (private keys, never read or print them).
- Airbyte OSS already installed via abctl, UI at http://localhost:8000. I create the source, destination
  and connection in the UI myself. You write the exact click-by-click settings in docs/airbyte_setup.md.

## Global rules
1. Never hardcode secrets. Use .env files (git-ignored) plus committed .env.example files with placeholders.
   Never open, print or log anything in secrets/ or any .env.
2. I will connect AWS and other services later. Everything must run with placeholders and fail with a
   clear, friendly error message when a required env var is missing.
3. Memory budget: Docker has about 10 GB total and Airbyte already uses a large share. So no CeleryExecutor,
   Redis or Flower. Use the smallest Airflow setup that works (LocalExecutor, webserver, scheduler, metadata
   Postgres). Pin all versions. Prefer slim images.
4. Do not run destructive commands (docker system prune, rm -rf outside the project, etc.). Ask before
   starting heavy containers. Do not install anything outside the project or its venvs.
5. Work in phases. After each phase STOP, summarise what you created, and give me exact verification commands
   plus what the expected output looks like. Wait for my "go" before the next phase.
6. Add short comments at the top of every file explaining its purpose. Keep the code beginner friendly.
7. Use small, meaningful git commits per phase (no secrets).

## Target folder structure
de-project/
  PROJECT.md, README.md, Makefile, .env.example, .gitignore
  source/            (exists)
  data/              (exists, git-ignored)
  secrets/           (exists, git-ignored)
  dbt/olist_dbt/     dbt project (models/staging, models/marts, tests, macros, profiles.yml using env vars)
  airflow/           Dockerfile, docker-compose.yml, dags/, requirements, .env.example
  app/               Streamlit app
  sql/               Redshift setup scripts (schemas, users, grants)
  docs/              aws_setup.md, airbyte_setup.md, architecture.md (Mermaid diagram), data_dictionary.md,
                     runbook.md, testing.md, screenshots_checklist.md

## PHASE 0: Scaffolding
- Create the folder structure, README (how to run everything, in order), Makefile with helpful targets,
  root .env.example listing every variable the project will need (Redshift host/port/db/user/password,
  AWS region, S3 bucket, Airbyte API URL/client id/secret/connection id, LLM provider and key, etc.).
- Update .gitignore (.env, secrets/, data/, .venv, dbt target/ and logs, __pycache__).
- Write docs/architecture.md with a Mermaid diagram of the whole pipeline and one paragraph per component.

## PHASE 1: AWS and Airbyte documentation, plus Redshift SQL
- docs/aws_setup.md: beginner checklist for Redshift Serverless (namespace and workgroup, smallest base
  capacity, a usage limit as a cost guard, publicly accessible with a security group allowing port 5439 only
  from my IP, S3 bucket for Airbyte staging, IAM role and access keys if Airbyte needs them), a budget alert
  step, and a "delete everything after the demo" teardown checklist. Mark which values go in which .env key.
- sql/01_schemas.sql: create schemas raw, staging, marts.
- sql/02_users.sql: dbt user (full access to staging and marts, read on raw), app_readonly user (SELECT
  on marts only). Passwords are placeholders.
- docs/airbyte_setup.md: exact UI settings for the Postgres source (host host.docker.internal, port 5433, db
  olist, SSL disabled, user-defined cursor/standard replication), the Redshift destination (default schema
  raw), and a connection using Full refresh | Overwrite for all 6 tables, manual schedule. Include how to find
  the connection ID and how to create Airbyte API client credentials (Settings -> Applications).

## PHASE 2: dbt project (dbt-redshift)
- Create dbt/olist_dbt with profiles.yml that reads all credentials from env vars. Put source schema and
  table names in dbt vars so I can adjust them after I see what Airbyte really created.
- sources.yml for raw tables, with freshness or row-count style checks where reasonable.
- Staging models (views): stg_customers, stg_orders, stg_order_items, stg_order_payments, stg_products
  (join the English category translation). Rename columns consistently, cast types (timestamps, numerics),
  drop Airbyte metadata columns.
- Marts (tables):
  * mart_daily_sales (date, orders, items sold, revenue, avg order value)
  * mart_top_products (product, category, units sold, revenue, rank)
  * mart_customer_summary (customer, state/city, order count, total spend, first/last order date)
  * mart_delivery_performance (month, avg delivery days, % late vs estimated)
- Tests in schema.yml: not_null, unique, relationships, accepted_values (order_status) plus one singular
  test (e.g. revenue is never negative). Add descriptions for every model and column.
- Verify commands: dbt debug, dbt deps (if packages are used), dbt run, dbt test, dbt docs generate.

## PHASE 3: Airflow orchestration
- airflow/Dockerfile installing Airflow with a pinned stable version, plus dbt-redshift installed in a
  SEPARATE virtualenv (for example /opt/dbt-venv) to avoid dependency conflicts, and call dbt via that path.
- airflow/docker-compose.yml: minimal LocalExecutor setup, mounts dags/ and ../dbt, reads env from
  airflow/.env, and can reach Airbyte on the host via host.docker.internal:8000.
- DAG olist_daily_pipeline (daily schedule, catchup False, retries with delay):
  1. trigger Airbyte sync (Airbyte API, authenticated with client id/secret, connection id from env,
     wait for completion, fail clearly if the sync fails)
  2. dbt run (staging, then marts)
  3. dbt test
  4. final task that logs a success summary
  Use clear task ids, task documentation (doc_md) and readable logs.
- Also provide the instructions to run it manually and to view the graph.

## PHASE 4: Conversational BI app (Streamlit)
- app/streamlit_app.py plus helper modules. A chat box where I ask business questions in plain English.
- Flow: read table and column schemas of the marts schema from the warehouse -> send question and schema
  to an LLM -> get SQL back -> VALIDATE -> run -> show the SQL, a results table, and a chart when sensible.
- LLM provider is switchable via env LLM_PROVIDER (gemini or anthropic) with a small adapter class.
- SQL safety validator (use sqlglot): exactly one statement, SELECT only, only tables in the marts schema,
  no DDL or DML, force a LIMIT of at most 1000. Connect with the read-only app user. On a SQL error,
  retry once by sending the error back to the LLM.
- Sidebar: list of mart tables with descriptions, 6 clickable sample questions, and a query history for
  the session. Friendly error messages. Never show credentials.
- Unit tests (pytest) for the SQL validator.

## PHASE 5: Documentation and demo support (NOT the college report)
- docs/data_dictionary.md for raw, staging and marts tables.
- docs/runbook.md: start-up order, how to run end to end, how to stop things to save RAM and AWS cost.
- docs/testing.md: a table of test cases (what, how, expected result, pass or fail column left blank).
- docs/screenshots_checklist.md: everything I should screenshot for my report (Airbyte sync, Redshift
  tables, dbt run and test, dbt docs lineage graph, Airflow green DAG, Streamlit answers).
- A 5-minute demo script and a list of 10 likely viva questions with short answers.

## Definition of done
Running the Airflow DAG once loads Postgres data into Redshift raw, builds staging and marts with passing
dbt tests, and the Streamlit app answers the sample questions from the mart tables.