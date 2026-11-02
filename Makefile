# ==============================================================================
# Makefile - Antigravity DE Microproject Helper Commands
# Keep commands simple, self-documenting, and reproducible.
# ==============================================================================

.PHONY: help source-up source-down source-load warehouse-up warehouse-down warehouse-init warehouse-logs dbt-debug dbt-deps dbt-run dbt-test dbt-docs airflow-up airflow-down airflow-logs app-run test clean

help: ## Show this help message
	@echo "========================================================================"
	@echo "  End-to-End Data Pipeline with Conversational BI - Command Helper"
	@echo "========================================================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ------------------------------------------------------------------------------
# 1. Source (Postgres) Targets (Port 5433)
# ------------------------------------------------------------------------------
source-up: ## Start the local Olist Source Postgres container (port 5433)
	docker compose -f source/docker-compose.yml up -d

source-down: ## Stop the local Olist Source Postgres container
	docker compose -f source/docker-compose.yml down

source-load: ## Load Olist CSV datasets into local Source Postgres
	python source/load_olist.py

# ------------------------------------------------------------------------------
# 2. Warehouse (Postgres) Targets (Port 5434)
# ------------------------------------------------------------------------------
warehouse-up: ## Start the local Warehouse Postgres container (port 5434)
	docker compose -f warehouse/docker-compose.yml up -d

warehouse-down: ## Stop the local Warehouse Postgres container
	docker compose -f warehouse/docker-compose.yml down

warehouse-init: ## Execute schema and user provisioning scripts in warehouse
	docker exec -i olist-warehouse psql -U postgres -d warehouse < sql/01_schemas.sql
	docker exec -i olist-warehouse psql -U postgres -d warehouse < sql/02_users.sql

warehouse-logs: ## Follow Warehouse Postgres container logs
	docker compose -f warehouse/docker-compose.yml logs -f

# ------------------------------------------------------------------------------
# 3. dbt Targets (Run inside dbt/olist_dbt)
# ------------------------------------------------------------------------------
dbt-debug: ## Check dbt connection to local warehouse (port 5434)
	cd dbt/olist_dbt && dbt debug

dbt-deps: ## Install required dbt packages
	cd dbt/olist_dbt && dbt deps

dbt-run: ## Run dbt staging and marts models
	cd dbt/olist_dbt && dbt run

dbt-test: ## Run all dbt data tests (staging and marts)
	cd dbt/olist_dbt && dbt test

dbt-docs: ## Generate and serve dbt documentation & lineage graph
	cd dbt/olist_dbt && dbt docs generate && dbt docs serve --port 8080

# ------------------------------------------------------------------------------
# 4. Airflow Targets (Run from airflow/)
# ------------------------------------------------------------------------------
airflow-up: ## Start minimal Airflow stack (LocalExecutor, Webserver, Scheduler)
	docker compose -f airflow/docker-compose.yml up -d

airflow-down: ## Stop Airflow stack
	docker compose -f airflow/docker-compose.yml down

airflow-logs: ## Follow Airflow container logs
	docker compose -f airflow/docker-compose.yml logs -f

# ------------------------------------------------------------------------------
# 5. Streamlit App & Testing Targets
# ------------------------------------------------------------------------------
app-run: ## Launch the Streamlit Conversational BI chat application
	streamlit run app/streamlit_app.py

test: ## Run unit tests (including SQL safety validator tests)
	pytest -v

# ------------------------------------------------------------------------------
# 6. Maintenance Targets
# ------------------------------------------------------------------------------
clean: ## Clean up Python cache and temporary files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.py[cod]" -delete 2>/dev/null || true
	rm -rf .pytest_cache/ 2>/dev/null || true
