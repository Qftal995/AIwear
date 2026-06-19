#!/usr/bin/env python
"""
CI entry point for AIWear evaluation.

Runs the full evaluation suite with regression comparison against the
latest baseline, then exits 0 only if everything passes with no regressions.

Usage
-----

    # Run CI with default cases
    python -m eval.run_ci --cases cases/sample_cases.json

    # Use specific baseline
    python -m eval.run_ci --cases cases/sample_cases.json \\
                          --baseline eval/history/latest.json

    # Mock mode for fast smoke test
    python -m eval.run_ci --cases cases/sample_cases.json --mock

Exit code: 0 if all pass AND no regressions vs baseline; 1 otherwise.
"""

import argparse
import json
import sys
import os

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from eval.runner import run_eval, load_cases
from eval.reporter import generate_report, save_baseline
from eval.history import EvalHistory


def _resolve_path(path: str, relative_to: str) -> str:
    if not os.path.isabs(path):
        return os.path.join(relative_to, path)
    return path


def main():
    parser = argparse.ArgumentParser(
        description="AIWear CI Evaluation Runner"
    )
    parser.add_argument(
        "--cases",
        required=True,
        help="Path to test-cases JSON file",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use stub agent instead of real agent",
    )
    parser.add_argument(
        "--baseline",
        help="Path to baseline JSON. Defaults to latest in eval/history/",
    )
    parser.add_argument(
        "--save-baseline",
        help="Save results as a new baseline JSON",
    )
    parser.add_argument(
        "--tag",
        help="Only run cases with this tag",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-case details",
    )
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    cases_path = _resolve_path(args.cases, script_dir)

    # ---- Load test cases ----
    try:
        cases = load_cases(cases_path)
    except FileNotFoundError:
        print(f"[CI] Error: Cases file not found: {cases_path}")
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"[CI] Error: Invalid JSON in cases file: {exc}")
        sys.exit(1)

    if not isinstance(cases, list):
        print("[CI] Error: Cases file must contain a JSON array")
        sys.exit(1)

    # ---- Tag filter ----
    if args.tag:
        filtered = [c for c in cases if args.tag in c.get("tags", [])]
        skipped = len(cases) - len(filtered)
        cases = filtered
        if skipped:
            print(f"[CI] Tag filter '{args.tag}': {len(cases)} matched, {skipped} skipped")

    print(f"[CI] Loaded {len(cases)} test case(s) from {os.path.basename(cases_path)}")
    print(f"[CI] Mode: {'Mock (stub)' if args.mock else 'Real agent'}")

    # ---- Resolve baseline ----
    baseline_path = None
    if args.baseline:
        baseline_path = _resolve_path(args.baseline, script_dir)
    else:
        eh = EvalHistory()
        latest = eh.latest_path()
        if latest and os.path.exists(latest):
            baseline_path = latest
            print(f"[CI] Auto-resolved baseline: {baseline_path}")

    # ---- Run evaluation ----
    print()
    results = run_eval(cases, use_mock=args.mock)

    # ---- Save to history ----
    eh = EvalHistory()
    history_path = eh.save(results, label="ci")
    print(f"[CI] Results saved to history: {history_path}")

    # ---- Verbose per-case output ----
    if args.verbose:
        print()
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
                fb = " [fallback]" if r.get("fallback") else ""
                print(f"  [{status}] {r['id']} "
                      f"agent={r['output'].get('agent','?')} "
                      f"action={r['output'].get('action','?')} "
                      f"lat={r['latency_ms']:.0f}ms{fb}")

    # ---- Save baseline ----
    if args.save_baseline:
        bl_path = _resolve_path(args.save_baseline, script_dir)
        save_baseline(results, bl_path)

    # ---- Regression comparison ----
    regressions_found = False
    if baseline_path and os.path.exists(baseline_path):
        report = generate_report(results, baseline_path)
        if "error" not in report:
            new_failures = report.get("new_failures", [])
            if new_failures:
                regressions_found = True
                print(f"\n[CI] REGRESSIONS DETECTED: {len(new_failures)} new failure(s)")
                for f in new_failures:
                    print(f"      - {f['id']}: {f['reason']}")

    # ---- Summary ----
    passed = results["passed"]
    total = results["total"]
    failed = results["failed"]

    print()
    print(f"  {'=' * 40}")
    print(f"  CI Results: {passed}/{total} passed")
    print(f"  Accuracy:   {results['accuracy']:.2%}")
    print(f"  Avg Latency: {results['avg_latency_ms']:.1f}ms")
    print(f"  {'=' * 40}")

    # ---- Exit ----
    has_failures = failed > 0
    if has_failures:
        print(f"\n[CI] FAILED: {failed} case(s) failed")
        sys.exit(1)
    if regressions_found:
        print(f"\n[CI] FAILED: Regressions detected vs baseline")
        sys.exit(1)
    print(f"\n[CI] PASSED: All {total} case(s) passed, no regressions")
    sys.exit(0)


if __name__ == "__main__":
    main()
