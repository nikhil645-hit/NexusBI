# Screenshots Checklist for College Report & Viva Submission

Capture the following screenshots during your evaluation run. These provide indisputable visual evidence for your project report and defense presentation.

---

## 1. Section A: Source Database & Data Loading
- [ ] **Screenshot 1: Local PostgreSQL Container**
  - **Where:** Terminal.
  - **Command:** `docker ps --filter "name=olist-postgres"`
  - **What to highlight:** Container name `olist-postgres`, image `postgres:16`, status `Up`, and port `5433->5432`.
- [ ] **Screenshot 2: Source Tables & Record Counts**
  - **Where:** Terminal or DBeaver / pgAdmin.
  - **Command:** `SELECT count(*) FROM orders;` and `SELECT count(*) FROM customers;`
  - **What to highlight:** Total order count showing `99,441` rows loaded from Olist CSVs.

---

## 2. Section B: Ingestion with Airbyte OSS
- [ ] **Screenshot 3: Airbyte Source Configuration**
  - **Where:** Airbyte Web UI (`http://localhost:8000`) -> Sources -> `olist-postgres-source`.
  - **What to highlight:** Host `host.docker.internal`, port `5433`, database `olist`, and green connection check status.
- [ ] **Screenshot 4: Airbyte Destination Configuration**
  - **Where:** Airbyte Web UI -> Destinations -> `redshift-serverless-dest`.
  - **What to highlight:** Host pointing to Redshift Serverless endpoint, default schema `raw`, and S3 staging mode enabled.
- [ ] **Screenshot 5: Green Replication Run**
  - **Where:** Airbyte Web UI -> Connections -> `Olist Postgres to Redshift` -> Job History.
  - **What to highlight:** Green status badge `Succeeded`, sync mode `Full Refresh | Overwrite`, record count (~100k records), and runtime duration.

---

## 3. Section C: Amazon Redshift Serverless & RBAC
- [ ] **Screenshot 6: Redshift Serverless Workgroup & Namespace**
  - **Where:** AWS Management Console -> Amazon Redshift -> Redshift Serverless.
  - **What to highlight:** Namespace `olist-namespace`, Workgroup `olist-workgroup`, status `Available`, Base capacity `8 RPUs`, region `ap-south-1`.
- [ ] **Screenshot 7: Redshift Query Editor v2 - Schema Hierarchy**
  - **Where:** AWS Redshift Query Editor v2.
  - **What to highlight:** Left sidebar expanding database `dev`, displaying three distinct schemas: `raw`, `staging`, and `marts`.
- [ ] **Screenshot 8: Security Group Inbound Rule**
  - **Where:** AWS EC2 Management Console -> Security Groups.
  - **What to highlight:** Inbound rule allowing TCP port `5439` restricted to your IP (`<my-ip>/32`).

---

## 4. Section D: dbt Transformation, Lineage & Quality Tests
- [ ] **Screenshot 9: Terminal `dbt run` Execution**
  - **Where:** Terminal (`cd dbt/olist_dbt && dbt run`).
  - **What to highlight:** Green output lines building 5 staging views (`stg_customers`, `stg_orders`, etc.) and 4 physical marts tables (`mart_daily_sales`, `mart_top_products`, etc.).
- [ ] **Screenshot 10: Terminal `dbt test` Execution**
  - **Where:** Terminal (`dbt test`).
  - **What to highlight:** All tests passing (`PASS unique_...`, `PASS not_null_...`, `PASS relationships_...`, `PASS assert_revenue_is_non_negative`). Final summary showing `Passed: 100%`.
- [ ] **Screenshot 11: dbt Interactive Lineage Graph**
  - **Where:** Browser (`dbt docs generate && dbt docs serve --port 8080`).
  - **What to highlight:** Directed Acyclic Graph (DAG) visual showing arrows flowing from `sources.raw` -> `staging views` -> `marts tables`.

---

## 5. Section E: Apache Airflow Orchestration
- [ ] **Screenshot 12: Airflow DAG Overview**
  - **Where:** Airflow Web UI (`http://localhost:8080`) -> DAGs list.
  - **What to highlight:** DAG `olist_daily_pipeline` active, schedule `@daily`, recent run status green circle.
- [ ] **Screenshot 13: Airflow 5-Node Graph View (All Green)**
  - **Where:** Airflow Web UI -> `olist_daily_pipeline` -> **Graph** tab.
  - **What to highlight:** All 5 task nodes colored dark green (`success`):
    `trigger_airbyte_sync` -> `dbt_run_staging` -> `dbt_run_marts` -> `dbt_test` -> `log_pipeline_summary`.
- [ ] **Screenshot 14: Airflow Task Execution Logs**
  - **Where:** Airflow Web UI -> Click `log_pipeline_summary` -> Logs.
  - **What to highlight:** Banner displaying `OLIST DAILY PIPELINE EXECUTION SUCCESS` and execution timestamps.

---

## 6. Section F: Conversational BI Web App (Streamlit)
- [ ] **Screenshot 15: Streamlit Chat Interface & Sample Query**
  - **Where:** Streamlit App (`http://localhost:8501`).
  - **What to highlight:** Natural language prompt ("What are the top 5 product categories by total revenue?"), expandable verified SQL query, results DataFrame, and auto-generated bar chart.
- [ ] **Screenshot 16: Time-Series Trend Visualization**
  - **Where:** Streamlit App (`http://localhost:8501`).
  - **What to highlight:** Daily sales question displaying multi-line chart comparing `total_revenue` and `avg_order_value`.
- [ ] **Screenshot 17: Defense-in-Depth Security Block Demonstration**
  - **Where:** Streamlit App (`http://localhost:8501`).
  - **Command entered in chat:** `DROP TABLE marts.mart_daily_sales;` or `SELECT * FROM raw.customers;`
  - **What to highlight:** Yellow/red warning banner: `🛡️ Query Rejected by Security Guardrail: Security Violation: Access to schema 'raw' is forbidden`. Proves your app cannot be hijacked.
