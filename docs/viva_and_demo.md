# 5-Minute Demo Script & Top 10 Viva Defense Questions

This guide is your secret weapon for the project evaluation and viva examination. Read through the 5-minute timed demo script and memorize the concise viva defense answers.

---

## ⏱️ 5-Minute Timed Demo Script

### Minute 0:00 – 1:00: Problem Statement & Architecture
- **What to say:**
  > "Good morning examiners. Today I am presenting an end-to-end modern data engineering pipeline with a Conversational BI interface built on the real-world Brazilian E-Commerce dataset (Olist, ~100,000 transactions).
  >
  > Instead of legacy ETL pipelines where transformation happens on a single bottleneck server, we built a modern **ELT architecture** following the **Medallion design pattern**:
  > 1. Source transactional PostgreSQL (OLTP).
  > 2. Airbyte OSS extracts and loads raw data into Amazon Redshift Serverless (`raw` schema) using Amazon S3 for high-throughput staging.
  > 3. dbt compiles cleansed views in `staging` and dimensional star-schema tables in `marts`.
  > 4. Apache Airflow orchestrates the workflow on a daily schedule.
  > 5. Finally, a Streamlit chat app enables non-technical business stakeholders to ask questions in plain English, verified through an AST SQL security guardrail."
- **What to show:** Open [docs/architecture.md](architecture.md) or show the architecture slide diagram.

---

### Minute 1:00 – 2:00: Orchestration & Ingestion Live View
- **What to say:**
  > "Let's examine the pipeline in action. Here is our Apache Airflow DAG: `olist_daily_pipeline`.
  > To respect our local machine's 16 GB memory ceiling, Airflow runs in a lean `LocalExecutor` mode without heavy Redis or Celery dependencies, staying under our 10 GB Docker RAM budget.
  >
  > When triggered, the first task calls the Airbyte REST API via OAuth credentials to sync all 6 Olist tables in `Full refresh | Overwrite` mode into Redshift's `raw` schema. Once the sync succeeds, Airflow invokes dbt."
- **What to show:** Airflow Web UI (`http://localhost:8080`) showing the green 5-task DAG graph view.

---

### Minute 2:00 – 3:00: dbt Data Modeling & Automated Quality Assertions
- **What to say:**
  > "Inside Amazon Redshift Serverless, we enforce software engineering best practices using dbt:
  > - Staging views clean and cast timestamps, normalize foreign keys, and drop ingestion metadata.
  > - Marts physical tables compute aggregated business metrics: daily sales trends, top product leaderboards, customer lifetime value, and logistics delivery SLAs.
  > - We enforce automated data quality tests before any stakeholder sees the data: uniqueness, not-null, referential integrity, and a custom singular SQL test asserting that revenue is never negative."
- **What to show:** Show terminal or report screenshot of `dbt test` passing 100% or open `dbt docs` lineage graph.

---

### Minute 3:00 – 4:00: Conversational BI & Deterministic AST Security
- **What to say:**
  > "Now for the presentation layer. In our Streamlit conversational BI application, users can ask natural language questions like: *'What are the top 5 product categories by total revenue?'*
  >
  > The LLM generates the SQL, but we NEVER execute raw LLM output directly. Instead, we built a deterministic security validator using `sqlglot` that parses the Abstract Syntax Tree (AST). It enforces 5 non-negotiable safety rules:
  > 1. Exactly one SQL statement (no query stacking/chaining).
  > 2. Read-only `SELECT` only (no `DROP`, `DELETE`, or `UPDATE`).
  > 3. Strict schema isolation to `marts` only (blocking `raw` or `pg_catalog`).
  > 4. Forced `LIMIT 1000` to prevent runaway cloud data egress.
  > 5. Database execution runs under a restricted `app_readonly` database user."
- **What to show:**
  1. Click sample question 1 in Streamlit (`http://localhost:8501`). Show the generated SQL, result table, and dynamic bar chart.
  2. Type `DROP TABLE marts.mart_daily_sales;` in chat. Show the immediate red security violation alert blocking the query!

---

### Minute 4:00 – 5:00: Cloud Cost Control & Conclusion
- **What to say:**
  > "Finally, as a student project, cloud cost management was paramount:
  > - We deployed Amazon Redshift Serverless at the minimum 8 Base RPUs.
  > - Configured an AWS 4 RPU-hour daily usage limit and a $5 monthly budget alert.
  > - Configured a 24-hour S3 auto-expiration lifecycle rule for staging files.
  > - Warehouse-specific code is isolated strictly in `profiles.yml` and `db_helper.py`, allowing the entire warehouse to be ported to Snowflake or BigQuery with minimal changes.
  >
  > In conclusion, this project demonstrates end-to-end data engineering: extraction, loading, cloud data warehousing, dimensional modeling, automated testing, containerized orchestration, and secure AI-assisted business intelligence. Thank you, and I am ready for your questions."

---

## 🎓 Top 10 Viva Questions with Concise Answers

### Q1: What is the difference between ETL and ELT, and why did you choose ELT?
**Answer:** In ETL, transformations happen on a separate processing server before loading into the warehouse, creating an architectural bottleneck. In ELT, raw data is loaded directly into the cloud warehouse (`raw` schema), and transformations are performed inside the warehouse using its distributed columnar engine (`dbt` on Redshift). We chose ELT because cloud data warehouses are massively parallel and scale far better than external ETL servers.

---

### Q2: Why did you use Amazon Redshift Serverless instead of a provisioned cluster?
**Answer:** Redshift Serverless decouples compute from storage and automatically spins down when idle, charging only for the compute capacity consumed in RPU-hours. A provisioned cluster charges 24/7 even when no queries are executing, which would incur high costs for a student project.

---

### Q3: Why did you choose `LocalExecutor` instead of `CeleryExecutor` in Airflow?
**Answer:** Our workstation has 16 GB of RAM, and Airbyte already consumes a substantial share of Docker memory. `CeleryExecutor` requires running Redis/RabbitMQ message brokers and Flower monitoring workers across multiple containers. `LocalExecutor` executes tasks as lightweight worker processes directly within the scheduler container, staying well within our 10 GB Docker RAM budget.

---

### Q4: Why is `dbt` installed in a separate virtual environment inside the Airflow Docker image?
**Answer:** Apache Airflow and dbt have complex Python dependency trees with conflicting versions of foundational libraries (e.g., `protobuf`, `jinja2`, `pyyaml`). Installing `dbt-redshift` in an isolated virtual environment (`/opt/dbt-venv`) eliminates library collisions and prevents Airflow scheduler crashes.

---

### Q5: How does Airbyte load data into Amazon Redshift so fast?
**Answer:** Airbyte uses **S3 Staging**. Instead of running thousands of slow individual SQL `INSERT` statements over JDBC, Airbyte writes compressed batches into an S3 bucket and issues Redshift's distributed `COPY` command. Redshift's MPP architecture reads directly from S3 in parallel across compute slices.

---

### Q6: What are the differences between your `raw`, `staging`, and `marts` schemas?
**Answer:**
- `raw`: The landing zone where Airbyte writes source tables untouched, preserving audit history and enabling re-processing.
- `staging`: Lightweight dbt views that clean data, cast timestamps, rename columns consistently, and drop metadata.
- `marts`: Physical star-schema tables aggregated around business entities (`mart_daily_sales`, `mart_top_products`, etc.) designed for fast analytical reporting.

---

### Q7: Why are staging models materialized as views, while marts are materialized as tables?
**Answer:** Staging views perform simple 1-to-1 transformations without heavy aggregations; materializing them as views avoids duplicating raw storage. Marts tables perform complex joins, aggregations, and window ranking functions; materializing them as physical tables ensures dashboard queries in Streamlit respond in milliseconds without re-computing aggregations on every request.

---

### Q8: How do you defend against Prompt Injection in the LLM text-to-SQL interface?
**Answer:** We implement **Defense in Depth** across two independent layers:
1. **Application Layer (AST Validator):** We use `sqlglot` to parse the query into an Abstract Syntax Tree, strictly permitting only a single `SELECT` statement, enforcing that tables belong exclusively to the `marts` schema, and capping results to `LIMIT 1000`.
2. **Database Layer (RBAC):** The app connects with the `app_readonly` database user, which has `SELECT` privileges only on the `marts` schema. Even if the validator were somehow bypassed, the database itself physically rejects any `DROP`, `DELETE`, or `UPDATE` commands.

---

### Q9: What happens if the LLM generates a SQL query with a syntax error?
**Answer:** Our application implements **Single-Turn Self-Correction**. If Redshift returns a database syntax error, the exception is intercepted, sanitized (to prevent leaking credentials), and sent back to the LLM along with the original question and failed SQL. The LLM corrects the query, which is re-validated and executed automatically without crashing the user session.

---

### Q10: How portable is this pipeline if your company decides to switch to Snowflake?
**Answer:** The architecture is strictly decoupled:
- All warehouse-specific configuration is restricted to `dbt/olist_dbt/profiles.yml`, `app/db_helper.py`, and SQL user provisioning scripts.
- The dbt models use ANSI standard SQL.
- Switching to Snowflake requires only changing the dbt adapter to `dbt-snowflake`, pointing Airbyte's destination to Snowflake, and updating the connection credentials in `db_helper.py` without modifying a single line of business logic.
