# ==============================================================================
# app/pages/1_Live_Dashboards.py - Dedicated Multi-Page Analytical Dashboard Portal
#
# Accessible locally at: http://localhost:8501/Live_Dashboards
# Accessible on AWS at:  http://<AWS_HOST>:8501/Live_Dashboards
# ==============================================================================

import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

import streamlit as st

from app.dashboard_renderer import (
    render_360_overview_dashboard,
    render_customer_dashboard,
    render_delivery_dashboard,
    render_product_dashboard,
    render_sales_dashboard,
)

st.set_page_config(
    page_title="NexusBI | Live Analytics Dashboards",
    page_icon="⚡",
    layout="wide",
)

st.markdown(
    """
    <style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #1E293B; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1.05rem; color: #64748B; margin-bottom: 1.2rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Header
col_title, col_action = st.columns([8, 2])
with col_title:
    st.markdown("<div class='main-header'>⚡ NexusBI: Live Analytical Dashboards</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>Interactive business intelligence studio querying curated marts on AWS RDS PostgreSQL (ap-southeast-2 Sydney).</div>", unsafe_allow_html=True)

with col_action:
    if st.button("💬 Open Conversational BI Chat", use_container_width=True):
        st.switch_page("streamlit_app.py")

# Query Param Support (e.g. ?type=sales or ?type=delivery)
requested_type = st.query_params.get("type", "sales").lower()
type_map = {
    "sales": 0,
    "revenue": 0,
    "delivery": 1,
    "logistics": 1,
    "customer": 2,
    "customers": 2,
    "product": 3,
    "products": 3,
    "360": 4,
    "overview": 4,
}
default_idx = type_map.get(requested_type, 0)

dashboard_choice = st.radio(
    "Select Dashboard to View:",
    options=[
        "📈 Sales & Revenue Performance",
        "🚚 Delivery & Fulfillment SLAs",
        "👥 Customer Segmentation & LTV",
        "📦 Product Catalog & Rankings",
        "🌐 Executive 360° Platform Cockpit",
    ],
    index=default_idx,
    horizontal=True,
)

st.divider()

if "Sales" in dashboard_choice:
    st.query_params["type"] = "sales"
    render_sales_dashboard()
elif "Delivery" in dashboard_choice:
    st.query_params["type"] = "delivery"
    render_delivery_dashboard()
elif "Customer" in dashboard_choice:
    st.query_params["type"] = "customer"
    render_customer_dashboard()
elif "Product" in dashboard_choice:
    st.query_params["type"] = "product"
    render_product_dashboard()
elif "360" in dashboard_choice:
    st.query_params["type"] = "360"
    render_360_overview_dashboard()

