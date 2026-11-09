# ⚡ NexusBI: Conversational Business Intelligence & Modern Data Pipeline

[![CI Test Suite](https://github.com/nexusbi/nexusbi/actions/workflows/ci.yml/badge.svg)](https://github.com/nexusbi/nexusbi/actions/workflows/ci.yml)
[![dbt Tests](https://img.shields.io/badge/dbt%20tests-45%20passed-brightgreen.svg)](dbt/olist_dbt/models/marts/_marts__models.yml)
[![AST Guardrail Tests](https://img.shields.io/badge/AST%20Guardrail-59%20passed-blue.svg)](tests/test_sql_guardrail.py)
[![Benchmark Accuracy](https://img.shields.io/badge/Benchmark%20Accuracy-83.3%25%20strict%20%7C%2087.8%25%20lenient-success.svg)](benchmarks/results/REPORT.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

NexusBI is a modern data engineering pipeline and conversational business intelligence application built by a 3rd-year computer engineering student. It translates natural language questions into verified, read-only SQL queries over **100,000 real-world e-commerce transactions** (the Brazilian Olist dataset) using a deterministic **Abstract Syntax Tree (AST) security guardrail**.

---

## 📊 Grounded Numbers & Verified Facts

All figures below are generated directly by our test suites, dbt assertions, and database queries:

| Metric | Measured Value | Verification Source |
| :--- | :--- | :--- |
| **Raw Transactional Records** | ~100,000 orders across 9 relational tables | PostgreSQL 16 source database (`olist-postgres:5433`) |
| **Unique Customer Entities** | **94,989** distinct buyers across Brazilian states | `marts.mart_customer_summary` |
| **Daily Sales Data Points** | **614** calendar days of revenue and orders | `marts.mart_daily_sales` |
| **Product Leaderboard Items** | **32,735** unique SKUs ranked by revenue and units | `marts.mart_top_products` |
| **Monthly Logistics SLA Points** | **23** months tracking delivery lead times and delays | `marts.mart_delivery_performance` |
| **Automated dbt Data Tests** | **45 passed** (0 errors, 0 warnings) | `dbt test` against warehouse |
| **AST Guardrail Unit Tests** | **59 passed** (22 allowed, 36 blocked vectors) | `pytest -v tests/test_sql_guardrail.py` |
| **Text-to-SQL Benchmark Score** | **83.3% strict** / **87.8% lenient** mean over 3 live runs (v1 baseline: 73.3%); 10/10 on sanity check set | `benchmarks/run_benchmark.py --runs 3` |
| **LLM Generation Latency** | ~0.5 to 1.5 seconds per query | Cloud Groq API (`openai/gpt-oss-120b`) |

---

## 🏗️ System Architecture

```text
[Source OLTP: Postgres 16 (Port 5433)]
         │
         ▼ (Airbyte OSS: Full Refresh Overwrite)
[Warehouse: Postgres 16 / AWS RDS / Neon (raw schema)]
         │
         ▼ (dbt Core: Cleansed Views)
[Staging Schema: stg_orders, stg_customers, stg_order_items, stg_products]
         │
         ▼ (dbt Core: Materialized Tables + Incremental Model)
[Marts Schema: 4 Curated Analytics Marts + 45 Automated Tests]
         │
         ├─────────────────────────────────────────┐
         ▼                                         ▼
[Streamlit Conversational Web App]        [Apache Airflow DAG]
  ├─ User Prompt (max 500 chars)            └─ Daily scheduled ELT sync:
  ├─ Semantic Layer Metric Injection             1. Source DB Ping
  ├─ Cloud LLM (Groq / Gemini)                   2. Trigger Airbyte Sync
  ├─ sqlglot AST Security Guardrail              3. dbt Staging Views
  ├─ app_readonly Role (SELECT only)             4. dbt Incremental Marts
  └─ Dynamic Chart & Studio Generation           5. 45 dbt Integrity Tests
```

---

## ⚡ Quickstart: 100% Free Local Setup (Docker Compose)

Anyone reviewing this repository can start the complete data warehouse and application locally with **zero external cloud setup** or credit card requirement:

```bash
# 1. Clone repository
git clone https://github.com/nexusbi/nexusbi.git
cd nexusbi

# 2. Copy environment template
cp .env.example .env

# 3. Start local Postgres warehouse and Streamlit app
docker compose up -d

# 4. Open in your browser
# Web Interface: http://localhost:8501
```

The Docker Compose service automatically:
- Starts a PostgreSQL 16 warehouse on port `5434`.
- Initializes the `marts` schema with sample data across all 4 tables.
- Creates the `app_readonly` role with restricted permissions.
- Launches the Streamlit app with mock fallback LLM adapter.

---

## ☁️ Cloud Setup (Neon / AWS RDS + Streamlit Cloud)

NexusBI supports a hybrid decoupled architecture: heavy ingestion runs locally on Docker for free, and curated data marts (~10 MB) are served in the cloud.

```bash
# 1. Export analytical marts from local warehouse to Parquet / CSV
python scripts/export_marts.py --format both

# 2. Provision cloud database (Neon serverless Postgres or AWS RDS)
python scripts/load_marts_to_cloud.py \
  --host "your-neon-or-rds-host.tech" \
  --port 5432 \
  --dbname "neondb" \
  --user "admin_user" \
  --password "admin_password" \
  --sslmode "require" \
  --readonly-password "app_readonly_password" \
  --confirm

# 3. Set environment variables in .env or Streamlit Cloud Settings
DB_HOST=your-neon-or-rds-host.tech
DB_PORT=5432
DB_NAME=neondb
DB_USER=app_readonly
DB_PASSWORD=app_readonly_password
DB_SSLMODE=require

LLM_PROVIDER=groq
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-120b
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for step-by-step Neon, Streamlit Cloud, and safe AWS RDS teardown instructions.

### 🔄 Migration Verification Before RDS Decommissioning

Before decommissioning the AWS RDS instance, run the read-only migration verification script to verify that the 4 analytical marts in Neon match AWS RDS across schema, counts, numeric checksums, date bounds, and MD5 table fingerprints:

```bash
# Run full read-only equivalence check and output report
python scripts/verify_migration.py --report docs/MIGRATION_VERIFICATION.md
# Or via Makefile:
make verify-migration
```

This verification:
- Connects in strict read-only mode (`SET default_transaction_read_only = on`) with `sslmode=require` and a 30s timeout.
- Compares row counts across all 4 marts (614, 32,735, 94,989, 23 rows).
- Verifies column ordinal positions and PostgreSQL data type compatibility (`varchar`/`text`, `numeric`/`double precision`).
- Validates numeric metric sums and null counts.
- Computes whole-table and 20-tile chunked MD5 content fingerprints across all 128,361 rows.
- Checks cell-by-cell parity across a deterministic seeded sample of 50 rows per table.
- Audits the Neon `app_readonly` user permissions (confirming `SELECT` is granted and all write/alter/drop/catalog access is denied).

See the full verification audit in [docs/MIGRATION_VERIFICATION.md](docs/MIGRATION_VERIFICATION.md).

---

## 🛡️ Security Invariants & AST Guardrail

Natural language prompts are inherently untrusted. NexusBI enforces a 5-layer defense-in-depth model:

1. **Input Length & Rate Limiting**: Rejects queries over 500 characters and enforces an hourly rate limit (default: 20 requests/hour/session).
2. **Abstract Syntax Tree (AST) Validation (`sqlglot`)**:
   - Parses raw generated SQL into an AST.
   - Enforces single statement execution (rejects semicolon chaining `;`).
   - Verifies root node is `exp.Select` (blocks `DROP`, `ALTER`, `CREATE`, `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `GRANT`, `REVOKE`, `SELECT ... INTO`, and `FOR UPDATE`).
   - Whitelists physical tables strictly to the 4 marts (`mart_daily_sales`, `mart_top_products`, `mart_customer_summary`, `mart_delivery_performance`).
   - Automatically injects or clamps `LIMIT 1000`.
   - Blocks dangerous PostgreSQL functions (`pg_sleep`, `pg_read_file`, `dblink`, `lo_export`, `set_config`, and all `pg_*` catalogs).
3. **Database Least Privilege**: Application user `app_readonly` has `SELECT` only on schema `marts`. Cannot access `raw` or `staging`.
4. **Statement Timeout**: Server-side timeout enforced on connections (`statement_timeout = 10000;`).
5. **Audit Logging**: Query audit records written to `logs/queries.jsonl` with API keys and passwords sanitized.

Verified with 59 test cases:
```bash
pytest -v tests/test_sql_guardrail.py
```

---

## 🎯 Text-to-SQL Accuracy Benchmark

To evaluate translation accuracy without relying on qualitative impressions, NexusBI includes a quantitative benchmark harness (`benchmarks/run_benchmark.py`) covering 30 ground truth questions across all 4 data marts:

```bash
# Run benchmark in mock/smoke-test mode (CI friendly, no API key required)
make benchmark-mock

# Run live benchmark with cloud LLM
make benchmark
```

### Benchmark Results (30 Questions, Evaluated Over 3 Live Runs at Temperature 0.0):
- **Strict Mean Accuracy**: **`83.3%`** (25/30 passed consistently across all 3 runs; initial strict baseline was `73.3%` / 22/30)
- **Lenient Mean Accuracy**: **`87.8%`** (26 to 27 passed; permits harmless extra helper columns when all expected metrics and rows match)
- **Strict Flipping Questions**: 2 questions flipped across runs (`q14`, `q23`), with 28/30 questions completely deterministic.
- **q07 Correction**: Verified against 96,470 order-level transactions in `staging.stg_orders` where true mean delivery days is 12.50 days. Ground truth was updated from the naive unweighted monthly mean (14.31) to the true volume-weighted mean (12.50).
- **Held-Out Evaluation Set**: **`100.0%`** (10/10 passed on `heldout.yaml`). Note: This is a small 10-question sanity check written alongside the project, not an independent test, and is reported separately from the headline benchmark accuracy.

See the multi-run report in [benchmarks/results/REPORT.md](benchmarks/results/REPORT.md), multi-run JSON in [benchmarks/results/multi_run.json](benchmarks/results/multi_run.json), held-out report in [benchmarks/results/heldout_REPORT.md](benchmarks/results/heldout_REPORT.md), and v1 baseline in [benchmarks/results/v1_REPORT.md](benchmarks/results/v1_REPORT.md).

---

## ⚠️ Known Limitations

1. **CTE Scalar Division in Complex Ratios**: The model sometimes mixes a scalar aggregate with a CTE column in the same `SELECT` statement without proper `GROUP BY` grouping, which PostgreSQL rejects with an execution error (observed in `q23`).
2. **Auxiliary Column Projection**: The model occasionally includes intermediate calculation columns (such as component totals alongside ratios in `q22`), which causes strict shape mismatches while passing lenient value verification.
3. **Rolling-Window Calculations**: Multi-step window functions over date intervals (such as 7-day rolling revenue in `q28`) require careful framing to ensure the model filters after window computation rather than before.

---

## 📁 Repository Structure

```text
nexusbi/
├── .github/workflows/          # CI/CD (Ruff, Pytest, Benchmark, dbt Docs, Keepalive)
├── airflow/dags/               # Apache Airflow orchestration DAGs
├── app/                        # Streamlit web application & core logic
│   ├── streamlit_app.py        # Conversational BI main app & Dashboard Studio
│   ├── sql_validator.py        # sqlglot AST security guardrail
│   ├── llm_helper.py           # Unified LLM provider adapter (Groq, Gemini, Mock)
│   ├── semantic_layer.yaml     # Canonical metric formulas & few-shot examples
│   ├── audit_logger.py         # Structured JSON-lines query audit logging
│   └── dashboard_renderer.py   # Multi-chart analytics dashboard layouts
├── benchmarks/                 # Text-to-SQL evaluation harness
│   ├── questions.yaml          # 30 business questions with verified ground-truth SQL
│   ├── run_benchmark.py        # Automated test execution & semantic comparison
│   └── results/                # latest.json and REPORT.md artifacts
├── data/marts_export/          # Exported Parquet & CSV analytical data marts
├── dbt/olist_dbt/              # dbt Core transformation project (Postgres)
│   ├── models/staging/         # Staging views (stg_orders, stg_customers, etc.)
│   ├── models/marts/           # Analytics tables (sales, products, delivery)
│   └── profiles.yml            # Host-independent profile (dev, local, aws, neon)
├── docs/                       # Comprehensive engineering documentation
│   ├── ARCHITECTURE.md         # System design, data flow, and Mermaid diagrams
│   ├── DECISIONS.md            # Architecture Decision Records (ADRs)
│   ├── SECURITY.md             # Threat model, AST defense layers, test suite
│   ├── DEPLOYMENT.md           # Neon, Streamlit Cloud, and RDS teardown guides
│   ├── RESUME_BULLETS.md       # 3 resume bullets and 10 viva interview Q&A
│   └── UPGRADE_PLAN.md         # Milestone upgrade plan and tracking
├── scripts/                    # Automation utilities
│   ├── export_marts.py         # Exports 4 marts tables to Parquet & CSV
│   ├── load_marts_to_cloud.py  # Idempotent cloud schema & data provisioner
│   ├── build_dbt_docs.py       # Compiles standalone offline dbt docs bundle
│   └── init_local_warehouse.sql# Local Docker warehouse seeding script
├── tests/                      # Automated test suites
│   └── test_sql_guardrail.py   # 59 parameterized security guardrail unit tests
├── docker-compose.yml          # Self-contained local Postgres + App deployment
├── Dockerfile                  # Application container image definition
├── Makefile                    # Standard targets: test, lint, dbt-test, benchmark
├── requirements.txt            # Pinned runtime dependencies
├── requirements-dev.txt        # Pinned development & testing dependencies
├── pyproject.toml              # Ruff linter & Pytest configurations
└── LICENSE                     # MIT License
```

---

## 🛠️ Makefile Command Reference

```bash
make help            # Display list of available targets
make test            # Run pytest guardrail test suite (59 tests)
make lint            # Run ruff linter check
make benchmark-mock  # Run Text-to-SQL benchmark smoke test (CI mode)
make benchmark       # Run live Text-to-SQL benchmark against cloud LLM
make dbt-test        # Run all 45 dbt data quality assertions
make dbt-docs        # Compile standalone dbt docs bundle
make app             # Launch Streamlit web interface locally
make verify-migration# Run read-only Neon vs RDS equivalence verification
```

---

## 📜 Documentation Index

- [Architecture & System Flow](docs/ARCHITECTURE.md)
- [Architecture Decision Records (ADRs)](docs/DECISIONS.md)
- [Security Threat Model & AST Defense](docs/SECURITY.md)
- [Deployment, Neon & AWS Teardown Guide](docs/DEPLOYMENT.md)
- [Migration Equivalence Verification Report](docs/MIGRATION_VERIFICATION.md)
- [Resume Bullets & Viva Defense Q&A](docs/RESUME_BULLETS.md)
- [Text-to-SQL Benchmark Report](benchmarks/results/REPORT.md)

---

## ⚖️ License & Author

- **Author**: 3rd-Year Computer Engineering Student
- **Dataset**: [Olist Brazilian E-Commerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (Public Domain / CC BY-NC-SA 4.0)
- **License**: [MIT License](LICENSE)
