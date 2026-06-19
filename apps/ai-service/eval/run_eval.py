#!/usr/bin/env python
"""
CLI entry point for AIWear evaluation.

Usage
-----

    # Run single-turn cases with stub agent (fast validation)
    python -m eval.run_eval --mock --cases cases/sample_cases.json

    # Run with real agent
    python -m eval.run_eval --cases cases/sample_cases.json

    # Run multi-turn cases and save baseline
    python -m eval.run_eval --cases cases/multi_turn_cases.json        \
                            --save-baseline baselines/multi_baseline.json

    # Run, compare against baseline, save report
    python -m eval.run_eval --cases cases/sample_cases.json            \
                            --baseline baselines/latest_baseline.json  \
                            --output reports/latest_report.json

    # CI mode: exit 0 only if all pass AND no regressions
    python -m eval.run_eval --cases cases/sample_cases.json --ci --baseline eval/history/latest.json

    # Tag filter: only run cases tagged "wardrobe"
    python -m eval.run_eval --mock --cases cases/sample_cases.json --tag wardrobe

    # Save report to a timestamped directory
    python -m eval.run_eval --mock --cases cases/sample_cases.json --output-dir reports

Exit code: 0 if all cases pass (and in CI mode, no regressions); 1 otherwise.
"""

import argparse
import json
import sys
import os
from datetime import datetime

# Ensure the project root is on sys.path so that ``from server import ...``
# works when the real agent is used.
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from eval.runner import run_eval, load_cases, save_results
from eval.reporter import generate_report, save_baseline
from eval.history import EvalHistory


def _resolve_path(path: str, relative_to: str) -> str:
    """If *path* is relative, make it absolute relative to *relative_to*."""
    if not os.path.isabs(path):
        return os.path.join(relative_to, path)
    return path


def _filter_by_tag(cases: list, tag: str) -> list:
    """Keep only cases whose ``tags`` list contains *tag*."""
    filtered = [c for c in cases if tag in c.get("tags", [])]
    skipped = len(cases) - len(filtered)
    if skipped:
        print(f"  Tag filter '{tag}': {len(filtered)} matched, {skipped} skipped")
    return filtered


def main():
    parser = argparse.ArgumentParser(
        description="AIWear Evaluation Runner"
    )
    parser.add_argument(
        "--cases",
        help="Path to test-cases JSON file (e.g. cases/sample_cases.json)",
    )
    parser.add_argument(
        "--suite",
        choices=["smoke", "rag", "mcp", "agent", "memory"],
        help="Run a named eval suite (smoke/rag/mcp/agent/memory)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock (keyword-matching stub) instead of the real agent",
    )
    parser.add_argument(
        "--baseline",
        help="Path to a baseline JSON for regression comparison",
    )
    parser.add_argument(
        "--output",
        help="Save evaluation report JSON to this file",
    )
    parser.add_argument(
        "--save-baseline",
        help="Save current results as a new baseline JSON",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-case details to console",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI mode: exit 0 only if all pass AND no regressions vs baseline",
    )
    parser.add_argument(
        "--tag",
        help="Only run cases with this tag (filters by case.tags list)",
    )
    parser.add_argument(
        "--output-dir",
        help="Save report to a timestamped directory under this path",
    )
    args = parser.parse_args()

    if not args.cases and not args.suite:
        parser.error("Either --cases or --suite is required")

    # Resolve paths relative to this script's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))

    if args.suite:
        suite_map = {
            "smoke": "smoke_cases.json",
            "rag": "rag_cases.json",
            "mcp": "mcp_cases.json",
            "agent": "agent_cases.json",
            "memory": "memory_cases.json",
        }
        cases_path = os.path.join(script_dir, "cases", suite_map[args.suite])
    else:
        cases_path = _resolve_path(args.cases, script_dir)

    # ---- Load test cases ----
    try:
        cases = load_cases(cases_path)
    except FileNotFoundError:
        print(f"  Error: Cases file not found: {cases_path}")
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"  Error: Invalid JSON in cases file: {exc}")
        sys.exit(1)

    if not isinstance(cases, list):
        print("  Error: Cases file must contain a JSON array")
        sys.exit(1)

    # ---- Tag filter ----
    if args.tag:
        cases = _filter_by_tag(cases, args.tag)

    multi_turn = any("turns" in c for c in cases)

    print(f"  Loaded {len(cases)} test case(s) from {os.path.basename(cases_path)}")
    print(f"  Mode:      {'Mock (stub)' if args.mock else 'Real agent'}")
    if args.ci:
        print(f"  CI mode:   ON")
    if args.tag:
        print(f"  Tag:       {args.tag}")
    if multi_turn:
        multi_count = sum(1 for c in cases if "turns" in c)
        print(f"  Type:      {multi_count} multi-turn, {len(cases) - multi_count} single-turn")
    if args.baseline:
        baseline_path = _resolve_path(args.baseline, script_dir)
        print(f"  Baseline:  {baseline_path}")
    if args.output:
        output_path = _resolve_path(args.output, script_dir)
        print(f"  Output:    {output_path}")
    if args.output_dir:
        output_dir = _resolve_path(args.output_dir, script_dir)
        print(f"  Output dir: {output_dir}")

    # ---- Run evaluation ----
    print()
    results = run_eval(cases, use_mock=args.mock)

    # ---- Historically save ----
    if args.ci or args.output_dir:
        eh = EvalHistory()
        eh.save(results)

    # ---- Verbose per-case output ----
    if args.verbose:
        print(f"\n  {'─' * 58}")
        for r in results.get("results", []):
            status = "PASS" if r["passed"] else "FAIL"
            if r.get("type") == "multi_turn":
                trs = r.get("turn_results", [])
                turn_summary = ", ".join(
                    f"t{t['turn_index']}: {'PASS' if t['passed'] else 'FAIL'}"
                    for t in trs
                )
                print(f"  [{status}] {r['id']} ({r.get('num_turns', 0)} turns) "
                      f"lat={r['latency_ms']:.0f}ms  [{turn_summary}]")
            else:
                fallback_mark = " [fallback]" if r.get("fallback") else ""
                print(f"  [{status}] {r['id']} "
                      f"agent={r['output'].get('agent','?')} "
                      f"action={r['output'].get('action','?')} "
                      f"lat={r['latency_ms']:.0f}ms{fallback_mark}")
        print(f"  {'─' * 58}")

    # ---- Save results ----
    if args.output:
        save_results(results, output_path)
        print(f"\n  Results saved to {output_path}")

    # ---- Save to timestamped directory ----
    generated_report_path = None
    if args.output_dir:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(args.output_dir, exist_ok=True)
        report_path = os.path.join(args.output_dir, f"eval_report_{timestamp}.json")
        save_results(results, report_path)
        generated_report_path = report_path
        print(f"\n  Report saved to {report_path}")

    # ---- Save baseline ----
    if args.save_baseline:
        bl_path = _resolve_path(args.save_baseline, script_dir)
        save_baseline(results, bl_path)

    # ---- Regression comparison ----
    regressions_found = False
    if args.baseline:
        report = generate_report(
            results,
            baseline_path,
            output_path=generated_report_path or (output_path if args.output else None),
        )
        if "error" not in report and report.get("new_failures"):
            regressions_found = True

    # ---- Summary ----
    print(f"\n  {'=' * 40}")
    print(f"  Results: {results['passed']}/{results['total']} passed")
    print(f"  Accuracy: {results['accuracy']:.2%}")
    print(f"  Avg Latency: {results['avg_latency_ms']:.1f}ms")
    if results.get("fallback_count"):
        print(f"  {len(results.get('results',[])) - results['fallback_count']}/{results['total']} real-agent calls")
    print(f"  {'=' * 40}")

    # ---- Exit (CI mode: pass + no regressions) ----
    if args.ci:
        if results["failed"] > 0:
            print("\n  CI: FAILED — some cases failed")
            sys.exit(1)
        if regressions_found:
            print("\n  CI: FAILED — regressions detected vs baseline")
            sys.exit(1)
        print("\n  CI: PASSED — all cases passed, no regressions")
        sys.exit(0)

    # Non-zero exit iff any case failed
    if results["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
