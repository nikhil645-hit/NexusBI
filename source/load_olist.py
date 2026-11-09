import os

import pandas as pd
from sqlalchemy import create_engine

pw = os.environ["PG_PASSWORD"]
engine = create_engine(f"postgresql+psycopg2://olist:{pw}@localhost:5433/olist")

DATA = "../data/"
tables = {
    "customers": ("olist_customers_dataset.csv", []),
    "orders": ("olist_orders_dataset.csv", [
        "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date",
        "order_estimated_delivery_date"]),
    "order_items": ("olist_order_items_dataset.csv", ["shipping_limit_date"]),
    "order_payments": ("olist_order_payments_dataset.csv", []),
    "products": ("olist_products_dataset.csv", []),
    "category_translation": ("product_category_name_translation.csv", []),
}

for name, (file, dates) in tables.items():
    df = pd.read_csv(DATA + file, parse_dates=dates)
    df.to_sql(name, engine, if_exists="replace", index=False, chunksize=10000)
    print(f"{name}: {len(df)} rows loaded")
