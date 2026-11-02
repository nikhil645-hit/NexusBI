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
import time
from typing import Optional
import streamlit as st
import pandas as pd

from app.sql_validator import validate_and_sanitize_sql
from app.db_helper import (
    get_marts_schema_text,
    execute_marts_query,
    is_warehouse_configured,
)
from app.llm_helper import get_llm_adapter, BaseLLMAdapter

# ------------------------------------------------------------------------------
# Page Configuration & Styling
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="Olist Conversational BI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom styling for clean enterprise demo
st.markdown(
    """
    <style>
    .main-header { font-size: 2.1rem; font-weight: 700; color: #1E293B; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1.05rem; color: #64748B; margin-bottom: 1.5rem; }
    .badge-provider { background-color: #EEF2F6; color: #1E40AF; padding: 4px 10px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; }
    .badge-status-ok { background-color: #DCFCE7; color: #166534; padding: 4px 10px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; }
    .badge-status-mock { background-color: #FEF3C7; color: #92400E; padding: 4px 10px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; }
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


# ------------------------------------------------------------------------------
# Sidebar: System Metadata, Data Dictionary & Sample Prompts
# ------------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ System Control")

    # Provider and Warehouse Status
    provider_name = os.getenv("LLM_PROVIDER", "gemini").upper()
    has_db = is_warehouse_configured()

    st.markdown(f"**LLM Provider:** <span class='badge-provider'>{provider_name}</span>", unsafe_allow_html=True)
    if has_db:
        st.markdown("**Warehouse:** <span class='badge-status-ok'>Local Postgres (5434)</span>", unsafe_allow_html=True)
    else:
        st.markdown("**Warehouse:** <span class='badge-status-mock'>Offline / Mock Mode</span>", unsafe_allow_html=True)

    st.divider()

    # Marts Schema Overview
    st.subheader("📚 Data Marts Catalog")
    with st.expander("mart_daily_sales (Sales Trends)", expanded=False):
        st.caption("Daily revenue, order volume, freight costs, and average order value (AOV).")
    with st.expander("mart_top_products (Catalog)", expanded=False):
        st.caption("Leaderboard ranking products and categories by gross revenue and volume.")
    with st.expander("mart_customer_summary (Buyers)", expanded=False):
        st.caption("Customer lifetime spend, geographic state/city, order count, and dates.")
    with st.expander("mart_delivery_performance (Logistics)", expanded=False):
        st.caption("Fulfillment SLAs, carrier transit durations, and percentage of delayed shipments.")

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
        if st.button(f"{i}. {q}", key=f"sample_{i}", use_container_width=True):
            st.session_state.selected_sample_question = q

    st.divider()

    # Session Query History
    st.subheader("🕒 Session Query History")
    if not st.session_state.query_history:
        st.caption("No queries executed yet.")
    else:
        for idx, item in enumerate(reversed(st.session_state.query_history[-5:])):
            st.caption(f"**Q:** {item['question']}")
            st.code(item['sql'], language="sql")


# ------------------------------------------------------------------------------
# Main Application Header
# ------------------------------------------------------------------------------
st.markdown("<div class='main-header'>📊 Olist Conversational BI</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='sub-header'>"
    "Ask analytical questions in natural language. Queries are translated to SQL by LLM, "
    "verified through <code>sqlglot</code> security guardrails, and executed against PostgreSQL data warehouse marts."
    "</div>",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------------------
# Intelligent Chart Rendering Helper
# ------------------------------------------------------------------------------
def render_intelligent_chart(df: pd.DataFrame):
    """Detects date or categorical series and plots sensible interactive Streamlit charts."""
    if df.empty or len(df.columns) < 2:
        return

    col_names_lower = [c.lower() for c in df.columns]

    # Date-based time series -> Line Chart
    date_cols = [c for c in df.columns if any(k in c.lower() for k in ["date", "month", "day", "time"])]
    numeric_cols = [c for c in df.select_dtypes(include=["number"]).columns]

    if date_cols and numeric_cols:
        primary_date_col = date_cols[0]
        st.markdown("##### 📈 Trend Visualization")
        chart_data = df[[primary_date_col] + numeric_cols[:2]].copy()
        try:
            chart_data = chart_data.set_index(primary_date_col)
            st.line_chart(chart_data)
            return
        except Exception:
            pass

    # Categorical Leaderboard -> Bar Chart
    cat_cols = [c for c in df.select_dtypes(include=["object", "string"]).columns]
    if cat_cols and numeric_cols:
        primary_cat = cat_cols[0]
        primary_num = numeric_cols[0]
        st.markdown("##### 📊 Comparative Bar Chart")
        bar_data = df[[primary_cat, primary_num]].copy().head(10)
        try:
            bar_data = bar_data.set_index(primary_cat)
            st.bar_chart(bar_data)
            return
        except Exception:
            pass


# ------------------------------------------------------------------------------
# Render Past Chat Messages
# ------------------------------------------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "sql" in msg:
            with st.expander("🔍 View Verified SQL Query", expanded=False):
                st.code(msg["sql"], language="sql")
        if "df" in msg and msg["df"] is not None:
            st.dataframe(msg["df"], use_container_width=True)
            render_intelligent_chart(msg["df"])


# ------------------------------------------------------------------------------
# Chat Input & Query Execution Pipeline
# ------------------------------------------------------------------------------
# Check if user clicked a sample question from sidebar
user_prompt = st.chat_input("Ask a question about sales, products, customers, or delivery...")
if st.session_state.selected_sample_question:
    user_prompt = st.session_state.selected_sample_question
    st.session_state.selected_sample_question = None

if user_prompt:
    # 1. Display User Question
    st.session_state.messages.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        st.markdown(user_prompt)

    # 2. Process with LLM and Security Guardrails
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        schema_text = get_marts_schema_text()
        llm = get_llm_adapter()

        with st.spinner("🤖 Translating question to PostgreSQL SQL..."):
            t_start = time.time()
            raw_sql = llm.generate_sql(question=user_prompt, schema_info=schema_text)

        # 3. Deterministic AST Security Validation
        is_valid, sanitized_sql, error_msg = validate_and_sanitize_sql(raw_sql)

        if not is_valid:
            # First attempt failed validation -> Trigger 1-turn retry to let LLM self-correct
            with st.spinner("⚠️ Security rule triggered. Retrying with self-correction..."):
                corrected_sql_raw = llm.generate_sql(
                    question=user_prompt,
                    schema_info=schema_text,
                    error_context=f"Query rejected by security validator: {error_msg}. Follow strict rules.",
                )
                is_valid, sanitized_sql, error_msg = validate_and_sanitize_sql(corrected_sql_raw)

        if not is_valid:
            error_response = (
                f"🛡️ **Query Rejected by Security Guardrail**\n\n"
                f"**Reason:** {error_msg}\n\n"
                f"*In a viva defense, this demonstrates our defense-in-depth architecture blocking unauthorized access.*"
            )
            message_placeholder.markdown(error_response)
            st.session_state.messages.append({"role": "assistant", "content": error_response})
        else:
            # 4. Execute Query Against Database
            with st.spinner("⚡ Executing query against warehouse marts..."):
                query_error = None
                result_df = None

                try:
                    result_df = execute_marts_query(sanitized_sql)
                except Exception as db_err:
                    query_error = str(db_err)

                # If database execution failed -> Trigger 1-turn retry by sending database error back to LLM
                if query_error:
                    with st.spinner("🔄 Database returned an error. Requesting LLM to correct SQL..."):
                        retry_sql_raw = llm.generate_sql(
                            question=user_prompt,
                            schema_info=schema_text,
                            error_context=f"SQL execution error in warehouse: {query_error}",
                        )
                        is_valid_retry, sanitized_sql_retry, err_retry = validate_and_sanitize_sql(retry_sql_raw)
                        if is_valid_retry:
                            try:
                                result_df = execute_marts_query(sanitized_sql_retry)
                                sanitized_sql = sanitized_sql_retry
                                query_error = None
                            except Exception as db_err_retry:
                                query_error = str(db_err_retry)

            # 5. Display Results
            if query_error:
                fail_msg = (
                    f"❌ **Execution Error:** {query_error}\n\n"
                    "Please refine your question or select one of the suggested sample questions in the sidebar."
                )
                message_placeholder.markdown(fail_msg)
                with st.expander("Attempted SQL"):
                    st.code(sanitized_sql, language="sql")
                st.session_state.messages.append({"role": "assistant", "content": fail_msg, "sql": sanitized_sql})
            else:
                elapsed_time = round(time.time() - t_start, 2)
                row_count = len(result_df) if result_df is not None else 0

                success_content = f"✅ Query executed successfully in **{elapsed_time}s** ({row_count} rows returned)."
                message_placeholder.markdown(success_content)

                with st.expander("🔍 View Verified SQL Query", expanded=False):
                    st.code(sanitized_sql, language="sql")

                if result_df is not None and not result_df.empty:
                    st.dataframe(result_df, use_container_width=True)
                    render_intelligent_chart(result_df)
                else:
                    st.info("Query returned 0 rows.")

                # Save to session states
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": success_content,
                    "sql": sanitized_sql,
                    "df": result_df,
                })
                st.session_state.query_history.append({
                    "question": user_prompt,
                    "sql": sanitized_sql,
                })

