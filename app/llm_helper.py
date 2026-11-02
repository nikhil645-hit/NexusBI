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
from typing import Optional

SYSTEM_PROMPT_TEMPLATE = """You are an expert Data Engineering and Business Intelligence SQL Assistant.
Your task is to convert business questions into PostgreSQL / Amazon Redshift compliant SQL queries.

You have access ONLY to the following tables in the 'marts' schema:
{schema_info}

CRITICAL RULES:
1. Output ONLY executable SQL. Do NOT include markdown explanations, thought processes, or greetings.
2. Query ONLY tables in the 'marts' schema (mart_daily_sales, mart_top_products, mart_customer_summary, mart_delivery_performance).
3. Do NOT query 'raw' or 'staging' schemas.
4. Use standard read-only SELECT statements only. Never use DROP, DELETE, UPDATE, INSERT, ALTER, or TRUNCATE.
5. Always alias aggregated columns cleanly (e.g. total_revenue, units_sold).
6. When comparing dates or ordering by time, use sensible ORDER BY clauses.
7. Wrap your SQL output cleanly in ```sql ... ``` code blocks.
"""


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
        system_instruction = SYSTEM_PROMPT_TEMPLATE.format(schema_info=schema_info)
        
        prompt = f"User Question: {question}\n\nGenerate the Redshift SQL query:"
        if error_context:
            prompt += (
                f"\n\nNOTE: A previous attempt generated an error:\n{error_context}\n"
                "Please correct the SQL query to resolve this error."
            )

        full_prompt = f"{system_instruction}\n\n{prompt}"
        response = self.model.generate_content(full_prompt)
        return _extract_sql_from_text(response.text)


class AnthropicAdapter(BaseLLMAdapter):
    """Anthropic Claude LLM Adapter (claude-3-5-sonnet)."""

    def __init__(self, api_key: str):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)

    def generate_sql(
        self,
        question: str,
        schema_info: str,
        error_context: Optional[str] = None,
    ) -> str:
        system_instruction = SYSTEM_PROMPT_TEMPLATE.format(schema_info=schema_info)

        user_content = f"Question: {question}"
        if error_context:
            user_content += f"\n\nPrevious attempt failed with error:\n{error_context}\nPlease correct the SQL."

        message = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            temperature=0.0,
            system=system_instruction,
            messages=[{"role": "user", "content": user_content}],
        )
        return _extract_sql_from_text(message.content[0].text)


class MockLLMAdapter(BaseLLMAdapter):
    """
    Fallback adapter providing deterministic SQL for demonstration questions
    when no cloud LLM API key is present.
    """

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

    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY", "")
        if api_key and "your_" not in api_key:
            return GeminiAdapter(api_key=api_key)
    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if api_key and "your_" not in api_key:
            return AnthropicAdapter(api_key=api_key)

    # Fallback to Mock Adapter with a notification
    return MockLLMAdapter()
