# ==============================================================================
# app/dashboard_renderer.py - Enterprise Dynamic Dashboard Engine
#
# Generates and renders full-screen, production-grade analytical dashboards
# for Sales, Logistics/Delivery, Customers, Product Catalog, and 360 Overview.
#
# Connects directly to the curated marts schema on Cloud PostgreSQL (Neon / Local).
# Uses st.cache_data(ttl=600) for query result caching.
# ==============================================================================

import pandas as pd
import streamlit as st

from app.db_helper import execute_marts_query

# Streamlit caching helper with fallback for non-streamlit execution
try:
    _cache_data = st.cache_data
except Exception:

    def _cache_data(**kwargs):
        def dec(fn):
            return fn

        return dec


@_cache_data(ttl=600)
def fetch_sales_data() -> pd.DataFrame:
    """Fetches daily sales metrics from marts.mart_daily_sales (cached for 10m)."""
    sql = """
    SELECT
        sales_date,
        total_orders,
        total_items_sold,
        total_revenue,
        total_freight,
        avg_order_value
    FROM marts.mart_daily_sales
    ORDER BY sales_date ASC;
    """
    return execute_marts_query(sql)


@_cache_data(ttl=600)
def fetch_delivery_data() -> pd.DataFrame:
    """Fetches monthly logistics and delivery SLA metrics from marts.mart_delivery_performance."""
    sql = """
    SELECT
        year_month,
        total_delivered_orders,
        late_orders_count,
        pct_late_vs_estimated,
        avg_delivery_days,
        avg_estimated_delivery_days
    FROM marts.mart_delivery_performance
    ORDER BY year_month ASC;
    """
    return execute_marts_query(sql)


@_cache_data(ttl=600)
def fetch_customer_kpis() -> pd.DataFrame:
    """Fetches high-level buyer aggregates computed in SQL (1 row, <1s)."""
    sql = """
    SELECT
        COUNT(*) AS total_buyers,
        ROUND(SUM(total_spend)::numeric, 2) AS total_customer_spend,
        ROUND(AVG(total_spend)::numeric, 2) AS avg_spend_per_buyer,
        COUNT(*) FILTER (WHERE total_orders > 1) AS repeat_buyers,
        ROUND((COUNT(*) FILTER (WHERE total_orders > 1) * 100.0 / NULLIF(COUNT(*), 0))::numeric, 2) AS repeat_rate
    FROM marts.mart_customer_summary;
    """
    return execute_marts_query(sql)


@_cache_data(ttl=600)
def fetch_customer_state_spend(limit: int = 10) -> pd.DataFrame:
    """Fetches top Brazilian states by revenue aggregated in SQL (10 rows)."""
    sql = f"""
    SELECT
        customer_state,
        ROUND(SUM(total_spend)::numeric, 2) AS total_spend
    FROM marts.mart_customer_summary
    GROUP BY customer_state
    ORDER BY total_spend DESC
    LIMIT {limit};
    """
    return execute_marts_query(sql)


@_cache_data(ttl=600)
def fetch_customer_city_spend(limit: int = 10) -> pd.DataFrame:
    """Fetches top Brazilian cities by revenue aggregated in SQL (10 rows)."""
    sql = f"""
    SELECT
        customer_city,
        ROUND(SUM(total_spend)::numeric, 2) AS total_spend
    FROM marts.mart_customer_summary
    GROUP BY customer_city
    ORDER BY total_spend DESC
    LIMIT {limit};
    """
    return execute_marts_query(sql)


@_cache_data(ttl=600)
def fetch_customer_vip_leaderboard(limit: int = 15) -> pd.DataFrame:
    """Fetches top VIP customers ordered by total spend in SQL (15 rows)."""
    sql = f"""
    SELECT
        customer_unique_id,
        customer_city,
        customer_state,
        total_orders,
        total_spend
    FROM marts.mart_customer_summary
    ORDER BY total_spend DESC
    LIMIT {limit};
    """
    return execute_marts_query(sql)


@_cache_data(ttl=600)
def fetch_customer_data(limit: int = 100) -> pd.DataFrame:
    """Fetches buyer and geographic sample from marts.mart_customer_summary."""
    sql = f"""
    SELECT
        customer_unique_id,
        customer_city,
        customer_state,
        total_orders,
        total_spend,
        first_order_date,
        last_order_date
    FROM marts.mart_customer_summary
    ORDER BY total_spend DESC
    LIMIT {limit};
    """
    return execute_marts_query(sql)


@_cache_data(ttl=600)
def fetch_product_data(limit: int = 100) -> pd.DataFrame:
    """Fetches catalog and category leaderboard from marts.mart_top_products."""
    sql = f"""
    SELECT
        product_id,
        category_name,
        units_sold,
        total_revenue,
        revenue_rank
    FROM marts.mart_top_products
    ORDER BY revenue_rank ASC
    LIMIT {limit};
    """
    return execute_marts_query(sql)


# ------------------------------------------------------------------------------
# 1. Complete Sales & Revenue Dashboard
# ------------------------------------------------------------------------------
def render_sales_dashboard():
    st.markdown("### 📈 Comprehensive Sales & Revenue Dashboard")
    st.caption("Live metrics from PostgreSQL Data Warehouse `marts.mart_daily_sales` — Tracking orders, gross revenue, freight, and AOV.")

    with st.spinner("⚡ Loading live sales data from data warehouse..."):
        try:
            df = fetch_sales_data()
        except ConnectionError as ce:
            st.error(f"🚨 {ce}")
            return
        except Exception as e:
            st.error(f"Failed to load sales data from warehouse: {e}")
            return

    if df.empty:
        st.warning("No sales data found in warehouse marts.")
        return

    # Check for expected columns gracefully
    expected_cols = {"sales_date", "total_revenue", "total_orders", "total_items_sold", "total_freight", "avg_order_value"}
    missing_cols = expected_cols - set(df.columns)
    if missing_cols:
        st.warning(f"Sales data is missing expected columns: {', '.join(sorted(missing_cols))}. Displaying available metrics.")

    # Defensive KPI extraction
    total_rev = float(df["total_revenue"].sum()) if "total_revenue" in df.columns else 0.0
    total_ord = int(df["total_orders"].sum()) if "total_orders" in df.columns else 0
    total_items = int(df["total_items_sold"].sum()) if "total_items_sold" in df.columns else 0
    overall_aov = (total_rev / total_ord) if total_ord > 0 else 0.0
    total_freight = float(df["total_freight"].sum()) if "total_freight" in df.columns else 0.0

    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    kpi1.metric("Gross Revenue", f"${total_rev:,.2f}")
    kpi2.metric("Total Orders", f"{total_ord:,}")
    kpi3.metric("Items Sold", f"{total_items:,}")
    kpi4.metric("Avg Order Value", f"${overall_aov:,.2f}")
    kpi5.metric("Total Freight", f"${total_freight:,.2f}")

    st.markdown("---")

    # If sales_date is absent or empty, skip time filter and show raw table
    if "sales_date" not in df.columns or df["sales_date"].dropna().empty:
        st.info("Sales date column not available for time filtering.")
        with st.expander("📋 View Raw Daily Sales Data", expanded=False):
            st.dataframe(df, width="stretch")
        return

    df["sales_date"] = pd.to_datetime(df["sales_date"])
    min_date = df["sales_date"].min().date()
    max_date = df["sales_date"].max().date()

    # Interactive Filter Controls
    col_ctrl1, col_ctrl2 = st.columns([6, 4])
    with col_ctrl1:
        date_range = st.date_input(
            "Filter Date Range:",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            key="sales_date_range",
        )
    with col_ctrl2:
        granularity = st.radio("Aggregation Level:", ["Daily", "Monthly"], horizontal=True, key="sales_gran")

    # Apply date filtering
    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        df_filtered = df[(df["sales_date"].dt.date >= date_range[0]) & (df["sales_date"].dt.date <= date_range[1])].copy()
    else:
        df_filtered = df.copy()

    if df_filtered.empty:
        st.info("No sales records found for the selected date range.")
        return

    if granularity == "Monthly":
        df_filtered["period"] = df_filtered["sales_date"].dt.to_period("M").astype(str)
        agg_dict = {}
        for c in ["total_revenue", "total_orders", "total_freight"]:
            if c in df_filtered.columns:
                agg_dict[c] = "sum"
        if "avg_order_value" in df_filtered.columns:
            agg_dict["avg_order_value"] = "mean"

        if agg_dict:
            chart_df = df_filtered.groupby("period").agg(agg_dict).reset_index().set_index("period")
        else:
            chart_df = df_filtered.set_index("period")
    else:
        chart_df = df_filtered.set_index("sales_date")

    # Visual Multi-Chart Studio
    tab1, tab2, tab3 = st.tabs(["📊 Revenue & Freight Growth", "📦 Order Volume & Demand", "🏷️ Average Order Value (AOV)"])

    with tab1:
        st.markdown("##### Gross Revenue vs Freight Over Time")
        chart_cols = [c for c in ["total_revenue", "total_freight"] if c in chart_df.columns]
        if chart_cols:
            st.line_chart(chart_df[chart_cols])
        else:
            st.info("Revenue or Freight metrics not available.")

    with tab2:
        st.markdown("##### Order Volume")
        if "total_orders" in chart_df.columns:
            st.bar_chart(chart_df["total_orders"])
        else:
            st.info("Order count metrics not available.")

    with tab3:
        st.markdown("##### Average Order Value (AOV)")
        if "avg_order_value" in chart_df.columns:
            st.line_chart(chart_df["avg_order_value"])
        else:
            st.info("Average order value metrics not available.")

    # Detailed Data Table
    with st.expander("📋 View Raw Daily Sales Data", expanded=False):
        st.dataframe(df_filtered, width="stretch")


# ------------------------------------------------------------------------------
# 2. Complete Delivery & Logistics Dashboard
# ------------------------------------------------------------------------------
def render_delivery_dashboard():
    st.markdown("### 🚚 Delivery & Fulfillment SLA Dashboard")
    st.caption("Live metrics from PostgreSQL Data Warehouse `marts.mart_delivery_performance` — Carrier transit durations, on-time rates, and SLA gaps.")

    with st.spinner("⚡ Loading logistics data from data warehouse..."):
        try:
            df = fetch_delivery_data()
        except ConnectionError as ce:
            st.error(f"🚨 {ce}")
            return
        except Exception as e:
            st.error(f"Failed to load delivery data from warehouse: {e}")
            return

    if df.empty:
        st.warning("No delivery data found in warehouse marts.")
        return

    expected_cols = {"year_month", "total_delivered_orders", "late_orders_count", "pct_late_vs_estimated", "avg_delivery_days", "avg_estimated_delivery_days"}
    missing_cols = expected_cols - set(df.columns)
    if missing_cols:
        st.warning(f"Delivery data is missing expected columns: {', '.join(sorted(missing_cols))}. Displaying available metrics.")

    # Top KPI Metrics Row defensively
    total_delivered = int(df["total_delivered_orders"].sum()) if "total_delivered_orders" in df.columns else 0
    total_late = int(df["late_orders_count"].sum()) if "late_orders_count" in df.columns else 0
    overall_late_pct = (total_late / total_delivered * 100) if total_delivered > 0 else 0.0
    on_time_pct = 100.0 - overall_late_pct
    avg_transit = float(df["avg_delivery_days"].mean()) if "avg_delivery_days" in df.columns else 0.0
    avg_estimate = float(df["avg_estimated_delivery_days"].mean()) if "avg_estimated_delivery_days" in df.columns else 0.0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Delivered Orders", f"{total_delivered:,}")
    k2.metric("On-Time SLA Rate", f"{on_time_pct:.1f}%")
    k3.metric("Late Deliveries", f"{total_late:,}")
    k4.metric("Avg Actual Transit", f"{avg_transit:.1f} days")
    k5.metric("Avg Estimated Transit", f"{avg_estimate:.1f} days")

    st.markdown("---")

    chart_df = df.set_index("year_month") if "year_month" in df.columns else df

    tab1, tab2 = st.tabs(["📉 Monthly Delay % Trend", "⏱️ Actual vs Estimated Delivery Days"])
    with tab1:
        st.markdown("##### Percentage of Delayed Shipments vs Target")
        if "pct_late_vs_estimated" in chart_df.columns:
            st.line_chart(chart_df["pct_late_vs_estimated"])
        else:
            st.info("Delay percentage metrics not available.")

    with tab2:
        st.markdown("##### Actual Delivery Days vs Carrier Estimated Days")
        transit_cols = [c for c in ["avg_delivery_days", "avg_estimated_delivery_days"] if c in chart_df.columns]
        if transit_cols:
            st.bar_chart(chart_df[transit_cols])
        else:
            st.info("Transit duration metrics not available.")

    with st.expander("📋 View Logistics Performance Data", expanded=False):
        st.dataframe(df, width="stretch")


# ------------------------------------------------------------------------------
# 3. Complete Customer & Regional Insights Dashboard (High Performance SQL)
# ------------------------------------------------------------------------------
def render_customer_dashboard():
    st.markdown("### 👥 Customer Lifetime Value & Geographic Segmentation")
    st.caption("Live metrics from PostgreSQL Data Warehouse `marts.mart_customer_summary` — Customer spend tiers, top buying states, and retention.")

    with st.spinner("⚡ Loading customer analytics from data warehouse..."):
        try:
            df_kpis = fetch_customer_kpis()
            df_states = fetch_customer_state_spend(10)
            df_cities = fetch_customer_city_spend(10)
            df_vips = fetch_customer_vip_leaderboard(15)
        except ConnectionError as ce:
            st.error(f"🚨 {ce}")
            return
        except Exception as e:
            st.error(f"Failed to load customer data from warehouse: {e}")
            return

    if df_kpis.empty:
        st.warning("No customer data found in warehouse marts.")
        return

    # Top KPI Metrics Row extracted directly from SQL aggregate
    row = df_kpis.iloc[0]
    total_buyers = int(row.get("total_buyers", 0))
    total_customer_spend = float(row.get("total_customer_spend", 0.0))
    avg_spend_per_buyer = float(row.get("avg_spend_per_buyer", 0.0))
    repeat_buyers = int(row.get("repeat_buyers", 0))
    repeat_rate = float(row.get("repeat_rate", 0.0))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Buyers", f"{total_buyers:,}")
    c2.metric("Total Customer Spend", f"${total_customer_spend:,.2f}")
    c3.metric("Avg Spend Per Buyer", f"${avg_spend_per_buyer:,.2f}")
    c4.metric("Repeat Buyer Rate", f"{repeat_rate:.2f}%", help=f"{repeat_buyers:,} buyers with > 1 order")

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["🗺️ Top 10 States by Revenue", "🏙️ Top 10 Cities by Revenue", "🏆 VIP Customers"])
    with tab1:
        st.markdown("##### Top Brazilian States by Total Spend")
        if not df_states.empty and "customer_state" in df_states.columns and "total_spend" in df_states.columns:
            st.bar_chart(df_states.set_index("customer_state")["total_spend"])
        else:
            st.info("State spend breakdown not available.")

    with tab2:
        st.markdown("##### Top Brazilian Cities by Total Spend")
        if not df_cities.empty and "customer_city" in df_cities.columns and "total_spend" in df_cities.columns:
            st.bar_chart(df_cities.set_index("customer_city")["total_spend"])
        else:
            st.info("City spend breakdown not available.")

    with tab3:
        st.markdown("##### Top 15 Highest Spending Customers")
        if not df_vips.empty:
            st.dataframe(df_vips, width="stretch")
        else:
            st.info("Customer details not available.")


# ------------------------------------------------------------------------------
# 4. Complete Product Catalog & Leaderboard Dashboard
# ------------------------------------------------------------------------------
def render_product_dashboard():
    st.markdown("### 📦 Product Catalog & Category Leaderboards")
    st.caption("Live metrics from PostgreSQL Data Warehouse `marts.mart_top_products` — High margin categories, best sellers, and unit velocities.")

    with st.spinner("⚡ Loading product catalog from data warehouse..."):
        try:
            df = fetch_product_data(limit=100)
        except ConnectionError as ce:
            st.error(f"🚨 {ce}")
            return
        except Exception as e:
            st.error(f"Failed to load product catalog from warehouse: {e}")
            return

    if df.empty:
        st.warning("No product data found in warehouse marts.")
        return

    expected_cols = {"product_id", "category_name", "units_sold", "total_revenue", "revenue_rank"}
    missing_cols = expected_cols - set(df.columns)
    if missing_cols:
        st.warning(f"Product data is missing expected columns: {', '.join(sorted(missing_cols))}. Displaying available metrics.")

    total_skus = len(df)
    total_units = int(df["units_sold"].sum()) if "units_sold" in df.columns else 0
    total_rev = float(df["total_revenue"].sum()) if "total_revenue" in df.columns else 0.0
    top_cat = "N/A"
    if "category_name" in df.columns and "total_revenue" in df.columns and not df.empty:
        cat_grouped = df.groupby("category_name")["total_revenue"].sum()
        if not cat_grouped.empty:
            top_cat = str(cat_grouped.idxmax())

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Catalog SKUs (Sample)", f"{total_skus:,}")
    p2.metric("Total Units Sold", f"{total_units:,}")
    p3.metric("Catalog Revenue", f"${total_rev:,.2f}")
    p4.metric("Top Category", f"{top_cat}")

    st.markdown("---")

    t1, t2, t3 = st.tabs(["📊 Top Categories (Revenue)", "📦 Top Categories (Units)", "📋 Product Leaderboard"])
    with t1:
        st.markdown("##### Top 10 Product Categories by Gross Revenue")
        if "category_name" in df.columns and "total_revenue" in df.columns:
            cat_rev = df.groupby("category_name")["total_revenue"].sum().sort_values(ascending=False).head(10)
            st.bar_chart(cat_rev)
        else:
            st.info("Category revenue breakdown not available.")

    with t2:
        st.markdown("##### Top 10 Product Categories by Units Sold")
        if "category_name" in df.columns and "units_sold" in df.columns:
            cat_units = df.groupby("category_name")["units_sold"].sum().sort_values(ascending=False).head(10)
            st.bar_chart(cat_units)
        else:
            st.info("Category unit breakdown not available.")

    with t3:
        st.markdown("##### Best-Selling Products Leaderboard")
        st.dataframe(df.head(25), width="stretch")


# ------------------------------------------------------------------------------
# 5. Executive 360° All-In-One Cockpit Dashboard
# ------------------------------------------------------------------------------
def render_360_overview_dashboard():
    st.markdown("### 🌐 Executive 360° Platform Cockpit")
    st.caption("Unified multi-dimensional view synthesizing Sales, Logistics, Customers, and Catalog performance.")

    st.info("💡 **Executive Cockpit**: Showing cross-functional health metrics from all 4 data marts in data warehouse.")
    render_sales_dashboard()
    st.markdown("---")
    render_delivery_dashboard()
    st.markdown("---")
    render_customer_dashboard()


# ------------------------------------------------------------------------------
# Master Dashboard Dispatcher
# ------------------------------------------------------------------------------
def render_dashboard_by_type(dashboard_type: str = "sales"):
    """Dispatches rendering to the appropriate dashboard view."""
    dtype = dashboard_type.lower().strip()
    if "sale" in dtype or "rev" in dtype:
        render_sales_dashboard()
    elif "deliver" in dtype or "logist" in dtype or "late" in dtype:
        render_delivery_dashboard()
    elif "custom" in dtype or "buy" in dtype or "state" in dtype:
        render_customer_dashboard()
    elif "prod" in dtype or "cat" in dtype:
        render_product_dashboard()
    else:
        render_sales_dashboard()
