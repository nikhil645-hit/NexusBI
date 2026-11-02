# Operational Runbook: End-to-End Pipeline

> [!IMPORTANT]
> Follow this runbook sequentially during local development, demo preparation, and final viva evaluation. Adhering to the cold-start and shut-down order ensures you stay within your 16 GB workstation RAM budget and prevents AWS cloud billing charges.

---

## 1. System Cold-Start Order

Always start components in this exact order:

```text
[1. Local Postgres] ──> [2. Airbyte OSS] ──> [3. Redshift Serverless] ──> [4. Airflow Stack] ──> [5. Streamlit App]
```

### Step 1: Start Source PostgreSQL Container
1. Ensure Docker Desktop is running.
2. Launch the transactional Postgres container:
   ```bash
   make source-up
   # Or: docker compose -f source/docker-compose.yml up -d
   ```
3. Check container health:
   ```bash
   docker ps --filter "name=olist-postgres"
   ```
4. If this is a fresh setup, load the Olist dataset (~100k rows):
   ```bash
   make source-load
   # Or: python source/load_olist.py
   ```

### Step 2: Start Airbyte OSS
1. Launch Airbyte via `abctl`:
   ```bash
   abctl local start
   ```
2. Verify Airbyte UI is accessible at **`http://localhost:8000`**.
3. Confirm that the Postgres source and Redshift destination show **Passed** in connection status.

### Step 3: Verify AWS Redshift Serverless & Security Group
1. Open the AWS Redshift Console (Region: `ap-south-1` Mumbai).
2. Check that workgroup `olist-workgroup` is in **Available** status.
3. **CRITICAL (IP Check):** Verify the VPC Security Group allows inbound port `5439` from your current IP. If you changed WiFi networks, update the inbound rule to **My IP**.

### Step 4: Start Airflow Orchestration
1. Ensure your `airflow/.env` file is populated with valid Redshift and Airbyte connection variables:
   ```bash
   cp airflow/.env.example airflow/.env
   # Update values in airflow/.env
   ```
2. Launch the minimal LocalExecutor Airflow stack:
   ```bash
   make airflow-up
   # Or: docker compose -f airflow/docker-compose.yml up -d
   ```
3. Monitor startup logs until webserver and scheduler are healthy:
   ```bash
   docker compose -f airflow/docker-compose.yml ps
   ```
4. Access the Airflow UI at **`http://localhost:8080`** (Login: `admin` / `admin`).

### Step 5: Launch Streamlit Conversational BI
1. In a separate terminal or virtual environment:
   ```bash
   make app-run
   # Or: streamlit run app/streamlit_app.py
   ```
2. Access the conversational interface at **`http://localhost:8501`**.

---

## 2. End-to-End Pipeline Execution

To trigger the complete ingestion, transformation, testing, and analytics cycle:

1. In Airflow (`http://localhost:8080`), locate DAG **`olist_daily_pipeline`**.
2. Unpause the DAG (toggle switch to Active).
3. Click the **Trigger DAG** (▶) button.
4. Watch the pipeline flow through all 5 tasks in the Graph View:
   - `trigger_airbyte_sync` (Airbyte reads Postgres -> writes to Redshift `raw`).
   - `dbt_run_staging` (dbt builds 5 staging views).
   - `dbt_run_marts` (dbt builds 4 analytical marts tables).
   - `dbt_test` (dbt executes all schema and non-negative tests).
   - `log_pipeline_summary` (Emits execution report).
5. Once all 5 nodes are **Dark Green**, switch to Streamlit (`http://localhost:8501`).
6. Click any sample question in the sidebar. Verify:
   - Generated SQL is displayed.
   - Result table displays real transformed data.
   - Dynamic chart renders automatically.

---

## 3. Resource Conservation & Cost Shutdown

When your demonstration or development session is complete, **immediately** execute this shutdown procedure:

### Part A: Save Local Workstation RAM (Free up ~8-10 GB)
1. Stop the Airflow stack:
   ```bash
   make airflow-down
   ```
2. Stop Airbyte OSS:
   ```bash
   abctl local stop
   ```
3. Stop the local Postgres container:
   ```bash
   make source-down
   ```

### Part B: Save AWS Cloud Costs ($0 Inactive Spend)
Redshift Serverless automatically pauses compute billing when no queries are running. However, to guarantee zero storage or idle costs between college sessions:

1. **Delete / Pause Redshift Workgroup & Namespace:**
   - Go to AWS Console -> **Redshift Serverless** -> Workgroups.
   - If not actively developing, delete the workgroup `olist-workgroup` and namespace `olist-namespace`.
   - *(You can recreate them in 5 minutes using [docs/aws_setup.md](aws_setup.md) before your next demo).*
2. **Purge S3 Staging Bucket:**
   - Empty any temporary staged files in `olist-airbyte-staging-...`.

---

## 4. Troubleshooting & Healthcheck Matrix

| Symptom | Probable Cause | Exact Solution |
| :--- | :--- | :--- |
| **`dbt debug` times out connecting to Redshift** | Home/Mobile IP changed or Security Group port 5439 blocked | Go to AWS Console -> EC2 -> Security Groups -> Edit Inbound Rules -> Change port 5439 source to **My IP** -> Save. |
| **Docker runs out of memory (OOMKilled)** | Celery or too many heavy containers active simultaneously | Ensure Celery/Redis are disabled. Run `docker stats` to verify memory usage stays below 10 GB. Restart Docker Desktop if needed. |
| **Airbyte task in Airflow fails with 401 Unauthorized** | Airbyte API Client Secret expired or mismatched | Open Airbyte UI -> Settings -> Applications -> Generate a new Client Secret -> Update `AIRBYTE_CLIENT_SECRET` in `airflow/.env`. |
| **Streamlit displays "Query Rejected by Security Guardrail"** | User prompt attempted DDL, multi-statement, or non-marts table | Check the error message in the chat. The query was intentionally blocked by the `sqlglot` validator to protect warehouse integrity. |
| **dbt run fails with "Relation raw.orders does not exist"** | Airbyte replication has not run yet | Trigger Airbyte sync in the UI or via Airflow so raw landing tables are physically created in Redshift first. |
