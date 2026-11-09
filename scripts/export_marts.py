# ==============================================================================
# scripts/export_marts.py - Safe Export of Curated Analytical Marts
#
# Copies ONLY the 4 curated marts tables from the warehouse to local storage:
#   - marts.mart_daily_sales
#   - marts.mart_top_products
#   - marts.mart_customer_summary
#   - marts.mart_delivery_performance
#
# Safety Guarantees:
#   - Read-only queries strictly on 'marts' schema.
#   - Never accesses 'raw' or 'staging' schemas.
#   - Exports to data/marts_export/ in parquet and CSV formats.
# ==============================================================================

import argparse
import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning, module="pandas")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db_helper import get_connection, is_warehouse_configured
from app.sql_validator import ALLOWED_MART_TABLES

EXPORT_DIR = ROOT_DIR / "data" / "marts_export"


def export_marts(output_format: str = "parquet") -> None:
    """Exports all 4 marts tables to the specified directory."""
    if not is_warehouse_configured():
        print("[ERROR] Warehouse is not configured. Check your .env file.")
        sys.exit(1)

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_connection()

    print("\n" + "=" * 65)
    print(" NEXUSBI MARTS EXPORT UTILITY")
    print("=" * 65)
    print(f" Output Directory : {EXPORT_DIR}")
    print(f" Target Tables    : {', '.join(sorted(ALLOWED_MART_TABLES))}")
    print("=" * 65 + "\n")

    for table in sorted(ALLOWED_MART_TABLES):
        print(f"[EXPORTING] marts.{table}...")
        query = f"SELECT * FROM marts.{table};"
        try:
            df = pd.read_sql_query(query, conn)
            row_count = len(df)

            if output_format in ("parquet", "both"):
                parquet_path = EXPORT_DIR / f"{table}.parquet"
                df.to_parquet(parquet_path, index=False)
                size_kb = round(parquet_path.stat().st_size / 1024, 2)
                print(f"   Saved {parquet_path.name} ({row_count} rows, {size_kb} KB)")

            if output_format in ("csv", "both"):
                csv_path = EXPORT_DIR / f"{table}.csv"
                df.to_csv(csv_path, index=False)
                size_kb = round(csv_path.stat().st_size / 1024, 2)
                print(f"   Saved {csv_path.name} ({row_count} rows, {size_kb} KB)")

        except Exception as e:
            print(f"[ERROR] Failed to export marts.{table}: {e}")
            conn.close()
            sys.exit(1)

    conn.close()
    print("\n" + "=" * 65)
    print(" [SUCCESS] All marts successfully exported!")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export curated marts tables to local files")
    parser.add_argument(
        "--format",
        choices=["parquet", "csv", "both"],
        default="parquet",
        help="Export file format (default: parquet)",
    )
    args = parser.parse_args()
    export_marts(output_format=args.format)
