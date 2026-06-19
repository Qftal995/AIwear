"""
Regression comparison report generator.

Compares current evaluation results against a baseline JSON file,
produces colorized console output and a detailed JSON report.
"""

import json
import os
from datetime import datetime

# ---------------------------------------------------------------------------
# Coloured console helpers (works on Windows 10+ with VT processing)
# ---------------------------------------------------------------------------

try:
    from colorama import init, Fore, Style as ColStyle

    init()
    GREEN = Fore.GREEN
    RED = Fore.RED
    YELLOW = Fore.YELLOW
    CYAN = Fore.CYAN
    RESET = ColStyle.RESET_ALL
    BOLD = ColStyle.BRIGHT
except ImportError:
    GREEN = RED = YELLOW = CYAN = RESET = BOLD = ""


def _c(val: float, up_good: bool = True) -> str:
    """Return a colour-coded string for a numeric change value."""
    if val > 0:
        return f"{GREEN if up_good else RED}{val:+.2%}{RESET}"
    if val < 0:
        return f"{RED if up_good else GREEN}{val:+.2%}{RESET}"
    return f"{YELLOW}{val:+.2%}{RESET}"


def _lat_color(delta_ms: float) -> str:
    if delta_ms > 500:
        return RED
    if delta_ms > 100:
        return YELLOW
    if delta_ms < -500:
        return GREEN
    return RESET


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_report(
    current_results: dict, baseline_path: str, output_path: str = None
) -> dict:
    """Compare current evaluation results against a baseline.

    Args:
        current_results: Output dict from ``runner.run_eval()``.
        baseline_path: Path to a baseline JSON file (previously saved results).
        output_path: If set, save the full report JSON to this path.

    Returns:
        A dict with comparison data, or ``{"error": ...}`` if the baseline
        file cannot be read.
    """
    if not os.path.exists(baseline_path):
        print(
            f"{YELLOW}[WARN] Baseline not found at {baseline_path}. "
            f"Skipping comparison.{RESET}"
        )
        return {"error": "Baseline not found"}

    with open(baseline_path, encoding="utf-8") as f:
        baseline = json.load(f)

    current_map = _index_results(current_results)
    baseline_map = _index_results(baseline)

    all_ids = set(list(current_map.keys()) + list(baseline_map.keys()))

    new_failures = []
    fixed_cases = []
    still_failing = []
    latency_regressions = []
    latency_improvements = []
    new_cases = []

    for cid in sorted(all_ids):
        cur = current_map.get(cid)
        base = baseline_map.get(cid)

        # Case only in current (newly added)
        if cur and not base:
            if not cur["passed"]:
                new_failures.append(
                    {"id": cid, "reason": "New case (failing)"}
                )
            else:
                new_cases.append({"id": cid, "reason": "New case (passing)"})
            continue

        # Case only in baseline (removed) — skip
        if not cur and base:
            continue

        # Both exist — compare
        cur_pass = cur["passed"]
        base_pass = base["passed"]
        cur_lat = cur.get("latency_ms", 0)
        base_lat = base.get("latency_ms", 0)
        lat_diff = round(cur_lat - base_lat, 2)

        if base_pass and not cur_pass:
            new_failures.append(
                {
                    "id": cid,
                    "reason": "Previously passed, now failing",
                    "latency_ms": cur_lat,
                    "latency_change_ms": lat_diff,
                }
            )
        elif not base_pass and cur_pass:
            fixed_cases.append(
                {
                    "id": cid,
                    "reason": "Previously failed, now passing",
                    "latency_ms": cur_lat,
                    "latency_change_ms": lat_diff,
                }
            )
        elif not base_pass and not cur_pass:
            still_failing.append({"id": cid, "reason": "Still failing"})

        if lat_diff > 500:
            latency_regressions.append(
                {"id": cid, "change_ms": lat_diff}
            )
        elif lat_diff < -500:
            latency_improvements.append(
                {"id": cid, "change_ms": lat_diff}
            )

    # Summary numbers
    base_acc = baseline.get("accuracy", 0)
    cur_acc = current_results.get("accuracy", 0)
    base_lat = baseline.get("avg_latency_ms", 0)
    cur_lat = current_results.get("avg_latency_ms", 0)

    report = {
        "generated_at": datetime.now().isoformat(),
        "baseline": baseline_path,
        "summary": {
            "baseline_accuracy": base_acc,
            "current_accuracy": cur_acc,
            "accuracy_change": round(cur_acc - base_acc, 4),
            "baseline_avg_latency_ms": base_lat,
            "current_avg_latency_ms": cur_lat,
            "latency_change_ms": round(cur_lat - base_lat, 2),
            "total_cases": current_results.get("total", 0),
            "passed": current_results.get("passed", 0),
            "failed": current_results.get("failed", 0),
            "fallback_count": current_results.get("fallback_count", 0),
        },
        "new_cases": new_cases,
        "new_failures": new_failures,
        "fixed_cases": fixed_cases,
        "still_failing": still_failing,
        "latency_regressions": latency_regressions,
        "latency_improvements": latency_improvements,
    }

    _print_report(report)

    if output_path:
        _ensure_dir(output_path)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"{CYAN}Report saved to: {output_path}{RESET}")

    return report


def save_baseline(results: dict, path: str):
    """Save current evaluation results as a new baseline.

    Args:
        results: Output dict from ``runner.run_eval()``.
        path: Target file path for the baseline JSON.
    """
    _ensure_dir(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"{GREEN}Baseline saved to: {path}{RESET}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _index_results(results: dict) -> dict:
    """Flatten per-case results into a ``{id: result}`` lookup dict.

    Handles both single-turn (``results[i]``) and multi-turn
    (``results[i].turn_results[j]``) entries.
    """
    indexed = {}
    for r in results.get("results", []):
        if r.get("type") == "multi_turn" and "turn_results" in r:
            for tr in r["turn_results"]:
                key = f"{r['id']}_t{tr['turn_index']}"
                indexed[key] = {
                    "id": key,
                    "passed": tr["passed"],
                    "latency_ms": tr.get("latency_ms", 0),
                }
        else:
            indexed[r["id"]] = r
    return indexed


def _print_report(report: dict):
    """Print a colorized regression report to the console."""
    if "error" in report:
        return

    s = report["summary"]

    print()
    print(f"{'=' * 62}")
    print(f"{BOLD}        Evaluation Regression Report{RESET}")
    print(f"{'=' * 62}")
    print(f"  Generated at: {report['generated_at']}")
    print(f"  Baseline:     {report['baseline']}")
    print()

    # Accuracy
    acc_delta = s["accuracy_change"]
    print(f"{BOLD}  Accuracy{RESET}")
    print(f"    Baseline: {s['baseline_accuracy']:.2%}")
    print(f"    Current:  {s['current_accuracy']:.2%}")
    print(f"    Change:   {_c(acc_delta)}")

    # Latency
    lat_delta = s["latency_change_ms"]
    lc = _lat_color(lat_delta)
    print(f"\n{BOLD}  Latency{RESET}")
    print(f"    Baseline: {s['baseline_avg_latency_ms']:.1f} ms")
    print(f"    Current:  {s['current_avg_latency_ms']:.1f} ms")
    print(f"    Change:   {lc}{lat_delta:+.1f} ms{RESET}")

    # Pass / fail tally
    print(f"\n{BOLD}  Results{RESET}")
    print(f"    Total:  {s['total_cases']}")
    print(f"    Passed: {GREEN}{s['passed']}{RESET}")
    print(f"    Failed: {RED}{s['failed']}{RESET}")
    if s.get("fallback_count"):
        print(f"    {YELLOW}Fallback: {s['fallback_count']} cases used stub{RESET}")

    # New failures (most important — show first)
    nf = report.get("new_failures", [])
    if nf:
        print(f"\n{RED}{BOLD}  [-] New Failures ({len(nf)}){RESET}")
        for f in nf:
            print(f"    {RED}- {f['id']}: {f['reason']}{RESET}")
            if "latency_change_ms" in f and f["latency_change_ms"]:
                print(f"       latency: {f['latency_ms']:.0f}ms "
                      f"(change: {f['latency_change_ms']:+.0f}ms)")

    # Fixed cases
    fx = report.get("fixed_cases", [])
    if fx:
        print(f"\n{GREEN}{BOLD}  [+] Fixed Cases ({len(fx)}){RESET}")
        for f in fx:
            print(f"    {GREEN}+ {f['id']}: {f['reason']}{RESET}")

    # Still failing
    sf = report.get("still_failing", [])
    if sf:
        print(f"\n{YELLOW}{BOLD}  [!] Still Failing ({len(sf)}){RESET}")
        for f in sf:
            print(f"    {YELLOW}! {f['id']}: {f['reason']}{RESET}")

    # Latency regressions
    lr = report.get("latency_regressions", [])
    if lr:
        print(f"\n{RED}{BOLD}  [<] Latency Regressions ({len(lr)}){RESET}")
        for r_ in lr:
            print(f"    {RED}< {r_['id']}: {r_['change_ms']:+.0f}ms{RESET}")

    # Latency improvements
    li = report.get("latency_improvements", [])
    if li:
        print(f"\n{GREEN}{BOLD}  [>] Latency Improvements ({len(li)}){RESET}")
        for r_ in li:
            print(f"    {GREEN}> {r_['id']}: {r_['change_ms']:+.0f}ms{RESET}")

    # New passing cases
    nc = report.get("new_cases", [])
    if nc:
        print(f"\n{CYAN}{BOLD}  [*] New Cases ({len(nc)}){RESET}")
        for c in nc:
            print(f"    {CYAN}* {c['id']}: {c['reason']}{RESET}")

    print(f"\n{'=' * 62}\n")


def _ensure_dir(path: str):
    """Create parent directories for *path* if they don't exist."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
