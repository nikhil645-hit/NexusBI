# 🏗️ NexusBI System Architecture & Technical Design

NexusBI is an end-to-end modern data engineering and conversational business intelligence platform built by a 3rd-year computer engineering student. It translates natural language business questions into verified SQL queries over 100,000 real-world Brazilian E-Commerce (Olist) transactions.

---

## 📐 End-to-End Pipeline Overview

```mermaid
flowchart TD
    subgraph S1["1. Transactional Source (OLTP)"]
        A["PostgreSQL 16 (port 5433)<br/>9 Olist Raw Tables (~100k Orders)"]
    end

    subgraph S2["2. Ingestion Tier"]
        B["Airbyte OSS<br/>Full Refresh / Overwrite Replicator"]
    end

    subgraph S3["3. Orchestration"]
        C["Apache Airflow (LocalExecutor)<br/>Daily Scheduled DAG with Retries"]
    end

    subgraph S4["4. Data Warehouse & Transformation"]
        D1["Raw Schema<br/>Landing tables"]
        D2["Staging Schema (dbt Views)<br/>stg_orders, stg_customers, stg_items"]
        D3["Marts Schema (dbt Tables)<br/>4 Analytics Marts<br/>(Daily Sales, Top Products, Customers, Delivery)"]
        D4["dbt Data Tests<br/>45 Automated Schema & Integrity Tests"]
    end

    subgraph S5["5. Security & Semantic Layer"]
        E1["Semantic Layer (YAML)<br/>Metric formulas & canonical few-shots"]
        E2["sqlglot AST Validator<br/>Single statement, SELECT-only, forced LIMIT"]
        E3["app_readonly Role<br/>SELECT only on marts schema"]
    end

    subgraph S6["6. Conversational Analytics Interface"]
        F1["Streamlit Web Application<br/>Natural language chat + Dashboard Studio"]
        F2["Cloud LLM Adapter<br/>Groq (gpt-oss-120b) / Gemini 1.5 Flash"]
    end

    A -->|Extract| B
    B -->|Load| D1
    C -->|Trigger & Monitor| B
    C -->|Trigger| D2
    D1 --> D2
    D2 --> D3
    D3 --> D4
    F1 -->|User Question| F2
    E1 -->|Context Injection| F2
    F2 -->|Generated SQL| E2
    E2 -->|Sanitized Query| E3
    E3 -->|Execute via psycopg2| D3
    D3 -->|Result Table| F1
```

---

## 🔍 Detailed Component Breakdown

### 1. Source Database (OLTP)
- **Engine**: PostgreSQL 16 running in a local Docker container (`olist-postgres`, port `5433`).
- **Dataset**: Brazilian E-Commerce Public Dataset by Olist (9 relational tables: `orders`, `order_items`, `order_payments`, `order_reviews`, `customers`, `geolocation`, `products`, `sellers`, `product_category_name_translation`).
- **Characteristics**: Normalized transactional schema optimized for row-level writes (OLTP).

### 2. Ingestion Tier (Airbyte OSS)
- **Engine**: Airbyte Open Source running on Kubernetes/Docker.
- **Strategy**: Extracts records from the source PostgreSQL database and writes them into the `raw` schema of the analytical warehouse.
- **Mode**: Full Refresh Overwrite, replicating operational tables without mutating transactional state.

### 3. Orchestration Engine (Apache Airflow)
- **Engine**: Apache Airflow 2.8+ using `LocalExecutor`.
- **DAG**: `olist_daily_pipeline` running on a daily schedule (`@daily`).
- **Task Graph**:
  1. `wait_for_source_db`: Pings the source PostgreSQL instance.
  2. `trigger_airbyte_sync`: Calls the Airbyte API to trigger and poll connector synchronization.
  3. `dbt_run_staging`: Builds dbt staging views cleaning types, timestamps, and column names.
  4. `dbt_run_marts`: Materializes the 4 analytical data marts (including incremental loading).
  5. `dbt_test`: Executes 45 data quality assertions.

### 4. Transformation & Data Modeling (dbt Core)
Data modeling follows dimensional design principles divided into two distinct layers:

#### A. Staging Layer (`staging` schema - Views)
Light transformations that do not duplicate storage:
- `stg_orders`: Standardizes timestamp fields, cleans order statuses, and filters invalid records.
- `stg_order_items`: Normalizes item sequence IDs, prices, and freight amounts.
- `stg_customers`: Deduplicates customer identities and normalizes Brazilian state codes.
- `stg_products`: Joins product dimension with English category name translations.
- `stg_order_payments`: Aggregates split tender payments by order.

#### B. Marts Layer (`marts` schema - Tables)
Aggregated dimensional models designed for fast analytical queries:
- `mart_daily_sales`: Daily grain table with sales date, order volume, items sold, gross revenue, freight charges, and average order value (AOV). Uses **incremental materialization** with a 3-day lookback window.
- `mart_top_products`: Product and category leaderboard with units sold, gross merchandise revenue, and dense ranks.
- `mart_customer_summary`: Customer lifetime summary (LTV, repeat buyer status, first/last purchase timestamps, city, and state).
- `mart_delivery_performance`: Monthly logistics fulfillment tracking actual delivery days against promised estimated delivery dates and late delivery rates.

#### C. Data Quality Assurance
- **45 Automated dbt Tests** run against the warehouse:
  - `unique` and `not_null` assertions on all primary keys and critical metrics.
  - Foreign key `relationships` tests verifying integrity across orders, customers, and items.
  - `accepted_values` checks on operational order statuses (`delivered`, `shipped`, `canceled`, etc.).
  - Range and domain validation on financial metrics (revenue and freight non-negative).

---

## 🛡️ Security & Guardrail Architecture

Allowing a language model to interact with a production warehouse introduces security risks, including prompt injection, SQL injection, denial-of-service, and unauthorized data exfiltration.

NexusBI implements a five-layer defense-in-depth model:

```mermaid
flowchart LR
    A["User Prompt"] --> B["Layer 1: Input Length & Rate Limit<br/>(Max 500 chars, 20/hr)"]
    B --> C["Layer 2: LLM Text-to-SQL + Semantic Layer<br/>(Deterministic system prompts)"]
    C --> D["Layer 3: sqlglot AST Security Guardrail<br/>(AST tree inspection & sanitization)"]
    D --> E["Layer 4: Database Role Enforcement<br/>(app_readonly user, search_path=marts)"]
    E --> F["Layer 5: Database Statement Timeout<br/>(statement_timeout = 10000ms)"]
    F --> G["Warehouse Query Execution"]
```

1. **Input Length & Rate Limiting**: Caps user prompts to 500 characters and enforces an hourly rate limit (default: 20 queries/hour/session).
2. **Abstract Syntax Tree (AST) Validation (`sqlglot`)**:
   - Parses incoming SQL into an AST before sending to the database.
   - Enforces single statement execution (strictly blocks `;` semicolon chaining).
   - Allows only `exp.Select` statements (blocks `DROP`, `ALTER`, `CREATE`, `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `GRANT`, `SELECT ... INTO`, and `FOR UPDATE`).
   - Restricts all physical table access to the 4 approved marts (`mart_daily_sales`, `mart_top_products`, `mart_customer_summary`, `mart_delivery_performance`).
   - Automatically injects `LIMIT 1000` to prevent memory exhaustion.
   - Blocks dangerous PostgreSQL functions (`pg_sleep`, `pg_read_file`, `dblink`, `lo_export`, `set_config`, and all `pg_*` catalogs).
3. **Database-Level Least Privilege**:
   - Web application connects exclusively via `app_readonly`.
   - `app_readonly` has `USAGE` only on the `marts` schema and `SELECT` only on the 4 marts tables.
   - Cannot read `raw` or `staging`, and has no write privileges anywhere.
4. **Server-Side Statement Timeout**:
   - `statement_timeout = 10000` (10 seconds) enforced directly on the PostgreSQL connection session. Any query taking longer than 10 seconds is killed by the database engine.

---

## 💡 Architectural Decisions & Trade-Offs

| Decision | Alternative Considered | Why Chosen |
| :--- | :--- | :--- |
| **ELT via dbt** | Traditional Python ETL script | Separates data loading from transformation. Enables version-controlled SQL models, automated testing, and lineage documentation directly inside the warehouse. |
| **sqlglot AST Parser** | Regex / Keyword Blacklisting | Regex string matching is easily bypassed by SQL comments (`/* */`), whitespace, subqueries, and casing tricks. AST parsing analyzes the actual syntax tree representation deterministically. |
| **Decoupled Serving Layer** | Ingestion pipeline running in cloud | Heavy data ingestion (Airbyte, Airflow, raw tables) runs locally on Docker for free. Only the lightweight curated marts (~10 MB) are served in the cloud, keeping cloud hosting costs at zero. |
| **Cloud LLM (Groq / Gemini)** | Local Ollama LLM | Local LLM execution requires 6-8 GB of host RAM, causing memory errors on developer laptops. Free cloud LLM APIs generate SQL in ~0.5 to 1.5 seconds with zero local RAM usage. |
