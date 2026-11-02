# ==============================================================================
# airflow/Dockerfile - Custom Airflow Image with Isolated dbt Virtualenv
#
# In a viva: Explain that dbt and Airflow have heavy, frequently conflicting
# Python dependency trees (e.g. differing versions of protobuf, jinja2, pyyaml).
# Installing dbt inside an isolated virtualenv (/opt/dbt-venv) guarantees that
# neither tool interferes with the other's stability or runtime libraries.
# ==============================================================================

FROM apache/airflow:2.9.3-python3.10

# Switch to root to create directory and virtual environment
USER root

# Install system dependencies (build-essential, git, libpq-dev)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create isolated virtualenv for dbt-redshift and assign ownership to airflow user
RUN python -m venv /opt/dbt-venv \
    && /opt/dbt-venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/dbt-venv/bin/pip install --no-cache-dir \
       dbt-core==1.8.2 \
       dbt-redshift==1.8.1 \
    && chown -R airflow:root /opt/dbt-venv \
    && chmod -R 775 /opt/dbt-venv

# Switch back to airflow user
USER airflow

# Copy and install Airflow-specific Python requirements
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
