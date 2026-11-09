# 🚀 NexusBI Deployment & Cloud Hosting Guide

This guide provides step-by-step instructions to deploy NexusBI for free or on AWS, configure GitHub Actions secrets, publish dbt documentation to GitHub Pages, and safely tear down AWS RDS to avoid unexpected cloud charges.

---

## 📋 Table of Contents
1. [Option A: 100% Free Cloud Deployment (Neon + Streamlit Cloud)](#option-a-100-free-cloud-deployment-neon--streamlit-cloud)
2. [Option B: AWS RDS PostgreSQL Deployment](#option-b-aws-rds-postgresql-deployment)
3. [Safe AWS RDS Teardown (Avoid Cloud Charges)](#safe-aws-rds-teardown-avoid-cloud-charges)
4. [Setting up dbt Documentation on GitHub Pages](#setting-up-dbt-documentation-on-github-pages)
5. [Configuring GitHub Actions Secrets](#configuring-github-actions-secrets)

---

## Option A: 100% Free Cloud Deployment (Neon + Streamlit Cloud)

This configuration hosts the serving layer on **Neon** (serverless PostgreSQL with a generous free tier) and the frontend on **Streamlit Community Cloud** (free public app hosting).

### Step 1: Create a Free Neon Database
1. Go to [Neon.tech](https://neon.tech/) and sign up or log in.
2. Click **Create Project** -> Name it `nexusbi-warehouse`.
3. Choose the region closest to you (e.g., `us-east-1` or `eu-central-1`).
4. Note your database credentials from the Neon dashboard:
   - Host: `ep-xxxxxx.region.aws.neon.tech`
   - Database: `neondb`
   - User: `neondb_owner` (or your admin user)
   - Password: `[YOUR_NEON_PASSWORD]`

### Step 2: Export Local Marts & Provision Neon
On your local machine, run the export and cloud loader:

```bash
# 1. Export the 4 curated marts tables from your current warehouse
python scripts/export_marts.py --format both

# 2. Provision schema and load data to your Neon database
python scripts/load_marts_to_cloud.py \
  --host "ep-xxxxxx.region.aws.neon.tech" \
  --port 5432 \
  --dbname "neondb" \
  --user "neondb_owner" \
  --password "YOUR_NEON_PASSWORD" \
  --sslmode "require" \
  --readonly-password "a_strong_password_for_app_readonly" \
  --confirm
```

This command automatically:
- Creates schema `marts`.
- Creates role `app_readonly` with SELECT permissions.
- Copies the 4 tables (`mart_daily_sales`, `mart_top_products`, `mart_customer_summary`, `mart_delivery_performance`).

### Step 3: Deploy Frontend to Streamlit Community Cloud
1. Push your repository to your GitHub account (`main` branch).
2. Go to [share.streamlit.io](https://share.streamlit.io/) and log in with GitHub.
3. Click **Create app** -> Select your repo `NexusBI`, branch `main`, and main file `app/streamlit_app.py`.
4. Click **Advanced settings...** and add your secrets:

```toml
# Streamlit Cloud Secrets (Advanced Settings)
DB_HOST = "ep-xxxxxx.region.aws.neon.tech"
DB_PORT = "5432"
DB_NAME = "neondb"
DB_USER = "app_readonly"
DB_PASSWORD = "a_strong_password_for_app_readonly"
DB_SSLMODE = "require"

LLM_PROVIDER = "groq"
GROQ_API_KEY = "gsk_your_groq_api_key_here"
GROQ_MODEL = "openai/gpt-oss-120b"

RATE_LIMIT_PER_HOUR = "20"
MAX_PROMPT_LENGTH = "500"
```

5. Click **Deploy!** Your app will be live with a public URL in 2 minutes.

---

## Option B: AWS RDS PostgreSQL Deployment

If you prefer deploying the data warehouse on AWS:

### Step 1: Provision AWS RDS Instance
1. In the AWS Console, open **RDS** -> **Databases** -> **Create database**.
2. Select **Standard create** -> **PostgreSQL** (version 15 or 16).
3. Select **Free tier** template.
4. Settings:
   - DB instance identifier: `olist-warehouse`
   - Master username: `postgres`
   - Master password: `[YOUR_PASSWORD]`
5. Connectivity:
   - Public access: **Yes** (to allow connections from Streamlit Cloud or your IP).
   - VPC Security Group: Create or select one allowing inbound TCP port `5432` from your IP or `0.0.0.0/0` (with restricted DB passwords).

### Step 2: Configure Environment
In your `.env`:
```env
DB_HOST=olist-warehouse.xxxxxx.ap-southeast-2.rds.amazonaws.com
DB_PORT=5432
DB_NAME=warehouse
DB_USER=app_readonly
DB_PASSWORD=your_readonly_password
DB_SSLMODE=prefer
```

---

## Safe AWS RDS Teardown (Avoid Cloud Charges)

> [!IMPORTANT]
> AWS RDS Free Tier expires after 12 months or incurs charges if storage/I/O limits are exceeded. Follow these steps to export your data and delete the instance cleanly.

### Step 1: Export Curated Marts Locally
Before terminating your RDS instance, ensure all analytical data is backed up:

```bash
python scripts/export_marts.py --format both
```
Verify that `data/marts_export/` contains `.parquet` and `.csv` files for all 4 marts.

### Step 2: Delete RDS Instance in AWS Console
1. Open the [AWS RDS Console](https://console.aws.amazon.com/rds/).
2. Click **Databases** -> Select `olist-warehouse`.
3. Click **Actions** -> **Delete**.
4. In the confirmation dialog:
   - Uncheck *Create final snapshot* (unless you want an S3 snapshot retained).
   - Check *I acknowledge that upon instance deletion, automated backups, including point-in-time recovery, will no longer be available.*
   - Type `delete me` in the box.
5. Click **Delete**. The instance status will change to *Deleting* and will disappear in ~5 minutes. Zero further AWS charges will accrue.

---

## Setting up dbt Documentation on GitHub Pages

The repository includes a workflow (`.github/workflows/dbt-docs.yml`) that automatically compiles and publishes your dbt data lineage and catalog to GitHub Pages.

### Manual Steps in GitHub:
1. Open your repository on GitHub.
2. Go to **Settings** -> **Pages** (in the left navigation).
3. Under **Build and deployment**:
   - Source: **GitHub Actions**.
4. On the next push to `main` (or by running the workflow manually under **Actions** -> **Deploy dbt Documentation**), GitHub Pages will deploy.
5. Your dbt lineage and data dictionary will be viewable at `https://<your-username>.github.io/<repo-name>/`.

---

## Configuring GitHub Actions Secrets

To enable automated testing and keepalive monitoring in GitHub Actions:

1. Open your repository on GitHub.
2. Go to **Settings** -> **Secrets and variables** -> **Actions**.
3. Under **Repository secrets**, click **New repository secret**:

| Secret Name | Value | Purpose |
| :--- | :--- | :--- |
| `GROQ_API_KEY` | `gsk_...` | Enables live Text-to-SQL benchmark evaluation in CI. |
| `APP_URL` | `https://nexusbi.streamlit.app` | Used by `.github/workflows/keepalive.yml` to ping your demo app weekly. |
| `DB_HOST` | `ep-xxxx.neon.tech` | Target warehouse host for dbt documentation compilation. |
| `DB_USER` | `dbt_user` | dbt transform role username. |
| `DB_PASSWORD` | `...` | dbt transform role password. |

> [!NOTE]
> Even without database secrets configured in GitHub, the CI pipeline runs in `--mock` mode with zero external dependencies!
