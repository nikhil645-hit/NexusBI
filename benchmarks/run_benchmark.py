# ==============================================================================
# benchmarks/run_benchmark.py - Text-to-SQL Accuracy & Safety Benchmark Harness
#
# Evaluates text-to-SQL generation accuracy against hand-crafted ground truth
# queries on Brazilian E-Commerce data marts.
#
# Flags:
#   --mock       Runs benchmark in mock/smoke-test mode for CI without API keys.
#   --limit N    Runs only the first N questions.
#   --verbose    Prints query details and error traces.
# ==============================================================================

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

# Add root directory to python path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db_helper import execute_marts_query, get_marts_schema_text
from app.llm_helper import get_llm_adapter
from app.sql_validator import validate_and_sanitize_sql

BENCHMARK_DIR = ROOT_DIR / "benchmarks"
QUESTIONS_FILE = BENCHMARK_DIR / "questions.yaml"
RESULTS_DIR = BENCHMARK_DIR / "results"


def load_questions() -> List[Dict[str, Any]]:
    """Loads benchmark questions from YAML ground truth file."""
    if not QUESTIONS_FILE.exists():
        raise FileNotFoundError(f"Questions file not found: {QUESTIONS_FILE}")
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("questions", [])


def compare_result_sets(
    df_gen: pd.DataFrame,
    df_exp: pd.DataFrame,
    order_sensitive: bool = False,
    float_tolerance: float = 0.05,
) -> Tuple[bool, str]:
    """
    Compares two query result sets semantically.
    Ignores column names/aliases and casing.
    Allows small float tolerance for rounding differences.
    """
    if df_gen is None or df_exp is None:
        return False, "One of the result DataFrames is None"

    if df_gen.empty and df_exp.empty:
        return True, "Both result sets are empty"

    if df_gen.shape != df_exp.shape:
        return (
            False,
            f"Shape mismatch: generated {df_gen.shape} vs expected {df_exp.shape}",
        )

    # Convert to numpy arrays without column names
    arr_gen = df_gen.to_numpy()
    arr_exp = df_exp.to_numpy()

    # If row order does not strictly matter and >1 row, sort by first numeric or string column
    if not order_sensitive and len(arr_gen) > 1:
        try:
            # Sort lexicographically by first column representation
            idx_gen = np.lexsort([arr_gen[:, 0].astype(str)])
            idx_exp = np.lexsort([arr_exp[:, 0].astype(str)])
            arr_gen = arr_gen[idx_gen]
            arr_exp = arr_exp[idx_exp]
        except Exception:
            pass

    for r in range(arr_gen.shape[0]):
        for c in range(arr_gen.shape[1]):
            val_g = arr_gen[r, c]
            val_e = arr_exp[r, c]

            # Handle None / NaN
            if pd.isna(val_g) and pd.isna(val_e):
                continue
            if pd.isna(val_g) != pd.isna(val_e):
                return False, f"Null mismatch at row {r}, col {c}: {val_g} != {val_e}"

            # Numeric comparison with relative & absolute tolerance
            try:
                num_g = float(val_g)
                num_e = float(val_e)
                if not np.isclose(num_g, num_e, rtol=float_tolerance, atol=float_tolerance):
                    return (
                        False,
                        f"Value mismatch at row {r}, col {c}: {num_g} != {num_e} (tol={float_tolerance})",
                    )
                continue
            except (ValueError, TypeError):
                pass

            # String comparison (lowercase, trimmed)
            str_g = str(val_g).strip().lower()
            str_e = str(val_e).strip().lower()
            if str_g != str_e:
                # Normalize date and year-month representations (e.g. '2018-01-01' vs '2018-01')
                norm_g = re.sub(r"^(\d{4}-\d{2})(-\d{2})?.*$", r"\1", str_g)
                norm_e = re.sub(r"^(\d{4}-\d{2})(-\d{2})?.*$", r"\1", str_e)
                if re.match(r"^\d{4}-\d{2}$", norm_g) and re.match(r"^\d{4}-\d{2}$", norm_e) and norm_g == norm_e:
                    continue
                return (
                    False,
                    f"String mismatch at row {r}, col {c}: '{str_g}' != '{str_e}'",
                )

    return True, "Results match within tolerance"


def execute_with_guardrail(sql_query: str) -> Tuple[bool, Optional[pd.DataFrame], str]:
    """Validates query via AST guardrail and executes if valid."""
    is_valid, sanitized_sql, fail_reason = validate_and_sanitize_sql(sql_query)
    if not is_valid:
        return False, None, f"Guardrail Rejection: {fail_reason}"

    try:
        df = execute_marts_query(sanitized_sql)
        return True, df, sanitized_sql
    except Exception as e:
        return False, None, f"SQL Execution Error: {str(e)}"


def run_benchmark(
    mock: bool = False,
    limit: Optional[int] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Runs the benchmark suite across all configured questions."""
    questions = load_questions()
    if limit:
        questions = questions[:limit]

    schema_info = get_marts_schema_text()

    if mock:
        print("[INFO] Running benchmark in MOCK smoke-test mode (CI/Offline).")
        llm = None
    else:
        llm = get_llm_adapter()
        print(f"[INFO] Running live benchmark with adapter: {type(llm).__name__}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    total_latency_ms = 0.0

    print(f"\n[BENCHMARK] Executing {len(questions)} test cases...")
    print("-" * 75)

    for idx, item in enumerate(questions, 1):
        q_id = item["id"]
        q_diff = item["difficulty"]
        q_text = item["question"]
        expected_sql = item["expected_sql"]
        order_matters = "order by" in expected_sql.lower() and "limit" in expected_sql.lower()

        # Step 1: Run expected SQL ground truth to get baseline result
        exp_valid, exp_df, exp_info = execute_with_guardrail(expected_sql)
        if not exp_valid:
            print(f"[ERROR] Ground truth query for {q_id} failed: {exp_info}")

        # Step 2: Generate SQL via LLM (or mock ground truth in mock mode)
        start_time = time.time()
        generated_sql = ""
        gen_error = ""

        if mock:
            # Smoke test: simulates correct generation through real AST guardrail & DB execution
            generated_sql = expected_sql
            time.sleep(0.01)
        else:
            # Real LLM call with retry logic for rate limits
            retries = 3
            backoff = 2.0
            for attempt in range(retries):
                try:
                    generated_sql = llm.generate_sql(q_text, schema_info)
                    break
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "rate limit" in err_str.lower():
                        if attempt < retries - 1:
                            time.sleep(backoff)
                            backoff *= 2
                            continue
                    gen_error = f"LLM Generation Error: {err_str}"
                    break

        latency_ms = round((time.time() - start_time) * 1000, 2)
        total_latency_ms += latency_ms

        # Step 3: Validate and execute generated SQL
        passed = False
        blocked_by_guardrail = False
        reason = ""

        if gen_error:
            reason = gen_error
        else:
            is_valid, gen_df, gen_info = execute_with_guardrail(generated_sql)
            if not is_valid:
                blocked_by_guardrail = True
                reason = gen_info
            elif exp_df is not None and gen_df is not None:
                matched, cmp_reason = compare_result_sets(
                    gen_df, exp_df, order_sensitive=order_matters
                )
                passed = matched
                reason = cmp_reason if not matched else "PASSED"
            else:
                passed = False
                reason = "Comparison failed: missing DataFrame"

        status_icon = "PASS" if passed else "FAIL"
        print(f"[{status_icon}] {q_id} ({q_diff.upper()}): {q_text[:45]}... ({latency_ms}ms)")
        if not passed and verbose:
            print(f"       Generated: {generated_sql[:60]}...")
            print(f"       Reason:    {reason}")

        results.append({
            "id": q_id,
            "difficulty": q_diff,
            "question": q_text,
            "passed": passed,
            "guardrail_blocked": blocked_by_guardrail,
            "latency_ms": latency_ms,
            "reason": reason,
            "generated_sql": generated_sql,
            "expected_sql": expected_sql,
        })

    # Metrics computation
    total_count = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    overall_acc = round((passed_count / total_count) * 100, 2) if total_count else 0.0
    avg_latency = round(total_latency_ms / total_count, 2) if total_count else 0.0

    diff_breakdown: Dict[str, Dict[str, Any]] = {}
    for diff in ["easy", "medium", "hard"]:
        diff_items = [r for r in results if r["difficulty"] == diff]
        diff_total = len(diff_items)
        diff_passed = sum(1 for r in diff_items if r["passed"])
        diff_acc = round((diff_passed / diff_total) * 100, 2) if diff_total else 0.0
        diff_breakdown[diff] = {
            "total": diff_total,
            "passed": diff_passed,
            "accuracy_pct": diff_acc,
        }

    summary_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "mock" if mock else "live",
        "llm_provider": "MockLLM" if mock else type(llm).__name__,
        "total_questions": total_count,
        "passed": passed_count,
        "overall_accuracy_pct": overall_acc,
        "avg_latency_ms": avg_latency,
        "difficulty_breakdown": diff_breakdown,
        "results": results,
    }

    # Write latest.json
    json_path = RESULTS_DIR / "latest.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)

    # Write REPORT.md
    report_path = RESULTS_DIR / "REPORT.md"
    generate_markdown_report(summary_payload, report_path)

    print("\n" + "=" * 75)
    print(" BENCHMARK COMPLETE SUMMARY")
    print("=" * 75)
    print(f" Mode               : {'MOCK (CI Smoke Test)' if mock else 'LIVE'}")
    print(f" Total Questions    : {total_count}")
    print(f" Passed             : {passed_count}/{total_count}")
    print(f" Overall Accuracy   : {overall_acc}%")
    print(f" Average Latency    : {avg_latency} ms")
    print(f" Easy Accuracy      : {diff_breakdown['easy']['accuracy_pct']}% ({diff_breakdown['easy']['passed']}/{diff_breakdown['easy']['total']})")
    print(f" Medium Accuracy    : {diff_breakdown['medium']['accuracy_pct']}% ({diff_breakdown['medium']['passed']}/{diff_breakdown['medium']['total']})")
    print(f" Hard Accuracy      : {diff_breakdown['hard']['accuracy_pct']}% ({diff_breakdown['hard']['passed']}/{diff_breakdown['hard']['total']})")
    print(f" Artifacts Saved To : {RESULTS_DIR}")
    print("=" * 75)

    return summary_payload


def generate_markdown_report(data: Dict[str, Any], output_path: Path):
    """Generates an honest, clear Markdown report of benchmark results."""
    lines = [
        "# 📊 Text-to-SQL Accuracy Benchmark Report",
        "",
        f"- **Timestamp**: `{data['timestamp']}`",
        f"- **Benchmark Mode**: `{data['mode']}`",
        f"- **LLM Evaluated**: `{data['llm_provider']}`",
        f"- **Total Test Questions**: `{data['total_questions']}`",
        f"- **Overall Accuracy**: **`{data['overall_accuracy_pct']}%`** ({data['passed']}/{data['total_questions']})",
        f"- **Average Query Latency**: `{data['avg_latency_ms']} ms`",
        "",
        "## 🎯 Accuracy by Difficulty",
        "",
        "| Difficulty | Total Questions | Passed | Accuracy % |",
        "| :--- | :---: | :---: | :---: |",
    ]

    for diff, stats in data["difficulty_breakdown"].items():
        lines.append(
            f"| **{diff.capitalize()}** | {stats['total']} | {stats['passed']} | {stats['accuracy_pct']}% |"
        )

    lines.extend([
        "",
        "## 🔬 Failure Analysis",
        "",
    ])

    failures = [r for r in data["results"] if not r["passed"]]
    if not failures:
        lines.append("All benchmark questions passed semantic validation against ground truth.")
    else:
        lines.append("| Question ID | Difficulty | Question | Reason |")
        lines.append("| :--- | :---: | :--- | :--- |")
        for f in failures:
            lines.append(
                f"| `{f['id']}` | {f['difficulty']} | {f['question']} | {f['reason']} |"
            )

        lines.extend([
            "",
            "### Detailed Failure Diffs",
            "",
        ])
        for f in failures:
            lines.extend([
                f"#### `{f['id']}` - {f['question']}",
                f"- **Failure Reason**: {f['reason']}",
                "```sql",
                "-- Generated SQL",
                f"{f['generated_sql']}",
                "",
                "-- Expected Ground Truth SQL",
                f"{f['expected_sql']}",
                "```",
                "",
            ])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run NexusBI Text-to-SQL Benchmark")
    parser.add_argument("--mock", action="store_true", help="Run in mock/smoke test mode for CI")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of questions")
    parser.add_argument("--verbose", action="store_true", help="Verbose failure output")
    args = parser.parse_args()

    run_benchmark(mock=args.mock, limit=args.limit, verbose=args.verbose)

