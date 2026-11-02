# Data Dictionary: Olist E-Commerce Pipeline

This data dictionary documents all tables and columns across the three logical layers of the project:
1. **Raw Schema (`raw`)**: Untouched landing zone loaded by Airbyte from local PostgreSQL.
2. **Staging Schema (`staging`)**: Cleansed and standardized views managed by dbt.
3. **Marts Schema (`marts`)**: Curated star-schema analytical tables optimized for reporting and conversational BI.

---

## 1. Raw Layer (`raw`)

Data in this schema mirrors the source transactional database (`olist-postgres`). It contains raw source columns plus Airbyte extraction metadata (e.g., `_airbyte_raw_id`, `_airbyte_extracted_at`).

### `raw.customers`
- **Description:** Customer identity and geographical location.
- **Grain:** One record per customer order registration.

| Column Name | Data Type | Description |
| :--- | :--- | :--- |
| `customer_id` | VARCHAR | Order-level customer identifier (foreign key for orders). |
| `customer_unique_id` | VARCHAR | Unique physical customer identifier across multiple purchases. |
| `customer_zip_code_prefix` | VARCHAR / INT | First 5 digits of Brazilian zip code (CEP). |
| `customer_city` | VARCHAR | City name of customer residence. |
| `customer_state` | VARCHAR | Two-letter Brazilian state code (e.g., `SP`, `RJ`, `MG`). |

### `raw.orders`
- **Description:** Order lifecycle milestones and fulfillment tracking.
- **Grain:** One record per customer order.

| Column Name | Data Type | Description |
| :--- | :--- | :--- |
| `order_id` | VARCHAR | Unique order identifier (Primary Key). |
| `customer_id` | VARCHAR | Foreign key linking to `raw.customers`. |
| `order_status` | VARCHAR | Lifecycle state: `delivered`, `shipped`, `canceled`, `invoiced`, `processing`, etc. |
| `order_purchase_timestamp` | TIMESTAMP | Timestamp when order was placed. |
| `order_approved_at` | TIMESTAMP | Timestamp of payment confirmation. |
| `order_delivered_carrier_date` | TIMESTAMP | Timestamp when order was handed to logistics partner. |
| `order_delivered_customer_date`| TIMESTAMP | Actual delivery timestamp to customer. |
| `order_estimated_delivery_date`| TIMESTAMP | Promised delivery date committed to customer at purchase. |

### `raw.order_items`
- **Description:** Line items associated with each order transaction.
- **Grain:** One record per product line item within an order.

| Column Name | Data Type | Description |
| :--- | :--- | :--- |
| `order_id` | VARCHAR | Foreign key linking to `raw.orders`. |
| `order_item_id` | INTEGER | Sequential line item number within the order (1, 2, 3...). |
| `product_id` | VARCHAR | Foreign key linking to `raw.products`. |
| `seller_id` | VARCHAR | Unique seller identifier. |
| `shipping_limit_date` | TIMESTAMP | Seller shipping deadline to carrier. |
| `price` | NUMERIC | Item price in Brazilian Reais (BRL). |
| `freight_value` | NUMERIC | Shipping freight charge allocated to this item. |

### `raw.order_payments`
- **Description:** Payment transactions and installments per order.
- **Grain:** One record per payment transaction method.

| Column Name | Data Type | Description |
| :--- | :--- | :--- |
| `order_id` | VARCHAR | Foreign key linking to `raw.orders`. |
| `payment_sequential` | INTEGER | Sequence number of payment method used. |
| `payment_type` | VARCHAR | Payment method: `credit_card`, `boleto`, `voucher`, `debit_card`. |
| `payment_installments` | INTEGER | Number of payment installments chosen. |
| `payment_value` | NUMERIC | Transaction payment amount in BRL. |

### `raw.products`
- **Description:** Product catalog attributes and physical dimensions.
- **Grain:** One record per product item.

| Column Name | Data Type | Description |
| :--- | :--- | :--- |
| `product_id` | VARCHAR | Unique product identifier (Primary Key). |
| `product_category_name` | VARCHAR | Portuguese category name. |
| `product_name_lenght` | INTEGER | Length of product title. |
| `product_description_lenght` | INTEGER | Length of product description. |
| `product_photos_qty` | INTEGER | Number of product catalog photos. |
| `product_weight_g` | NUMERIC | Weight in grams. |
| `product_length_cm` | NUMERIC | Length in centimeters. |
| `product_height_cm` | NUMERIC | Height in centimeters. |
| `product_width_cm` | NUMERIC | Width in centimeters. |

### `raw.category_translation`
- **Description:** Portuguese-to-English product category mapping.
- **Grain:** One record per product category.

| Column Name | Data Type | Description |
| :--- | :--- | :--- |
| `product_category_name` | VARCHAR | Category name in Portuguese. |
| `product_category_name_english`| VARCHAR | Translated category name in English. |

---

## 2. Staging Layer (`staging`)

Staging views clean, cast, and rename columns while dropping Airbyte ingestion metadata. Staging models do not perform heavy aggregations.

### `staging.stg_customers` (View)
- `customer_id` (VARCHAR): Standardized order-level customer key.
- `customer_unique_id` (VARCHAR): Unique buyer identity.
- `customer_zip_code_prefix` (VARCHAR): Cleansed 5-digit zip code.
- `customer_city` (VARCHAR): Lowercase trimmed city name.
- `customer_state` (VARCHAR): Uppercase 2-letter state code.

### `staging.stg_orders` (View)
- `order_id` (VARCHAR): Unique order ID.
- `customer_id` (VARCHAR): Foreign key to `stg_customers`.
- `order_status` (VARCHAR): Validated status (`delivered`, `shipped`, `canceled`, etc.).
- `order_purchase_timestamp` (TIMESTAMP): Purchase timestamp.
- `order_purchase_date` (DATE): Extracted calendar date.
- `order_approved_at` (TIMESTAMP): Payment approval timestamp.
- `order_delivered_carrier_date` (TIMESTAMP): Hand-off to carrier.
- `order_delivered_customer_date` (TIMESTAMP): Actual customer receipt.
- `order_estimated_delivery_date` (TIMESTAMP): SLA delivery target.

### `staging.stg_order_items` (View)
- `order_id` (VARCHAR): Order reference.
- `order_item_id` (INTEGER): Item sequence.
- `product_id` (VARCHAR): Product reference.
- `seller_id` (VARCHAR): Seller reference.
- `shipping_limit_date` (TIMESTAMP): Shipping deadline.
- `price` (NUMERIC(10,2)): Cleansed unit price.
- `freight_value` (NUMERIC(10,2)): Cleansed freight cost.
- `total_item_cost` (NUMERIC(10,2)): Computed `price + freight_value`.

### `staging.stg_order_payments` (View)
- `order_id` (VARCHAR): Order reference.
- `payment_sequential` (INTEGER): Payment method index.
- `payment_type` (VARCHAR): Normalized payment channel.
- `payment_installments` (INTEGER): Installment count.
- `payment_value` (NUMERIC(10,2)): Monetary amount.

### `staging.stg_products` (View)
- `product_id` (VARCHAR): Product reference.
- `category_name_portuguese` (VARCHAR): Original category name.
- `category_name` (VARCHAR): Translated English category name (`unknown` if unmapped).
- `product_name_length` (INTEGER): Corrected spelling alias.
- `product_description_length` (INTEGER): Description length.
- `product_photos_qty` (INTEGER): Photo count.
- `weight_g`, `length_cm`, `height_cm`, `width_cm` (NUMERIC(10,2)): Standardized physical dimensions.

---

## 3. Marts Layer (`marts`)

Physical analytical tables optimized for queries from Streamlit, dashboards, and BI tools.

### `marts.mart_daily_sales` (Table)
- **Description:** Daily sales performance tracking order counts, merchandise volume, and revenues.
- **Grain:** One record per purchase date (`sales_date`).

| Column Name | Data Type | Description | Sample Value |
| :--- | :--- | :--- | :--- |
| `sales_date` | DATE | Calendar date of order purchase (Primary Key). | `2018-05-15` |
| `total_orders` | INTEGER | Number of distinct non-canceled orders. | `245` |
| `total_items_sold` | INTEGER | Total line item units sold. | `288` |
| `total_revenue` | NUMERIC(10,2) | Gross merchandise revenue (sum of item prices). | `34200.10` |
| `total_freight` | NUMERIC(10,2) | Total freight fees collected. | `4520.50` |
| `avg_order_value` | NUMERIC(10,2) | Average order value (`total_revenue / total_orders`). | `139.59` |

### `marts.mart_top_products` (Table)
- **Description:** Product-level performance leaderboard ranked by revenue and units sold.
- **Grain:** One record per product ID (`product_id`).

| Column Name | Data Type | Description | Sample Value |
| :--- | :--- | :--- | :--- |
| `product_id` | VARCHAR | Unique product identifier (Primary Key). | `bb50f2e236e5eee0100688a1c0d074b7` |
| `category_name` | VARCHAR | English category name. | `health_beauty` |
| `units_sold` | INTEGER | Total units purchased across non-canceled orders. | `9670` |
| `total_revenue` | NUMERIC(10,2) | Total gross revenue generated. | `1258681.34` |
| `avg_unit_price` | NUMERIC(10,2) | Average unit sale price. | `130.16` |
| `revenue_rank` | INTEGER | Dense rank based on revenue (1 = highest revenue). | `1` |
| `units_sold_rank`| INTEGER | Dense rank based on unit sales volume. | `2` |

### `marts.mart_customer_summary` (Table)
- **Description:** Customer analytical profile capturing geographic location, lifetime spend, and lifecycle dates.
- **Grain:** One record per physical buyer (`customer_unique_id`).

| Column Name | Data Type | Description | Sample Value |
| :--- | :--- | :--- | :--- |
| `customer_unique_id` | VARCHAR | Unique physical customer ID (Primary Key). | `8d50f5eadf50201ccdcedfb9e2ac8455` |
| `customer_city` | VARCHAR | Primary residential city. | `sao paulo` |
| `customer_state` | VARCHAR | Primary state code. | `SP` |
| `total_orders` | INTEGER | Lifetime order count completed. | `16` |
| `total_spend` | NUMERIC(10,2) | Lifetime expenditure (merchandise + freight). | `1248.50` |
| `first_order_date` | TIMESTAMP | Timestamp of earliest purchase. | `2017-05-15 10:20:00` |
| `last_order_date` | TIMESTAMP | Timestamp of most recent purchase. | `2018-08-20 14:32:00` |

### `marts.mart_delivery_performance` (Table)
- **Description:** Monthly delivery fulfillment analytics measuring carrier lead times and SLA breach rates.
- **Grain:** One record per year and month (`year_month`).

| Column Name | Data Type | Description | Sample Value |
| :--- | :--- | :--- | :--- |
| `year_month` | VARCHAR | Calendar month formatted as YYYY-MM (Primary Key). | `2018-05` |
| `order_month` | DATE | Truncated first day of month. | `2018-05-01` |
| `total_delivered_orders` | INTEGER | Total orders successfully delivered to customers. | `6873` |
| `avg_delivery_days` | NUMERIC(10,2) | Average elapsed days from purchase to delivery. | `11.20` |
| `avg_estimated_delivery_days`| NUMERIC(10,2) | Average days promised at checkout. | `23.40` |
| `late_orders_count` | INTEGER | Number of orders delivered past estimated date. | `412` |
| `pct_late_vs_estimated` | NUMERIC(10,2) | Percentage of orders delivered late (`late / total`). | `6.00` |
