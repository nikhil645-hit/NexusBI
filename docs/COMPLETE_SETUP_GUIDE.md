# The Complete, Beginner-Proof Setup Guide
## End-to-End Data Pipeline with Amazon Redshift Serverless, dbt, Airbyte, Airflow & Streamlit

> [!IMPORTANT]
> **Who this is for:** A beginner data engineer on Windows 11 + WSL Ubuntu (`~/de-project`, 16 GB RAM, Docker Desktop) with an AWS account and promotional credits (~$120).
> **Goal:** Take you step-by-step from zero cloud infrastructure to a fully orchestrated, green, end-to-end data pipeline with Conversational BI.
> **Safety:** Follow every cost guardrail and security rule. Zero private secrets are committed or hardcoded.

---

## 📋 Table of Contents
- [Prerequisites & Note on Documented Names](#prerequisites--note-on-documented-names)
- [PART 0: Before Touching AWS (Cost Safety & Account Preparation)](#part-0-before-touching-aws-cost-safety--account-preparation)
- [PART 1: Create Amazon S3 Staging Bucket](#part-1-create-amazon-s3-staging-bucket)
- [PART 2: Identity & Access Management (IAM Least Privilege)](#part-2-identity--access-management-iam-least-privilege)
- [PART 3: Network Security & Inbound Access](#part-3-network-security--inbound-access)
- [PART 4: Provision Amazon Redshift Serverless & Database RBAC](#part-4-provision-amazon-redshift-serverless--database-rbac)
- [PART 5: Configure Airbyte OSS Destination & Replicate Data](#part-5-configure-airbyte-oss-destination--replicate-data)
- [PART 6: Execute Transformations & Data Quality Tests with dbt](#part-6-execute-transformations--data-quality-tests-with-dbt)
- [PART 7: Orchestrate the Entire Pipeline with Apache Airflow](#part-7-orchestrate-the-entire-pipeline-with-apache-airflow)
- [PART 8: Launch Conversational BI Web App (Streamlit + LLM)](#part-8-launch-conversational-bi-web-app-streamlit--llm)
- [PART 9: End-to-End Demo Rehearsal & Evidence Checklist](#part-9-end-to-end-demo-rehearsal--evidence-checklist)
- [PART 10: Daily Shutdown & Complete Post-Demo Teardown](#part-10-daily-shutdown--complete-post-demo-teardown)
- [PART 11: Comprehensive Troubleshooting Matrix (25+ Scenarios)](#part-11-comprehensive-troubleshooting-matrix-25-scenarios)

---

## Prerequisites & Note on Documented Names

### Your Local Working Environment
- **OS:** Windows 11 with WSL 2 (Ubuntu distribution).
- **Project Directory:** `~/de-project` (in WSL) mounted at `/mnt/d/de-project` (Windows `D:\de-project`).
- **RAM Budget:** 16 GB physical RAM with ~10 GB assigned to Docker Desktop.
- **Pre-existing Local Services:**
  - PostgreSQL 16 container (`olist-postgres`) running on port `5433` (db: `olist`, user: `olist`).
  - Airbyte OSS running via `abctl` at `http://localhost:8000`.

### Standardized Infrastructure Identifiers
To prevent confusion across console pages, scripts, and configuration files, this guide uses the following exact names:

| Resource Type | Resource Identifier | Purpose / Viva Justification |
| :--- | :--- | :--- |
| **AWS Region** | `ap-south-1` (Asia Pacific - Mumbai) | Minimizes latency to India and keeps cloud resources co-located. |
| **S3 Staging Bucket** | `olist-pipeline-<your-initials>-<random4digits>` | Dedicated staging buffer for bulk parallel ingestion into Redshift. |
| **IAM Staging Role** | `redshift-s3-role` | Allows Redshift to read bulk staged files from S3 securely. |
| **IAM Airbyte User** | `airbyte-user` | Programmatic API user allowing Airbyte to upload files to S3. |
| **Security Group** | `olist-redshift-sg` | Firewall restricting Redshift port `5439` exclusively to your public IP. |
| **Redshift Namespace** | `olist-ns` | Logical database storage unit in Redshift Serverless. |
| **Redshift Workgroup** | `olist-wg` | Serverless compute engine running queries at lowest Base RPU (8). |
| **Redshift Database** | `dev` | Default target database created inside the namespace. |
| **Redshift Admin** | `awsadmin` | Superuser used solely for provisioning schemas and users. |
| **dbt Database User** | `dbt_user` | Dedicated role with write access to `staging` and `marts`. |
| **App Read-Only User** | `app_readonly` | Dedicated role with read-only access to `marts` only. |

> [!TIP]
> **Keep a Private Notes File:** Open Notepad or a text editor outside your git directory (e.g. on your Desktop: `C:\Users\Acer\Desktop\private_de_notes.txt`). As you complete the steps below, paste each generated value into this file. **Never commit this notes file or paste its contents into chat.**

---

## PART 0: Before Touching AWS (Cost Safety & Account Preparation)

*Why this exists:* Protects your student promotional credits, prevents billing surprises, and guarantees your AWS account has sufficient permissions to provision serverless data warehouses.

### 0.1 Set Region to ap-south-1 (Mumbai)
1. Log in to the [AWS Management Console](https://console.aws.amazon.com/).
2. Look at the top navigation bar, in the upper-right corner next to your account name. Click the **Region dropdown**.
3. Select **Asia Pacific (Mumbai) ap-south-1**.
4. **Verification:** The navigation bar now permanently displays **Mumbai**.

### 0.2 Check Promotional Credits Balance
1. In the top search bar, type `Billing` and press Enter. Click **Billing and Cost Management**.
2. In the left navigation pane, under *Cost management* (the label may differ slightly; look for *Billing* or *Payments*), click **Credits**.
3. **Inspect the table:**
   - Confirm your promotional balance (~$120).
   - Check the **Expiration date**.
   - Review **Applicable products** to verify Redshift and S3 are covered (almost all AWS general promotional credits cover both).

### 0.3 Check Account Plan & Service Restrictions
New or credit-funded AWS accounts occasionally operate under an initial restricted "Free/Sandbox" tier that restricts Redshift Serverless or IAM operations:
1. In the top search bar, type `Redshift` and select **Amazon Redshift**.
2. Click **Redshift Serverless** in the left sidebar.
3. If the console displays a banner: *"Your account is currently verifying"* or *"Upgrade your support plan / payment method"*, follow the on-screen prompts to complete phone verification or attach an active payment method. Promotional credits will continue to pay your usage fees before any card is billed.
4. Check [AWS Official Redshift Pricing](https://aws.amazon.com/redshift/pricing/): Redshift Serverless in `ap-south-1` costs a fraction of a cent per RPU-minute while running, and is completely free when paused. Never rely on estimates from memory.

### 0.4 Enable CloudWatch Billing Alerts & Create a Safety Budget
1. In the top search bar, type `Billing` and open **Billing and Cost Management**.
2. In the left menu, click **Billing preferences**. Check the box **Receive CloudWatch billing alerts** -> click **Save preferences**.
3. In the left menu, click **Budgets** (or search `Budgets` in the top bar).
4. Click the orange **Create budget** button.
5. Under *Budget setup*, select **Use a template (simplified)** -> select **Monthly cost budget**.
6. **Budget name:** `student-safety-budget`.
7. **Budget amount:** Enter `10` ($10.00 USD).
8. **Email recipients:** Enter your personal student email address.
9. Click **Create budget**.
10. **Verification:** You will see `student-safety-budget` listed with status *OK*. AWS will email you the moment forecasted spend exceeds $8.00 (80%).

### 0.5 Secure the Root Account with MFA
1. In the top-right corner, click your account name -> select **Security credentials**.
2. Under *Multi-factor authentication (MFA)*, click **Assign MFA**.
3. Name your device: `student-mobile-authenticator`. Choose **Authenticator app** (Google Authenticator, Microsoft Authenticator, or Authy).
4. Scan the QR code with your phone, enter two consecutive 6-digit codes, and click **Add MFA**.
5. *Rule:* Never generate or use root user AWS access keys.

> [!NOTE]
> **CHECKPOINT 0:**
> - AWS Region is **ap-south-1 (Mumbai)**.
> - AWS Budgets shows `student-safety-budget` active.
> - Multi-Factor Authentication (MFA) is active on your account.
> - **Screenshot for report:** The *AWS Budgets* overview screen showing your $10 threshold and email alert recipient.

---

## PART 1: Create Amazon S3 Staging Bucket

*Why this exists (Viva Defense):* Amazon Redshift is a distributed columnar MPP database. Loading 100,000 records row-by-row with SQL `INSERT` takes hours. Airbyte uploads compressed data batches to S3, and Redshift loads them in parallel in seconds using its distributed `COPY` command.

### 1.1 Create the Staging Bucket
1. In the top search bar, type `S3` and select the **S3** service.
2. Click the orange **Create bucket** button on the right.
3. **AWS Region:** Verify it is set to `Asia Pacific (Mumbai) ap-south-1`.
4. **Bucket name:** Type `olist-pipeline-<your-initials>-<random4digits>` (e.g., `olist-pipeline-nk-7821`).
   > *Note:* Bucket names are globally unique across all AWS accounts worldwide. Use only lowercase letters, numbers, and hyphens.
5. **Object Ownership:** Keep *ACLs disabled (recommended)*.
6. **Block Public Access settings for this bucket:** Keep **Block all public access** checked (all 4 checkboxes must be ON). Airbyte accesses S3 via authenticated IAM keys, not public URLs.
7. **Bucket Versioning:** Keep *Disable*.
8. **Default encryption:** Choose *Server-side encryption with Amazon S3 managed keys (SSE-S3)*.
9. Click **Create bucket** at the bottom of the page.

### 1.2 Add an Auto-Delete Lifecycle Rule (Prevents Storage Cost)
1. In the buckets list, click the name of your newly created bucket: `olist-pipeline-<your-initials>-<random4digits>`.
2. Select the **Management** tab (between *Permissions* and *Metrics*).
3. Scroll down to *Lifecycle rules* -> click **Create lifecycle rule**.
4. **Lifecycle rule name:** `auto-delete-staging-after-2-days`.
5. **Choose a rule scope:** Select **Apply to all objects in the bucket**. Check the confirmation box *"I acknowledge that this rule applies to all objects in the bucket"*.
6. Under *Lifecycle rule actions*, check the box **Expire current versions of objects**.
7. Under *Expire current versions of objects*, enter `2` in the field **Days after object creation**.
8. Click **Create rule** at the bottom.

### 1.3 Record to Private Notes & Environment
- Open your private notes file and write down:
  `S3_BUCKET_NAME = olist-pipeline-<your-initials>-<random4digits>`
- This matches the `S3_BUCKET_NAME` variable in your project's `.env` file.

> [!NOTE]
> **CHECKPOINT 1:**
> - In S3 console, your bucket is listed in region `ap-south-1` with Access set to *Bucket and objects not public*.
> - The *Management* tab displays the lifecycle rule expiring objects after 2 days.
> - **Screenshot for report:** S3 Bucket *Properties* tab showing the bucket name, region, and encryption status.

---

## PART 2: Identity & Access Management (IAM Least Privilege)

*Why this exists (Viva Defense):* We follow the Principle of Least Privilege. Redshift only needs to read from our staging bucket, while Airbyte only needs to write staging files. Neither has administrator rights over the AWS account.

### 2.1 Create the IAM Role for Redshift (`redshift-s3-role`)
1. In the top search bar, type `IAM` and select **IAM**.
2. In the left navigation pane, click **Roles** -> click the blue **Create role** button.
3. Under *Trusted entity type*, select **AWS service**.
4. Under *Use case*, scroll down or select **Redshift**, then select **Redshift - Customizable** (or simply choose *Redshift*). Click **Next**.
5. In the permissions policy search bar, click the **Create policy** button (opens in a new browser tab).
6. In the new policy tab, click the **JSON** tab and replace the editor contents with the following exact policy (replace `<your-bucket-name>` with your actual bucket name):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "s3:GetObject",
           "s3:ListBucket"
         ],
         "Resource": [
           "arn:aws:s3:::<your-bucket-name>",
           "arn:aws:s3:::<your-bucket-name>/*"
         ]
       }
     ]
   }
   ```
7. Click **Next**.
8. **Policy name:** `RedshiftS3StagingReadPolicy`. Click **Create policy**.
9. Close this tab and return to the *Create role* tab. Click the small refresh icon next to the search box.
10. Search for `RedshiftS3StagingReadPolicy`, check the checkbox next to it, and click **Next**.
11. **Role name:** `redshift-s3-role`.
12. **Role description:** `Allows Redshift Serverless to read staged files from S3`.
13. Click **Create role**.
14. Search for `redshift-s3-role` in the roles list and click on it.
15. **Copy the ARN** (format: `arn:aws:iam::<your-12-digit-account-id>:role/redshift-s3-role`).
16. Save it in your private notes as `REDSHIFT_ROLE_ARN`.

---

### 2.2 Create the IAM User for Airbyte (`airbyte-user`)
1. In the IAM console, click **Users** in the left navigation pane.
2. Click the blue **Create user** button.
3. **User name:** `airbyte-user`.
4. Leave *"Provide user access to the AWS Management Console"* **unchecked** (this user only needs API access). Click **Next**.
5. Under *Permissions options*, choose **Attach policies directly**.
6. Click the **Create policy** button (opens in a new tab).
7. Select the **JSON** tab and paste the following policy (replace `<your-bucket-name>` with your actual bucket name):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "s3:PutObject",
           "s3:GetObject",
           "s3:ListBucket",
           "s3:DeleteObject"
         ],
         "Resource": [
           "arn:aws:s3:::<your-bucket-name>",
           "arn:aws:s3:::<your-bucket-name>/*"
         ]
       }
     ]
   }
   ```
8. Click **Next** -> **Policy name:** `AirbyteS3StagingWritePolicy` -> click **Create policy**.
9. Close this tab, return to the *Create user* tab, click the refresh button, search for `AirbyteS3StagingWritePolicy`, check the box, and click **Next**.
10. Click **Create user**.

### 2.3 Generate Access Key for Airbyte
1. In the users list, click on `airbyte-user`.
2. Click the **Security credentials** tab.
3. Scroll down to *Access keys* -> click **Create access key**.
4. Under *Use case*, select **Application running outside AWS**.
5. Check the confirmation box at the bottom (*"I understand the above recommendation..."*) and click **Next**.
6. Set description tag: `airbyte-oss-staging-uploader`. Click **Create access key**.
7. **CRITICAL STEP:**
   - Copy **Access key ID** (e.g., `AKIA...`).
   - Click *Show* and copy **Secret access key** (e.g., `wJalr...`).
   - Store both immediately in your private notes file.
   - *Never share or commit these keys.*
8. Click **Done**.

### 2.4 Map Values to Environment
In your private notes:
```text
AWS_REGION = ap-south-1
AWS_ACCESS_KEY_ID = <copied-access-key-id>
AWS_SECRET_ACCESS_KEY = <copied-secret-access-key>
```
These map directly to `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in root `.env` and in the Airbyte destination settings.

> [!NOTE]
> **CHECKPOINT 2:**
> - IAM Role `redshift-s3-role` exists with policy `RedshiftS3StagingReadPolicy`.
> - IAM User `airbyte-user` has active Access Keys and policy `AirbyteS3StagingWritePolicy`.
> - **Screenshot for report:** The `airbyte-user` *Security credentials* page showing the active Access Key ID (with secret hidden).

---

## PART 3: Network Security & Inbound Access

*Why this exists (Viva Defense):* Redshift Serverless lives inside an AWS Virtual Private Cloud (VPC). Since our data engineering tools (dbt, Airbyte, Streamlit) run locally on our workstation, Redshift must be publicly accessible, but protected by a Security Group allowing port 5439 traffic exclusively from our laptop's public IP address.

### 3.1 Find Your Current Public IP Address
1. Open PowerShell or your WSL terminal on your laptop.
2. Run:
   ```bash
   curl -s https://checkip.amazonaws.com
   ```
3. It will print a single IP address (e.g., `103.15.24.89`).
4. Write this down in your private notes as `MY_PUBLIC_IP`.

### 3.2 Create the Security Group (`olist-redshift-sg`)
1. In the top search bar, type `VPC` and select the **VPC** service.
2. In the left navigation pane, under *Security*, click **Security groups**.
3. Click the orange **Create security group** button.
4. **Basic details:**
   - **Security group name:** `olist-redshift-sg`.
   - **Description:** `Allow Redshift inbound on port 5439 from student IP`.
   - **VPC:** Select your **Default VPC** (e.g., `vpc-xxxxxxx (Default)`).
5. **Inbound rules:**
   - Click **Add rule**.
   - **Type:** Select **Redshift** (or *Custom TCP*).
   - **Port range:** `5439`.
   - **Source:** Select **My IP** from the dropdown (AWS will automatically format it as `<your-ip>/32`).
   - **Description:** `Student Laptop Access`.
6. **Outbound rules:** Leave default (*All traffic to 0.0.0.0/0*).
7. Click **Create security group** at the bottom.
8. In the security groups list, copy the **Security group ID** (e.g., `sg-0123456789abcdef0`) and save it in your private notes.

### 3.3 What to Do When Your IP Changes (e.g. New Wi-Fi Network)
If your laptop disconnects, switches to mobile hotspot, or reconnects on a new Wi-Fi network, your public IP will change, and `dbt` or `psycopg2` will time out with `Connection refused` or `ETIMEDOUT`.
- **The 30-second fix:**
  1. Open VPC -> **Security groups** -> click `olist-redshift-sg`.
  2. Select the **Inbound rules** tab -> click **Edit inbound rules**.
  3. Under *Source*, click the dropdown, select **My IP** (AWS detects your new IP), and click **Save rules**.

> [!NOTE]
> **CHECKPOINT 3:**
> - Security Group `olist-redshift-sg` has an inbound rule for TCP `5439` with source `<your-ip>/32`.
> - **Screenshot for report:** The *Inbound rules* tab of `olist-redshift-sg` displaying port 5439 and your masked IP.

---

## PART 4: Provision Amazon Redshift Serverless & Database RBAC

*Why this exists (Viva Defense):* Amazon Redshift Serverless automatically handles scaling and provisioning. We set the compute capacity to the absolute lowest tier (8 RPUs) and enforce a daily RPU limit so accidental runaway analytical queries shut down automatically.

### 4.1 Create Namespace (`olist-ns`) and Workgroup (`olist-wg`)
1. In the top search bar, type `Redshift` and click **Amazon Redshift**.
2. In the left sidebar, click **Redshift Serverless**.
3. Click the orange **Create workgroup** button (or click *Customize settings*).

#### Step A: Workgroup Settings (Compute)
- **Workgroup name:** `olist-wg`.
- **Capacity (RPUs):** Under *Base capacity*, choose **8 RPUs** (the minimum allowed in AWS, keeping compute costs minimal).
- Click **Next**.

#### Step B: Namespace Settings (Storage & Credentials)
- Choose **Create a new namespace**.
- **Namespace name:** `olist-ns`.
- **Database name:** `dev`.
- **Admin user credentials:** Select **Manually set admin password**.
- **Admin user name:** `awsadmin`.
- **Admin user password:** Generate a strong password (at least 8 characters, with 1 uppercase, 1 lowercase, and 1 number, e.g., `OlistAdmin2026!Demo`).
  > *Save this password in your private notes as `REDSHIFT_ADMIN_PASSWORD`.*
- **Permissions / IAM roles:**
  - Click **Manage IAM roles** -> choose **Associate IAM roles**.
  - Check the box next to `redshift-s3-role` (created in Part 2).
  - Click **Associate IAM roles**.
- Click **Next**.

#### Step C: Network and Security (Connectivity)
- **VPC:** Ensure your **Default VPC** is selected.
- **VPC security groups:**
  - Remove any default group.
  - Select `olist-redshift-sg` (created in Part 3).
- **Publicly accessible:**
  - Select **Turn on** (enabled).
  > [!IMPORTANT]
  > Turning this ON assigns a public IP to the workgroup so your laptop can reach it over port 5439.
- Click **Next** to review.
- Click **Create workgroup** (or *Create*).

### 4.2 Wait for Workgroup Availability
- The status will initially show `Creating` with a spinning icon.
- Wait approximately 3 to 5 minutes.
- When the status turns to **Available** (green), proceed.

### 4.3 Configure Cost Guardrail (Usage Limit)
1. In Redshift Serverless, click on your workgroup `olist-wg`.
2. Click the **Limits** tab.
3. Under *Usage limits*, click **Manage usage limits** (or *Add limit*).
4. Configure:
   - **Limit type:** `RPU-hours`.
   - **Amount:** `4` RPU-hours.
   - **Frequency:** `Daily`.
   - **Action:** Select **Turn off query execution** and **Alert**.
5. Click **Save**.

### 4.4 Copy Endpoint & Construct Host for `.env`
1. On the `olist-wg` overview page, find **General information** -> **Endpoint**.
2. It looks like:
   `olist-wg.<account-id>.ap-south-1.redshift-serverless.amazonaws.com:5439/dev`
3. The **Host** is the portion *before* the colon `:5439`:
   `olist-wg.<account-id>.ap-south-1.redshift-serverless.amazonaws.com`
4. Copy this host value to your private notes as `REDSHIFT_HOST`.

---

### 4.5 Execute Database Initialization Scripts via Query Editor v2
We will now execute `sql/01_schemas.sql` and `sql/02_users.sql` to initialize our schemas and users.

1. In the Redshift console left sidebar, click **Query editor v2** (this opens in the same or a new tab).
2. In the left panel, find your workgroup `olist-wg` -> click on it to connect:
   - **Authentication:** Choose **Database user name and password**.
   - **Database:** `dev`.
   - **User name:** `awsadmin`.
   - **Password:** Enter your `REDSHIFT_ADMIN_PASSWORD`.
   - Click **Save** / **Connect**.
3. Once connected, open a new SQL editor tab by clicking the **+** (Create query) button.

#### Execute `sql/01_schemas.sql`:
1. In WSL or your project directory, open [sql/01_schemas.sql](file:///d:/de-project/sql/01_schemas.sql) and copy its entire text:
   ```sql
   CREATE SCHEMA IF NOT EXISTS raw;
   CREATE SCHEMA IF NOT EXISTS staging;
   CREATE SCHEMA IF NOT EXISTS marts;
   ```
2. Paste it into Query Editor v2 and click **Run** (or press Ctrl+Enter).
3. **Verify Output:** You should see `Status: Success`. In the left schema tree under `dev`, refresh and verify that `raw`, `staging`, and `marts` are visible.

#### Execute `sql/02_users.sql`:
1. Open [sql/02_users.sql](file:///d:/de-project/sql/02_users.sql).
2. Generate two unique strong passwords in your private notes:
   - `REDSHIFT_DBT_PASSWORD` (e.g., `DbtUserPass2026!Secure`)
   - `REDSHIFT_APP_PASSWORD` (e.g., `AppReadOnlyPass2026!Secure`)
3. In Query Editor v2, paste the contents of `02_users.sql`, replacing the placeholder strings with your actual passwords:
   ```sql
   CREATE USER dbt_user WITH PASSWORD 'DbtUserPass2026!Secure';
   GRANT USAGE ON SCHEMA raw TO dbt_user;
   GRANT ALL ON SCHEMA staging TO dbt_user;
   GRANT ALL ON SCHEMA marts TO dbt_user;
   GRANT SELECT ON ALL TABLES IN SCHEMA raw TO dbt_user;
   GRANT ALL ON ALL TABLES IN SCHEMA staging TO dbt_user;
   GRANT ALL ON ALL TABLES IN SCHEMA marts TO dbt_user;
   ALTER DEFAULT PRIVILEGES IN SCHEMA raw GRANT SELECT ON TABLES TO dbt_user;
   ALTER DEFAULT PRIVILEGES IN SCHEMA staging GRANT ALL ON TABLES TO dbt_user;
   ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT ALL ON TABLES TO dbt_user;

   CREATE USER app_readonly WITH PASSWORD 'AppReadOnlyPass2026!Secure';
   GRANT USAGE ON SCHEMA marts TO app_readonly;
   GRANT SELECT ON ALL TABLES IN SCHEMA marts TO app_readonly;
   ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT ON TABLES TO app_readonly;
   REVOKE CREATE ON SCHEMA raw FROM app_readonly;
   REVOKE CREATE ON SCHEMA staging FROM app_readonly;
   REVOKE CREATE ON SCHEMA marts FROM app_readonly;
   ```
4. Click **Run**.
5. **Verify Output:** `Status: Success`.

---

### 4.6 Test Connection From Your Laptop (Python Test)
Before moving to Airbyte, test connectivity from your WSL terminal using the project virtual environment.

1. Open WSL terminal in `~/de-project`:
   ```bash
   cd ~/de-project
   ```
2. Run a one-line Python test:
   ```bash
   ~/de-project/.venv/bin/python -c "
   import psycopg2
   conn = psycopg2.connect(
       host='<your-redshift-host>',
       port=5439,
       dbname='dev',
       user='awsadmin',
       password='<your-admin-password>'
   )
   cur = conn.cursor()
   cur.execute('SELECT current_user, current_database(), version();')
   print('Connection successful:', cur.fetchone())
   conn.close()
   "
   ```
3. **Expected Output:**
   `Connection successful: ('awsadmin', 'dev', 'PostgreSQL 8.0.2 on i686-pc-linux-gnu...')`

> [!NOTE]
> **CHECKPOINT 4:**
> - Redshift Serverless workgroup `olist-wg` is **Available**.
> - Query Editor v2 displays schemas: `raw`, `staging`, `marts`.
> - Python test connects cleanly from your local laptop.
> - **Screenshot for report:** Query Editor v2 left tree showing schemas `raw`, `staging`, and `marts`.

---

## PART 5: Configure Airbyte OSS Destination & Replicate Data

*Why this exists (Viva Defense):* Airbyte automates extraction and loading from our operational Postgres database into Redshift, handling schema mapping, error retries, and high-throughput S3 bulk copy.

### 5.1 Analysis of Airbyte Redshift Connector Upload Methods
The modern Airbyte Redshift Destination connector (`airbyte/destination-redshift`) supports two data loading approaches:
1. **S3 Staging (Selected Approach):** Airbyte streams records as compressed files into your S3 staging bucket, then instructs Redshift to execute a distributed `COPY` command. This is chosen because:
   - It completes in under 1 minute for ~100k rows.
   - It avoids long-lived open transactions that lock Postgres tables.
   - It is the production standard for Amazon Redshift.
2. **Direct / Standard Inserts:** Uses JDBC batch inserts directly over port 5439. *Why rejected:* Takes 20–30 minutes for Olist data, frequently times out, and exhausts workstation RAM.

### 5.2 Configure the Redshift Destination in Airbyte UI
1. Open your browser and navigate to the Airbyte UI: **`http://localhost:8000`**.
2. In the left navigation menu, click **Destinations**.
3. If an old Redshift destination exists, click it -> **Settings** -> **Delete destination**. Then click **+ New destination**.
4. In the search box, type `Redshift` and select the **Redshift** connector.
5. Enter the exact configuration:

| Field in Airbyte UI | Exact Value to Enter | Explanation |
| :--- | :--- | :--- |
| **Destination name** | `redshift-serverless-dest` | Descriptive name in the UI |
| **Host** | `<your-REDSHIFT_HOST>` | Endpoint host from Step 4.4 without `:5439` |
| **Port** | `5439` | Default Redshift port |
| **Database** | `dev` | Database inside namespace `olist-ns` |
| **Default Schema** | `raw` | Airbyte writes directly into the `raw` schema |
| **User** | `awsadmin` | Admin user for schema ingestion |
| **Password** | `<your-REDSHIFT_ADMIN_PASSWORD>` | Admin password set in Step 4.1 |
| **Staging Mode** | Select **S3 Staging** | High performance parallel bulk copy |
| **S3 Bucket Name** | `<your-S3_BUCKET_NAME>` | Bucket created in Part 1 |
| **S3 Bucket Region** | `ap-south-1` | Matches your AWS region |
| **S3 Access Key ID** | `<your-AWS_ACCESS_KEY_ID>` | Created for `airbyte-user` in Part 2 |
| **S3 Secret Key** | `<your-AWS_SECRET_ACCESS_KEY>` | Secret for `airbyte-user` in Part 2 |
| **Purge Staging Files** | **Yes** (checked) | Deletes temporary staged files from S3 upon load |

6. Click **Set up destination**. Airbyte will test connectivity and S3 write/read permissions. Wait for the green checkmark: *All connection tests passed*.

---

### 5.3 Set Up Connection & Trigger Full Refresh Sync
1. In the left navigation menu, click **Connections** -> click **+ New connection** (or select your existing Postgres-to-Redshift connection).
2. **Source:** Select `olist-postgres-source`.
3. **Destination:** Select `redshift-serverless-dest`.
4. Configure Sync Settings:
   - **Connection name:** `Olist Postgres to Redshift`.
   - **Schedule type:** `Manual` (Airflow will trigger this programmatically).
   - **Destination namespace:** Select **Custom format** and type `raw`.
   - **Destination stream prefix:** Leave empty.
   - **Non-breaking schema updates:** Select *Approve and re-sync changes*.
5. In the **Streams (Tables)** list, select all 6 tables and set sync mode to **Full refresh | Overwrite**:
   - `customers` -> `Full refresh | Overwrite`
   - `orders` -> `Full refresh | Overwrite`
   - `order_items` -> `Full refresh | Overwrite`
   - `order_payments` -> `Full refresh | Overwrite`
   - `products` -> `Full refresh | Overwrite`
   - `category_translation` -> `Full refresh | Overwrite`
6. Click **Set up connection**.
7. On the connection page, click **Sync now**.
8. **Watch the live logs:** Airbyte will read the ~100k rows from local Postgres, stage them in S3, and load them into Redshift. The sync should complete in 1 to 3 minutes.
9. Verify the final status displays: **Succeeded** (green).

---

### 5.4 Verify Raw Row Counts in Redshift Query Editor v2
Open Redshift Query Editor v2 and run this verification query:
```sql
SELECT 'customers' as tbl, count(*) as row_count FROM raw.customers
UNION ALL
SELECT 'orders', count(*) FROM raw.orders
UNION ALL
SELECT 'order_items', count(*) FROM raw.order_items
UNION ALL
SELECT 'order_payments', count(*) FROM raw.order_payments
UNION ALL
SELECT 'products', count(*) FROM raw.products
UNION ALL
SELECT 'category_translation', count(*) FROM raw.category_translation;
```
**Expected Verification Table:**
```text
tbl                   row_count
customers             99441
orders                99441   <-- EXACT MATCH
order_items           112650
order_payments        103886
products              32951
category_translation  71
```

> [!NOTE]
> **Check Table Naming Convention:**
> Airbyte creates tables named `raw.customers`, `raw.orders`, etc. If your Airbyte version prepends a prefix like `raw._airbyte_raw_orders`, open [dbt/olist_dbt/dbt_project.yml](file:///d:/de-project/dbt/olist_dbt/dbt_project.yml) and adjust the `vars:` block:
> ```yaml
> vars:
>   source_schema: "raw"
>   table_orders: "_airbyte_raw_orders"  # Only if your Airbyte prefixed the table name
> ```
> With modern Airbyte and our custom namespace setting, names match directly without any changes.

---

### 5.5 Extract Airbyte Connection ID & API Credentials
Airflow needs these values to trigger synchronization programmatically:

1. **Find Connection ID:**
   - Look at the URL in your browser while viewing the connection:
     `http://localhost:8000/workspaces/<workspace-id>/connections/<connection-id>/status`
   - Copy the `<connection-id>` UUID (e.g. `1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d`).
   - Save in your private notes as `AIRBYTE_CONNECTION_ID`.

2. **Generate API Client Credentials:**
   - In the bottom-left corner of Airbyte UI, click the **Settings** gear icon (⚙️).
   - Under *Workspace*, click **Applications**.
   - Click **+ New application**.
   - **Application name:** `airflow-orchestrator`.
   - Click **Create application**.
   - Copy the **Client ID** and **Client Secret**.
   - Save in your private notes as `AIRBYTE_CLIENT_ID` and `AIRBYTE_CLIENT_SECRET`.

> [!NOTE]
> **CHECKPOINT 5:**
> - Airbyte connection completed with a green **Succeeded** status.
> - Redshift Query Editor v2 shows `raw.orders` has exactly `99,441` rows.
> - `AIRBYTE_CONNECTION_ID`, `AIRBYTE_CLIENT_ID`, and `AIRBYTE_CLIENT_SECRET` are stored in your private notes.
> - **Screenshot for report:** The Airbyte sync history page showing `Succeeded` status and record counts.

---

## PART 6: Execute Transformations & Data Quality Tests with dbt

*Why this exists (Viva Defense):* dbt brings software engineering rigor (modularity, version control, automated testing, documentation) to data warehouses. It builds our staging views and marts tables while ensuring data quality.

### 6.1 Populate Root `.env`
In your project root (`~/de-project`), copy the example file to `.env`:
```bash
cp .env.example .env
```
Open `.env` in an editor (`nano .env` or VS Code) and populate your exact values from your private notes:
```bash
# 1. Local Postgres
PG_HOST=localhost
PG_PORT=5433
PG_DB=olist
PG_USER=olist
PG_PASSWORD=<your_source_postgres_password>

# 2. AWS & Redshift Serverless
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=<your_airbyte_access_key_id>
AWS_SECRET_ACCESS_KEY=<your_airbyte_secret_access_key>
REDSHIFT_HOST=olist-wg.<account-id>.ap-south-1.redshift-serverless.amazonaws.com
REDSHIFT_PORT=5439
REDSHIFT_DB=dev
REDSHIFT_ADMIN_USER=awsadmin
REDSHIFT_ADMIN_PASSWORD=<your_admin_password>
REDSHIFT_DBT_USER=dbt_user
REDSHIFT_DBT_PASSWORD=<your_dbt_user_password>
REDSHIFT_APP_USER=app_readonly
REDSHIFT_APP_PASSWORD=<your_app_readonly_password>
S3_BUCKET_NAME=<your_s3_bucket_name>

# 3. Airbyte OSS
AIRBYTE_API_URL=http://localhost:8000/api/v1
AIRBYTE_CLIENT_ID=<your_airbyte_client_id>
AIRBYTE_CLIENT_SECRET=<your_airbyte_client_secret>
AIRBYTE_CONNECTION_ID=<your_airbyte_connection_id>

# 4. Airflow
AIRFLOW_UID=50000
AIRFLOW_PROJ_DIR=.
AIRFLOW__CORE__LOAD_EXAMPLES=False

# 5. Conversational BI & LLM
LLM_PROVIDER=gemini
GEMINI_API_KEY=<your_gemini_api_key_or_leave_placeholder_for_mock>
ANTHROPIC_API_KEY=
STREAMLIT_SERVER_PORT=8501
```

---

### 6.2 Test Connection with `dbt debug`
In your WSL terminal:
```bash
cd ~/de-project/dbt/olist_dbt
# Export variables from root .env into current shell session
export $(grep -v '^#' ../../.env | xargs)

# Run dbt debug
dbt debug
```
**Expected Output:**
```text
Configuration:
  profiles.yml file [OK found and valid]
  dbt_project.yml file [OK found and valid]

Required dependencies:
  - git [OK]

Connection:
  host: olist-wg.xxxxxx.ap-south-1.redshift-serverless.amazonaws.com
  port: 5439
  user: dbt_user
  database: dev
  schema: staging
  Connection test: [OK connection ok]

All checks passed!
```

---

### 6.3 Install Dependencies, Run Models & Run Tests
```bash
# 1. Install external package (dbt_utils)
dbt deps

# 2. Compile and run all staging views and marts tables
dbt run
```
**Expected Output:**
```text
Running with dbt=1.8.x
Found 9 models, 4 sources, 21 data tests...
Concurrency: 4 threads (target='dev')

1 of 9 START sql view model staging.stg_customers .................... [RUN]
2 of 9 START sql view model staging.stg_orders ....................... [RUN]
3 of 9 START sql view model staging.stg_order_items .................. [RUN]
4 of 9 START sql view model staging.stg_order_payments ............... [RUN]
5 of 9 START sql view model staging.stg_products ..................... [RUN]
1 of 9 OK created sql view model staging.stg_customers ............... [OK in 1.42s]
...
6 of 9 START sql table model marts.mart_daily_sales .................. [RUN]
7 of 9 START sql table model marts.mart_top_products ................. [RUN]
8 of 9 START sql table model marts.mart_customer_summary ............. [RUN]
9 of 9 START sql table model marts.mart_delivery_performance ......... [RUN]
...
Finished running 5 view models, 4 table models in 18.24s.
Completed successfully
Done. PASS=9 WARN=0 ERROR=0 SKIP=0 TOTAL=9
```

```bash
# 3. Execute all automated data quality assertions
dbt test
```
**Expected Output:**
```text
Running with dbt=1.8.x
Found 21 data tests...

1 of 21 START test unique_stg_customers_customer_id .................. [RUN]
1 of 21 PASS unique_stg_customers_customer_id ........................ [PASS in 0.82s]
...
21 of 21 START test assert_revenue_is_non_negative ................... [RUN]
21 of 21 PASS assert_revenue_is_non_negative ......................... [PASS in 0.74s]

Finished running 21 tests in 12.10s.
Completed successfully
Done. PASS=21 WARN=0 ERROR=0 SKIP=0 TOTAL=21
```

```bash
# 4. Generate and inspect documentation & lineage graph
dbt docs generate
dbt docs serve --port 8080
```
- Open your browser to `http://localhost:8080` (or `http://localhost:8081` if Airflow is using 8080).
- Click the teal circle in the bottom right corner to view the interactive DAG lineage graph. Press `Ctrl+C` in your terminal when finished.

---

### 6.4 Top 10 Common dbt Errors & Immediate Fixes

1. **`Connection refused / could not connect to server: Connection timed out`**
   - *Cause:* Your local public IP changed, or the security group rule was modified.
   - *Fix:* Re-run `curl -s https://checkip.amazonaws.com`, open AWS Security Groups -> `olist-redshift-sg`, and update port 5439 source to **My IP**.
2. **`permission denied for schema raw`**
   - *Cause:* `dbt_user` was not granted `SELECT` privileges on the `raw` schema.
   - *Fix:* Run Query Editor v2 as `awsadmin` and execute: `GRANT USAGE ON SCHEMA raw TO dbt_user; GRANT SELECT ON ALL TABLES IN SCHEMA raw TO dbt_user;`.
3. **`permission denied for schema staging` or `schema marts`**
   - *Cause:* Missing `CREATE` or `ALL` permissions for `dbt_user`.
   - *Fix:* In Query Editor v2: `GRANT ALL ON SCHEMA staging TO dbt_user; GRANT ALL ON SCHEMA marts TO dbt_user;`.
4. **`relation "raw.orders" does not exist`**
   - *Cause:* Airbyte sync was not run before `dbt run`.
   - *Fix:* Complete Part 5 and trigger a sync in Airbyte so the raw landing tables physically exist in Redshift.
5. **`relation "_airbyte_raw_orders" does not exist`**
   - *Cause:* Mismatch between dbt table identifier and Airbyte output.
   - *Fix:* In Query Editor v2, run `SELECT table_name FROM information_schema.tables WHERE table_schema = 'raw';` and update the table variables in `dbt_project.yml` to match.
6. **`Password authentication failed for user "dbt_user"`**
   - *Cause:* Password in root `.env` (`REDSHIFT_DBT_PASSWORD`) does not match the password specified in `sql/02_users.sql`.
   - *Fix:* Update `REDSHIFT_DBT_PASSWORD` in `.env` to match the exact string passed in `02_users.sql`.
7. **`column "order_purchase_timestamp" cannot be cast automatically to type timestamp`**
   - *Cause:* Postgres source timestamp column contains unexpected empty strings.
   - *Fix:* In `stg_orders.sql`, use `nullif(order_purchase_timestamp, '')::timestamp`.
8. **`Compilation Error: Could not find profile named 'olist_dbt'`**
   - *Cause:* `profiles.yml` is missing or `profile:` in `dbt_project.yml` has a typo.
   - *Fix:* Ensure [profiles.yml](file:///d:/de-project/dbt/olist_dbt/profiles.yml) exists in `dbt/olist_dbt/` and has top-level key `olist_dbt:`.
9. **`Test failed: assert_revenue_is_non_negative`**
   - *Cause:* Corrupt test data with negative pricing.
   - *Fix:* Inspect failing records: `SELECT * FROM marts.mart_daily_sales WHERE total_revenue < 0;`.
10. **`ModuleNotFoundError: No module named 'dbt'`**
    - *Cause:* Running outside the virtual environment.
    - *Fix:* Activate your virtualenv (`source ~/de-project/.venv/bin/activate`) or call `~/de-project/.venv/bin/dbt`.

> [!NOTE]
> **CHECKPOINT 6:**
> - `dbt debug` passes all checks.
> - `dbt run` compiles 5 staging views and 4 marts tables.
> - `dbt test` reports **PASS=21 WARN=0 ERROR=0**.
> - **Screenshot for report:** Terminal output displaying `dbt run` and `dbt test` green completion banners.

---

## PART 7: Orchestrate the Entire Pipeline with Apache Airflow

*Why this exists (Viva Defense):* Airflow automates the end-to-end data pipeline on a schedule. It coordinates cross-system dependencies: Airbyte API sync must finish successfully before dbt transformation models and quality tests are executed.

### 7.1 Populate Airflow Environment
Copy the example file in the `airflow/` directory:
```bash
cd ~/de-project
cp airflow/.env.example airflow/.env
```
Edit `airflow/.env` to include your exact Redshift credentials, Airbyte Connection ID, and Airbyte API keys:
```bash
AIRFLOW_UID=50000
AIRFLOW_DB_PASSWORD=airflow
AIRFLOW__CORE__FERNET_KEY=46BKJoQYlPPOexq0OhDZnIlNepKFf87WFwLbfzqnzq8=

# Airbyte OSS Integration (from inside Docker container)
AIRBYTE_API_URL=http://host.docker.internal:8000/api/v1
AIRBYTE_CLIENT_ID=<your_airbyte_client_id>
AIRBYTE_CLIENT_SECRET=<your_airbyte_client_secret>
AIRBYTE_CONNECTION_ID=<your_airbyte_connection_id>

# Redshift Serverless Warehouse Configuration (forwarded to dbt runner)
REDSHIFT_HOST=olist-wg.<account-id>.ap-south-1.redshift-serverless.amazonaws.com
REDSHIFT_PORT=5439
REDSHIFT_DB=dev
REDSHIFT_DBT_USER=dbt_user
REDSHIFT_DBT_PASSWORD=<your_dbt_user_password>
```

---

### 7.2 Workstation RAM Management Order
> [!CAUTION]
> **Memory Budget Alert:** Your workstation has 16 GB of physical RAM, with ~10 GB assigned to Docker.
> Running Postgres, Airbyte, Airflow, and Streamlit simultaneously consumes approximately 8.5–9.5 GB.
> **Operational Rule:** If Docker becomes sluggish or Airbyte crashes, stop Airflow while debugging Airbyte (`make airflow-down`), and only start Airflow when ready to orchestrate (`make airflow-up`).

---

### 7.3 Start Airflow Containers
In your WSL terminal:
```bash
cd ~/de-project
make airflow-up
# Or: docker compose -f airflow/docker-compose.yml up -d
```
Verify container statuses:
```bash
docker compose -f airflow/docker-compose.yml ps
```
**Expected Output:**
```text
NAME                IMAGE               COMMAND                  SERVICE             STATUS
airflow-init        olist-airflow:2.9.3 "/bin/bash -c 'airfl…"   airflow-init        exited (0)
airflow-postgres    postgres:16-alpine  "docker-entrypoint.s…"   postgres            Up (healthy)
airflow-scheduler   olist-airflow:2.9.3 "/usr/bin/dumb-init …"   airflow-scheduler   Up
airflow-webserver   olist-airflow:2.9.3 "/usr/bin/dumb-init …"   airflow-webserver   Up (healthy)
```

---

### 7.4 Trigger & Monitor DAG in Airflow UI
1. Open your browser and navigate to: **`http://localhost:8080`**.
2. **Log in:** Username `admin` | Password `admin`.
3. Locate DAG **`olist_daily_pipeline`**.
4. Toggle the switch on the left from *Paused* to **Active** (Blue).
5. On the right side, click the **Trigger DAG** (▶) button.
6. Click on the DAG name `olist_daily_pipeline` -> open the **Graph** tab.
7. **Watch the execution flow:**
   - `trigger_airbyte_sync` runs -> calls Airbyte API -> turns **Dark Green**.
   - `dbt_run_staging` runs -> builds views in Redshift -> turns **Dark Green**.
   - `dbt_run_marts` runs -> builds physical tables -> turns **Dark Green**.
   - `dbt_test` runs -> executes 21 assertions -> turns **Dark Green**.
   - `log_pipeline_summary` runs -> turns **Dark Green**.
8. Click on `log_pipeline_summary` -> click **Logs** -> observe the final success banner:
   ```text
   ========================================================================
   🎉 OLIST DAILY PIPELINE EXECUTION SUCCESS
   ========================================================================
   Execution Date: 2026-11-02
   Orchestrator  : Apache Airflow (LocalExecutor)
   Layers Updated:
     1. Source Ingestion  : Postgres -> Redshift 'raw' (Airbyte OSS)
     2. Staging Models    : Redshift 'staging' views (dbt-redshift)
     3. Analytical Marts  : Redshift 'marts' tables (dbt-redshift)
     4. Quality Assurance : Schema & Business rule assertions PASSED (0 failures)
   Status: All downstream tables ready for Streamlit Conversational BI querying.
   ========================================================================
   ```

---

### 7.5 Common Airflow Issues & Fixes
- **Issue: `trigger_airbyte_sync` fails with `ConnectionRefusedError: [Errno 111]`**
  - *Fix:* The container cannot reach `localhost:8000`. Verify `extra_hosts: ["host.docker.internal:host-gateway"]` is present in `docker-compose.yml`, and ensure `AIRBYTE_API_URL` uses `host.docker.internal:8000`.
- **Issue: `dbt_run_staging` fails with `dbt: not found`**
  - *Fix:* Ensure the task calls `/opt/dbt-venv/bin/dbt` rather than system `dbt`.
- **Issue: Task logs show `AIRBYTE_CONNECTION_ID is not configured`**
  - *Fix:* Populate `AIRBYTE_CONNECTION_ID` in `airflow/.env` and restart the stack (`make airflow-down && make airflow-up`).

> [!NOTE]
> **CHECKPOINT 7:**
> - Airflow Web UI shows all 5 nodes of `olist_daily_pipeline` in dark green (`success`).
> - Task logs confirm Airbyte sync and dbt test completion.
> - **Screenshot for report:** Airflow Graph View displaying all 5 dark green task nodes.

---

## PART 8: Launch Conversational BI Web App (Streamlit + LLM)

*Why this exists (Viva Defense):* Enables business executives to query the data warehouse using plain English. Our Abstract Syntax Tree (AST) validator (`sqlglot`) deterministically prevents prompt injection and unauthorized queries.

### 8.1 Obtain a Free Google Gemini API Key
The application defaults to `LLM_PROVIDER=gemini`. Google Gemini offers a generous free tier for developers:
1. Navigate to [Google AI Studio](https://aistudio.google.com/).
2. Sign in with your Google account.
3. Click the blue **Get API key** button -> click **Create API key in new project**.
4. Copy the generated key (format: `AIzaSy...`).
5. Open your root `.env` file and set:
   ```bash
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=AIzaSy...your-actual-key...
   ```
*(Note: If you do not have an API key right now, leave it blank; the app automatically engages a built-in Mock LLM adapter providing realistic SQL for all sample questions!)*

---

### 8.2 Launch the Streamlit Web Application
In your WSL terminal:
```bash
cd ~/de-project
# Run Streamlit using the project virtual environment
~/de-project/.venv/bin/streamlit run app/streamlit_app.py
```
**Expected Output:**
```text
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://172.x.x.x:8501
```
Open your browser to: **`http://localhost:8501`**.

---

### 8.3 Test the 6 Clickable Sample Questions
In the left sidebar, click each sample question and verify the generated response:

1. **"What are the top 5 product categories by total revenue?"**
   - *Verified SQL:* Aggregates `mart_top_products` grouped by `category_name`, ordered by `total_revenue DESC LIMIT 5`.
   - *Display:* Interactive table and comparative **bar chart** showing `health_beauty`, `bed_bath_table`, etc.
2. **"Show the daily sales trend and average order value for the last 30 days."**
   - *Verified SQL:* Queries `mart_daily_sales` ordered by `sales_date DESC LIMIT 30`.
   - *Display:* Multi-series **line chart** showing revenue trends.
3. **"Which Brazilian states have the highest customer lifetime spend?"**
   - *Verified SQL:* Aggregates `mart_customer_summary` grouped by `customer_state`.
   - *Display:* Table showing state rankings (`SP`, `RJ`, `MG`).
4. **"What percentage of orders were delivered late each month?"**
   - *Verified SQL:* Queries `mart_delivery_performance` calculating `pct_late_vs_estimated`.
   - *Display:* Monthly metrics table and trend line.
5. **"Who are the top 10 customers by total spend?"**
   - *Verified SQL:* Queries `mart_customer_summary` ordered by `total_spend DESC LIMIT 10`.
   - *Display:* Table with customer IDs and spend amounts.
6. **"What is the average delivery duration in days compared to estimated delivery days?"**
   - *Verified SQL:* Queries `avg_delivery_days` vs `avg_estimated_delivery_days` in `mart_delivery_performance`.
   - *Display:* Comparative logistics metrics.

---

### 8.4 Demonstrate Defense-in-Depth Security Guardrail (Viva Highlight)
Type the following malicious query into the chat input:
```text
DROP TABLE marts.mart_daily_sales;
```
**Observed Result:**
The application immediately displays a warning banner:
`🛡️ Query Rejected by Security Guardrail: Security Violation: Forbidden statement type 'DROP'. Only read-only SELECT queries are permitted.`
*Viva Explanation:* Even if an attacker uses prompt injection to trick an LLM, our deterministic `sqlglot` AST parser rejects destructive queries before they ever reach Redshift. Furthermore, the database connection uses `app_readonly`, which lacks DDL/DML permissions.

> [!NOTE]
> **CHECKPOINT 8:**
> - Streamlit app renders at `http://localhost:8501`.
> - Sample questions return verified SQL, data tables, and dynamic charts.
> - Security injection test displays the red guardrail rejection banner.
> - **Screenshot for report:** Streamlit UI showing a answered query with both table and chart visible, plus the security rejection alert.

---

## PART 9: End-to-End Demo Rehearsal & Evidence Checklist

### 9.1 Ordered Cold-Start Execution Routine
Follow this exact execution checklist for your final evaluation:

1. **Start Source Database:**
   ```bash
   make source-up
   ```
2. **Start Airbyte OSS:**
   ```bash
   abctl local start
   ```
3. **Verify Redshift Workgroup Status:**
   Open AWS Console -> Amazon Redshift Serverless -> Verify `olist-wg` is **Available**.
4. **Start Airflow Stack:**
   ```bash
   make airflow-up
   ```
5. **Trigger Airflow DAG:**
   Open `http://localhost:8080` -> Trigger `olist_daily_pipeline` -> Wait for all 5 tasks to turn **Dark Green**.
6. **Launch Conversational BI:**
   ```bash
   make app-run
   ```
7. **Ask 3 Questions in Streamlit (`http://localhost:8501`):**
   - Click Sample Question 1 (Top Categories).
   - Click Sample Question 2 (Daily Sales Trend).
   - Type Malicious Query (`DROP TABLE marts.mart_top_products;`) to show security defense.

---

### 9.2 Complete Evidence Screenshots Checklist for Project Report

Save all screenshots into a dedicated folder (e.g. `report_screenshots/`):

| Step | Screen / Window to Capture | Recommended File Name |
| :---: | :--- | :--- |
| **1** | Terminal output showing `docker ps` with `olist-postgres` healthy | `01_source_postgres_container.png` |
| **2** | Postgres order count query showing `99,441` rows | `02_postgres_orders_count.png` |
| **3** | AWS S3 Console showing staging bucket and lifecycle rule | `03_aws_s3_staging_bucket.png` |
| **4** | AWS IAM Console showing `airbyte-user` and `redshift-s3-role` | `04_aws_iam_least_privilege.png` |
| **5** | AWS Redshift Serverless overview: `olist-wg` (8 RPUs, `ap-south-1`) | `05_redshift_serverless_overview.png` |
| **6** | Redshift Query Editor v2 displaying `raw`, `staging`, and `marts` | `06_redshift_query_editor_schemas.png` |
| **7** | Airbyte UI showing Green `Succeeded` sync for 6 tables | `07_airbyte_sync_succeeded.png` |
| **8** | Terminal running `dbt run` with 9 models passing | `08_dbt_run_terminal.png` |
| **9** | Terminal running `dbt test` with 21 data assertions passing | `09_dbt_test_terminal.png` |
| **10**| Browser view of `dbt docs` interactive lineage DAG graph | `10_dbt_lineage_graph.png` |
| **11**| Airflow UI Graph view showing all 5 dark green task nodes | `11_airflow_dag_graph_green.png` |
| **12**| Airflow task execution log showing pipeline summary | `12_airflow_pipeline_summary_log.png` |
| **13**| Streamlit Conversational BI chat interface with verified SQL & table | `13_streamlit_conversational_bi.png` |
| **14**| Streamlit trend chart visualization | `14_streamlit_trend_chart.png` |
| **15**| Streamlit security guardrail blocking a `DROP TABLE` injection | `15_streamlit_security_rejection.png` |

---

## PART 10: Daily Shutdown & Complete Post-Demo Teardown

### 10.1 Daily Shutdown Routine (Preserves RAM & Zero Inactive Spend)
Whenever you finish working for the day:

1. **Stop Streamlit:** Press `Ctrl+C` in the Streamlit terminal.
2. **Stop Airflow Containers (Frees ~4 GB RAM):**
   ```bash
   make airflow-down
   ```
3. **Stop Airbyte OSS (Frees ~3 GB RAM):**
   ```bash
   abctl local stop
   ```
4. **Stop Source Postgres Container:**
   ```bash
   make source-down
   ```
5. **Redshift Serverless:** Automatically pauses query billing when idle. No action is strictly required for overnight storage if you plan to work the next day.

---

### 10.2 Final Post-Demo Teardown Checklist (Guarantees $0 Ongoing Cost)
After your college evaluation and viva presentation are finished, delete all cloud resources to ensure zero ongoing credit consumption:

1. **Delete Redshift Serverless Workgroup:**
   - Redshift Console -> **Redshift Serverless** -> Workgroups -> Select `olist-wg` -> Actions -> **Delete** -> Confirm.
2. **Delete Redshift Serverless Namespace:**
   - Redshift Serverless -> Namespaces -> Select `olist-ns` -> Actions -> **Delete** -> Choose *Do not create final snapshot* -> Confirm.
3. **Empty and Delete S3 Staging Bucket:**
   - S3 Console -> Select `olist-pipeline-<your-initials>-<random4digits>` -> Click **Empty** -> Type `permanently delete` -> Click **Empty**.
   - After emptying, click **Delete bucket** -> Type the bucket name -> Click **Delete bucket**.
4. **Delete IAM User & Keys:**
   - IAM Console -> **Users** -> Select `airbyte-user` -> Click **Delete**.
5. **Delete IAM Role:**
   - IAM Console -> **Roles** -> Select `redshift-s3-role` -> Click **Delete**.
6. **Delete Security Group:**
   - VPC Console -> **Security groups** -> Select `olist-redshift-sg` -> Actions -> **Delete security group**.
7. **Delete CloudWatch Budget:**
   - Billing Console -> **Budgets** -> Select `student-safety-budget` -> Actions -> **Delete**.
8. **Next Day Billing Check:**
   - Log into AWS the following day, open **Billing and Cost Management**, and confirm that current active spend has stopped.

---

## PART 11: Comprehensive Troubleshooting Matrix (25+ Scenarios)

| Scenario ID | Error / Symptom | Probable Cause | Exact Click-by-Click Solution |
| :---: | :--- | :--- | :--- |
| **1** | `psycopg2.OperationalError: Connection timed out (port 5439)` | Public IP address changed after reconnecting Wi-Fi | Re-run `curl -s https://checkip.amazonaws.com`, open VPC Security Groups -> `olist-redshift-sg` -> Inbound Rules -> Edit -> Change port 5439 source to **My IP** -> Save. |
| **2** | `Redshift Serverless status shows: Failed / Error` | AWS account restricted or Base capacity set too high | Check Billing for account verification status. Ensure Base Capacity is set to **8 RPUs**. Recreate the workgroup if necessary. |
| **3** | `Airbyte sync fails: Access Denied to S3 bucket` | IAM policy on `airbyte-user` does not match bucket name | Open IAM -> Policies -> `AirbyteS3StagingWritePolicy` -> Verify bucket ARN matches `arn:aws:s3:::<your-actual-bucket-name>/*`. |
| **4** | `Redshift COPY command fails: S3 read access denied` | IAM Role `redshift-s3-role` is not associated with namespace | Open Redshift Serverless -> Namespace `olist-ns` -> Click *Manage IAM roles* -> Associate `redshift-s3-role`. |
| **5** | `dbt run fails: relation "raw.orders" does not exist` | Airbyte replication has not been executed yet | Open Airbyte UI (`http://localhost:8000`) -> Connections -> `Olist Postgres to Redshift` -> Click **Sync now**. |
| **6** | `dbt run fails: permission denied for schema marts` | User `dbt_user` missing schema ownership or grants | Connect as `awsadmin` in Query Editor v2 and run: `GRANT ALL ON SCHEMA marts TO dbt_user; GRANT ALL ON SCHEMA staging TO dbt_user;`. |
| **7** | `dbt test fails: assert_revenue_is_non_negative` | Negative numerical values present in orders or prices | Inspect the failing rows: `SELECT * FROM marts.mart_daily_sales WHERE total_revenue < 0;`. Verify upstream source data. |
| **8** | `Airflow task trigger_airbyte_sync fails: HTTP 401 Unauthorized` | Airbyte API Client Secret has expired or is invalid | Open Airbyte UI -> Settings -> Applications -> Create a new application -> Copy the new secret into `airflow/.env`. |
| **9** | `Airflow task fails: ConnectionRefused to host.docker.internal` | Docker host gateway mapping missing on Linux/WSL | Verify `extra_hosts: ["host.docker.internal:host-gateway"]` is present in `airflow/docker-compose.yml`. |
| **10**| `Docker Desktop crashes / system freezes (OOM)` | Total RAM allocated to containers exceeded host physical limits | Run `docker stats` to identify high-memory containers. Stop unnecessary containers (`make source-down` or `make airflow-down`). |
| **11**| `Query Editor v2: Password authentication failed for awsadmin` | Password typo or special character escaping error | In Redshift Serverless namespace `olist-ns`, click *Actions* -> *Edit admin password* to reset it, then update your private notes. |
| **12**| `Streamlit app shows: Query Rejected by Security Guardrail` | Query contained non-marts tables or DDL commands | Review the rejection reason in the chat box. The AST validator intentionally blocked the query to preserve security. |
| **13**| `Streamlit app displays: Gemini API quota exceeded` | Free tier API limits temporarily saturated | Wait 60 seconds and re-submit, or toggle to `LLM_PROVIDER=mock` in root `.env` to demonstrate offline. |
| **14**| `Airbyte source check fails: Connection to localhost:5433 refused` | Airbyte container cannot resolve `localhost` of host machine | In the Airbyte Postgres source configuration, change Host from `localhost` to `host.docker.internal`. |
| **15**| `Postgres source container olist-postgres is not starting` | Port 5433 is already occupied by another local service | Run `netstat -ano | findstr 5433` (in Windows) to identify and terminate conflicting background processes. |
| **16**| `Airflow webserver displays: DAG olist_daily_pipeline not found` | DAG file has a Python syntax or import error | Run `docker compose -f airflow/docker-compose.yml logs airflow-scheduler` to inspect the exact Python traceback. |
| **17**| `dbt debug: profiles.yml file [NOT FOUND]` | dbt command executed from wrong working directory | Make sure you execute dbt commands from inside `dbt/olist_dbt/` where `profiles.yml` and `dbt_project.yml` reside. |
| **18**| `Redshift RPU usage limit reached: Query execution stopped` | Cost safety guardrail activated after 4 RPU-hours | This is working as intended! If you need more testing capacity, edit the usage limit in `olist-wg` -> *Limits* to 6 RPU-hours. |
| **19**| `Streamlit shows: Table marts.mart_daily_sales does not exist` | Marts models were not built in the warehouse | Run `dbt run --select marts` in your terminal to build the physical analytical tables in Redshift. |
| **20**| `S3 bucket creation fails: Bucket name already exists` | Bucket name collision across AWS worldwide | Add unique numbers or your initials to the end: `olist-pipeline-<initials>-<random5digits>`. |
| **21**| `Airbyte connection check fails: SSL connection error` | SSL mode set incorrectly for local Postgres | In Airbyte Postgres source settings, ensure **SSL Mode** is explicitly set to `disable`. |
| **22**| `WSL terminal: /bin/bash^M: bad interpreter` | File saved with Windows CRLF line endings instead of Linux LF | In WSL, run `dos2unix <filename>` or change line endings in VS Code bottom status bar to **LF**. |
| **23**| `Airflow scheduler container keeps restarting (Exit Code 1)` | Incompatible database connection string or missing UID | Verify `AIRFLOW_UID=50000` is present in `airflow/.env` and `AIRFLOW__CORE__EXECUTOR` is `LocalExecutor`. |
| **24**| `Streamlit chart fails to render or shows empty box` | Query returned 0 rows or non-numeric columns | Check the generated SQL in the expander. Rephrase the question to target non-empty date ranges or categories. |
| **25**| `AWS billing shows unexpected S3 storage fees` | Staging objects were not purged automatically | Ensure S3 bucket lifecycle rule is active (Part 1.2) and Airbyte destination setting **Purge Staging Files** is set to `Yes`. |
| **26**| `dbt test fails: relationships constraint between orders and customers` | Incomplete raw dataset loaded into Postgres | Verify that all 6 CSV files were loaded without errors via `python source/load_olist.py`. |
