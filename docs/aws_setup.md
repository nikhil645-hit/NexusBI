# AWS Setup Guide: Redshift Serverless & S3 (ap-south-1 Mumbai)

> [!NOTE]
> This guide is tailored for students and beginners. It details how to set up Amazon Redshift Serverless with minimal cost safeguards, configure an S3 bucket for Airbyte staging, and safely delete all cloud resources after your demo.

---

## 1. Prerequisites
- An active AWS Account.
- AWS Management Console logged in with an IAM Admin user (not root, if possible).
- AWS Region: Ensure the top-right console dropdown is set to **Asia Pacific (Mumbai) `ap-south-1`**.

---

## 2. Step 1: Create S3 Staging Bucket (For Airbyte)

Airbyte transfers bulk data into Redshift by staging CSV/Parquet files in S3 and issuing Redshift's fast parallel `COPY` command.

1. Navigate to **S3** in the AWS Console.
2. Click **Create bucket**.
3. **Bucket name:** `olist-airbyte-staging-<your-student-id>` (bucket names are globally unique; use lowercase, hyphens, and numbers).
4. **AWS Region:** `Asia Pacific (Mumbai) ap-south-1`.
5. **Block Public Access:** Keep **Block all public access** checked (Airbyte uses authenticated AWS IAM credentials, not public access).
6. **Bucket Versioning:** Disabled.
7. Click **Create bucket**.

### Lifecycle Rule (Auto-cleanup to save storage cost)
1. Click your newly created bucket -> open the **Management** tab.
2. Scroll to **Lifecycle rules** -> click **Create lifecycle rule**.
3. **Rule name:** `auto-delete-staging-files`.
4. **Rule scope:** Choose *Apply to all objects in the bucket* (check the acknowledgement box).
5. **Lifecycle rule actions:** Check *Expire current versions of objects*.
6. **Days after object creation:** Enter `1` (deletes temporary sync files after 24 hours).
7. Click **Create rule**.

---

## 3. Step 2: Create IAM User & Access Keys for Airbyte

Airbyte needs AWS programmatic credentials to write staging files to S3.

1. Navigate to **IAM** -> **Users** -> click **Create user**.
2. **User name:** `airbyte-s3-staging-user`.
3. Do **not** check "Provide user access to the AWS Management Console" (this is an API-only service user). Click **Next**.
4. In Permissions options, select **Attach policies directly**.
5. Click **Create policy** (opens a new tab):
   - Choose **JSON** tab and paste:
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
   - Replace `<your-bucket-name>` with your actual S3 bucket name.
   - Click **Next** -> Policy name: `AirbyteS3StagingPolicy` -> click **Create policy**.
6. Return to the user creation tab, click the refresh button, search for `AirbyteS3StagingPolicy`, check it, and click **Next** -> **Create user**.
7. Click on the user `airbyte-s3-staging-user` -> open the **Security credentials** tab.
8. Scroll to **Access keys** -> click **Create access key**.
9. Select **Application running outside AWS** -> click **Next** -> click **Create access key**.
10. **Copy the Access Key ID and Secret Access Key immediately**. You will paste them into `.env` and Airbyte destination settings.

---

## 4. Step 3: Redshift IAM Role (S3 Read Access)

Redshift needs permission to read staged files from your S3 bucket during the `COPY` command.

1. In IAM -> **Roles** -> click **Create role**.
2. **Trusted entity type:** AWS service -> **Use case:** `Redshift - Customizable`.
3. Click **Next**.
4. Search for the managed policy `AmazonS3ReadOnlyAccess`, select it, and click **Next**.
5. **Role name:** `RedshiftServerlessS3Role` -> click **Create role**.
6. Open the created role and copy its **ARN** (format: `arn:aws:iam::<account-id>:role/RedshiftServerlessS3Role`).

---

## 5. Step 4: Create Redshift Serverless Workgroup & Namespace

Amazon Redshift Serverless separates storage (**Namespace**) from compute (**Workgroup**).

1. Navigate to **Amazon Redshift** -> click **Redshift Serverless** in the left sidebar.
2. If this is your first time, click **Create workgroup** (or customized settings).
3. **Workgroup settings:**
   - **Workgroup name:** `olist-workgroup`.
   - **Base capacity:** Set to **8 RPUs** (Redshift Processing Units) — the lowest possible setting to minimize cost.
4. **Namespace settings:**
   - Choose **Customize settings** or create a new namespace.
   - **Namespace name:** `olist-namespace`.
   - **Database name:** `dev`.
   - **Admin user credentials:** Select *Manually set admin password*.
   - **Admin user name:** `admin`.
   - **Admin user password:** Enter a strong password (at least 8 chars, 1 uppercase, 1 lowercase, 1 number).
   - Under **Permissions / IAM roles**, click **Manage IAM roles** -> **Associate IAM roles** -> select `RedshiftServerlessS3Role` created in Step 3 -> click **Associate IAM roles**.
5. Click **Next** to Network configuration:
   - **VPC:** Default VPC.
   - **Security groups:** Leave default or create a dedicated security group (we configure port 5439 in Step 5).
   - **Turn ON "Publicly accessible"**: This allows local tools (dbt, Airbyte, Streamlit) to connect over the internet.
6. Click **Save** / **Create**. Wait 3–5 minutes for the status to show **Available**.

---

## 6. Step 5: Security Group Inbound Rule (Port 5439)

Allow your computer's IP address to reach Redshift on port `5439`.

1. Go to the Redshift Serverless console -> open your workgroup `olist-workgroup`.
2. Under **General information** -> click the linked **VPC security group**.
3. In the EC2 Security Groups console, click the **Inbound rules** tab -> click **Edit inbound rules**.
4. Click **Add rule**:
   - **Type:** Redshift (or Custom TCP).
   - **Port range:** `5439`.
   - **Source:** Select **My IP** (AWS automatically detects your public IP as `<your-ip>/32`).
     > [!TIP]
     > If your home/mobile WiFi reconnects and changes your IP, come back here and click **My IP** again to update the rule.
5. Click **Save rules**.

---

## 7. Step 6: Cost Guardrails (Usage Limits & AWS Budget)

Redshift Serverless only charges for query execution time in RPU-hours. We will set limits so a runaway query never runs up a bill.

### 1. Redshift Usage Limit
1. In the Redshift Serverless console, select your workgroup `olist-workgroup`.
2. Click the **Limits** tab -> under **Usage limits**, click **Manage usage limits**.
3. Click **Add limit**:
   - **Limit type:** RPU-hours.
   - **Amount:** `4` RPU-hours.
   - **Frequency:** Daily (or Monthly).
   - **Action:** Select **Alert** and/or **Turn off query execution**.
4. Click **Save**.

### 2. AWS Billing Budget Alert ($5 Safety Net)
1. In the top search bar, type **Budgets** -> open **AWS Budgets**.
2. Click **Create budget**.
3. Choose **Zero spend budget** or **Cost budget - Recommended**.
4. Enter budget amount: `$5.00` USD.
5. In email recipients, enter your student email address to receive alerts at 80% ($4.00).
6. Click **Create budget**.

---

## 8. Mapping AWS Console Values to `.env`

Copy these values from the AWS console into your project root `.env` file:

| AWS Console Location | Value Example | `.env` Key |
| :--- | :--- | :--- |
| Redshift Serverless -> Workgroup -> Endpoint (host before `:5439`) | `olist-workgroup.123456789012.ap-south-1.redshift-serverless.amazonaws.com` | `REDSHIFT_HOST` |
| Redshift Serverless default port | `5439` | `REDSHIFT_PORT` |
| Namespace -> Database name | `dev` | `REDSHIFT_DB` |
| Namespace -> Admin username | `admin` | `REDSHIFT_ADMIN_USER` |
| Namespace -> Admin password | *(Your chosen admin password)* | `REDSHIFT_ADMIN_PASSWORD` |
| S3 Console -> Bucket name | `olist-airbyte-staging-<id>` | `S3_BUCKET_NAME` |
| Region dropdown | `ap-south-1` | `AWS_REGION` |
| IAM User `airbyte-s3-staging-user` -> Access Key | `AKIAIOSFODNN7EXAMPLE` | `AWS_ACCESS_KEY_ID` |
| IAM User `airbyte-s3-staging-user` -> Secret Key | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` | `AWS_SECRET_ACCESS_KEY` |

---

## 9. 🛑 Teardown Checklist (Run After Project Demo)

To ensure zero ongoing charges after your evaluation:

- [ ] **Delete Redshift Workgroup:** Redshift Serverless -> Workgroups -> Select `olist-workgroup` -> Actions -> **Delete**.
- [ ] **Delete Redshift Namespace:** Redshift Serverless -> Namespaces -> Select `olist-namespace` -> Actions -> **Delete**.
- [ ] **Empty & Delete S3 Bucket:** S3 -> Select `olist-airbyte-staging-...` -> Click **Empty** (confirm) -> Click **Delete**.
- [ ] **Delete IAM User:** IAM -> Users -> Select `airbyte-s3-staging-user` -> **Delete**.
- [ ] **Delete IAM Role:** IAM -> Roles -> Select `RedshiftServerlessS3Role` -> **Delete**.
- [ ] **Delete Budget Alert:** AWS Budgets -> Select the budget -> Actions -> **Delete**.

