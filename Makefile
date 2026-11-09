# ==============================================================================
# Makefile - NexusBI Helper Commands
# Simple, reproducible workflow targets for development, testing, and CI
# ==============================================================================

.PHONY: help test lint dbt-test dbt-run dbt-docs benchmark benchmark-mock app verify-migration clean

help: ## Show this help message
	@echo "========================================================================"
	@echo "  NexusBI: Conversational BI & Data Pipeline Helper"
	@echo "========================================================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

test: ## Run unit tests with pytest
	pytest -v tests/

lint: ## Run linter with ruff
	python -m ruff check .

dbt-test: ## Run all dbt data quality tests
	python -m dbt.cli.main test --project-dir dbt/olist_dbt --profiles-dir dbt/olist_dbt

dbt-run: ## Run all dbt models (staging views + marts tables)
	python -m dbt.cli.main run --project-dir dbt/olist_dbt --profiles-dir dbt/olist_dbt

dbt-docs: ## Generate and serve dbt documentation locally
	python -m dbt.cli.main docs generate --project-dir dbt/olist_dbt --profiles-dir dbt/olist_dbt
	python -m dbt.cli.main docs serve --project-dir dbt/olist_dbt --profiles-dir dbt/olist_dbt --port 8080

benchmark: ## Run Text-to-SQL accuracy benchmark against active LLM
	python benchmarks/run_benchmark.py

benchmark-mock: ## Run Text-to-SQL benchmark in mock mode (no API key needed)
	python benchmarks/run_benchmark.py --mock

app: ## Launch Streamlit Conversational BI interface
	streamlit run app/streamlit_app.py

verify-migration: ## Verify Neon vs AWS RDS data mart equivalence before teardown
	python scripts/verify_migration.py --report docs/MIGRATION_VERIFICATION.md

clean: ## Clean up temporary Python cache and dbt artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.py[cod]" -delete 2>/dev/null || true
	rm -rf .pytest_cache/ 2>/dev/null || true
