# NexusBI Upgrade Plan: Portfolio & Resume Hardening

This document outlines the step-by-step implementation plan to polish **NexusBI** into a clean, honest, and resume-ready portfolio project built by a 3rd-year computer engineering student.

The upgrade focuses on adding tangible engineering proof (AST guardrail test suite, Text-to-SQL benchmark harness, semantic layer, observability, CI/CD, and concise documentation) while strictly avoiding buzzwords.

---

## File Modification & Creation Inventory

### Phase 1: Repo Structure & Cleanup
- **Create/Modify**:
  - `requirements.txt`: Root requirements file pinning runtime dependencies.
  - `requirements-dev.txt`: Development dependencies (`pytest`, `ruff`, `pyyaml`).
  - `Makefile`: Commands for `test`, `lint`, `dbt-test`, `benchmark`, `app`.
  - `.env.example`: Complete environment variable template with all DB and LLM variables.
  - `.gitignore`: Confirm coverage of `.env`, `secrets.toml`, `*.pem`, `target/`, `logs/`.
  - `README.md`, `app/streamlit_app.py`: Remove inflated buzzwords.

### Phase 2: Guardrail Hardening & Unit Tests
- **Create/Modify**:
  - `app/sql_validator.py`: Extend AST parser to block dangerous functions (`pg_sleep`, `pg_read_file`, `pg_ls_dir`, `lo_import`, `lo_export`, `dblink`, `copy`, `set_config`, `current_setting`, any `pg_*` or `information_schema`), comment-based multi-statement tricks, schema casing/quoted identifier bypasses, `SELECT ... INTO`, and `FOR UPDATE`.
  - `app/db_helper.py`: Add database-side connection `statement_timeout` (10s) and enforce LIMIT <= 1000.
  - `tests/test_sql_guardrail.py`: Pytest suite with 40+ parameterized test cases split into `SHOULD_PASS` and `SHOULD_BLOCK`.

### Phase 3: Text-to-SQL Accuracy Benchmark
- **Create**:
  - `benchmarks/questions.yaml`: 30 realistic analytical questions across the 4 marts (categorized by difficulty: easy, medium, hard) with gold-standard SQL.
  - `benchmarks/run_benchmark.py`: Execution harness testing generation, guardrail validation, execution against warehouse, and semantic result-set matching, with `--mock` flag and rate-limiting backoff.
  - `benchmarks/results/latest.json` & `benchmarks/results/REPORT.md`: Benchmark output artifacts.

### Phase 4: Semantic Layer
- **Create/Modify**:
  - `app/semantic_layer.yaml`: Metric definitions, column descriptions, and few-shot examples for the 4 marts (`mart_daily_sales`, `mart_top_products`, `mart_customer_summary`, `mart_delivery_performance`).
  - `app/llm_helper.py`: Ingest semantic definitions into the SQL generation system prompt.

### Phase 5: Observability & Abuse Protection
- **Create/Modify**:
  - `app/streamlit_app.py`:
    - Structured JSONL logging to `logs/queries.jsonl` (no secrets logged).
    - Per-session rate limiter (default 20 requests/hour, env-configurable).
    - Prompt length validation (max 500 chars) and friendly error handling.
    - "Usage / Health" panel in the right-side drawer.

### Phase 6: Host-Independent Database & Portability
- **Create/Modify**:
  - `app/db_helper.py`: Support generic `DB_*` variables with fallback to `WAREHOUSE_*`.
  - `dbt/olist_dbt/profiles.yml`: Configure env-driven profiles (`dev`, `local`, `aws`, `neon`) with `sslmode=require` support.
  - `scripts/export_marts.py`: Export only the 4 marts tables to CSV/SQL.
  - `scripts/load_marts_to_cloud.py`: Idempotently load the 4 marts tables into target Postgres (e.g., Neon) with `app_readonly` user creation.
  - `docker-compose.yml`: Root compose file allowing full local replication of warehouse + app.

### Phase 7: dbt Improvements
- **Modify**:
  - `dbt/olist_dbt/models/marts/mart_daily_sales.sql`: Add incremental materialization with `is_incremental()`.
  - `dbt/olist_dbt/models/staging/_staging__sources.yml`: Add source freshness config and dataset note.
  - `dbt/olist_dbt/models/marts/_marts__models.yml`: Add extra column constraints and range tests.
  - `scripts/build_dbt_docs.py`: Helper script to compile dbt documentation.

### Phase 8: CI/CD with GitHub Actions
- **Create**:
  - `.github/workflows/ci.yml`: GitHub Actions workflow running linting (`ruff`), unit tests (`pytest`), and benchmark smoke test (`--mock`).
  - `.github/workflows/dbt-docs.yml`: GitHub Pages deployment workflow for dbt docs.
  - `.github/workflows/keepalive.yml`: Scheduled workflow pinging free-tier database endpoint.

### Phase 9: Documentation
- **Create/Modify**:
  - `README.md`: Structured, honest overview with real numbers and clear instructions.
  - `docs/ARCHITECTURE.md`: Architecture diagrams and plain-English explanation.
  - `docs/DECISIONS.md`: Architecture Decision Records (ADRs) explaining technical choices and trade-offs.
  - `docs/SECURITY.md`: Threat model and defense controls.
  - `docs/DEPLOYMENT.md`: Step-by-step instructions for Neon, Streamlit Cloud, GitHub Secrets, and AWS RDS teardown.
  - `docs/RESUME_BULLETS.md`: 3 honest resume bullets and 10 technical interview Q&A.
  - `LICENSE`: MIT License.

### Phase 10: Final Verification
- Run full test suite (`ruff`, `pytest`, `dbt test`, `benchmark --mock`, headless Streamlit check).
- Create `docs/CHANGELOG.md`.
- Generate final completion summary.

