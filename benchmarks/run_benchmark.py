# ==============================================================================
# benchmarks/run_benchmark.py - Text-to-SQL Accuracy & Safety Benchmark Harness
#
# Evaluates text-to-SQL generation accuracy against hand-crafted ground truth
# queries on Brazilian E-Commerce data marts.
#
# Scoring Policy:
#   1. Strict: Requires exact DataFrame matrix dimensions and 1:1 column match.
#   2. Lenient: Requires matching row count and presence of all expected column
#      values in generated result (allows extra generated helper columns).
#
# Flags:
#   --mock       Runs benchmark in mock/smoke-test mode for CI without API keys.
#   --limit N    Runs only the first N questions.
#   --verbose    Prints query details and error traces.
#   --runs N     Runs the suite N times to evaluate variance, mean/min/max accuracy.
#   --set SET    Question set to evaluate: 'main' (default) or 'heldout'.
# ==============================================================================

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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
RESULTS_DIR = BENCHMARK_DIR / "results"


def load_questions(question_set: str = "main") -> List[Dict[str, Any]]:
    """Loads benchmark questions from YAML ground truth file."""
    if question_set == "heldout":
        target_file = BENCHMARK_DIR / "heldout.yaml"
    else:
        target_file = BENCHMARK_DIR / "questions.yaml"

    if not target_file.exists():
        raise FileNotFoundError(f"Questions file not found: {target_file}")
    with open(target_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("questions", [])


def _values_match(val_g: Any, val_e: Any, float_tolerance: float = 0.05) -> bool:
    """Helper comparing two scalar values with float tolerance, None handling, and date normalization."""
    if pd.isna(val_g) and pd.isna(val_e):
        return True
    if pd.isna(val_g) != pd.isna(val_e):
        return False

    # Numeric comparison with relative & absolute tolerance
    try:
        num_g = float(val_g)
        num_e = float(val_e)
        diff = abs(num_g - num_e)
        denom = max(abs(num_e), 1e-9)
        rel_diff = diff / denom
        if rel_diff <= float_tolerance or diff <= float_tolerance:
            return True
        return False
    except (ValueError, TypeError):
        pass

    # String comparison (case-insensitive & whitespace-trimmed)
    str_g = str(val_g).strip().lower()
    str_e = str(val_e).strip().lower()

    # Date format normalization: treat '2018-01-01' and '2018-01' as equal
    norm_g = re.sub(r"^(\d{4}-\d{2})(-\d{2})?.*$", r"\1", str_g)
    norm_e = re.sub(r"^(\d{4}-\d{2})(-\d{2})?.*$", r"\1", str_e)
    if norm_g == norm_e:
        return True

    return str_g == str_e


def compare_result_sets(
    df_gen: pd.DataFrame,
    df_exp: pd.DataFrame,
    order_sensitive: bool = False,
    float_tolerance: float = 0.05,
) -> Tuple[bool, str]:
    """
    Strict comparator:
    Requires exact shape match, row count, column count, and cell-by-cell equality.
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

    arr_gen = df_gen.to_numpy()
    arr_exp = df_exp.to_numpy()

    # If row order does not strictly matter and >1 row, sort by first column
    if not order_sensitive and len(arr_gen) > 1:
        try:
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

            if not _values_match(val_g, val_e, float_tolerance):
                try:
                    num_g = float(val_g)
                    num_e = float(val_e)
                    return (
                        False,
                        f"Value mismatch at row {r}, col {c}: {num_g} != {num_e} (tol={float_tolerance})",
                    )
                except (ValueError, TypeError):
                    return (
                        False,
                        f"String mismatch at row {r}, col {c}: '{val_g}' != '{val_e}'",
                    )

    return True, "PASSED"


def compare_result_sets_lenient(
    df_gen: pd.DataFrame,
    df_exp: pd.DataFrame,
    order_sensitive: bool = False,
    float_tolerance: float = 0.05,
) -> Tuple[bool, str]:
    """
    Lenient comparator:
    - Pass if every expected column's values appear in the generated result
      (matched by values, not names).
    - Row count must match.
    - Extra generated columns are allowed.
    - Ordering rules and numeric tolerance stay unchanged.
    """
    if df_gen is None or df_exp is None:
        return False, "One of the result DataFrames is None"

    if df_gen.empty and df_exp.empty:
        return True, "Both result sets are empty"

    if len(df_gen) != len(df_exp):
        return (
            False,
            f"Row count mismatch: generated {len(df_gen)} vs expected {len(df_exp)}",
        )

    if df_gen.shape[1] < df_exp.shape[1]:
        return (
            False,
            f"Fewer columns in generated ({df_gen.shape[1]}) than expected ({df_exp.shape[1]})",
        )

    arr_gen = df_gen.to_numpy()
    arr_exp = df_exp.to_numpy()
    num_rows = len(arr_exp)
    num_exp_cols = arr_exp.shape[1]
    num_gen_cols = arr_gen.shape[1]

    # If row order does not strictly matter, align rows by sorting on first matching key
    if not order_sensitive and num_rows > 1:
        try:
            idx_exp = np.lexsort([arr_exp[:, 0].astype(str)])
            arr_exp = arr_exp[idx_exp]

            best_gen_sort_col = 0
            for g_col in range(num_gen_cols):
                matches = sum(
                    1 for r in range(num_rows)
                    if _values_match(arr_gen[r, g_col], arr_exp[r, 0], float_tolerance)
                )
                if matches == num_rows:
                    best_gen_sort_col = g_col
                    break
            idx_gen = np.lexsort([arr_gen[:, best_gen_sort_col].astype(str)])
            arr_gen = arr_gen[idx_gen]
        except Exception:
            pass

    # Match each expected column to a unique generated column
    assigned_gen_cols: Set[int] = set()
    unmatched_exp_cols: List[int] = []

    for c_e in range(num_exp_cols):
        matched_gen_col: Optional[int] = None
        for c_g in range(num_gen_cols):
            if c_g in assigned_gen_cols:
                continue
            col_match = True
            for r in range(num_rows):
                if not _values_match(arr_gen[r, c_g], arr_exp[r, c_e], float_tolerance):
                    col_match = False
                    break
            if col_match:
                matched_gen_col = c_g
                break

        if matched_gen_col is not None:
            assigned_gen_cols.add(matched_gen_col)
        else:
            unmatched_exp_cols.append(c_e)

    if unmatched_exp_cols:
        return (
            False,
            f"Expected column(s) {unmatched_exp_cols} not found among generated columns",
        )

    return True, "PASSED"


def execute_with_guardrail(sql: str) -> Tuple[bool, Optional[pd.DataFrame], str]:
    """Validates SQL query through AST guardrail and executes on warehouse if valid."""
    is_valid, sanitized_sql, reason = validate_and_sanitize_sql(sql)
    if not is_valid:
        return False, None, f"Guardrail Blocked: {reason}"

    try:
        df = execute_marts_query(sanitized_sql)
        return True, df, "Success"
    except Exception as e:
        return False, None, f"SQL Execution Error: {str(e)}"


def run_single_pass(
    questions: List[Dict[str, Any]],
    schema_info: str,
    llm: Any,
    mock: bool = False,
    verbose: bool = False,
    pass_index: int = 1,
    total_passes: int = 1,
) -> Dict[str, Any]:
    """Executes a single benchmark iteration across questions with dual strict/lenient evaluation."""
    results: List[Dict[str, Any]] = []
    total_latency_ms = 0.0

    header_prefix = f" [Run {pass_index}/{total_passes}]" if total_passes > 1 else ""
    print(f"\n[BENCHMARK]{header_prefix} Executing {len(questions)} test cases...")
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
            generated_sql = expected_sql
            time.sleep(0.01)
        else:
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
        passed_strict = False
        passed_lenient = False
        blocked_by_guardrail = False
        reason_strict = ""
        reason_lenient = ""

        if gen_error:
            reason_strict = gen_error
            reason_lenient = gen_error
        else:
            is_valid, gen_df, gen_info = execute_with_guardrail(generated_sql)
            if not is_valid:
                blocked_by_guardrail = True
                reason_strict = gen_info
                reason_lenient = gen_info
            elif exp_df is not None and gen_df is not None:
                matched_strict, cmp_reason_strict = compare_result_sets(
                    gen_df, exp_df, order_sensitive=order_matters
                )
                matched_lenient, cmp_reason_lenient = compare_result_sets_lenient(
                    gen_df, exp_df, order_sensitive=order_matters
                )
                passed_strict = matched_strict
                passed_lenient = matched_lenient
                reason_strict = cmp_reason_strict if not matched_strict else "PASSED"
                reason_lenient = cmp_reason_lenient if not matched_lenient else "PASSED"
            else:
                passed_strict = False
                passed_lenient = False
                reason_strict = "Comparison failed: missing DataFrame"
                reason_lenient = "Comparison failed: missing DataFrame"

        status_icon = (
            "PASS"
            if passed_strict
            else ("PASS-LENIENT" if passed_lenient else "FAIL")
        )
        print(f"[{status_icon}] {q_id} ({q_diff.upper()}): {q_text[:45]}... ({latency_ms}ms)", flush=True)
        if not passed_strict and verbose:
            print(f"       Generated: {generated_sql[:60]}...", flush=True)
            print(f"       Reason (Strict):  {reason_strict}", flush=True)
            if passed_lenient:
                print("       Status (Lenient): PASSED (extra columns allowed)", flush=True)

        results.append({
            "id": q_id,
            "difficulty": q_diff,
            "question": q_text,
            "passed": passed_strict,
            "passed_strict": passed_strict,
            "passed_lenient": passed_lenient,
            "guardrail_blocked": blocked_by_guardrail,
            "latency_ms": latency_ms,
            "reason": reason_strict,
            "reason_strict": reason_strict,
            "reason_lenient": reason_lenient,
            "generated_sql": generated_sql,
            "expected_sql": expected_sql,
        })

    # Metrics computation
    total_count = len(results)
    passed_strict_count = sum(1 for r in results if r["passed_strict"])
    passed_lenient_count = sum(1 for r in results if r["passed_lenient"])
    strict_acc = round((passed_strict_count / total_count) * 100, 2) if total_count else 0.0
    lenient_acc = round((passed_lenient_count / total_count) * 100, 2) if total_count else 0.0
    avg_latency = round(total_latency_ms / total_count, 2) if total_count else 0.0

    diff_breakdown: Dict[str, Dict[str, Any]] = {}
    for diff in ["easy", "medium", "hard"]:
        diff_items = [r for r in results if r["difficulty"] == diff]
        diff_total = len(diff_items)
        diff_strict_pass = sum(1 for r in diff_items if r["passed_strict"])
        diff_lenient_pass = sum(1 for r in diff_items if r["passed_lenient"])
        diff_breakdown[diff] = {
            "total": diff_total,
            "passed": diff_strict_pass,
            "passed_strict": diff_strict_pass,
            "passed_lenient": diff_lenient_pass,
            "accuracy_pct": round((diff_strict_pass / diff_total) * 100, 2) if diff_total else 0.0,
            "strict_accuracy_pct": round((diff_strict_pass / diff_total) * 100, 2) if diff_total else 0.0,
            "lenient_accuracy_pct": round((diff_lenient_pass / diff_total) * 100, 2) if diff_total else 0.0,
        }

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_questions": total_count,
        "passed": passed_strict_count,
        "passed_strict": passed_strict_count,
        "passed_lenient": passed_lenient_count,
        "overall_accuracy_pct": strict_acc,
        "strict_accuracy_pct": strict_acc,
        "lenient_accuracy_pct": lenient_acc,
        "avg_latency_ms": avg_latency,
        "difficulty_breakdown": diff_breakdown,
        "results": results,
    }


def run_benchmark(
    mock: bool = False,
    limit: Optional[int] = None,
    verbose: bool = False,
    runs: int = 1,
    question_set: str = "main",
) -> Dict[str, Any]:
    """Runs the benchmark suite across all configured questions with dual strict/lenient scoring and variance testing."""
    questions = load_questions(question_set=question_set)
    if limit:
        questions = questions[:limit]

    schema_info = get_marts_schema_text()

    if mock:
        print(f"[INFO] Running benchmark in MOCK smoke-test mode (CI/Offline) on set '{question_set}'.")
        llm = None
    else:
        llm = get_llm_adapter()
        print(f"[INFO] Running live benchmark with adapter: {type(llm).__name__} (set: '{question_set}', temperature: 0.0)")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    all_passes: List[Dict[str, Any]] = []
    strict_status_map: Dict[str, List[bool]] = {q["id"]: [] for q in questions}
    lenient_status_map: Dict[str, List[bool]] = {q["id"]: [] for q in questions}

    for run_idx in range(1, runs + 1):
        pass_res = run_single_pass(
            questions=questions,
            schema_info=schema_info,
            llm=llm,
            mock=mock,
            verbose=verbose,
            pass_index=run_idx,
            total_passes=runs,
        )
        all_passes.append(pass_res)
        for r in pass_res["results"]:
            strict_status_map[r["id"]].append(r["passed_strict"])
            lenient_status_map[r["id"]].append(r["passed_lenient"])

    latest_pass = all_passes[-1]

    # Metrics across passes
    strict_accs = [p["strict_accuracy_pct"] for p in all_passes]
    lenient_accs = [p["lenient_accuracy_pct"] for p in all_passes]

    mean_strict = round(float(np.mean(strict_accs)), 2)
    min_strict = round(float(min(strict_accs)), 2)
    max_strict = round(float(max(strict_accs)), 2)

    mean_lenient = round(float(np.mean(lenient_accs)), 2)
    min_lenient = round(float(min(lenient_accs)), 2)
    max_lenient = round(float(max(lenient_accs)), 2)

    flipping_strict = [
        qid for qid, passes in strict_status_map.items() if len(set(passes)) > 1
    ]
    flipping_lenient = [
        qid for qid, passes in lenient_status_map.items() if len(set(passes)) > 1
    ]

    summary_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "mock" if mock else "live",
        "llm_provider": "MockLLM" if mock else type(llm).__name__,
        "set": question_set,
        "runs": runs,
        "total_questions": latest_pass["total_questions"],
        "passed": latest_pass["passed_strict"],
        "passed_strict": latest_pass["passed_strict"],
        "passed_lenient": latest_pass["passed_lenient"],
        "overall_accuracy_pct": latest_pass["strict_accuracy_pct"],
        "strict_accuracy_pct": latest_pass["strict_accuracy_pct"],
        "lenient_accuracy_pct": latest_pass["lenient_accuracy_pct"],
        "mean_accuracy_pct": mean_strict,
        "mean_strict_accuracy_pct": mean_strict,
        "mean_lenient_accuracy_pct": mean_lenient,
        "min_strict_accuracy_pct": min_strict,
        "max_strict_accuracy_pct": max_strict,
        "min_lenient_accuracy_pct": min_lenient,
        "max_lenient_accuracy_pct": max_lenient,
        "flipping_questions": flipping_strict,
        "flipping_strict": flipping_strict,
        "flipping_lenient": flipping_lenient,
        "avg_latency_ms": latest_pass["avg_latency_ms"],
        "difficulty_breakdown": latest_pass["difficulty_breakdown"],
        "results": latest_pass["results"],
    }

    # Output destination routing
    if question_set == "heldout":
        json_path = RESULTS_DIR / "heldout.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary_payload, f, indent=2)
        report_path = RESULTS_DIR / "heldout_REPORT.md"
        generate_markdown_report(summary_payload, report_path)
    else:
        json_path = RESULTS_DIR / "latest.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary_payload, f, indent=2)

        if runs > 1:
            multi_run_payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mode": "mock" if mock else "live",
                "llm_provider": "MockLLM" if mock else type(llm).__name__,
                "set": question_set,
                "runs": runs,
                "total_questions": latest_pass["total_questions"],
                "mean_strict_accuracy_pct": mean_strict,
                "min_strict_accuracy_pct": min_strict,
                "max_strict_accuracy_pct": max_strict,
                "mean_lenient_accuracy_pct": mean_lenient,
                "min_lenient_accuracy_pct": min_lenient,
                "max_lenient_accuracy_pct": max_lenient,
                "flipping_strict": flipping_strict,
                "flipping_lenient": flipping_lenient,
                "per_run_summaries": [
                    {
                        "run_index": i + 1,
                        "passed_strict": p["passed_strict"],
                        "strict_accuracy_pct": p["strict_accuracy_pct"],
                        "passed_lenient": p["passed_lenient"],
                        "lenient_accuracy_pct": p["lenient_accuracy_pct"],
                        "total": p["total_questions"],
                        "avg_latency_ms": p["avg_latency_ms"],
                    }
                    for i, p in enumerate(all_passes)
                ],
                "question_stability": {
                    qid: {
                        "strict_passes": strict_status_map[qid],
                        "lenient_passes": lenient_status_map[qid],
                        "strict_flips": len(set(strict_status_map[qid])) > 1,
                        "lenient_flips": len(set(lenient_status_map[qid])) > 1,
                    }
                    for qid in strict_status_map
                },
            }
            multi_json_path = RESULTS_DIR / "multi_run.json"
            with open(multi_json_path, "w", encoding="utf-8") as f:
                json.dump(multi_run_payload, f, indent=2)

            report_path = RESULTS_DIR / "REPORT.md"
            generate_multi_run_markdown_report(
                summary_payload, multi_run_payload, report_path
            )
        else:
            report_path = RESULTS_DIR / "REPORT.md"
            generate_markdown_report(summary_payload, report_path)

    print("\n" + "=" * 75)
    print(" BENCHMARK COMPLETE SUMMARY")
    print("=" * 75)
    print(f" Mode                 : {'MOCK (CI Smoke Test)' if mock else 'LIVE'}")
    print(f" Set                  : {question_set.upper()}")
    print(f" Runs Executed        : {runs}")
    if runs > 1:
        print(f" Strict Mean Accuracy : {mean_strict}% (min: {min_strict}%, max: {max_strict}%)")
        print(f" Lenient Mean Accuracy: {mean_lenient}% (min: {min_lenient}%, max: {max_lenient}%)")
        print(f" Strict Flipping Qs   : {len(flipping_strict)} ({', '.join(flipping_strict) if flipping_strict else 'None'})")
        print(f" Lenient Flipping Qs  : {len(flipping_lenient)} ({', '.join(flipping_lenient) if flipping_lenient else 'None'})")
    else:
        print(f" Strict Accuracy      : {latest_pass['strict_accuracy_pct']}% ({latest_pass['passed_strict']}/{latest_pass['total_questions']})")
        print(f" Lenient Accuracy     : {latest_pass['lenient_accuracy_pct']}% ({latest_pass['passed_lenient']}/{latest_pass['total_questions']})")
    print(f" Average Latency      : {latest_pass['avg_latency_ms']} ms")
    print(f" Artifacts Saved To   : {RESULTS_DIR}")
    print("=" * 75)

    return summary_payload


def generate_markdown_report(data: Dict[str, Any], output_path: Path):
    """Generates an honest, clear Markdown report of benchmark results with dual strict/lenient scores."""
    lines = [
        "# 📊 Text-to-SQL Accuracy Benchmark Report",
        "",
        f"- **Timestamp**: `{data['timestamp']}`",
        f"- **Benchmark Mode**: `{data['mode']}`",
        f"- **Evaluation Set**: `{data.get('set', 'main')}`",
        f"- **LLM Evaluated**: `{data['llm_provider']}`",
        f"- **Total Test Questions**: `{data['total_questions']}`",
        f"- **Strict Accuracy**: **`{data['strict_accuracy_pct']}%`** ({data['passed_strict']}/{data['total_questions']})",
        f"- **Lenient Accuracy**: **`{data['lenient_accuracy_pct']}%`** ({data['passed_lenient']}/{data['total_questions']})",
        f"- **Average Query Latency**: `{data['avg_latency_ms']} ms`",
        "",
        "> [!NOTE]",
        "> **Strict scoring** requires exact matrix shape match (1:1 column projection).",
        "> **Lenient scoring** requires matching row count and all expected column values, but permits harmless extra helper columns.",
        "",
        "## 🎯 Accuracy by Difficulty",
        "",
        "| Difficulty | Total Questions | Strict Passed | Strict % | Lenient Passed | Lenient % |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ]

    for diff, stats in data["difficulty_breakdown"].items():
        lines.append(
            f"| **{diff.capitalize()}** | {stats['total']} | {stats['passed_strict']} | {stats['strict_accuracy_pct']}% | {stats['passed_lenient']} | {stats['lenient_accuracy_pct']}% |"
        )

    lines.extend([
        "",
        "## 🔬 Failure Analysis (Strict Scoring)",
        "",
    ])

    failures = [r for r in data["results"] if not r["passed_strict"]]
    if not failures:
        lines.append("All benchmark questions passed strict semantic validation against ground truth.")
    else:
        lines.append("| Question ID | Difficulty | Question | Reason (Strict) | Passed Lenient? |")
        lines.append("| :--- | :---: | :--- | :--- | :---: |")
        for f in failures:
            lines.append(
                f"| `{f['id']}` | {f['difficulty']} | {f['question']} | {f['reason_strict']} | {'✅ Yes' if f['passed_lenient'] else '❌ No'} |"
            )

        lines.extend([
            "",
            "### Detailed Failure Diffs",
            "",
        ])
        for f in failures:
            len_status = (
                "PASSED (Contains all expected columns; extra columns present)"
                if f["passed_lenient"]
                else f"FAILED ({f['reason_lenient']})"
            )
            lines.extend([
                f"#### `{f['id']}` - {f['question']}",
                f"- **Strict Failure Reason**: {f['reason_strict']}",
                f"- **Lenient Outcome**: {len_status}",
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


def generate_multi_run_markdown_report(
    data: Dict[str, Any],
    multi_data: Dict[str, Any],
    output_path: Path,
):
    """Generates an honest, clear Markdown report including multi-run variance and dual scoring metrics."""
    lines = [
        "# 📊 Text-to-SQL Accuracy & Variance Benchmark Report",
        "",
        f"- **Timestamp**: `{data['timestamp']}`",
        f"- **Benchmark Mode**: `{data['mode']}`",
        f"- **Evaluation Set**: `{data.get('set', 'main')}`",
        f"- **LLM Evaluated**: `{data['llm_provider']}` (Temperature: `0.0`)",
        f"- **Runs Evaluated**: `{multi_data['runs']}`",
        f"- **Strict Mean Accuracy**: **`{multi_data['mean_strict_accuracy_pct']}%`** (Min: `{multi_data['min_strict_accuracy_pct']}%`, Max: `{multi_data['max_strict_accuracy_pct']}%`)",
        f"- **Lenient Mean Accuracy**: **`{multi_data['mean_lenient_accuracy_pct']}%`** (Min: `{multi_data['min_lenient_accuracy_pct']}%`, Max: `{multi_data['max_lenient_accuracy_pct']}%`)",
        f"- **Strict Flipping Questions**: `{len(multi_data['flipping_strict'])}`",
        f"- **Average Query Latency**: `{data['avg_latency_ms']} ms`",
        "",
        "> [!NOTE]",
        "> **Strict scoring** requires exact matrix shape match (1:1 column projection).",
        "> **Lenient scoring** requires matching row count and all expected column values, but permits harmless extra helper columns.",
        "",
        "## 📈 Multi-Run Variance Breakdown",
        "",
        "| Run Index | Strict Passed | Strict % | Lenient Passed | Lenient % | Total Qs | Avg Latency (ms) |",
        "| :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for r in multi_data["per_run_summaries"]:
        lines.append(
            f"| Run {r['run_index']} | {r['passed_strict']} | **{r['strict_accuracy_pct']}%** | {r['passed_lenient']} | **{r['lenient_accuracy_pct']}%** | {r['total']} | {r['avg_latency_ms']} |"
        )

    lines.extend([
        "",
        "## 🔄 Question Stability & Flips Across Runs",
        "",
    ])

    flips = multi_data["flipping_strict"]
    if not flips:
        lines.append("Zero flipping questions observed across runs under strict scoring.")
    else:
        lines.append(f"The following {len(flips)} question(s) flipped under strict scoring across evaluation runs:")
        lines.append("")
        lines.append("| Question ID | Run 1 (Strict) | Run 2 (Strict) | Run 3 (Strict) | Lenient Outcome |")
        lines.append("| :--- | :---: | :---: | :---: | :--- |")
        for qid in flips:
            passes = multi_data["question_stability"][qid]["strict_passes"]
            statuses = ["✅ PASS" if p else "❌ FAIL" for p in passes]
            run_cols = " | ".join(statuses)
            lenient_p = multi_data["question_stability"][qid]["lenient_passes"]
            len_summary = "100% Pass" if all(lenient_p) else f"{sum(lenient_p)}/{len(lenient_p)} Pass"
            lines.append(f"| `{qid}` | {run_cols} | {len_summary} |")

    lines.extend([
        "",
        "## 🎯 Accuracy by Difficulty (Latest Run)",
        "",
        "| Difficulty | Total Questions | Strict Passed | Strict % | Lenient Passed | Lenient % |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ])

    for diff, stats in data["difficulty_breakdown"].items():
        lines.append(
            f"| **{diff.capitalize()}** | {stats['total']} | {stats['passed_strict']} | {stats['strict_accuracy_pct']}% | {stats['passed_lenient']} | {stats['lenient_accuracy_pct']}% |"
        )

    lines.extend([
        "",
        "## 🔬 Failure Analysis (Latest Run - Strict Scoring)",
        "",
    ])

    failures = [r for r in data["results"] if not r["passed_strict"]]
    if not failures:
        lines.append("All benchmark questions passed strict semantic validation against ground truth.")
    else:
        lines.append("| Question ID | Difficulty | Question | Reason (Strict) | Passed Lenient? |")
        lines.append("| :--- | :---: | :--- | :--- | :---: |")
        for f in failures:
            lines.append(
                f"| `{f['id']}` | {f['difficulty']} | {f['question']} | {f['reason_strict']} | {'✅ Yes' if f['passed_lenient'] else '❌ No'} |"
            )

        lines.extend([
            "",
            "### Detailed Failure Diffs",
            "",
        ])
        for f in failures:
            len_status = (
                "PASSED (Contains all expected columns; extra columns present)"
                if f["passed_lenient"]
                else f"FAILED ({f['reason_lenient']})"
            )
            lines.extend([
                f"#### `{f['id']}` - {f['question']}",
                f"- **Strict Failure Reason**: {f['reason_strict']}",
                f"- **Lenient Outcome**: {len_status}",
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
    parser.add_argument("--runs", type=int, default=1, help="Number of benchmark iterations to measure variance")
    parser.add_argument("--set", type=str, default="main", choices=["main", "heldout"], help="Question set (main or heldout)")
    args = parser.parse_args()

    run_benchmark(
        mock=args.mock,
        limit=args.limit,
        verbose=args.verbose,
        runs=args.runs,
        question_set=args.set,
    )
