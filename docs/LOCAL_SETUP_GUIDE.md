# The Local Setup Guide: 100% Free, Zero-AWS Pipeline
## End-to-End Data Engineering Pipeline with Local Warehouse, dbt, Airbyte, Airflow & Streamlit

> [!NOTE]
> **Zero Cloud Cost:** This guide replaces Amazon Redshift with a second local PostgreSQL 16 container (`olist-warehouse` on port `5434`).
> Everything runs on your local workstation (Windows 11 + WSL 2, Docker Desktop) with **$0 cloud spend** and **zero AWS credentials**.
> *(If you ever need to evaluate on AWS Redshift Serverless, see the optional cloud guide: [COMPLETE_SETUP_GUIDE.md](COMPLETE_SETUP_GUIDE.md)).*

---

## 🏗️ Architecture & Port Mapping

Our local architecture runs two isolated PostgreSQL databases alongside our ingestion, orchestration, and presentation services:

| Service | Docker Container | Host URL / Port | Credentials / Schema | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Source OLTP Database** | `olist-postgres` | `localhost:5433` (from containers: `host.docker.internal:5433`) | db: `olist`, user: `olist` | Operational e-commerce database (99,441 orders) |
| **Airbyte OSS** | `abctl` containers | `http://localhost:8000` | Basic auth from abctl | EL data replication engine |
| **Data Warehouse** | `olist-warehouse` | `localhost:5434` (from containers: `host.docker.internal:5434`) | db: `warehouse`, schemas: `raw`, `staging`, `marts` | Dedicated analytical data warehouse |
| **Apache Airflow** | `airflow-webserver`, `scheduler`, `postgres` | `http://localhost:8080` | user: `admin`, pass: `admin` | Automated daily pipeline orchestration |
| **Conversational BI** | Local Python process | `http://localhost:8501` | user: `app_readonly` | Streamlit + LLM text-to-SQL interface |

---

## 📋 Table of Contents
- [Prerequisites Verification](#prerequisites-verification)
- [PART 1: Start and Provision Local Warehouse (Port 5434)](#part-1-start-and-provision-local-warehouse-port-5434)
- [PART 2: Configure Airbyte OSS (Source, Destination & Sync)](#part-2-configure-airbyte-oss-source-destination--sync)
- [PART 3: Configure Environment & Run dbt Transformations](#part-3-configure-environment--run-dbt-transformations)
- [PART 4: Orchestrate with Apache Airflow](#part-4-orchestrate-with-apache-airflow)
- [PART 5: Launch Conversational BI (Streamlit)](#part-5-launch-conversational-bi-streamlit)
- [PART 6: Screenshots Checklist for Report](#part-6-screenshots-checklist-for-report)
- [PART 7: Local Troubleshooting Matrix](#part-7-local-troubleshooting-matrix)

---

## Prerequisites Verification

Before starting, verify that your pre-existing services are running:

### 1. Check Source Database (Port 5433)
In your WSL terminal:
```bash
docker ps --filter "name=olist-postgres"
```
**Expected:** Container `olist-postgres` is `Up` and port mapping shows `0.0.0.0:5433->5432/tcp`.

### 2. Check Airbyte OSS (Port 8000)
Open your browser to: **`http://localhost:8000`**.
**Expected:** The Airbyte Web UI loads cleanly.

---

## PART 1: Start and Provision Local Warehouse (Port 5434)

*Why this exists (Viva Defense):* We follow production data engineering standards by separating the transactional database (OLTP on port 5433) from the analytical warehouse (OLAP on port 5434). Analytical queries never lock production tables.

### 1.1 Create Warehouse Environment Configuration
1. Open your terminal in `~/de-project`:
   ```bash
   cd ~/de-project
   cp warehouse/.env.example warehouse/.env
   ```
2. Inspect `warehouse/.env`. It defines:
   ```bash
   WAREHOUSE_ADMIN_USER=postgres
   WAREHOUSE_ADMIN_PASSWORD=warehouse_secure_pass_123
   WAREHOUSE_DB=warehouse
   WAREHOUSE_PORT=5434
   ```
   *(You can keep `warehouse_secure_pass_123` for local development).*

### 1.2 Start the Warehouse Container
Run the Makefile command:
```bash
make warehouse-up
# Or: docker compose -f warehouse/docker-compose.yml up -d
```
Verify the container is healthy:
```bash
docker ps --filter "name=olist-warehouse"
```
**Expected Output:**
```text
CONTAINER ID   IMAGE         COMMAND                  STATUS                   PORTS
xxxxxxxxxxxx   postgres:16   "docker-entrypoint.s…"   Up (healthy)             0.0.0.0:5434->5432/tcp
```

### 1.3 Initialize Schemas and Users
Run the initialization script using the Makefile target:
```bash
make warehouse-init
```
*(This automatically runs `sql/01_schemas.sql` to create `raw`, `staging`, `marts` and `sql/02_users.sql` to provision `dbt_user` and `app_readonly` inside the container).*

Alternatively, run via `docker exec`:
```bash
docker exec -i olist-warehouse psql -U postgres -d warehouse < sql/01_schemas.sql
docker exec -i olist-warehouse psql -U postgres -d warehouse < sql/02_users.sql
```

### 1.4 Verify Database Initialization
Run a check inside the warehouse container:
```bash
docker exec -it olist-warehouse psql -U postgres -d warehouse -c "\dn"
```
**Expected Output:**
```text
  List of schemas
  Name   |  Owner   
---------+----------
 marts   | postgres
 public  | postgres
 raw     | postgres
 staging | postgres
(4 rows)
```
Check users:
```bash
docker exec -it olist-warehouse psql -U postgres -d warehouse -c "\du"
```
**Expected Output:**
```text
                                   List of roles
  Role name   |                         Attributes                         
--------------+------------------------------------------------------------
 app_readonly | Cannot login (or standard login), SELECT on marts
 dbt_user     | Full access to staging/marts, read on raw
 postgres     | Superuser, Create role, Create DB, Replication, Bypass RLS
```

> [!NOTE]
> **CHECKPOINT 1:**
> - Container `olist-warehouse` is healthy on port `5434`.
> - Schemas `raw`, `staging`, and `marts` are present.
> - Roles `dbt_user` and `app_readonly` are provisioned.
> - **Screenshot for report:** Terminal output of `docker ps` showing both `olist-postgres` (5433) and `olist-warehouse` (5434).

---

## PART 2: Configure Airbyte OSS (Source, Destination & Sync)

*Why this exists (Viva Defense):* Airbyte functions as our Extract & Load (EL) data movement platform. In this local setup, Airbyte reads from our source container on port 5433 and replicates directly into our warehouse container on port 5434.

### 2.1 Verify / Configure the Source in Airbyte
1. Open your browser to **`http://localhost:8000`**.
2. In the left navigation menu, click **Sources**.
3. If `olist-postgres-source` already exists, click on it and verify:
   - **Host:** `host.docker.internal`
   - **Port:** `5433`
   - **Database:** `olist`
   - **User:** `olist`
   - **SSL Mode:** `disable`
4. If not created yet:
   - Click **+ New source** -> search `Postgres`.
   - Name: `olist-postgres-source`.
   - Fill in the values above and click **Set up source**.

---

### 2.2 Create the Warehouse Destination in Airbyte
1. In the left navigation menu, click **Destinations** -> click **+ New destination**.
2. In the search box, type `Postgres` and select the **Postgres** destination connector.
3. Fill in the exact connection settings:

| Field Name in Airbyte UI | Exact Value to Enter | Explanation |
| :--- | :--- | :--- |
| **Destination name** | `warehouse-postgres-dest` | Identifies your local warehouse |
| **Host** | `host.docker.internal` | Allows Airbyte container to reach host port 5434 |
| **Port** | `5434` | Host port mapped to `olist-warehouse` |
| **Database Name** | `warehouse` | Database created by warehouse container |
| **Default Schema** | `raw` | Tables will land in the `raw` schema |
| **User** | `postgres` | Warehouse admin user |
| **Password** | `warehouse_secure_pass_123` | Password defined in `warehouse/.env` |
| **SSL Mode** | `disable` | Local Docker connection does not require SSL |

4. Click **Set up destination**. Airbyte will run a connection check. Wait for the green checkmark: *All connection tests passed*.

---

### 2.3 Create Connection and Trigger Full Refresh Sync
1. In the left menu, click **Connections** -> click **+ New connection**.
2. **Source:** Select `olist-postgres-source`.
3. **Destination:** Select `warehouse-postgres-dest`.
4. Configure connection parameters:
   - **Connection name:** `Olist Source to Warehouse`.
   - **Schedule type:** `Manual` (Airflow will trigger this programmatically).
   - **Destination namespace:** Select **Custom format** and enter `raw`.
   - **Destination stream prefix:** Leave blank (no prefix).
   - **Non-breaking schema updates:** Select *Approve and re-sync changes*.
5. In the **Streams (Tables)** table, ensure all 6 tables are selected and set to **`Full refresh | Overwrite`**:
   - `customers` -> `Full refresh | Overwrite`
   - `orders` -> `Full refresh | Overwrite`
   - `order_items` -> `Full refresh | Overwrite`
   - `order_payments` -> `Full refresh | Overwrite`
   - `products` -> `Full refresh | Overwrite`
   - `category_translation` -> `Full refresh | Overwrite`
6. Click **Set up connection**.
7. On the connection status page, click the blue **Sync now** button.
8. Watch the sync progress. It will replicate ~100k rows across all 6 tables in about 30–60 seconds.
9. Verify the final status turns **Succeeded** (green).

---

### 2.4 Verify Replicated Data in Warehouse
Run this query in your terminal to inspect the row counts in `olist-warehouse`:
```bash
docker exec -it olist-warehouse psql -U postgres -d warehouse -c "
SELECT 'customers' as tbl, count(*) as rows FROM raw.customers
UNION ALL
SELECT 'orders', count(*) FROM raw.orders
UNION ALL
SELECT 'order_items', count(*) FROM raw.order_items
UNION ALL
SELECT 'order_payments', count(*) FROM raw.order_payments
UNION ALL
SELECT 'products', count(*) FROM raw.products
UNION ALL
SELECT 'category_translation', count(*) FROM raw.category_translation;
"
```
**Expected Verification Table:**
```text
         tbl          |  rows  
----------------------+--------
 customers            |  99441
 orders               |  99441   <-- EXACT MATCH
 order_items          | 112650
 order_payments       | 103886
 products             |  32951
 category_translation |     71
(6 rows)
```

---

### 2.5 Retrieve Airbyte Connection ID & API Credentials
Airflow needs these values to trigger synchronization programmatically:

1. **Find Connection ID:**
   - Look at your browser URL bar while viewing the connection:
     `http://localhost:8000/workspaces/<workspace-id>/connections/<connection-id>/status`
   - Copy the `<connection-id>` UUID (e.g. `c7b39a48-1234-5678-9abc-def012345678`).
2. **Find / Create API Client Credentials:**
   - In the bottom-left corner of the Airbyte UI, click the **Settings** gear icon (⚙️).
   - Under *Workspace*, click **Applications**.
   - If `airflow-orchestrator` is not already created, click **+ New application** -> Name: `airflow-orchestrator` -> click **Create application**.
   - Copy the **Client ID** and **Client Secret**.

> [!NOTE]
> **CHECKPOINT 2:**
> - Airbyte replication completed with status **Succeeded**.
> - Warehouse `raw.orders` has exactly `99,441` rows.
> - Connection ID and API credentials are saved for `.env`.
> - **Screenshot for report:** Airbyte connection screen showing green `Succeeded` sync badge with 6 streams.

---

## PART 3: Configure Environment & Run dbt Transformations

*Why this exists (Viva Defense):* dbt transforms raw data into analytics-ready models using modular SQL. It creates lightweight views in `staging` and physical tables in `marts`, enforcing automated data quality tests.

### 3.1 Populate Root `.env`
In `~/de-project`, create `.env` from `.env.example`:
```bash
cp .env.example .env
```
Edit `.env` (using `nano .env` or VS Code) to fill in your values:
```bash
# 1. Local Postgres Source (Port 5433)
PG_HOST=localhost
PG_PORT=5433
PG_DB=olist
PG_USER=olist
PG_PASSWORD=your_source_postgres_password

# 2. Local Postgres Warehouse (Port 5434)
WAREHOUSE_HOST=localhost
WAREHOUSE_PORT=5434
WAREHOUSE_DB=warehouse
WAREHOUSE_ADMIN_USER=postgres
WAREHOUSE_ADMIN_PASSWORD=warehouse_secure_pass_123
WAREHOUSE_DBT_USER=dbt_user
WAREHOUSE_DBT_PASSWORD=REPLACE_WITH_STRONG_DBT_PASSWORD_123!
WAREHOUSE_APP_USER=app_readonly
WAREHOUSE_APP_PASSWORD=REPLACE_WITH_STRONG_APP_PASSWORD_123!

# 3. Airbyte OSS
AIRBYTE_API_URL=http://localhost:8000/api/v1
AIRBYTE_CLIENT_ID=<your_airbyte_client_id>
AIRBYTE_CLIENT_SECRET=<your_airbyte_client_secret>
AIRBYTE_CONNECTION_ID=<your_airbyte_connection_id>

# 4. Airflow
AIRFLOW_UID=50000
AIRFLOW_PROJ_DIR=.
AIRFLOW__CORE__LOAD_EXAMPLES=False

# 5. Conversational BI & LLM
LLM_PROVIDER=gemini
GEMINI_API_KEY=<your_gemini_api_key_or_leave_empty_for_mock>
ANTHROPIC_API_KEY=
STREAMLIT_SERVER_PORT=8501
```

---

### 3.2 Install `dbt-postgres` in Project Virtual Environment
In your WSL terminal:
```bash
cd ~/de-project
~/de-project/.venv/bin/pip install dbt-postgres==1.8.2
```

---

### 3.3 Test Warehouse Connectivity with `dbt debug`
```bash
cd ~/de-project/dbt/olist_dbt
# Export variables from root .env
export $(grep -v '^#' ../../.env | xargs)

# Test dbt connection
~/de-project/.venv/bin/dbt debug
```
**Expected Output:**
```text
Configuration:
  profiles.yml file [OK found and valid]
  dbt_project.yml file [OK found and valid]

Required dependencies:
  - git [OK]

Connection:
  host: localhost
  port: 5434
  user: dbt_user
  database: warehouse
  schema: staging
  Connection test: [OK connection ok]

All checks passed!
```

---

### 3.4 Build Models & Run Automated Tests
```bash
# 1. Install package dependencies
~/de-project/.venv/bin/dbt deps

# 2. Compile and run all staging views and marts tables
~/de-project/.venv/bin/dbt run
```
**Expected Output:**
```text
Running with dbt=1.8.2
Found 9 models, 4 sources, 21 data tests...
Concurrency: 4 threads (target='dev')

1 of 9 START sql view model staging.stg_customers .................... [RUN]
2 of 9 START sql view model staging.stg_orders ....................... [RUN]
3 of 9 START sql view model staging.stg_order_items .................. [RUN]
4 of 9 START sql view model staging.stg_order_payments ............... [RUN]
5 of 9 START sql view model staging.stg_products ..................... [RUN]
1 of 9 OK created sql view model staging.stg_customers ............... [OK in 0.45s]
...
6 of 9 START sql table model marts.mart_daily_sales .................. [RUN]
7 of 9 START sql table model marts.mart_top_products ................. [RUN]
8 of 9 START sql table model marts.mart_customer_summary ............. [RUN]
9 of 9 START sql table model marts.mart_delivery_performance ......... [RUN]
...
Finished running 5 view models, 4 table models in 4.82s.
Completed successfully
Done. PASS=9 WARN=0 ERROR=0 SKIP=0 TOTAL=9
```

```bash
# 3. Execute all automated data quality assertions
~/de-project/.venv/bin/dbt test
```
**Expected Output:**
```text
Running with dbt=1.8.2
Found 21 data tests...

1 of 21 START test unique_stg_customers_customer_id .................. [RUN]
1 of 21 PASS unique_stg_customers_customer_id ........................ [PASS in 0.12s]
...
21 of 21 START test assert_revenue_is_non_negative ................... [RUN]
21 of 21 PASS assert_revenue_is_non_negative ......................... [PASS in 0.08s]

Finished running 21 tests in 2.34s.
Completed successfully
Done. PASS=21 WARN=0 ERROR=0 SKIP=0 TOTAL=21
```

> [!NOTE]
> **Model Change Report for Viva:**
> When switching from Redshift to PostgreSQL, all models worked identically with zero modifications except [mart_delivery_performance.sql](file:///d:/de-project/dbt/olist_dbt/models/marts/mart_delivery_performance.sql). Redshift's proprietary `datediff('day', ts1, ts2)` was replaced with standard ANSI SQL date subtraction: `(cast(ts2 as date) - cast(ts1 as date))`. This makes the model 100% portable across PostgreSQL, Redshift, and Snowflake!

> [!NOTE]
> **CHECKPOINT 3:**
> - `dbt debug` passes.
> - `dbt run` compiles 5 staging views and 4 marts tables in `olist-warehouse`.
> - `dbt test` reports **PASS=21 WARN=0 ERROR=0**.
> - **Screenshot for report:** Terminal output displaying `dbt run` and `dbt test` green completion summaries.

---

## PART 4: Orchestrate with Apache Airflow

*Why this exists (Viva Defense):* Airflow eliminates manual execution. It orchestrates the entire data pipeline on a schedule using a lean `LocalExecutor` configuration staying well within our 10 GB Docker RAM budget.

### 4.1 Populate Airflow Environment
```bash
cd ~/de-project
cp airflow/.env.example airflow/.env
```
Edit `airflow/.env` to configure your connection credentials:
```bash
AIRFLOW_UID=50000
AIRFLOW_DB_PASSWORD=airflow
AIRFLOW__CORE__FERNET_KEY=46BKJoQYlPPOexq0OhDZnIlNepKFf87WFwLbfzqnzq8=

# Airbyte OSS Integration (from container)
AIRBYTE_API_URL=http://host.docker.internal:8000/api/v1
AIRBYTE_CLIENT_ID=<your_airbyte_client_id>
AIRBYTE_CLIENT_SECRET=<your_airbyte_client_secret>
AIRBYTE_CONNECTION_ID=<your_airbyte_connection_id>

# Local PostgreSQL Warehouse Configuration (host.docker.internal:5434)
WAREHOUSE_HOST=host.docker.internal
WAREHOUSE_PORT=5434
WAREHOUSE_DB=warehouse
WAREHOUSE_DBT_USER=dbt_user
WAREHOUSE_DBT_PASSWORD=REPLACE_WITH_STRONG_DBT_PASSWORD_123!
```

---

### 4.2 Start Airflow Stack
Launch the containers using the Makefile target:
```bash
make airflow-up
# Or: docker compose -f airflow/docker-compose.yml up -d
```
Check container status:
```bash
docker compose -f airflow/docker-compose.yml ps
```
**Expected Output:**
```text
NAME                IMAGE                 COMMAND                  SERVICE             STATUS
airflow-init        olist-airflow:2.9.3   "/bin/bash -c 'airfl…"   airflow-init        exited (0)
airflow-postgres    postgres:16-alpine    "docker-entrypoint.s…"   postgres            Up (healthy)
airflow-scheduler   olist-airflow:2.9.3   "/usr/bin/dumb-init …"   airflow-scheduler   Up
airflow-webserver   olist-airflow:2.9.3   "/usr/bin/dumb-init …"   airflow-webserver   Up (healthy)
```

---

### 4.3 Trigger & Monitor DAG in Airflow UI
1. Open your browser and navigate to: **`http://localhost:8080`**.
2. **Log in:** Username `admin` | Password `admin`.
3. Locate DAG **`olist_daily_pipeline`**.
4. Toggle the switch on the left from *Paused* to **Active** (Blue).
5. On the right side, click the **Trigger DAG** (▶) button.
6. Click on the DAG name `olist_daily_pipeline` -> open the **Graph** tab.
7. Observe all 5 task nodes turn **Dark Green** (`success`) in sequence:
   - `trigger_airbyte_sync` -> calls Airbyte API -> completes.
   - `dbt_run_staging` -> builds 5 staging views in `warehouse`.
   - `dbt_run_marts` -> builds 4 physical tables in `warehouse`.
   - `dbt_test` -> runs 21 schema and singular assertions -> passes.
   - `log_pipeline_summary` -> logs completion summary.
8. Click `log_pipeline_summary` -> click **Logs** to view the success banner.

> [!NOTE]
> **CHECKPOINT 4:**
> - Airflow Web UI displays all 5 nodes of `olist_daily_pipeline` in dark green.
> - **Screenshot for report:** Airflow Graph view showing all 5 tasks green.

---

## PART 5: Launch Conversational BI (Streamlit)

*Why this exists (Viva Defense):* Enables business users to query data marts using natural language. Our `sqlglot` Abstract Syntax Tree (AST) validator deterministically prevents prompt injection and enforces read-only access.

### 5.1 Launch the Streamlit App
In your WSL terminal:
```bash
cd ~/de-project
make app-run
# Or: ~/de-project/.venv/bin/streamlit run app/streamlit_app.py
```
Open your browser to: **`http://localhost:8501`**.

---

### 5.2 Verify UI & Test the 6 Clickable Sample Questions
1. Look at the left sidebar:
   - **Warehouse status:** Displays `<span class='badge-status-ok'>Local Postgres (5434)</span>`.
   - **Data Marts Catalog:** Lists `mart_daily_sales`, `mart_top_products`, `mart_customer_summary`, and `mart_delivery_performance`.
2. Click any of the 6 sample questions:
   - *Sample Question 1:* "What are the top 5 product categories by total revenue?"
     - *Verified SQL:* Generated with `LIMIT 5`.
     - *Display:* Data table and comparative **bar chart**.
   - *Sample Question 2:* "Show the daily sales trend and average order value for the last 30 days."
     - *Verified SQL:* Generated with `ORDER BY sales_date DESC LIMIT 30`.
     - *Display:* Multi-series **line chart**.

---

### 5.3 Demonstrate Security Guardrail (Viva Highlight)
Type the following command into the chat input:
```text
DROP TABLE marts.mart_daily_sales;
```
**Observed Result:**
The app displays an immediate red warning banner:
`🛡️ Query Rejected by Security Guardrail: Security Violation: Forbidden statement type 'DROP'. Only read-only SELECT queries are permitted.`

> [!NOTE]
> **CHECKPOINT 5:**
> - Streamlit loads at `http://localhost:8501`.
> - Sample questions answer with verified SQL, data tables, and dynamic charts.
> - Security validator blocks malicious statements.
> - **Screenshot for report:** Streamlit UI showing an answered question with table + chart, plus the security rejection alert.

---

## PART 6: Screenshots Checklist for Report

Capture these screenshots as evidence for your college project report and viva presentation:

| Step | Screen / Window to Capture | Recommended File Name |
| :---: | :--- | :--- |
| **1** | Terminal output showing `docker ps` with both `olist-postgres` and `olist-warehouse` | `01_docker_containers_health.png` |
| **2** | Terminal output of warehouse schema and table check (`\dn` and row counts) | `02_warehouse_schemas_and_rows.png` |
| **3** | Airbyte UI showing Green `Succeeded` sync for 6 tables | `03_airbyte_local_sync_succeeded.png` |
| **4** | Terminal running `dbt run` showing 9 models successfully created | `04_dbt_run_terminal.png` |
| **5** | Terminal running `dbt test` showing 21 tests passing (100%) | `05_dbt_test_terminal.png` |
| **6** | Airflow Graph view showing all 5 tasks dark green (`success`) | `06_airflow_green_dag_graph.png` |
| **7** | Streamlit chat UI showing natural language query, SQL, table, and chart | `07_streamlit_conversational_bi.png` |
| **8** | Streamlit security rejection banner blocking `DROP TABLE` | `08_streamlit_security_guardrail.png` |

---

## PART 7: Local Troubleshooting Matrix

| Symptom | Probable Cause | Exact Solution |
| :--- | :--- | :--- |
| **`docker compose up` fails: port 5434 already allocated** | Another local service or Postgres instance is using port 5434 | Run `netstat -ano \| findstr 5434` (in Windows) to identify and terminate conflicting processes. |
| **Airbyte connection fails: connection to host.docker.internal:5434 refused** | `olist-warehouse` container is stopped or not listening on port 5434 | Run `make warehouse-up` and verify `docker ps` shows `0.0.0.0:5434->5432/tcp`. |
| **`dbt debug` fails: password authentication failed for user "dbt_user"** | `sql/02_users.sql` was not executed or password in `.env` differs | Run `make warehouse-init` and verify `WAREHOUSE_DBT_PASSWORD` in `.env` matches the password in `sql/02_users.sql`. |
| **`dbt run` fails: relation "raw.orders" does not exist** | Airbyte sync has not been triggered yet | Open Airbyte UI (`http://localhost:8000`) -> Connections -> `Olist Source to Warehouse` -> click **Sync now**. |
| **Airflow task `trigger_airbyte_sync` fails: ConnectionRefusedError** | Container cannot reach host port 8000 | Verify `extra_hosts: ["host.docker.internal:host-gateway"]` is present in `airflow/docker-compose.yml`. |
| **Airflow task fails: AIRBYTE_CONNECTION_ID is not configured** | Variable is empty in `airflow/.env` | Copy the Connection UUID from the Airbyte browser URL and paste into `airflow/.env`. |
| **Docker Desktop runs out of memory (freeze / crash)** | Celery or too many background containers active simultaneously | We use `LocalExecutor` to stay under 10 GB. If tight on RAM, stop Airbyte while testing dbt (`abctl local stop`). |
| **Streamlit displays: "Warehouse is not yet configured"** | `WAREHOUSE_HOST` or `WAREHOUSE_APP_PASSWORD` missing in `.env` | Ensure `.env` in project root contains `WAREHOUSE_HOST=localhost` and `WAREHOUSE_APP_PASSWORD`. |
| **Streamlit shows: Query Rejected by Security Guardrail** | Query attempted DDL or non-marts tables | This is normal behavior! The AST validator intentionally protects the database against prompt injection. |
| **`dbt run` fails with syntax error on `datediff`** | Using old Redshift SQL syntax | Ensure `mart_delivery_performance.sql` uses `(cast(delivered as date) - cast(purchase as date))`. |

