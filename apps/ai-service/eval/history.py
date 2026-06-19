"""
Evaluation history persistence, trend analysis, and run comparison.

Stores results as timestamped JSON files under ``eval/history/``.

Typical usage::

    from eval.history import EvalHistory

    eh = EvalHistory()
    eh.save(results_dict)

    trend = eh.get_trend(n=10)           # accuracy/latency over last 10 runs
    comparison = eh.compare_latest(2)    # side-by-side of the 2 most recent runs
    latest_path = eh.latest_path()       # path to most recent result file
"""

import json
import os
from datetime import datetime
from typing import Optional

_HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history")


class EvalHistory:
    """Persist and analyse evaluation runs."""

    def __init__(self, history_dir: str = None):
        self._history_dir = history_dir or _HISTORY_DIR
        os.makedirs(self._history_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Save / list
    # ------------------------------------------------------------------

    def save(self, results: dict, label: str = "") -> str:
        """Save evaluation results as a timestamped JSON file.

        Args:
            results: The dict returned by ``run_eval()``.
            label: Optional short label (e.g. ``"nightly"``) appended to the filename.

        Returns:
            The absolute path to the saved file.
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{label}" if label else ""
        filename = f"eval_{ts}{suffix}.json"
        path = os.path.join(self._history_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        return path

    def list_runs(self) -> list[dict]:
        """Return metadata for all historical runs, newest first."""
        entries = []
        for fname in sorted(os.listdir(self._history_dir), reverse=True):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(self._history_dir, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            entries.append(
                {
                    "file": fpath,
                    "filename": fname,
                    "timestamp": fname.replace("eval_", "").replace(".json", ""),
                    "total": data.get("total", 0),
                    "passed": data.get("passed", 0),
                    "failed": data.get("failed", 0),
                    "accuracy": data.get("accuracy", 0),
                    "avg_latency_ms": data.get("avg_latency_ms", 0),
                }
            )
        return entries

    def latest_path(self) -> Optional[str]:
        """Return the path of the most recent result file, or None."""
        entries = self.list_runs()
        return entries[0]["file"] if entries else None

    # ------------------------------------------------------------------
    # Trend
    # ------------------------------------------------------------------

    def get_trend(self, n: int = 10) -> list[dict]:
        """Return accuracy and latency for the last *n* runs.

        Each entry contains ``{timestamp, file, accuracy, avg_latency_ms,
        total, passed, failed}``.  Newest first.
        """
        return self.list_runs()[:n]

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    def compare_latest(self, n: int = 2) -> dict:
        """Compare the *n* most recent runs side-by-side.

        Returns a dict with:

        - ``runs`` — list of per-run summary dicts (newest first)
        - ``accuracy_delta`` — change in accuracy from oldest to newest
        - ``latency_delta_ms`` — change in avg latency (oldest to newest)
        - ``new_failures`` — case IDs that passed in the oldest but
          failed in the newest run
        - ``fixed_cases`` — case IDs that failed in the oldest but
          passed in the newest run
        """

        def _index(run: dict) -> dict:
            idx = {}
            for r in run.get("results", []):
                if r.get("type") == "multi_turn" and "turn_results" in r:
                    for tr in r["turn_results"]:
                        key = f"{r['id']}_t{tr['turn_index']}"
                        idx[key] = {"passed": tr["passed"], "latency_ms": tr.get("latency_ms", 0)}
                else:
                    idx[r["id"]] = {"passed": r["passed"], "latency_ms": r.get("latency_ms", 0)}
            return idx

        runs = self.list_runs()[:n]
        if len(runs) < 2:
            return {
                "runs": runs,
                "note": f"Need at least 2 runs to compare; only {len(runs)} available.",
            }

        # Load full data for oldest and newest
        newest_path = runs[0]["file"]
        oldest_path = runs[-1]["file"] if len(runs) > 1 else runs[0]["file"]

        with open(newest_path, encoding="utf-8") as f:
            newest_data = json.load(f)
        with open(oldest_path, encoding="utf-8") as f:
            oldest_data = json.load(f)

        newest_idx = _index(newest_data)
        oldest_idx = _index(oldest_data)

        all_ids = set(list(newest_idx.keys()) + list(oldest_idx.keys()))

        new_failures = []
        fixed_cases = []

        for cid in sorted(all_ids):
            n_val = newest_idx.get(cid)
            o_val = oldest_idx.get(cid)
            if n_val and o_val:
                if o_val["passed"] and not n_val["passed"]:
                    new_failures.append({"id": cid, "latency_ms": n_val.get("latency_ms", 0)})
                elif not o_val["passed"] and n_val["passed"]:
                    fixed_cases.append({"id": cid, "latency_ms": n_val.get("latency_ms", 0)})

        acc_new = newest_data.get("accuracy", 0)
        acc_old = oldest_data.get("accuracy", 0)
        lat_new = newest_data.get("avg_latency_ms", 0)
        lat_old = oldest_data.get("avg_latency_ms", 0)

        return {
            "runs": runs,
            "accuracy_delta": round(acc_new - acc_old, 4),
            "latency_delta_ms": round(lat_new - lat_old, 2),
            "new_failures": new_failures,
            "fixed_cases": fixed_cases,
        }
