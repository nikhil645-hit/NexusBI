"""
# ==============================================================================
# olist_daily_pipeline.py - Master Airflow Orchestration DAG
#
# Schedule: Daily (@daily, 02:00 UTC)
# Catchup: False
#
# Pipeline Flow:
#   1. trigger_airbyte_sync:
#      Authenticates with Airbyte REST API via Client ID & Secret, triggers
#      sync for Olist Source Postgres -> Warehouse Postgres, and polls until completion.
#   2. dbt_run_staging:
#      Executes dbt staging views in warehouse using isolated /opt/dbt-venv.
#   3. dbt_run_marts:
#      Executes dbt analytical mart tables in warehouse using /opt/dbt-venv.
#   4. dbt_test:
#      Executes all schema tests and custom non-negative singular assertions.
#   5. pipeline_summary:
#      Logs final execution report, timestamps, and row quality affirmations.
# ==============================================================================
"""

import logging
import os
import time
from datetime import datetime, timedelta

import requests
from airflow.exceptions import AirflowFailException
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

from airflow import DAG

logger = logging.getLogger(__name__)

# Default arguments applied to all tasks
default_args = {
    "owner": "data_engineering",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
}

# ------------------------------------------------------------------------------
# Task 1: Airbyte API Trigger & Polling Helper
# ------------------------------------------------------------------------------
def trigger_and_wait_airbyte_sync(**context):
    """
    Triggers an Airbyte sync job via REST API, polls for completion,
    and fails clearly if credentials are missing or the sync encounters an error.
    """
    api_url = os.getenv("AIRBYTE_API_URL", "http://host.docker.internal:8000/api/v1").rstrip("/")
    client_id = os.getenv("AIRBYTE_CLIENT_ID")
    client_secret = os.getenv("AIRBYTE_CLIENT_SECRET")
    connection_id = os.getenv("AIRBYTE_CONNECTION_ID")

    # Fail gracefully with actionable advice if env vars are missing
    if not connection_id or "placeholder" in connection_id or "your_" in connection_id:
        raise AirflowFailException(
            "\n[CONFIG ERROR] AIRBYTE_CONNECTION_ID is not configured in airflow/.env.\n"
            "Please open Airbyte UI (http://localhost:8000), copy your Connection UUID from "
            "the URL, and set AIRBYTE_CONNECTION_ID in airflow/.env."
        )

    logger.info(f"Connecting to Airbyte at: {api_url}")
    logger.info(f"Target Connection ID: {connection_id}")

    # Prepare authentication headers
    headers = {"Content-Type": "application/json"}

    # Authenticate via OAuth application token if Client ID/Secret are provided
    if client_id and client_secret and "your_" not in client_id:
        logger.info("Authenticating with Airbyte Applications API...")
        token_endpoint = f"{api_url}/applications/token"
        try:
            token_resp = requests.post(
                token_endpoint,
                json={"client_id": client_id, "client_secret": client_secret},
                timeout=15,
            )
            if token_resp.status_code == 200:
                access_token = token_resp.json().get("access_token")
                headers["Authorization"] = f"Bearer {access_token}"
                logger.info("Successfully authenticated with Airbyte token.")
            else:
                logger.warning(
                    f"Token auth returned {token_resp.status_code}: {token_resp.text}. "
                    "Attempting direct connection sync without bearer token..."
                )
        except Exception as e:
            logger.warning(f"Could not reach token endpoint: {e}. Proceeding with standard call...")

    # Trigger the sync job
    # Airbyte v1 API uses /connections/sync or /jobs
    trigger_endpoint = f"{api_url}/connections/sync"
    payload = {"connectionId": connection_id}

    logger.info(f"Triggering sync request to: {trigger_endpoint}")
    try:
        response = requests.post(trigger_endpoint, json=payload, headers=headers, timeout=30)
    except Exception as e:
        raise AirflowFailException(
            f"Failed to reach Airbyte API at {trigger_endpoint}. "
            f"Verify Airbyte container is running on the host and accessible. Error: {e}"
        )

    if response.status_code not in (200, 202):
        raise AirflowFailException(
            f"Airbyte sync trigger failed [HTTP {response.status_code}]: {response.text}"
        )

    sync_data = response.json()
    job_id = sync_data.get("job", {}).get("id") or sync_data.get("jobId")
    logger.info(f"Airbyte sync job initiated successfully! Job ID: {job_id}")

    if not job_id:
        logger.info("No polling Job ID returned; connection triggered synchronously.")
        return "Airbyte sync triggered."

    # Poll until job completion
    job_status_endpoint = f"{api_url}/jobs/get"
    timeout_seconds = 1800  # 30 minutes max wait time
    poll_interval = 10
    start_time = time.time()

    while True:
        if time.time() - start_time > timeout_seconds:
            raise AirflowFailException(f"Timed out waiting for Airbyte job {job_id} to finish.")

        try:
            job_resp = requests.post(job_status_endpoint, json={"id": job_id}, headers=headers, timeout=15)
            if job_resp.status_code == 200:
                job_info = job_resp.json().get("job", {})
                status = job_info.get("status", "").lower()
                logger.info(f"Airbyte Job {job_id} current status: {status}")

                if status in ("succeeded", "success"):
                    logger.info("Airbyte sync job completed with SUCCESS!")
                    return f"Job {job_id} succeeded"
                elif status in ("failed", "cancelled", "error"):
                    raise AirflowFailException(
                        f"Airbyte sync job {job_id} failed with status: {status}. Full info: {job_info}"
                    )
            else:
                logger.warning(f"Failed to poll job status: HTTP {job_resp.status_code}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Transient polling error: {e}")

        time.sleep(poll_interval)


# ------------------------------------------------------------------------------
# Task 5: Pipeline Success Summary Logger
# ------------------------------------------------------------------------------
def log_pipeline_summary(**context):
    """
    Logs a high-level summary of the completed daily pipeline run.
    """
    exec_date = context.get("ds", str(datetime.utcnow().date()))
    summary = f"""
    ========================================================================
    🎉 OLIST DAILY PIPELINE EXECUTION SUCCESS
    ========================================================================
    Execution Date: {exec_date}
    Orchestrator  : Apache Airflow (LocalExecutor)
    Layers Updated:
      1. Source Ingestion  : Source Postgres (5433) -> Warehouse 'raw' (5434) (Airbyte OSS)
      2. Staging Models    : Warehouse 'staging' views (dbt-postgres)
      3. Analytical Marts  : Warehouse 'marts' tables (dbt-postgres)
      4. Quality Assurance : Schema & Business rule assertions PASSED (0 failures)
    Status: All downstream tables ready for Streamlit Conversational BI querying.
    ========================================================================
    """
    logger.info(summary)
    print(summary)
    return "Pipeline completed successfully."


# ------------------------------------------------------------------------------
# DAG Definition
# ------------------------------------------------------------------------------
with DAG(
    dag_id="olist_daily_pipeline",
    default_args=default_args,
    description="Daily ingestion, transformation, and testing pipeline for Olist E-Commerce",
    schedule_interval="0 2 * * *",  # Daily at 02:00 AM UTC
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["olist", "dbt", "airbyte", "redshift", "microproject"],
    doc_md=__doc__,
) as dag:

    # Task 1: Airbyte Sync Trigger & Polling
    task_airbyte_sync = PythonOperator(
        task_id="trigger_airbyte_sync",
        python_callable=trigger_and_wait_airbyte_sync,
        doc_md="""
        ### Trigger Airbyte Sync
        Calls the Airbyte REST API to start full-refresh replication from Postgres into
        Redshift `raw` schema. Polls the job status until completion.
        """,
    )

    # Base command for dbt running in isolated virtual environment
    dbt_base_cmd = (
        "/opt/dbt-venv/bin/dbt "
        "--project-dir /opt/airflow/dbt/olist_dbt "
        "--profiles-dir /opt/airflow/dbt/olist_dbt "
    )

    # Task 2: dbt run staging models
    task_dbt_staging = BashOperator(
        task_id="dbt_run_staging",
        bash_command=f"{dbt_base_cmd} run --select staging",
        doc_md="""
        ### dbt Run Staging
        Compiles and builds all cleansed views in Redshift `staging` schema.
        """,
    )

    # Task 3: dbt run marts models
    task_dbt_marts = BashOperator(
        task_id="dbt_run_marts",
        bash_command=f"{dbt_base_cmd} run --select marts",
        doc_md="""
        ### dbt Run Marts
        Materializes physical analytical tables in Redshift `marts` schema.
        """,
    )

    # Task 4: dbt test
    task_dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"{dbt_base_cmd} test",
        doc_md="""
        ### dbt Test
        Executes schema validations (unique, not_null, accepted_values, relationships)
        and custom singular non-negative revenue assertions.
        """,
    )

    # Task 5: Success Summary Logger
    task_summary = PythonOperator(
        task_id="log_pipeline_summary",
        python_callable=log_pipeline_summary,
        doc_md="""
        ### Pipeline Summary
        Emits executive success report acknowledging that all mart tables
        are fresh and ready for the Streamlit Conversational BI interface.
        """,
    )

    # Execution Graph / Lineage
    task_airbyte_sync >> task_dbt_staging >> task_dbt_marts >> task_dbt_test >> task_summary

