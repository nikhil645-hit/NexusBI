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
                diff = abs(num_g - num_e)
                denom = max(abs(num_e), 1e-9)
                rel_diff = diff / denom
                if rel_diff > float_tolerance and diff > float_tolerance:
                    return (
                        False,
                        f"Value mismatch at row {r}, col {c}: {num_g} != {num_e} (tol={float_tolerance})",
                    )
                continue
            except (ValueError, TypeError):
                pass

            # String comparison (case-insensitive & whitespace-trimmed)
            str_g = str(val_g).strip().lower()
            str_e = str(val_e).strip().lower()

            # Date format normalization: treat '2018-01-01' and '2018-01' as equal
            norm_g = re.sub(r"^(\d{4}-\d{2})(-\d{2})?.*$", r"\1", str_g)
            norm_e = re.sub(r"^(\d{4}-\d{2})(-\d{2})?.*$", r"\1", str_e)
            if norm_g == norm_e:
                continue

            if str_g != str_e:
                return (
                    False,
                    f"String mismatch at row {r}, col {c}: '{val_g}' != '{val_e}'",
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
    """Executes a single benchmark iteration across questions."""
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

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_questions": total_count,
        "passed": passed_count,
        "overall_accuracy_pct": overall_acc,
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
    """Runs the benchmark suite across all configured questions with optional multi-run variance testing."""
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
    question_status_map: Dict[str, List[bool]] = {q["id"]: [] for q in questions}

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
            question_status_map[r["id"]].append(r["passed"])

    latest_pass = all_passes[-1]
    accuracies = [p["overall_accuracy_pct"] for p in all_passes]
    mean_acc = round(float(np.mean(accuracies)), 2)
    min_acc = round(float(min(accuracies)), 2)
    max_acc = round(float(max(accuracies)), 2)

    # Detect flipping questions (passed in some runs, failed in others)
    flipping_questions = [
        qid for qid, passes in question_status_map.items() if len(set(passes)) > 1
    ]

    summary_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "mock" if mock else "live",
        "llm_provider": "MockLLM" if mock else type(llm).__name__,
        "set": question_set,
        "runs": runs,
        "total_questions": latest_pass["total_questions"],
        "passed": latest_pass["passed"],
        "overall_accuracy_pct": latest_pass["overall_accuracy_pct"],
        "mean_accuracy_pct": mean_acc,
        "min_accuracy_pct": min_acc,
        "max_accuracy_pct": max_acc,
        "flipping_questions": flipping_questions,
        "avg_latency_ms": latest_pass["avg_latency_ms"],
        "difficulty_breakdown": latest_pass["difficulty_breakdown"],
        "results": latest_pass["results"],
    }

    # Handling output destinations based on parameters
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
                "mean_accuracy_pct": mean_acc,
                "min_accuracy_pct": min_acc,
                "max_accuracy_pct": max_acc,
                "flipping_questions": flipping_questions,
                "per_run_accuracies": accuracies,
                "per_run_summaries": [
                    {
                        "run_index": i + 1,
                        "passed": p["passed"],
                        "total": p["total_questions"],
                        "accuracy_pct": p["overall_accuracy_pct"],
                        "avg_latency_ms": p["avg_latency_ms"],
                    }
                    for i, p in enumerate(all_passes)
                ],
                "question_flip_details": {
                    qid: {
                        "passes": passes,
                        "flips": len(set(passes)) > 1,
                    }
                    for qid, passes in question_status_map.items()
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
    print(f" Mode               : {'MOCK (CI Smoke Test)' if mock else 'LIVE'}")
    print(f" Set                : {question_set.upper()}")
    print(f" Runs Executed      : {runs}")
    if runs > 1:
        print(f" Mean Accuracy      : {mean_acc}% (min: {min_acc}%, max: {max_acc}%)")
        print(f" Flipping Questions : {len(flipping_questions)} ({', '.join(flipping_questions) if flipping_questions else 'None'})")
    print(f" Latest Run Passed  : {latest_pass['passed']}/{latest_pass['total_questions']} ({latest_pass['overall_accuracy_pct']}%)")
    print(f" Average Latency    : {latest_pass['avg_latency_ms']} ms")
    print(f" Easy Accuracy      : {latest_pass['difficulty_breakdown']['easy']['accuracy_pct']}% ({latest_pass['difficulty_breakdown']['easy']['passed']}/{latest_pass['difficulty_breakdown']['easy']['total']})")
    print(f" Medium Accuracy    : {latest_pass['difficulty_breakdown']['medium']['accuracy_pct']}% ({latest_pass['difficulty_breakdown']['medium']['passed']}/{latest_pass['difficulty_breakdown']['medium']['total']})")
    print(f" Hard Accuracy      : {latest_pass['difficulty_breakdown']['hard']['accuracy_pct']}% ({latest_pass['difficulty_breakdown']['hard']['passed']}/{latest_pass['difficulty_breakdown']['hard']['total']})")
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
        f"- **Evaluation Set**: `{data.get('set', 'main')}`",
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


def generate_multi_run_markdown_report(
    data: Dict[str, Any],
    multi_data: Dict[str, Any],
    output_path: Path,
):
    """Generates an honest, clear Markdown report including multi-run variance and consistency metrics."""
    lines = [
        "# 📊 Text-to-SQL Accuracy & Variance Benchmark Report",
        "",
        f"- **Timestamp**: `{data['timestamp']}`",
        f"- **Benchmark Mode**: `{data['mode']}`",
        f"- **Evaluation Set**: `{data.get('set', 'main')}`",
        f"- **LLM Evaluated**: `{data['llm_provider']}` (Temperature: `0.0`)",
        f"- **Runs Evaluated**: `{multi_data['runs']}`",
        f"- **Mean Accuracy**: **`{multi_data['mean_accuracy_pct']}%`** (Min: `{multi_data['min_accuracy_pct']}%`, Max: `{multi_data['max_accuracy_pct']}%`)",
        f"- **Flipping Questions**: `{len(multi_data['flipping_questions'])}`",
        f"- **Average Query Latency**: `{data['avg_latency_ms']} ms`",
        "",
        "## 📈 Multi-Run Variance Breakdown",
        "",
        "| Run Index | Passed Questions | Total Questions | Accuracy % | Avg Latency (ms) |",
        "| :---: | :---: | :---: | :---: | :---: |",
    ]

    for r in multi_data["per_run_summaries"]:
        lines.append(
            f"| Run {r['run_index']} | {r['passed']} | {r['total']} | **{r['accuracy_pct']}%** | {r['avg_latency_ms']} |"
        )

    lines.extend([
        "",
        "## 🔄 Question Stability & Flips Across Runs",
        "",
    ])

    flips = multi_data["flipping_questions"]
    if not flips:
        lines.append("Zero flipping questions observed across runs. Query generation at temperature 0.0 was consistent.")
    else:
        lines.append(f"The following {len(flips)} question(s) flipped between passing and failing across evaluation runs:")
        lines.append("")
        lines.append("| Question ID | Run 1 | Run 2 | Run 3 | Stability Note |")
        lines.append("| :--- | :---: | :---: | :---: | :--- |")
        for qid in flips:
            passes = multi_data["question_flip_details"][qid]["passes"]
            statuses = ["✅ PASS" if p else "❌ FAIL" for p in passes]
            run_cols = " | ".join(statuses)
            pass_count = sum(passes)
            total = len(passes)
            lines.append(f"| `{qid}` | {run_cols} | Passed {pass_count}/{total} runs |")

    lines.extend([
        "",
        "## 🎯 Accuracy by Difficulty (Latest Run)",
        "",
        "| Difficulty | Total Questions | Passed | Accuracy % |",
        "| :--- | :---: | :---: | :---: |",
    ])

    for diff, stats in data["difficulty_breakdown"].items():
        lines.append(
            f"| **{diff.capitalize()}** | {stats['total']} | {stats['passed']} | {stats['accuracy_pct']}% |"
        )

    lines.extend([
        "",
        "## 🔬 Failure Analysis (Latest Run)",
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
