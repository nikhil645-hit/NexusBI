# ==============================================================================
# app/streamlit_app.py - Conversational BI Web Application
#
# Flow:
#   1. Read marts schema definition from warehouse.
#   2. Send user question + schema to LLM adapter (Gemini / Anthropic / Mock).
#   3. Validate generated SQL using AST parser (sqlglot).
#   4. Execute sanitized query using read-only user (app_readonly).
#   5. Handle single-turn self-correction on SQL errors.
#   6. Render generated SQL, data table, and intelligent visualizations.
# ==============================================================================

import os
import sys

# Crucial Windows fix: limit OpenBLAS / OMP threads before numpy/pandas/streamlit initialize
# to prevent "OpenBLAS error: Memory allocation still failed" crashes
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import time
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Ensure project root and app directory are in sys.path when executed via streamlit
project_root = Path(__file__).resolve().parent.parent
app_dir = Path(__file__).resolve().parent
for p in (str(project_root), str(app_dir)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Load environment variables from .env file
dotenv_file = project_root / ".env"
if dotenv_file.exists():
    load_dotenv(dotenv_path=dotenv_file, override=True)

try:
    from app.audit_logger import log_query_event
    from app.dashboard_renderer import render_dashboard_by_type
    from app.db_helper import (
        execute_marts_query,
        get_marts_schema_text,
        is_database_live,
        is_demo_mode,
    )
    from app.llm_helper import MockLLMAdapter, detect_dashboard_type, get_llm_adapter
    from app.sql_validator import validate_and_sanitize_sql
except ModuleNotFoundError:
    from audit_logger import log_query_event
    from dashboard_renderer import render_dashboard_by_type
    from db_helper import (
        execute_marts_query,
        get_marts_schema_text,
        is_database_live,
        is_demo_mode,
    )
    from llm_helper import MockLLMAdapter, detect_dashboard_type, get_llm_adapter
    from sql_validator import validate_and_sanitize_sql

# ------------------------------------------------------------------------------
# Page Configuration & Styling
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="NexusBI | Conversational BI & Analytics",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom styling for clean interface
st.markdown(
    """
    <style>
    .main-header { font-size: 2.1rem; font-weight: 700; color: #1E293B; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1.05rem; color: #64748B; margin-bottom: 1.5rem; }
    .badge-provider { background-color: #EEF2F6; color: #1E40AF; padding: 4px 10px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; }
    .badge-status-ok { background-color: #DCFCE7; color: #166534; padding: 4px 10px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; }
    .badge-status-mock { background-color: #FEF3C7; color: #92400E; padding: 4px 10px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; }

    /* Right-side floating slideout drawer for System Control */
    .right-slideout-drawer {
        position: fixed;
        top: 85px;
        right: -320px;
        width: 360px;
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 12px 0 0 12px;
        box-shadow: -6px 8px 24px rgba(15, 23, 42, 0.16);
        transition: right 0.35s cubic-bezier(0.16, 1, 0.3, 1);
        z-index: 999999;
        font-family: inherit;
        display: flex;
    }
    .right-slideout-drawer:hover, .right-slideout-drawer:focus-within {
        right: 0px;
    }
    .drawer-handle {
        width: 40px;
        background: linear-gradient(180deg, #1e293b, #0f172a);
        color: #f8fafc;
        writing-mode: vertical-rl;
        text-orientation: mixed;
        transform: rotate(180deg);
        padding: 22px 8px;
        cursor: pointer;
        border-radius: 0 10px 10px 0;
        font-size: 0.82rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        justify-content: center;
        letter-spacing: 0.8px;
        box-shadow: -2px 0 8px rgba(0,0,0,0.12);
        user-select: none;
    }
    .drawer-content {
        flex: 1;
        padding: 18px 20px;
        color: #334155;
        font-size: 0.88rem;
        max-height: 82vh;
        overflow-y: auto;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------------------
# Session State Initialization
# ------------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "query_history" not in st.session_state:
    st.session_state.query_history = []

if "selected_sample_question" not in st.session_state:
    st.session_state.selected_sample_question = None

if "saved_chats" not in st.session_state:
    st.session_state.saved_chats = []

if "session_id" not in st.session_state:
    import uuid
    st.session_state.session_id = str(uuid.uuid4())[:8]

if "request_timestamps" not in st.session_state:
    st.session_state.request_timestamps = []

if "total_requests" not in st.session_state:
    st.session_state.total_requests = 0

if "last_latency_ms" not in st.session_state:
    st.session_state.last_latency_ms = 0.0


# Observability & Rate Limiting Configuration
RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "20"))
MAX_PROMPT_LENGTH = int(os.getenv("MAX_PROMPT_LENGTH", "500"))

# Clean up timestamps older than 1 hour (3600s)
_now_ts = time.time()
st.session_state.request_timestamps = [
    t for t in st.session_state.request_timestamps if _now_ts - t < 3600
]
hourly_requests_used = len(st.session_state.request_timestamps)


# System Metadata Helpers
provider_name = os.getenv("LLM_PROVIDER", "gemini").upper()
has_db = is_database_live()
demo_on = is_demo_mode()

if has_db:
    wh_label = "LIVE Database (Connected)"
    wh_badge_class = "badge-status-ok"
    wh_mode_text = "Live Read-Only"
elif demo_on:
    wh_label = "DEMO Mode (Synthetic Data)"
    wh_badge_class = "badge-status-mock"
    wh_mode_text = "Synthetic Demo"
else:
    wh_label = "Database Offline"
    wh_badge_class = "badge-status-mock"
    wh_mode_text = "Disconnected"

active_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b") if provider_name == "GROQ" else os.getenv("GEMINI_MODEL", "gemini-1.5-flash")


# ------------------------------------------------------------------------------
# Right-side Hover Slideout Drawer (System Control Panel)
# ------------------------------------------------------------------------------
st.markdown(
    f"""
    <div class="right-slideout-drawer">
        <div class="drawer-handle">⚙️ System Control</div>
        <div class="drawer-content">
            <div style="font-weight:700; font-size:1.05rem; margin-bottom:10px; color:#0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px;">
                ⚙️ System Control & Infrastructure
            </div>
            <div style="margin: 8px 0;">
                <div style="font-size:0.75rem; color:#64748b; font-weight:700; text-transform:uppercase;">LLM Engine</div>
                <div style="margin-top:2px;"><strong>Provider:</strong> <span class="badge-provider">{provider_name}</span></div>
                <div style="font-size:0.78rem; color:#64748b; margin-top:2px;">Model: <code>{active_model}</code></div>
            </div>
            <div style="margin: 10px 0;">
                <div style="font-size:0.75rem; color:#64748b; font-weight:700; text-transform:uppercase;">Data Warehouse</div>
                <div style="margin-top:2px;"><strong>Status:</strong> <span class="{wh_badge_class}">{wh_label}</span></div>
                <div style="font-size:0.78rem; color:#64748b; margin-top:2px;">Access Mode: <code>{wh_mode_text}</code></div>
            </div>
            <div style="margin: 10px 0;">
                <div style="font-size:0.75rem; color:#64748b; font-weight:700; text-transform:uppercase;">Security & Governance</div>
                <div style="margin-top:2px;"><strong>AST Guardrail:</strong> <span class="badge-status-ok">sqlglot Active</span></div>
                <div style="font-size:0.78rem; color:#64748b; margin-top:2px;">User Role: <code>app_readonly</code></div>
                <div style="font-size:0.78rem; color:#64748b;">Enforcement: SELECT Only on marts</div>
            </div>
            <div style="margin: 10px 0;">
                <div style="font-size:0.75rem; color:#64748b; font-weight:700; text-transform:uppercase;">Usage & Health</div>
                <div style="font-size:0.78rem; color:#334155; margin-top:2px;">Session Requests: <strong>{st.session_state.total_requests}</strong></div>
                <div style="font-size:0.78rem; color:#334155;">Hourly Usage: <strong>{hourly_requests_used} / {RATE_LIMIT_PER_HOUR}</strong></div>
                <div style="font-size:0.78rem; color:#334155;">Last Latency: <strong>{st.session_state.last_latency_ms:.0f} ms</strong></div>
            </div>
            <hr style="margin: 12px 0; border:0; border-top:1px solid #e2e8f0;" />
            <div style="font-weight:600; font-size:0.85rem; margin-bottom:6px; color:#1e293b;">📚 Curated Marts Whitelist:</div>
            <ul style="padding-left:18px; margin:0; font-size:0.8rem; line-height:1.6; color:#475569;">
                <li><code>mart_daily_sales</code>: Sales, orders, AOV</li>
                <li><code>mart_top_products</code>: Product leaderboards</li>
                <li><code>mart_customer_summary</code>: Customer lifetime spend</li>
                <li><code>mart_delivery_performance</code>: Fulfillment SLAs</li>
            </ul>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------------------
# Sidebar: Previous Saved Chats, Operating Mode & Sample Prompts
# ------------------------------------------------------------------------------
with st.sidebar:
    st.title("💬 Chat History")

    # ➕ New Chat Button
    if st.button("➕ New Chat", use_container_width=True, help="Archive current chat and start a fresh session"):
        if st.session_state.messages:
            first_user_q = next((m["content"] for m in st.session_state.messages if m["role"] == "user"), "Conversation")
            title = first_user_q[:30] + ("..." if len(first_user_q) > 30 else "")
            st.session_state.saved_chats.append({
                "title": title,
                "messages": list(st.session_state.messages),
                "timestamp": time.strftime("%H:%M"),
            })
        st.session_state.messages = []
        st.session_state.selected_sample_question = None
        st.rerun()

    # List of Previous Saved Chats
    st.subheader("📁 Saved Conversations")
    if not st.session_state.saved_chats:
        st.caption("No archived conversations yet. Previous sessions will appear here.")
    else:
        for idx, chat in enumerate(reversed(st.session_state.saved_chats)):
            real_idx = len(st.session_state.saved_chats) - 1 - idx
            col_c, col_d = st.columns([8, 2])
            with col_c:
                if st.button(f"💬 {chat['title']}", key=f"load_saved_{real_idx}", use_container_width=True):
                    st.session_state.messages = list(chat["messages"])
                    st.rerun()
            with col_d:
                if st.button("✕", key=f"del_saved_{real_idx}", help="Delete chat"):
                    st.session_state.saved_chats.pop(real_idx)
                    st.rerun()

    # Active Queries in Current Session
    if st.session_state.messages:
        active_queries = [m["content"] for m in st.session_state.messages if m["role"] == "user"]
        if active_queries:
            st.caption("**Active Session:**")
            for q in active_queries[-3:]:
                st.markdown(f"<span style='font-size:0.82rem; color:#64748b;'>• {q[:32]}...</span>", unsafe_allow_html=True)

    if st.session_state.saved_chats or st.session_state.messages:
        if st.button("🗑️ Clear All Chats", key="clear_all_history", use_container_width=True):
            st.session_state.saved_chats = []
            st.session_state.messages = []
            st.session_state.query_history = []
            st.rerun()

    st.divider()

    # Multi-Purpose Assistant Capabilities
    st.subheader("🎛️ Assistant Capability")
    assistant_mode = st.radio(
        "Select Operating Mode:",
        options=[
            "🤖 Auto-Detect (Smart Router)",
            "📊 Data Analytics & Insights",
            "💡 Strategic Business Advisor",
            "🏗️ Pipeline Architecture & Viva",
        ],
        index=0,
        help="Auto-Detect routes automatically. You can also manually choose to query data, ask for business advice, or explore the engineering architecture."
    )

    st.divider()

    # 6 Clickable Sample Questions (Rule from PROJECT.md)
    st.subheader("💡 Sample Questions")
    sample_questions = [
        "What are the top 5 product categories by total revenue?",
        "Show the daily sales trend and average order value for the last 30 days.",
        "Which Brazilian states have the highest customer lifetime spend?",
        "What percentage of orders were delivered late each month?",
        "Who are the top 10 customers by total spend?",
        "What is the average delivery duration in days compared to estimated delivery days?",
    ]

    for i, q in enumerate(sample_questions, 1):
        if st.button(f"{i}. {q}", key=f"sample_{i}", width="stretch"):
            st.session_state.selected_sample_question = q


# ------------------------------------------------------------------------------
# Main Application Header & Right-Side System Popover
# ------------------------------------------------------------------------------
col_hdr_left, col_hdr_right = st.columns([7, 3])

with col_hdr_left:
    st.markdown("<div class='main-header'>⚡ NexusBI: Conversational Business Intelligence</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='sub-header'>"
        "Ask analytical questions or request live dashboards in natural language. Powered by LLM Text-to-SQL, "
        "deterministic <code>sqlglot</code> AST security guardrails, and PostgreSQL cloud data warehouse."
        "</div>",
        unsafe_allow_html=True,
    )

with col_hdr_right:
    with st.popover("⚙️ System Control & Status", use_container_width=True):
        st.markdown("#### ⚙️ System Control")
        st.markdown(f"**LLM Provider:** <span class='badge-provider'>{provider_name}</span>", unsafe_allow_html=True)
        st.caption(f"Model: `{active_model}`")
        st.markdown(f"**Warehouse:** <span class='{wh_badge_class}'>{wh_label}</span>", unsafe_allow_html=True)
        st.caption(f"Mode: `{wh_mode_text}`")
        st.markdown("**AST Guardrail:** <span class='badge-status-ok'>sqlglot Active</span>", unsafe_allow_html=True)
        st.caption("Read-only access enforced strictly on `marts` schema.")
        st.divider()
        st.markdown("##### 📊 Usage & Health")
        st.markdown(f"- **Session Requests:** `{st.session_state.total_requests}`")
        st.markdown(f"- **Hourly Usage:** `{hourly_requests_used} / {RATE_LIMIT_PER_HOUR}`")
        st.markdown(f"- **Last Latency:** `{st.session_state.last_latency_ms:.0f} ms`")
        st.divider()
        st.markdown("##### 📚 Data Marts Whitelist")
        st.markdown(
            "- `marts.mart_daily_sales`\n"
            "- `marts.mart_top_products`\n"
            "- `marts.mart_customer_summary`\n"
            "- `marts.mart_delivery_performance`"
        )

if is_demo_mode():
    st.warning("⚠️ **DEMO DATA - not real**: The application is running in DEMO MODE with synthetic sample data.")
elif not has_db:
    st.error("🚨 **Database not connected**: No active connection to the data warehouse. Please configure database credentials in environment or Streamlit Secrets.")


# ------------------------------------------------------------------------------
# Full-Screen Live Dashboard Studio (Activated via ?dashboard=... query param)
# ------------------------------------------------------------------------------
active_dashboard = st.query_params.get("dashboard")
if active_dashboard:
    col_back, col_switch = st.columns([3, 7])
    with col_back:
        if st.button("⬅️ Return to AI Conversational BI", use_container_width=True):
            st.query_params.pop("dashboard", None)
            st.rerun()

    dashboard_options = {
        "sales": "📈 Sales & Revenue Dashboard",
        "delivery": "🚚 Delivery & Fulfillment SLA Dashboard",
        "customer": "👥 Customer & Regional Insights Dashboard",
        "product": "📦 Product Catalog & Category Leaderboards",
        "360": "🌐 Executive 360° Platform Cockpit",
    }

    norm_key = "sales"
    for k in dashboard_options:
        if k in active_dashboard.lower():
            norm_key = k
            break

    keys_list = list(dashboard_options.keys())
    selected_dash = col_switch.selectbox(
        "Switch Dashboard Studio View:",
        options=keys_list,
        index=keys_list.index(norm_key),
        format_func=lambda x: dashboard_options[x],
    )

    st.markdown("---")
    render_dashboard_by_type(selected_dash)
    st.stop()


# ------------------------------------------------------------------------------
# Intelligent Chart & KPI Rendering Helper
# ------------------------------------------------------------------------------
def render_intelligent_chart(df: pd.DataFrame):
    """Detects metrics, date or categorical series and plots rich interactive Streamlit charts and KPI cards."""
    if df.empty:
        return

    # 1. Summary KPI Metric Cards
    numeric_cols = [c for c in df.select_dtypes(include=["number"]).columns]
    metrics_to_show = []

    for c in numeric_cols:
        c_lower = c.lower()
        if "revenue" in c_lower or "spend" in c_lower or "price" in c_lower:
            total_val = df[c].sum()
            metrics_to_show.append((c.replace("_", " ").title(), f"${total_val:,.2f}"))
        elif "orders" in c_lower or "units" in c_lower or "buyers" in c_lower or "count" in c_lower:
            total_val = df[c].sum()
            metrics_to_show.append((c.replace("_", " ").title(), f"{total_val:,.0f}"))
        elif "avg" in c_lower or "rate" in c_lower or "pct" in c_lower:
            mean_val = df[c].mean()
            if "pct" in c_lower or "rate" in c_lower:
                metrics_to_show.append((c.replace("_", " ").title(), f"{mean_val:.2f}%"))
            else:
                metrics_to_show.append((c.replace("_", " ").title(), f"${mean_val:,.2f}"))

    if metrics_to_show and len(metrics_to_show) >= 2:
        cols = st.columns(min(len(metrics_to_show), 4))
        for idx, (label, val_str) in enumerate(metrics_to_show[:4]):
            cols[idx].metric(label=label, value=val_str)

    if len(df.columns) < 2 or not numeric_cols:
        return

    # 2. Date-based time series -> Multi-Chart Tabs ("Various Graphs")
    date_cols = [c for c in df.columns if any(k in c.lower() for k in ["date", "month", "day", "time", "year"])]

    if date_cols and numeric_cols:
        primary_date_col = date_cols[0]
        st.markdown("##### 📈 Visual Trend Analysis")

        if len(numeric_cols) == 1:
            chart_data = df[[primary_date_col, numeric_cols[0]]].copy().set_index(primary_date_col)
            st.line_chart(chart_data)
        else:
            tab_titles = [f"📊 {col.replace('_', ' ').title()}" for col in numeric_cols[:4]]
            tabs = st.tabs(tab_titles)
            for i, col in enumerate(numeric_cols[:4]):
                with tabs[i]:
                    sub_chart = df[[primary_date_col, col]].copy().set_index(primary_date_col)
                    if any(term in col.lower() for term in ["order", "count", "units", "items"]):
                        st.bar_chart(sub_chart)
                    else:
                        st.line_chart(sub_chart)
        return

    # 3. Categorical Leaderboard -> Multi-Metric Bar Chart Tabs
    cat_cols = [c for c in df.select_dtypes(include=["object", "string"]).columns]
    if cat_cols and numeric_cols:
        primary_cat = cat_cols[0]
        st.markdown("##### 📊 Comparative Visualizations")

        if len(numeric_cols) == 1:
            bar_data = df[[primary_cat, numeric_cols[0]]].copy().head(10).set_index(primary_cat)
            st.bar_chart(bar_data)
        else:
            tab_titles = [f"📊 {col.replace('_', ' ').title()}" for col in numeric_cols[:3]]
            tabs = st.tabs(tab_titles)
            for i, col in enumerate(numeric_cols[:3]):
                with tabs[i]:
                    bar_data = df[[primary_cat, col]].copy().head(10).set_index(primary_cat)
                    st.bar_chart(bar_data)
        return


# ------------------------------------------------------------------------------
# Render Past Chat Messages
# ------------------------------------------------------------------------------
for msg_idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and is_demo_mode():
            st.caption("⚠️ *DEMO DATA - not real*")
        st.markdown(msg["content"])
        if msg.get("out_of_scope_buttons"):
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("📊 Top 5 product categories by revenue", key=f"oos_hist_1_{msg_idx}", use_container_width=True):
                    st.session_state.selected_sample_question = "What are the top 5 product categories by total revenue?"
                    st.rerun()
            with col2:
                if st.button("📈 Monthly revenue trend", key=f"oos_hist_2_{msg_idx}", use_container_width=True):
                    st.session_state.selected_sample_question = "Show the daily sales trend and average order value for the last 30 days."
                    st.rerun()
            with col3:
                if st.button("🚚 Late delivery rate by month", key=f"oos_hist_3_{msg_idx}", use_container_width=True):
                    st.session_state.selected_sample_question = "What percentage of orders were delivered late each month?"
                    st.rerun()
        if "dashboard_type" in msg:
            dtype_label = msg["dashboard_type"].title()
            if st.button(f"🚀 Open Full-Screen {dtype_label} Dashboard", key=f"btn_hist_{msg['dashboard_type']}_{msg_idx}"):
                st.query_params["dashboard"] = msg["dashboard_type"]
                st.rerun()
        if "sql" in msg:
            with st.expander("🔍 View Verified SQL Query", expanded=False):
                st.code(msg["sql"], language="sql")
        if "df" in msg and msg["df"] is not None:
            st.dataframe(msg["df"], width="stretch")
            render_intelligent_chart(msg["df"])
        if "insights" in msg and msg["insights"]:
            st.markdown("---")
            st.markdown("### 💡 Executive Analysis & Business Recommendations")
            st.markdown(msg["insights"])


# ------------------------------------------------------------------------------
# Chat Input & Query Execution Pipeline
# ------------------------------------------------------------------------------
# Check if user clicked a sample question from sidebar
user_prompt = st.chat_input("Ask a question about sales, products, customers, or delivery...")
if st.session_state.selected_sample_question:
    user_prompt = st.session_state.selected_sample_question
    st.session_state.selected_sample_question = None

if user_prompt:
    # 0. Check Database Connection
    if not is_demo_mode() and not is_database_live():
        with st.chat_message("user"):
            st.markdown(user_prompt)
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        err_msg = "🚨 **Database not connected**: No active connection to the data warehouse. Please configure database credentials in environment or Streamlit Secrets."
        with st.chat_message("assistant"):
            st.error(err_msg)
        st.session_state.messages.append({"role": "assistant", "content": err_msg})
        st.stop()

    # 0. Abuse Protection: Enforce maximum input length
    if len(user_prompt) > MAX_PROMPT_LENGTH:
        st.warning(
            f"⚠️ **Input Length Exceeded:** Your query is {len(user_prompt)} characters, "
            f"exceeding the limit of {MAX_PROMPT_LENGTH} characters. Please provide a more concise question."
        )
        log_query_event(
            session_id=st.session_state.session_id,
            intent="UNKNOWN",
            question=user_prompt[:80],
            generated_sql=None,
            guardrail_result="BLOCKED",
            rows_returned=0,
            latency_ms=0.0,
            error="Prompt length exceeded limit",
        )
        st.stop()

    # 0. Abuse Protection: Enforce per-session hourly rate limit
    if hourly_requests_used >= RATE_LIMIT_PER_HOUR:
        st.warning(
            f"⚠️ **Rate Limit Exceeded:** You have reached the limit of {RATE_LIMIT_PER_HOUR} requests "
            f"per hour for this session. Please wait before submitting additional queries."
        )
        log_query_event(
            session_id=st.session_state.session_id,
            intent="UNKNOWN",
            question=user_prompt[:80],
            generated_sql=None,
            guardrail_result="BLOCKED",
            rows_returned=0,
            latency_ms=0.0,
            error="Hourly rate limit exceeded",
        )
        st.stop()

    # Record request for session statistics
    st.session_state.request_timestamps.append(time.time())
    st.session_state.total_requests += 1

    # 1. Display User Question
    st.session_state.messages.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        st.markdown(user_prompt)

    # 2. Process with LLM and Security Guardrails
    with st.chat_message("assistant"):
        if is_demo_mode():
            st.caption("⚠️ *DEMO DATA - not real*")
        message_placeholder = st.empty()
        schema_text = get_marts_schema_text()
        llm = get_llm_adapter()
        if llm is None:
            err_msg = "🚨 **LLM not configured**: No valid LLM API key configured (GROQ_API_KEY or GEMINI_API_KEY). Please add your API key in environment variables or Streamlit Secrets, or set `DEMO_MODE=1` to use synthetic demo mode."
            message_placeholder.error("LLM not configured")
            st.error(err_msg)
            st.session_state.messages.append({"role": "assistant", "content": err_msg})
            log_query_event(
                session_id=st.session_state.session_id,
                intent="UNKNOWN",
                question=user_prompt,
                generated_sql=None,
                guardrail_result="BLOCKED",
                rows_returned=0,
                latency_ms=0.0,
                error="LLM not configured",
            )
            st.stop()
        t_pipeline_start = time.time()

        # Determine Intent (Auto-detect or Manual Override from Sidebar)
        if "Data Analytics" in assistant_mode:
            intent = "DATA_QUERY"
        elif "Strategic Business" in assistant_mode:
            intent = "BUSINESS_STRATEGY"
        elif "Pipeline Architecture" in assistant_mode:
            intent = "ARCHITECTURE_VIVA"
        else:
            with st.spinner("🧭 Understanding question context & intent..."):
                try:
                    intent = llm.classify_intent(user_prompt)
                except Exception:
                    intent = "OUT_OF_SCOPE"

        demo_banner = "⚠️ **DEMO DATA - not real**\n\n" if is_demo_mode() else ""

        # ----------------------------------------------------------------------
        # Path OUT_OF_SCOPE: Off-topic questions (coding, trivia, chit-chat, etc.)
        # ----------------------------------------------------------------------
        if intent == "OUT_OF_SCOPE":
            out_of_scope_msg = demo_banner + (
                "👋 I'm the **NexusBI Assistant**, focused specifically on exploring Brazilian E-Commerce (Olist) data, "
                "visualizing analytics dashboards, e-commerce business strategy, and data engineering pipeline architecture.\n\n"
                "I cannot help with general coding, homework, trivia, or non-ecommerce topics. "
                "If you were asking a data or strategy question, please rephrase it with specific terms (like sales, products, customers, or delivery).\n\n"
                "Here are a few questions you can ask me:"
            )
            message_placeholder.markdown(out_of_scope_msg)

            col1, col2, col3 = st.columns(3)
            oos_suffix = len(st.session_state.messages)
            with col1:
                if st.button("📊 Top 5 product categories by revenue", key=f"btn_oos_1_{oos_suffix}", use_container_width=True):
                    st.session_state.selected_sample_question = "What are the top 5 product categories by total revenue?"
                    st.rerun()
            with col2:
                if st.button("📈 Monthly revenue trend", key=f"btn_oos_2_{oos_suffix}", use_container_width=True):
                    st.session_state.selected_sample_question = "Show the daily sales trend and average order value for the last 30 days."
                    st.rerun()
            with col3:
                if st.button("🚚 Late delivery rate by month", key=f"btn_oos_3_{oos_suffix}", use_container_width=True):
                    st.session_state.selected_sample_question = "What percentage of orders were delivered late each month?"
                    st.rerun()

            st.session_state.messages.append({
                "role": "assistant",
                "content": out_of_scope_msg,
                "out_of_scope_buttons": True,
            })
            latency_ms = (time.time() - t_pipeline_start) * 1000
            st.session_state.last_latency_ms = latency_ms
            log_query_event(
                session_id=st.session_state.session_id,
                intent="OUT_OF_SCOPE",
                question=user_prompt,
                generated_sql=None,
                guardrail_result="PASSED",
                rows_returned=0,
                latency_ms=latency_ms,
                error=None,
            )

        # ----------------------------------------------------------------------
        # Path A: Dynamic Full-Screen Dashboard Generation (Localhost / AWS Cloud Link)
        # ----------------------------------------------------------------------
        elif intent == "DASHBOARD_REQUEST":
            dtype = detect_dashboard_type(user_prompt)
            dtype_titles = {
                "sales": "📈 Sales & Revenue Dashboard",
                "delivery": "🚚 Delivery & Fulfillment SLA Dashboard",
                "customer": "👥 Customer & Regional Insights Dashboard",
                "product": "📦 Product Catalog & Category Leaderboards",
                "360": "🌐 Executive 360° Platform Cockpit",
            }
            title = dtype_titles.get(dtype, "📈 Sales & Revenue Dashboard")

            success_msg = demo_banner + (
                f"### 🎉 {title} Generated Successfully!\n\n"
                f"Your complete interactive dashboard is active and querying live data marts on AWS RDS Sydney.\n\n"
                f"- 🔗 **Local URL Link:** [`http://localhost:8501/?dashboard={dtype}`](http://localhost:8501/?dashboard={dtype})\n"
                f"- 🔗 **Multi-Page Portal:** [`http://localhost:8501/Live_Dashboards?type={dtype}`](http://localhost:8501/Live_Dashboards?type={dtype})\n\n"
                f"*(When deployed on AWS, this exact link is accessible from any computer!)*\n\n"
                f"👇 Click the launch button below or open the link to view the complete dashboard in full-screen:"
            )
            message_placeholder.markdown(success_msg)

            col_btn, _ = st.columns([5, 5])
            with col_btn:
                if st.button(f"🚀 Open Full-Screen {dtype.title()} Dashboard", key="btn_launch_dash_live", use_container_width=True):
                    st.query_params["dashboard"] = dtype
                    st.rerun()

            st.markdown("---")
            st.markdown(f"#### 📊 In-Chat Interactive Preview ({dtype.title()}):")
            render_dashboard_by_type(dtype)

            st.session_state.messages.append({
                "role": "assistant",
                "content": success_msg,
                "dashboard_type": dtype,
            })
            st.session_state.query_history.append({
                "question": user_prompt,
                "sql": f"-- Generated {dtype} dashboard from curated marts",
            })
            latency_ms = (time.time() - t_pipeline_start) * 1000
            st.session_state.last_latency_ms = latency_ms
            log_query_event(
                session_id=st.session_state.session_id,
                intent="DASHBOARD_REQUEST",
                question=user_prompt,
                generated_sql=f"-- {dtype} dashboard",
                guardrail_result="PASSED",
                rows_returned=0,
                latency_ms=latency_ms,
                error=None,
            )

        # ----------------------------------------------------------------------
        # Path B: Direct Strategic Advisory or Architecture Mode (No SQL required)
        # ----------------------------------------------------------------------
        elif intent in ("BUSINESS_STRATEGY", "ARCHITECTURE_VIVA"):
            spinner_msg = (
                "💡 Formulating strategic e-commerce growth playbook..."
                if intent == "BUSINESS_STRATEGY"
                else "🏗️ Retrieving pipeline architecture & engineering specifications..."
            )
            with st.spinner(spinner_msg):
                system_type = "architecture" if intent == "ARCHITECTURE_VIVA" else "advisory"
                try:
                    response_text = llm.generate_advisory_or_architecture(
                        question=user_prompt, system_type=system_type
                    )
                except Exception as e:
                    response_text = f"The advisory assistant encountered an error ({type(e).__name__}). Please retry shortly."

                if is_demo_mode():
                    response_text = "⚠️ **DEMO DATA - not real**\n\n" + response_text

                message_placeholder.markdown(response_text)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response_text,
                })
                latency_ms = (time.time() - t_pipeline_start) * 1000
                st.session_state.last_latency_ms = latency_ms
                log_query_event(
                    session_id=st.session_state.session_id,
                    intent=intent,
                    question=user_prompt,
                    generated_sql=None,
                    guardrail_result="PASSED",
                    rows_returned=0,
                    latency_ms=latency_ms,
                    error=None,
                )

        # ----------------------------------------------------------------------
        # Path C: Warehouse Analytics & Data Insights (Text-to-SQL + AST + Synthesis)
        # ----------------------------------------------------------------------
        else:
            raw_sql = None
            try:
                with st.spinner("🤖 Translating question to PostgreSQL SQL..."):
                    t_start = time.time()
                    raw_sql = llm.generate_sql(question=user_prompt, schema_info=schema_text)
            except Exception as e:
                err_detail = str(e)
                if hasattr(e, "response") and getattr(e.response, "status_code", None) == 429:
                    err_msg = "LLM rate limit reached (HTTP 429: Too Many Requests). Please wait a few seconds and retry."
                else:
                    err_msg = f"Unable to reach the LLM provider ({type(e).__name__}): {err_detail}"
                st.error(f"❌ **AI Service Unavailable**: {err_msg}")
                latency_ms = (time.time() - t_pipeline_start) * 1000
                log_query_event(
                    session_id=st.session_state.session_id,
                    intent="DATA_QUERY",
                    question=user_prompt,
                    generated_sql=None,
                    guardrail_result="ERROR",
                    rows_returned=0,
                    latency_ms=latency_ms,
                    error=str(e),
                )
                st.stop()

            # 3. Deterministic AST Security Validation
            is_valid, sanitized_sql, error_msg = validate_and_sanitize_sql(raw_sql)

            if not is_valid:
                # First attempt failed validation -> Trigger 1-turn retry to let LLM self-correct
                with st.spinner("⚠️ Security rule triggered. Retrying with self-correction..."):
                    try:
                        corrected_sql_raw = llm.generate_sql(
                            question=user_prompt,
                            schema_info=schema_text,
                            error_context=f"Query rejected by security validator: {error_msg}. Follow strict rules.",
                        )
                        is_valid, sanitized_sql, error_msg = validate_and_sanitize_sql(corrected_sql_raw)
                    except Exception:
                        pass

            if not is_valid:
                latency_ms = (time.time() - t_pipeline_start) * 1000
                st.session_state.last_latency_ms = latency_ms
                error_response = (
                    f"🛡️ **Query Rejected by Security Guardrail**\n\n"
                    f"**Reason:** {error_msg}\n\n"
                    f"*Defense-in-depth AST guardrail prevented unauthorized database access.*"
                )
                message_placeholder.markdown(error_response)
                st.session_state.messages.append({"role": "assistant", "content": error_response})
                log_query_event(
                    session_id=st.session_state.session_id,
                    intent="DATA_QUERY",
                    question=user_prompt,
                    generated_sql=raw_sql,
                    guardrail_result="BLOCKED",
                    rows_returned=0,
                    latency_ms=latency_ms,
                    error=error_msg,
                )
            else:
                # 4. Execute Query Against Database
                with st.spinner("⚡ Executing query against warehouse marts..."):
                    query_error = None
                    result_df = None

                    is_mock_llm = isinstance(llm, MockLLMAdapter)
                    if is_mock_llm and is_database_live():
                        query_error = "Mock LLM + live DB is impossible: mock adapter queries are strictly prohibited from running against a live warehouse."
                    else:
                        try:
                            result_df = execute_marts_query(sanitized_sql, is_mock_llm=is_mock_llm)
                        except Exception as db_err:
                            query_error = str(db_err)

                    # If database execution failed -> Trigger 1-turn retry by sending database error back to LLM
                    if query_error and not (is_mock_llm and is_database_live()):
                        with st.spinner("🔄 Database returned an error. Requesting LLM to correct SQL..."):
                            try:
                                retry_sql_raw = llm.generate_sql(
                                    question=user_prompt,
                                    schema_info=schema_text,
                                    error_context=f"SQL execution error in warehouse: {query_error}",
                                )
                                is_valid_retry, sanitized_sql_retry, err_retry = validate_and_sanitize_sql(retry_sql_raw)
                                if is_valid_retry:
                                    result_df = execute_marts_query(sanitized_sql_retry, is_mock_llm=is_mock_llm)
                                    sanitized_sql = sanitized_sql_retry
                                    query_error = None
                            except Exception as db_err_retry:
                                query_error = str(db_err_retry)

                # 5. Display Results
                latency_ms = (time.time() - t_pipeline_start) * 1000
                st.session_state.last_latency_ms = latency_ms

                if query_error:
                    fail_msg = (
                        f"❌ **Execution Error:** {query_error}\n\n"
                        "Please refine your question or select one of the suggested sample questions in the sidebar."
                    )
                    message_placeholder.markdown(fail_msg)
                    with st.expander("Attempted SQL"):
                        st.code(sanitized_sql, language="sql")
                    st.session_state.messages.append({"role": "assistant", "content": fail_msg, "sql": sanitized_sql})
                    log_query_event(
                        session_id=st.session_state.session_id,
                        intent="DATA_QUERY",
                        question=user_prompt,
                        generated_sql=sanitized_sql,
                        guardrail_result="ERROR",
                        rows_returned=0,
                        latency_ms=latency_ms,
                        error=query_error,
                    )
                else:
                    elapsed_time = round(latency_ms / 1000.0, 2)
                    row_count = len(result_df) if result_df is not None else 0

                    if is_database_live():
                        success_content = f"✅ Query executed successfully against live warehouse in **{elapsed_time}s** ({row_count} rows returned)."
                    else:
                        success_content = f"⚠️ **DEMO DATA - not real** (Synthetic query simulation - {row_count} rows returned)."
                    message_placeholder.markdown(success_content)

                    with st.expander("🔍 View Verified SQL Query", expanded=False):
                        st.code(sanitized_sql, language="sql")

                    insights_text = None
                    if result_df is not None and not result_df.empty:
                        st.dataframe(result_df, width="stretch")
                        render_intelligent_chart(result_df)

                        # 6. Executive Analysis & Recommendations Synthesis
                        with st.spinner("🧠 Generating executive analysis & strategic business recommendations..."):
                            summary_preview = result_df.head(20).to_string(index=False)
                            try:
                                insights_text = llm.generate_insights(
                                    question=user_prompt,
                                    sql_query=sanitized_sql,
                                    data_summary=summary_preview,
                                )
                            except Exception as insight_err:
                                insights_text = f"⚠️ *Note on strategic synthesis: {type(insight_err).__name__}*"

                        if insights_text:
                            st.markdown("---")
                            st.markdown("### 💡 Executive Analysis & Strategic Recommendations")
                            st.markdown(insights_text)
                    else:
                        st.info("Query returned 0 rows.")

                    # Save to session states
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": success_content,
                        "sql": sanitized_sql,
                        "df": result_df,
                        "insights": insights_text,
                    })
                    st.session_state.query_history.append({
                        "question": user_prompt,
                        "sql": sanitized_sql,
                    })
                    log_query_event(
                        session_id=st.session_state.session_id,
                        intent="DATA_QUERY",
                        question=user_prompt,
                        generated_sql=sanitized_sql,
                        guardrail_result="PASSED",
                        rows_returned=row_count,
                        latency_ms=latency_ms,
                        error=None,
                    )

