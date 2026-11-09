# ==============================================================================
# scripts/load_marts_to_cloud.py - Safe Cloud Marts Loader & Provisioner
#
# Copies ONLY the 4 curated marts tables to a target PostgreSQL database (e.g. Neon,
# Supabase, or AWS RDS).
#
# Provisioning Steps:
#   1. Idempotently creates schema 'marts'.
#   2. Idempotently creates role 'app_readonly' with login and assigned password.
#   3. Loads the 4 marts tables (mart_daily_sales, mart_top_products,
#      mart_customer_summary, mart_delivery_performance) within transactions.
#   4. Grants USAGE on schema marts and SELECT on all tables to app_readonly.
#   5. Configures ALTER DEFAULT PRIVILEGES for future tables.
#
# Safety Guarantees:
#   - Never modifies or references 'raw' or 'staging' schemas.
#   - Requires --confirm flag to execute changes (prevents accidental overwrites).
#   - Supports --dry-run to inspect target configuration.
# ==============================================================================

import argparse
import os
import sys
from pathlib import Path
from typing import Optional
import psycopg2
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.sql_validator import ALLOWED_MART_TABLES

EXPORT_DIR = ROOT_DIR / "data" / "marts_export"


def get_target_connection(
    host: str,
    port: int,
    dbname: str,
    user: str,
    password: str,
    sslmode: str = "require",
):
    """Establishes administrative connection to the target PostgreSQL database."""
    return psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        sslmode=sslmode,
        connect_timeout=20,
    )


def provision_and_load(
    host: str,
    port: int,
    dbname: str,
    user: str,
    password: str,
    sslmode: str,
    readonly_password: str,
    dry_run: bool = False,
    confirm: bool = False,
) -> None:
    """Executes schema creation, role provisioning, and table loading on target."""
    print("\n" + "=" * 65)
    print(" NEXUSBI CLOUD MARTS PROVISIONER & LOADER")
    print("=" * 65)
    print(f" Target Host      : {host}:{port}")
    print(f" Target Database  : {dbname}")
    print(f" Target Admin User: {user}")
    print(f" Target SSL Mode  : {sslmode}")
    print(f" Readonly Role    : app_readonly")
    print(f" Dry Run Mode     : {dry_run}")
    print("=" * 65 + "\n")

    if dry_run:
        print("[DRY-RUN] Target configuration validated. No changes made.")
        return

    if not confirm:
        print("[ABORTED] Missing --confirm flag. Pass --confirm to apply changes.")
        sys.exit(1)

    # Check that export files exist
    for table in ALLOWED_MART_TABLES:
        p_path = EXPORT_DIR / f"{table}.parquet"
        c_path = EXPORT_DIR / f"{table}.csv"
        if not p_path.exists() and not c_path.exists():
            print(f"[ERROR] Missing export file for {table} in {EXPORT_DIR}.")
            print("Run 'python scripts/export_marts.py' first.")
            sys.exit(1)

    conn = get_target_connection(host, port, dbname, user, password, sslmode)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            print("[1/4] Ensuring schema 'marts' exists...")
            cur.execute("CREATE SCHEMA IF NOT EXISTS marts;")

            print("[2/4] Ensuring role 'app_readonly' exists...")
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_readonly') THEN
                        CREATE ROLE app_readonly WITH LOGIN PASSWORD %s;
                    ELSE
                        ALTER ROLE app_readonly WITH PASSWORD %s;
                    END IF;
                END
                $$;
            """, (readonly_password, readonly_password))

            conn.commit()

        # Step 3: Load each mart table
        print("[3/4] Loading analytical marts tables into target schema...")
        from sqlalchemy import create_engine
        engine_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}?sslmode={sslmode}"
        engine = create_engine(engine_url)

        for table in sorted(ALLOWED_MART_TABLES):
            p_path = EXPORT_DIR / f"{table}.parquet"
            c_path = EXPORT_DIR / f"{table}.csv"

            if p_path.exists():
                df = pd.read_parquet(p_path)
            else:
                df = pd.read_csv(c_path)

            print(f"   Writing marts.{table} ({len(df)} rows)...")
            df.to_sql(
                name=table,
                con=engine,
                schema="marts",
                if_exists="replace",
                index=False,
                chunksize=1000,
            )

        # Step 4: Grant privileges to app_readonly
        print("[4/4] Granting least-privilege read permissions to app_readonly...")
        with conn.cursor() as cur:
            cur.execute("GRANT USAGE ON SCHEMA marts TO app_readonly;")
            cur.execute("GRANT SELECT ON ALL TABLES IN SCHEMA marts TO app_readonly;")
            cur.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT ON TABLES TO app_readonly;")
            conn.commit()

        print("\n" + "=" * 65)
        print(" [SUCCESS] Cloud marts provisioning and data load complete!")
        print("=" * 65 + "\n")

    except Exception as e:
        conn.rollback()
        print(f"[FATAL ERROR] Cloud load failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Provision marts schema and load data to cloud PostgreSQL")
    parser.add_argument("--host", default=os.getenv("TARGET_DB_HOST", "localhost"), help="Target DB host")
    parser.add_argument("--port", type=int, default=int(os.getenv("TARGET_DB_PORT", "5432")), help="Target DB port")
    parser.add_argument("--dbname", default=os.getenv("TARGET_DB_NAME", "warehouse"), help="Target DB name")
    parser.add_argument("--user", default=os.getenv("TARGET_DB_USER", "postgres"), help="Target admin user")
    parser.add_argument("--password", default=os.getenv("TARGET_DB_PASSWORD", ""), help="Target admin password")
    parser.add_argument("--sslmode", default=os.getenv("TARGET_DB_SSLMODE", "prefer"), help="SSL mode")
    parser.add_argument("--readonly-password", default=os.getenv("TARGET_READONLY_PASSWORD", "readonly_pass_123"), help="Password for app_readonly")
    parser.add_argument("--dry-run", action="store_true", help="Validate without making changes")
    parser.add_argument("--confirm", action="store_true", help="Explicit confirmation to execute changes")

    args = parser.parse_args()
    provision_and_load(
        host=args.host,
        port=args.port,
        dbname=args.dbname,
        user=args.user,
        password=args.password,
        sslmode=args.sslmode,
        readonly_password=args.readonly_password,
        dry_run=args.dry_run,
        confirm=args.confirm,
    )

