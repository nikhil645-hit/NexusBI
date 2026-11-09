# ==============================================================================
# app/llm_helper.py - LLM Text-to-SQL Provider Adapter
#
# Supported Providers:
#   1. Google Gemini (LLM_PROVIDER=gemini, GEMINI_API_KEY)
#   2. Anthropic Claude (LLM_PROVIDER=anthropic, ANTHROPIC_API_KEY)
#   3. Mock Fallback (used when API keys are not yet configured)
#
# Includes single-turn retry logic: if a generated query fails validation or
# database execution, the error is fed back to the LLM to self-correct.
# ==============================================================================

import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import yaml

_SEMANTIC_LAYER_PATH = Path(__file__).resolve().parent / "semantic_layer.yaml"


def get_semantic_context() -> str:
    """Loads semantic layer metrics and canonical few-shot examples for LLM context."""
    if not _SEMANTIC_LAYER_PATH.exists():
        return ""
    try:
        with open(_SEMANTIC_LAYER_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        lines = ["\nBUSINESS METRIC DEFINITIONS & FORMULAS:"]
        for name, info in data.get("metrics", {}).items():
            lines.append(f"- {name.replace('_', ' ').title()}: {info['formula']} (Table: {info['table']}) - {info['description']}")

        lines.append("\nCANONICAL FEW-SHOT EXAMPLES:")
        for ex in data.get("canonical_examples", []):
            lines.append(f"-- Question: {ex['question']}")
            lines.append(f"{ex['sql'].strip()}\n")
        return "\n".join(lines)
    except Exception:
        return ""


SYSTEM_PROMPT_TEMPLATE = """You are an expert Data Engineering and Business Intelligence SQL Assistant.
Your task is to convert business questions into PostgreSQL compliant SQL queries.

You have access ONLY to the following tables in the 'marts' schema:
{schema_info}
{semantic_context}

CRITICAL RULES:
1. Output ONLY executable SQL. Do NOT include markdown explanations, thought processes, or greetings.
2. Query ONLY tables in the 'marts' schema (mart_daily_sales, mart_top_products, mart_customer_summary, mart_delivery_performance).
3. Do NOT query 'raw' or 'staging' schemas.
4. Use standard read-only SELECT statements only. Never use DROP, DELETE, UPDATE, INSERT, ALTER, or TRUNCATE.
5. Always alias aggregated columns cleanly (e.g. total_revenue, units_sold).
6. When comparing dates or ordering by time, use sensible ORDER BY clauses.
7. Wrap your SQL output cleanly in ```sql ... ``` code blocks.
8. Output exactly ONE single SELECT statement. NEVER output multiple semicolon-separated queries. If multiple metrics are asked, combine them into a single SELECT statement.
"""


def build_system_prompt(schema_info: str) -> str:
    """Builds the comprehensive system prompt including live schema and semantic layer definitions."""
    return SYSTEM_PROMPT_TEMPLATE.format(
        schema_info=schema_info,
        semantic_context=get_semantic_context(),
    )

INSIGHTS_SYSTEM_PROMPT = """You are an elite Senior Data Analyst and Business Strategy Consultant for an e-commerce platform.
The user asked an analytical question. A verified SQL query was executed on the PostgreSQL data warehouse, returning the data provided below.

Your job is to provide a comprehensive, high-impact Executive Summary and Actionable Strategic Recommendations:
1. 📊 Key Findings: 2-3 clear bullet points explaining what the data shows (quantify numbers, trends, peaks, drops).
2. 💡 Strategic Recommendations: Concrete, actionable business steps directly addressing the user's specific goals (e.g. how to increase revenue next month, marketing tactics, inventory/product focus, customer retention, logistics optimization).
3. 🎯 Projections & Next Steps: Quantifiable goals or milestones.

Be direct, professional, and data-driven. Format with clear Markdown headings and bullet points. Do NOT merely repeat raw tables; analyze and interpret the results to provide real business value.
"""

ADVISORY_SYSTEM_PROMPT = """You are a Principal E-Commerce Business Strategy and Growth Advisor.
You advise founders, retail directors, and executives on how to grow revenue, optimize margins, reduce customer churn, maximize average order value (AOV), and improve customer lifetime value (LTV).

Provide concrete, actionable, professional strategic frameworks with:
1. 💡 Core Strategic Levers (Acquisition, Conversion Rate Optimization, AOV Expansion, Retention)
2. 📋 30/60/90 Day Tactical Action Items
3. 🎯 Key Performance Indicators (KPIs) to track success
4. ⚠️ Common Pitfalls & Risks to avoid

Format your answer with clear markdown headings, bullet points, and high-impact executive summaries.
"""

ARCHITECTURE_SYSTEM_PROMPT = """You are a Principal Data Platform Architect and Academic Viva Defense Coach.
You designed and deployed this modern end-to-end Data Engineering pipeline for the Brazilian E-Commerce (Olist) public dataset.

Architecture Overview:
- Source: Local PostgreSQL 16 transactional OLTP database (port 5433).
- Ingestion: Airbyte OSS replicating data into AWS RDS PostgreSQL (ap-southeast-2 Sydney) 'raw' schema.
- Transformation: dbt Core modeling dimensional star schemas (views in 'staging', persistent analytics tables in 'marts': mart_daily_sales, mart_top_products, mart_customer_summary, mart_delivery_performance).
- Data Quality: 41 automated dbt schema tests (not_null, unique, relationships, accepted_values).
- Orchestration: Apache Airflow (LocalExecutor) running daily DAGs.
- Conversational BI: Streamlit web application powered by LLM (Groq / Gemini) with an Abstract Syntax Tree (AST) deterministic security guardrail (sqlglot) enforcing read-only SELECT queries on marts schema with forced limits.

Provide clear, technically rigorous, educational, and viva-ready explanations. Emphasize architectural decisions, trade-offs, scalability, and security best practices.
"""


def detect_dashboard_type(question: str) -> str:
    """Infers the requested dashboard category from user prompt."""
    q = question.lower()
    if any(k in q for k in ["deliver", "logist", "late", "transit", "sla", "shipping", "carrier"]):
        return "delivery"
    elif any(k in q for k in ["custom", "buyer", "spend", "user", "client", "retention", "ltv", "state", "geo"]):
        return "customer"
    elif any(k in q for k in ["product", "item", "catalog", "sku", "category", "leaderboard", "bestseller"]):
        return "product"
    elif any(k in q for k in ["360", "overview", "cockpit", "all", "company", "executive", "platform"]):
        return "360"
    else:
        return "sales"


class BaseLLMAdapter(ABC):
    """Abstract interface for LLM text-to-SQL adapters."""

    @abstractmethod
    def generate_sql(
        self,
        question: str,
        schema_info: str,
        error_context: Optional[str] = None,
    ) -> str:
        """Generates SQL from user question and schema definition."""
        pass

    @abstractmethod
    def generate_insights(
        self,
        question: str,
        sql_query: str,
        data_summary: str,
    ) -> str:
        """Generates executive business insights and recommendations based on returned data."""
        pass

    @abstractmethod
    def generate_advisory_or_architecture(
        self,
        question: str,
        system_type: str = "advisory",
    ) -> str:
        """Generates strategic business advice or data pipeline architectural explanations."""
        pass

    @abstractmethod
    def classify_intent(self, question: str) -> str:
        """Classifies user intent into: DATA_QUERY, BUSINESS_STRATEGY, or ARCHITECTURE_VIVA."""
        pass


class GeminiAdapter(BaseLLMAdapter):
    """Google Gemini LLM Adapter (gemini-1.5-flash)."""

    def __init__(self, api_key: str):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={"temperature": 0.0},
        )

    def generate_sql(
        self,
        question: str,
        schema_info: str,
        error_context: Optional[str] = None,
    ) -> str:
        system_instruction = build_system_prompt(schema_info)

        prompt = f"User Question: {question}\n\nGenerate the Redshift SQL query:"
        if error_context:
            prompt += (
                f"\n\nNOTE: A previous attempt generated an error:\n{error_context}\n"
                "Please correct the SQL query to resolve this error."
            )

        full_prompt = f"{system_instruction}\n\n{prompt}"
        response = self.model.generate_content(full_prompt)
        return _extract_sql_from_text(response.text)

    def generate_insights(
        self,
        question: str,
        sql_query: str,
        data_summary: str,
    ) -> str:
        prompt = (
            f"{INSIGHTS_SYSTEM_PROMPT}\n\n"
            f"User Question: {question}\n\n"
            f"Executed SQL Query:\n```sql\n{sql_query}\n```\n\n"
            f"Retrieved Data Summary:\n{data_summary}\n\n"
            "Provide executive analysis, key findings, and actionable recommendations answering the user's question."
        )
        response = self.model.generate_content(prompt)
        return response.text.strip()

    def generate_advisory_or_architecture(
        self,
        question: str,
        system_type: str = "advisory",
    ) -> str:
        sys_prompt = ARCHITECTURE_SYSTEM_PROMPT if system_type == "architecture" else ADVISORY_SYSTEM_PROMPT
        prompt = f"{sys_prompt}\n\nUser Question: {question}"
        response = self.model.generate_content(prompt)
        return response.text.strip()

    def classify_intent(self, question: str) -> str:
        q_lower = question.lower()
        if "dashboard" in q_lower:
            return "DASHBOARD_REQUEST"
        prompt = (
            "Classify this question into exactly one category: DASHBOARD_REQUEST, DATA_QUERY, BUSINESS_STRATEGY, or ARCHITECTURE_VIVA.\n"
            f"Question: {question}\nCategory:"
        )
        try:
            resp = self.model.generate_content(prompt)
            text = resp.text.strip().upper()
            if "DASH" in text:
                return "DASHBOARD_REQUEST"
            if "DATA" in text:
                return "DATA_QUERY"
            if "ARCH" in text or "VIVA" in text:
                return "ARCHITECTURE_VIVA"
            if "STRAT" in text or "BUS" in text:
                return "BUSINESS_STRATEGY"
            return "DATA_QUERY"
        except Exception:
            return "DATA_QUERY"


class GroqCloudAdapter(BaseLLMAdapter):
    """
    Groq Cloud Adapter (Free, ultra-fast cloud-hosted models e.g. openai/gpt-oss-120b, qwen/qwen3.8-27b).
    Uses 0 MB local RAM and generates SQL in ~0.5 seconds.
    """

    def __init__(self, api_key: str, model: str = "openai/gpt-oss-120b"):
        self.api_key = api_key
        self.model = model

    def generate_sql(
        self,
        question: str,
        schema_info: str,
        error_context: Optional[str] = None,
    ) -> str:
        import requests

        system_instruction = build_system_prompt(schema_info)
        user_prompt = f"User Question: {question}\n\nGenerate ONLY executable SQL inside ```sql ... ``` code block:"
        if error_context:
            user_prompt += f"\n\nPrevious attempt failed with error:\n{error_context}\nPlease correct the SQL."

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
        }

        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["choices"][0]["message"]["content"]
        return _extract_sql_from_text(raw_text)

    def generate_insights(
        self,
        question: str,
        sql_query: str,
        data_summary: str,
    ) -> str:
        import requests

        user_content = (
            f"User Question: {question}\n\n"
            f"Executed SQL Query:\n```sql\n{sql_query}\n```\n\n"
            f"Retrieved Data Summary:\n{data_summary}\n\n"
            "Provide executive analysis, key findings, and actionable recommendations answering the user's question."
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": INSIGHTS_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.3,
        }

        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def generate_advisory_or_architecture(
        self,
        question: str,
        system_type: str = "advisory",
    ) -> str:
        import requests

        sys_prompt = ARCHITECTURE_SYSTEM_PROMPT if system_type == "architecture" else ADVISORY_SYSTEM_PROMPT
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": question},
            ],
            "temperature": 0.3,
        }

        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def classify_intent(self, question: str) -> str:
        q_lower = question.lower()
        if "dashboard" in q_lower:
            return "DASHBOARD_REQUEST"

        import requests

        system_prompt = (
            "You are an intent classifier for a Data Engineering and Conversational BI platform. "
            "Given a user question, classify it into exactly one of four categories:\n"
            "1. DASHBOARD_REQUEST: The user asks to create, build, generate, open, or view a dashboard.\n"
            "2. DATA_QUERY: The user is asking for numbers, metrics, trends, counts, rankings, or specific data from the database (e.g. 'sales in 2018', 'revenue trend', 'top products', 'late delivery rate'). Even if they also ask 'how to increase it', if it asks for data/trends, classify as DATA_QUERY.\n"
            "3. BUSINESS_STRATEGY: The user is asking ONLY for general business advice, marketing ideas, conversion rate optimization, or growth tactics without asking for database queries.\n"
            "4. ARCHITECTURE_VIVA: The user is asking about how the data pipeline, Airbyte, dbt, Airflow, RDS, star schema, or security guardrails work.\n\n"
            "Reply with ONLY one exact keyword: DASHBOARD_REQUEST, DATA_QUERY, BUSINESS_STRATEGY, or ARCHITECTURE_VIVA."
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            "temperature": 0.0,
        }

        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            intent = resp.json()["choices"][0]["message"]["content"].strip().upper()
            if "DASH" in intent:
                return "DASHBOARD_REQUEST"
            elif "DATA" in intent or "QUERY" in intent:
                return "DATA_QUERY"
            elif "ARCH" in intent or "VIVA" in intent or "PIPELINE" in intent:
                return "ARCHITECTURE_VIVA"
            elif "STRAT" in intent or "BUS" in intent or "ADVIS" in intent:
                return "BUSINESS_STRATEGY"
            return "DATA_QUERY"
        except Exception:
            return "DATA_QUERY"


class OllamaAdapter(BaseLLMAdapter):
    """Local Ollama LLM Adapter (e.g. llama3.2, mistral, qwen2.5-coder)."""

    def __init__(self, model: str = "llama3.2:3b", base_url: str = "http://127.0.0.1:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def generate_sql(
        self,
        question: str,
        schema_info: str,
        error_context: Optional[str] = None,
    ) -> str:
        import requests

        system_instruction = build_system_prompt(schema_info)
        prompt = (
            f"{system_instruction}\n\n"
            f"User Question: {question}\n\n"
            "Generate ONLY the executable PostgreSQL SQL query inside ```sql ... ``` code block:"
        )
        if error_context:
            prompt += (
                f"\n\nNOTE: A previous attempt generated an error:\n{error_context}\n"
                "Please correct the SQL query to resolve this error."
            )

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,
            },
        }

        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=90,
            )
            resp.raise_for_status()
            raw_text = resp.json().get("response", "")
            return _extract_sql_from_text(raw_text)
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"Could not connect to Ollama at {self.base_url}.\n"
                "Please make sure Ollama is open and running on your computer."
            )

    def generate_insights(
        self,
        question: str,
        sql_query: str,
        data_summary: str,
    ) -> str:
        import requests

        prompt = (
            f"{INSIGHTS_SYSTEM_PROMPT}\n\n"
            f"User Question: {question}\n\n"
            f"Executed SQL Query:\n```sql\n{sql_query}\n```\n\n"
            f"Retrieved Data Summary:\n{data_summary}\n\n"
            "Provide executive analysis, key findings, and actionable recommendations answering the user's question."
        )
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3},
        }
        try:
            resp = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=90)
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except Exception as e:
            return f"Unable to generate insight via local Ollama: {e}"

    def generate_advisory_or_architecture(
        self,
        question: str,
        system_type: str = "advisory",
    ) -> str:
        import requests
        sys_prompt = ARCHITECTURE_SYSTEM_PROMPT if system_type == "architecture" else ADVISORY_SYSTEM_PROMPT
        payload = {
            "model": self.model,
            "prompt": f"{sys_prompt}\n\nQuestion: {question}",
            "stream": False,
        }
        try:
            resp = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=90)
            return resp.json().get("response", "").strip()
        except Exception as e:
            return f"Error via local Ollama: {e}"

    def classify_intent(self, question: str) -> str:
        return "DATA_QUERY"


class MockLLMAdapter(BaseLLMAdapter):
    """
    Fallback adapter providing deterministic SQL for demonstration questions
    when no cloud LLM API key is present.
    """

    def classify_intent(self, question: str) -> str:
        q_lower = question.lower()
        if "dashboard" in q_lower:
            return "DASHBOARD_REQUEST"
        if any(w in q_lower for w in ["architecture", "pipeline", "airbyte", "dbt", "airflow", "viva", "schema"]):
            return "ARCHITECTURE_VIVA"
        elif any(w in q_lower for w in ["how to increase", "how can we increase", "strategy", "marketing", "advice"]):
            return "BUSINESS_STRATEGY"
        return "DATA_QUERY"

    def generate_advisory_or_architecture(self, question: str, system_type: str = "advisory") -> str:
        if system_type == "architecture":
            return (
                "### 🏗️ Pipeline Architecture & Engineering Design\n"
                "- **Ingestion**: Airbyte OSS extracts from transactional PostgreSQL (`port 5433`) into AWS RDS PostgreSQL `raw` schema.\n"
                "- **Transformation**: dbt Core models dimensional star-schemas (`staging` views -> `marts` tables).\n"
                "- **Quality Assurance**: 41 automated dbt schema tests verify uniqueness, not-null constraints, and relationships.\n"
                "- **Orchestration**: Apache Airflow DAGs schedule daily ELT syncs with retry logic.\n"
                "- **Security**: `sqlglot` Abstract Syntax Tree (AST) deterministic guardrail ensures only read-only queries against marts are executed."
            )
        else:
            return (
                "### 💡 E-Commerce Revenue Growth Playbook\n"
                "1. **Conversion Rate Optimization**: Streamline the checkout funnel to reduce friction.\n"
                "2. **AOV Expansion**: Introduce complementary product bundles and minimum-spend free shipping thresholds.\n"
                "3. **Customer Retention**: Deploy automated email flows for high-intent abandoned carts and repeat buyer VIP tiers.\n"
                "4. **Logistics Optimization**: Reduce delivery lead times to boost seller ratings and repeat purchases."
            )

    def generate_insights(
        self,
        question: str,
        sql_query: str,
        data_summary: str,
    ) -> str:
        return (
            "### 📊 Key Findings\n"
            "- Analyzed performance across the queried dimension with solid order volumes.\n"
            "- Average order value remains healthy and consistent across the period.\n\n"
            "### 💡 Strategic Recommendations for Next Month\n"
            "1. **Targeted Campaigns**: Deploy personalized discounts for high-intent shoppers.\n"
            "2. **Product Bundling**: Bundle top-selling accessories to lift Average Order Value (AOV).\n"
            "3. **Logistics Optimization**: Reduce delivery lead times in top buyer states to boost 5-star ratings."
        )

    def generate_sql(
        self,
        question: str,
        schema_info: str,
        error_context: Optional[str] = None,
    ) -> str:
        q_lower = question.lower()
        if "top 5 product categories" in q_lower or "top product" in q_lower:
            return (
                "SELECT category_name, SUM(units_sold) AS total_units, SUM(total_revenue) AS total_revenue\n"
                "FROM marts.mart_top_products\n"
                "GROUP BY category_name\n"
                "ORDER BY total_revenue DESC\n"
                "LIMIT 5;"
            )
        elif "daily sales" in q_lower or "trend" in q_lower or "last 30 days" in q_lower:
            return (
                "SELECT sales_date, total_orders, total_revenue, avg_order_value\n"
                "FROM marts.mart_daily_sales\n"
                "ORDER BY sales_date DESC\n"
                "LIMIT 30;"
            )
        elif "brazilian states" in q_lower or "highest customer" in q_lower or "state" in q_lower:
            return (
                "SELECT customer_state, COUNT(DISTINCT customer_unique_id) AS total_buyers, SUM(total_spend) AS total_spend\n"
                "FROM marts.mart_customer_summary\n"
                "GROUP BY customer_state\n"
                "ORDER BY total_spend DESC\n"
                "LIMIT 10;"
            )
        elif "delivered late" in q_lower or "percentage" in q_lower or "late" in q_lower:
            return (
                "SELECT year_month, total_delivered_orders, late_orders_count, pct_late_vs_estimated\n"
                "FROM marts.mart_delivery_performance\n"
                "ORDER BY year_month DESC\n"
                "LIMIT 12;"
            )
        elif "top 10 customers" in q_lower or "customer" in q_lower:
            return (
                "SELECT customer_unique_id, customer_city, customer_state, total_orders, total_spend\n"
                "FROM marts.mart_customer_summary\n"
                "ORDER BY total_spend DESC\n"
                "LIMIT 10;"
            )
        elif "delivery duration" in q_lower or "delivery" in q_lower:
            return (
                "SELECT year_month, avg_delivery_days, avg_estimated_delivery_days\n"
                "FROM marts.mart_delivery_performance\n"
                "ORDER BY year_month DESC\n"
                "LIMIT 12;"
            )
        else:
            return (
                "SELECT * FROM marts.mart_daily_sales\n"
                "ORDER BY sales_date DESC\n"
                "LIMIT 10;"
            )


def _extract_sql_from_text(text: str) -> str:
    """Strips markdown code blocks and returns cleanly formatted SQL string."""
    match = re.search(r"```(?:sql)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()


def get_llm_adapter() -> BaseLLMAdapter:
    """Factory creating the appropriate LLM adapter based on environment variables."""
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()

    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY", "")
        if api_key and "your_" not in api_key:
            model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
            return GroqCloudAdapter(api_key=api_key, model=model)
    elif provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY", "")
        if api_key and "your_" not in api_key:
            return GeminiAdapter(api_key=api_key)
    elif provider == "ollama":
        model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        return OllamaAdapter(model=model, base_url=base_url)

    # Fallback to Mock Adapter with a notification
    return MockLLMAdapter()

