# 📝 NexusBI Changelog

All notable changes to the NexusBI platform are documented here following [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and [Conventional Commits](https://www.conventionalcommits.org/).

---

## [1.0.0] - 2026-11-09 - Resume & Portfolio Upgrade

### Added
- **sqlglot AST Security Guardrail (`app/sql_validator.py`)**:
  - AST-level enforcement of single-statement invariants and read-only `exp.Select` statements.
  - Whitelist containment strictly to the 4 curated marts tables.
  - Blacklist blocking dangerous PostgreSQL functions (`pg_sleep`, `pg_read_file`, `pg_ls_dir`, `lo_export`, `dblink`, `set_config`, `current_setting`, and `pg_*` system catalogs).
  - Explicit blocking of `SELECT ... INTO` table creations and `FOR UPDATE` / `FOR SHARE` row locking.
  - Automatic `LIMIT 1000` clamping.
- **Unit Test Suite (`tests/test_sql_guardrail.py`)**:
  - 59 parameterized pytest test cases (22 `SHOULD_PASS` safe query scenarios, 36 `SHOULD_BLOCK` attack vectors).
- **Text-to-SQL Benchmark Harness (`benchmarks/`)**:
  - `benchmarks/questions.yaml`: 30 verified business questions across all 4 marts covering Easy (10), Medium (12), and Hard (8) difficulty tiers.
  - `benchmarks/run_benchmark.py`: Automated execution, AST guardrail validation, warehouse execution, and semantic DataFrame result comparison with float tolerance.
  - Support for `--mock` smoke-testing mode for offline CI runs.
  - Automated output generation to `benchmarks/results/latest.json` and `benchmarks/results/REPORT.md`.
- **Semantic Layer (`app/semantic_layer.yaml`)**:
  - Standardized business metric formulas (Gross Revenue, AOV, LTV, On-Time Delivery Rate %, Repeat Buyer Count).
  - High-value few-shot question-to-SQL examples injected dynamically into the system prompt to prevent column hallucinations.
- **Observability & Abuse Protection**:
  - Structured JSON-Lines query audit logging to `logs/queries.jsonl` with API key and credential sanitization (`app/audit_logger.py`).
  - Per-session hourly rate limiter (`RATE_LIMIT_PER_HOUR=20`) and max prompt length cap (`MAX_PROMPT_LENGTH=500`).
  - "Usage & Health" telemetry panel in right-side drawer and header popover.
- **Portability & Host-Independent Database**:
  - Generic environment variables (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE`) with fallback to `WAREHOUSE_*`.
  - dbt profiles targets: `dev`, `local`, `aws`, `neon`.
  - `scripts/export_marts.py`: Exports 4 marts tables to Parquet and CSV.
  - `scripts/load_marts_to_cloud.py`: Idempotent cloud schema creator, role provisioner, and data loader.
  - Self-contained `docker-compose.yml` and `Dockerfile` starting local Postgres warehouse and Streamlit app.
- **dbt Enhancements**:
  - Incremental materialization for `mart_daily_sales` with 3-day lookback window.
  - Source freshness block in `sources.yml`.
  - 4 additional schema and range tests in `_marts__models.yml` (total: 45 tests passing).
  - `scripts/build_dbt_docs.py`: Standalone single-file dbt documentation compiler for offline browsing and GitHub Pages.
- **CI/CD with GitHub Actions**:
  - `.github/workflows/ci.yml`: Automated Ruff linting, AST guardrail pytest suite, and benchmark smoke tests on push/PR.
  - `.github/workflows/dbt-docs.yml`: Automatic deployment of dbt documentation to GitHub Pages.
  - `.github/workflows/keepalive.yml`: Weekly scheduled keepalive ping for free cloud hosting tiers.
- **Comprehensive Engineering Documentation**:
  - `docs/ARCHITECTURE.md`: Detailed component breakdown with Mermaid diagrams and design trade-offs.
  - `docs/DECISIONS.md`: 6 Architecture Decision Records (ADRs).
  - `docs/SECURITY.md`: 5-layer threat defense model and test verification.
  - `docs/DEPLOYMENT.md`: Step-by-step Neon, Streamlit Cloud, and safe AWS RDS teardown guides.
  - `docs/RESUME_BULLETS.md`: 3 resume bullet points and 10 technical viva interview Q&A.
  - `LICENSE`: MIT License.

### Changed
- Refactored `README.md` to present verified, honest metrics (100k orders, 94,989 customers, 614 sales days, 45 dbt tests, 59 guardrail tests, 83.3% strict / 87.8% lenient mean benchmark score, 10/10 sanity check score) as a 3rd-year computer engineering student portfolio project.
- Implemented dual evaluation policy (ADR-007) reporting both strict (1:1 column match) and lenient (value match permitting auxiliary helper columns) metrics. Evaluated against 3 live runs at temperature 0.0: strict mean accuracy reached 83.3% (min: 83.3%, max: 83.3%) and lenient mean accuracy reached 87.8% (min: 86.7%, max: 90.0%), progressing from the initial 73.3% strict v1 baseline.
- Corrected `q07` ground truth after cross-verifying delivery lead times against 96,470 order-level rows in `staging.stg_orders`, confirming that the true mean delivery duration is 12.50 days (matching the volume-weighted formula) rather than the naive unweighted mean of monthly averages (14.31 days).
- Added a 10-question held-out evaluation set (`benchmarks/heldout.yaml`) as an un-tuned sanity check alongside the project, scoring 100.0% (10/10).
- Documented model limitations in `README.md` (CTE scalar division syntax errors in `q23`, auxiliary column projection variance in `q22`, and rolling-window framing challenges).
- Resolved pandas DBAPI2 `UserWarning` in `app/db_helper.py` by building DataFrames directly from cursor records and type-casting numeric decimals.
- Removed inflated buzzwords ("enterprise-grade", "autonomous", "sub-second") across all codebase files.
- Consolidated linter and test configuration into `pyproject.toml`.

