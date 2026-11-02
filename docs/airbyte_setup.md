# Airbyte OSS Configuration Guide (Postgres to Redshift)

> [!NOTE]
> This guide provides the exact click-by-click instructions to configure the **Source**, **Destination**, and **Connection** in the Airbyte Open Source Software (OSS) Web UI (`http://localhost:8000`). It also explains how to locate your Connection ID and generate API client credentials for Apache Airflow orchestration.

---

## 1. Prerequisites
- Airbyte OSS is running via `abctl` (UI accessible at `http://localhost:8000`).
- Local Postgres container (`olist-postgres`) is running on host port `5433` (via `make source-up` or `docker compose -f source/docker-compose.yml up -d`).
- Amazon Redshift Serverless workgroup and S3 staging bucket are available (configured in [docs/aws_setup.md](aws_setup.md)).

---

## 2. Step 1: Create Postgres Source in Airbyte UI

1. Open your browser and navigate to `http://localhost:8000`.
2. In the left navigation sidebar, click **Sources** -> click the **+ New source** button.
3. In the search box, type `Postgres` and select the **Postgres** source connector.
4. Fill in the exact connection parameters:

| Field Name | Setting / Value | Explanation |
| :--- | :--- | :--- |
| **Source name** | `olist-postgres-source` | Readable identifier in the UI |
| **Host** | `host.docker.internal` | Allows Airbyte (running inside Docker) to reach the host machine where port 5433 is bound |
| **Port** | `5433` | Host port mapped to Postgres in `source/docker-compose.yml` |
| **Database Name** | `olist` | Database created by container |
| **Default Schemas** | `public` | Schema holding the Olist tables |
| **User** | `olist` | Default user defined in docker-compose |
| **Password** | *(Your PG_PASSWORD from source/.env)* | Database password |
| **SSL Mode** | `disable` | Local Docker-to-host connection does not require SSL |
| **Replication Method**| `Scan Changes with User Defined Cursor` or `Standard (full table sync)` | Suitable for full refresh syncs |

5. Click **Set up source**. Airbyte will run a connection check. Once verified green, proceed to the destination.

---

## 3. Step 2: Create Redshift Destination in Airbyte UI

1. In the left sidebar, click **Destinations** -> click **+ New destination**.
2. Search for `Redshift` and select the **Redshift** destination connector.
3. Fill in the parameters (referencing your AWS values from `.env`):

| Field Name | Setting / Value | Explanation |
| :--- | :--- | :--- |
| **Destination name** | `redshift-serverless-dest` | Descriptive name |
| **Host** | `olist-workgroup.<account-id>.ap-south-1.redshift-serverless.amazonaws.com` | Redshift Serverless Workgroup endpoint without `:5439` |
| **Port** | `5439` | Default Redshift port |
| **Database** | `dev` | Target database name |
| **Default Schema** | `raw` | Airbyte writes directly into the `raw` schema |
| **User** | `admin` | Redshift admin user |
| **Password** | *(Your REDSHIFT_ADMIN_PASSWORD)* | Redshift admin password |
| **Staging Mode** | **S3 Staging** (Recommended) | Redshift bulk-copy mechanism using S3 for speed |
| **S3 Bucket Name** | `olist-airbyte-staging-<id>` | S3 staging bucket created in Step 1 of AWS setup |
| **S3 Bucket Region**| `ap-south-1` | Must match your S3 bucket region (Mumbai) |
| **S3 Access Key ID**| *(AWS_ACCESS_KEY_ID from .env)* | Programmatic key of `airbyte-s3-staging-user` |
| **S3 Secret Key** | *(AWS_SECRET_ACCESS_KEY from .env)* | Programmatic secret of `airbyte-s3-staging-user` |
| **Purge Staging Files** | `Yes` (enabled) | Deletes temporary staged files from S3 after loading to Redshift |

4. Click **Set up destination**. Airbyte will test the connection and S3 write/read permissions.

---

## 4. Step 3: Create and Configure the Connection

1. In the left sidebar, click **Connections** -> click **+ New connection**.
2. Select your existing source: `olist-postgres-source`.
3. Select your existing destination: `redshift-serverless-dest`.
4. Configure the sync settings:
   - **Connection name:** `Olist Postgres to Redshift`.
   - **Schedule type:** `Manual` (or `Cron` - we use `Manual` because Apache Airflow will trigger it on demand).
   - **Destination namespace:** Select `Custom format` and enter `raw` (ensures tables are created inside `raw.<table_name>`).
   - **Destination stream prefix:** Leave blank (no prefix needed; tables will match source names).
   - **Non-breaking schema updates:** Select *Approve and re-sync changes*.
5. In the **Streams (Tables)** list, ensure all 6 Olist tables are selected:
   - `customers`
   - `orders`
   - `order_items`
   - `order_payments`
   - `products`
   - `category_translation`
6. For each table, set the **Sync mode** to:
   - **`Full refresh | Overwrite`**
   > [!NOTE]
   > Why Full Refresh \| Overwrite? For our college microproject, this guarantees that each pipeline run completely refreshes the raw landing schema cleanly without duplicated keys or orphaned records.
7. Click **Set up connection**. Airbyte will save the connection.
8. (Optional initial test): Click **Sync now** to perform a test replication. You can observe the sync status in the UI logs.

---

## 5. Step 4: Retrieve the Connection ID

Apache Airflow needs this unique ID to trigger the sync programmatically via the Airbyte API.

1. In the Airbyte UI, go to **Connections** and click on `Olist Postgres to Redshift`.
2. Look at your browser URL bar. It will follow this structure:
   ```text
   http://localhost:8000/workspaces/11111111-2222-3333-4444-555555555555/connections/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/status
   ```
3. Copy the UUID appearing right after `/connections/` (e.g. `aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee`).
4. Paste this value into your `.env` file:
   ```bash
   AIRBYTE_CONNECTION_ID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
   ```

---

## 6. Step 5: Create Airbyte API Client Credentials

Airbyte OSS requires Client ID and Client Secret authentication for REST API endpoints.

1. In the bottom-left corner of the Airbyte UI, click the **Settings** gear icon (⚙️).
2. Under the **Workspace** section, click **Applications**.
3. Click the **+ New application** button in the top right.
4. **Application name:** `airflow-orchestrator`.
5. Click **Create application**.
6. A modal will appear displaying:
   - **Client ID**
   - **Client Secret**
   > [!WARNING]
   > Copy the Client Secret immediately — Airbyte only displays it once!
7. Add these credentials to your project root `.env` file:
   ```bash
   AIRBYTE_API_URL=http://localhost:8000/api/v1
   AIRBYTE_CLIENT_ID=your_copied_client_id_here
   AIRBYTE_CLIENT_SECRET=your_copied_client_secret_here
   ```

---

## 7. Viva Defense Tips for Ingestion
- **Why Airbyte instead of custom Python ETL scripts?** Custom scripts require handling schema drift, API retries, rate limiting, and network failures manually. Airbyte provides battle-tested connectors with automated retry semantics and telemetry.
- **Why S3 Staging?** Amazon Redshift is an MPP (Massively Parallel Processing) columnar warehouse. Using `INSERT` queries row-by-row is orders of magnitude slower than dumping bulk columnar Parquet/CSV files into S3 and executing a distributed `COPY` command.
