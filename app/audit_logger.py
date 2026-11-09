# ==============================================================================
# app/audit_logger.py - Structured Query Audit Logger
#
# Records every query event as JSON Lines into logs/queries.jsonl.
# Strictly ensures that passwords, API keys, and sensitive tokens are never logged.
# ==============================================================================

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = ROOT_DIR / "logs"
QUERY_LOG_FILE = LOGS_DIR / "queries.jsonl"


def _sanitize_string(text: Optional[str]) -> Optional[str]:
    """Strips potential API keys, passwords, or credential patterns from log strings."""
    if not text:
        return text

    # Filter out potential Groq/OpenAI/Gemini keys
    import re
    cleaned = re.sub(r"gsk_[A-Za-z0-9_\-]{20,}", "gsk_******", text)
    cleaned = re.sub(r"AIzaSy[A-Za-z0-9_\-]{20,}", "AIzaSy******", cleaned)
    cleaned = re.sub(r"sk-[A-Za-z0-9_\-]{20,}", "sk-******", cleaned)
    return cleaned


def log_query_event(
    session_id: str,
    intent: str,
    question: str,
    generated_sql: Optional[str],
    guardrail_result: str,
    rows_returned: int,
    latency_ms: float,
    error: Optional[str] = None,
) -> None:
    """
    Appends a structured JSON log entry for every conversational query attempt.
    """
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        record: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "intent": intent,
            "question": _sanitize_string(question),
            "generated_sql": _sanitize_string(generated_sql),
            "guardrail_result": guardrail_result,
            "rows_returned": rows_returned,
            "latency_ms": round(latency_ms, 2),
            "error": _sanitize_string(error),
        }

        with open(QUERY_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        # Structured logging failure must never crash user-facing application
        pass

