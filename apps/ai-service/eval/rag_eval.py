"""
RAG Eval — 统计级评估报告

基于 live /api/rag/search 调用，对多组查询分别统计：
  - 文件命中率（top-k 中至少命中 1 个预期文件即算通过）
  - 关键词覆盖率（content 中覆盖 ≥50% 预期关键词即算通过）
  - Citation 完整性（file/title/section/chunkId/score/content 六字段齐全）
  - Score 分布（min/max/avg/P50/P95/P99）
  - Top-K Precision（Precision@1/@3/@5）

用法:
  py -3 eval/rag_eval.py [--base-url http://127.0.0.1:5001] [--cases eval/cases/rag_eval_cases.json]
                          [--output eval/results/rag_eval.json] [--baseline eval/results/rag_eval_baseline.json]
"""
import json
import os
import sys
import time
import argparse
from collections import defaultdict

import requests

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)


# ── 颜色输出 ─────────────────────────────────────────────────────────
_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"

def _ok(s): return f"{_GREEN}{s}{_RESET}"
def _bad(s): return f"{_RED}{s}{_RESET}"
def _warn(s): return f"{_YELLOW}{s}{_RESET}"
def _hdr(s): return f"{_BOLD}{_CYAN}{s}{_RESET}"


# ── 统计函数 ─────────────────────────────────────────────────────────

def _pct(n: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{n / total * 100:.1f}%"


def _score_stats(scores: list) -> dict:
    if not scores:
        return {"min": 0, "max": 0, "avg": 0, "p50": 0, "p95": 0, "p99": 0}
    s = sorted(scores)
    n = len(s)
    return {
        "min": round(s[0], 4),
        "max": round(s[-1], 4),
        "avg": round(sum(s) / n, 4),
        "p50": round(s[n // 2], 4),
        "p95": round(s[int(n * 0.95)], 4),
        "p99": round(s[int(n * 0.99)], 4),
    }


# ── Citation 完整性检查 ──────────────────────────────────────────────

CITATION_FIELDS = ("file", "title", "section", "chunkId", "score", "content")


def _check_citation(item: dict) -> dict:
    """检查单条结果的 citation 六字段完整性。"""
    present = [f for f in CITATION_FIELDS if f in item]
    missing = [f for f in CITATION_FIELDS if f not in item]
    return {
        "complete": len(missing) == 0,
        "present": present,
        "missing": missing,
        "present_count": len(present),
        "total_fields": len(CITATION_FIELDS),
    }


# ── 核心逻辑 ─────────────────────────────────────────────────────────

class RAGEvaluator:
    def __init__(self, base_url: str = "http://127.0.0.1:5001", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.results = []

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self.base_url}{path}"
        resp = requests.post(url, json=body, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # ── 单条执行 ──────────────────────────────────────────────────

    def _run_one(self, case: dict) -> dict:
        """执行一条 RAG 查询，采集完整响应数据。"""
        t0 = time.time()
        filters = case.get("filters", {})
        body = {
            "query": case["query"],
            "topK": case.get("topK", 5),
        }
        if filters.get("gender"):
            body["gender"] = filters["gender"]
        if filters.get("occasion"):
            body["occasion"] = filters["occasion"]
        if filters.get("season"):
            body["season"] = filters["season"]

        try:
            r = self._post("/api/rag/search", body)
            elapsed_ms = int((time.time() - t0) * 1000)
        except Exception as e:
            return {
                "id": case["id"], "query": case["query"],
                "error": str(e), "elapsed_ms": int((time.time() - t0) * 1000),
            }

        data = r.get("data", {})
        items = data.get("results", [])

        # ── 文件命中 ──
        expected_files = case.get("expected", {}).get("files", [])
        hit_files = []
        for ef in expected_files:
            for item in items:
                item_file = item.get("file", "")
                if ef in item_file or item_file in ef:
                    hit_files.append(ef)
                    break

        # ── 关键词覆盖 ──
        expected_keywords = case.get("expected", {}).get("keywords", [])
        all_content = " ".join(item.get("content", "") for item in items)
        matched_keywords = [kw for kw in expected_keywords if kw in all_content]
        kw_coverage = len(matched_keywords) / len(expected_keywords) if expected_keywords else 1.0

        # ── Citation 完整性 ──
        citation_checks = [_check_citation(item) for item in items]
        complete_count = sum(1 for c in citation_checks if c["complete"])

        # ── Score ──
        scores = [item.get("score", 0) for item in items]
        top1_score = scores[0] if scores else 0

        # ── Precision@K ──
        prec_at_1 = 1.0 if hit_files and items and expected_files and (
            any(ef in items[0].get("file", "") or items[0].get("file", "") in ef for ef in expected_files)
        ) else 0.0
        prec_at_3 = sum(1 for ef in expected_files if any(
            ef in item.get("file", "") or item.get("file", "") in ef
            for item in items[:3]
        )) / max(len(expected_files), 1) if expected_files else 1.0
        prec_at_5 = sum(1 for ef in expected_files if any(
            ef in item.get("file", "") or item.get("file", "") in ef
            for item in items
        )) / max(len(expected_files), 1) if expected_files else 1.0

        expected = case.get("expected", {})

        return {
            "id": case["id"],
            "query": case["query"],
            "filters": filters,
            "topK": case.get("topK", 5),
            "elapsed_ms": elapsed_ms,
            "total_hits": data.get("totalHits", 0),
            "result_count": len(items),
            "latency_ms": data.get("latencyMs", elapsed_ms),
            "rewritten_query": data.get("rewrittenQuery", ""),

            # 文件命中
            "files_expected": expected_files,
            "files_hit": hit_files,
            "files_missed": [f for f in expected_files if f not in hit_files],
            "file_hit_pass": len(hit_files) > 0,

            # 关键词覆盖
            "keywords_expected": expected_keywords,
            "keywords_matched": matched_keywords,
            "keywords_missed": [kw for kw in expected_keywords if kw not in matched_keywords],
            "keyword_coverage": round(kw_coverage, 3),
            "keyword_pass": kw_coverage >= 0.5,

            # Citation 完整性
            "citations_complete": complete_count,
            "citations_total": len(items),
            "citation_completeness": round(complete_count / len(items), 3) if items else 0,
            "citation_pass": complete_count == len(items) if items else True,

            # Score
            "scores": [round(s, 4) for s in scores],
            "top1_score": round(top1_score, 4),
            "min_score_expected": expected.get("min_score", 0),
            "score_pass": top1_score >= expected.get("min_score", 0) if expected.get("min_score") else True,

            # 结果数
            "min_results_expected": expected.get("min_results", 0),
            "results_pass": len(items) >= expected.get("min_results", 0) if expected.get("min_results", 0) > 0 else True,

            # Precision@K
            "prec_at_1": prec_at_1,
            "prec_at_3": prec_at_3,
            "prec_at_5": prec_at_5,

            # 综合通过
            "pass": (len(hit_files) > 0 and kw_coverage >= 0.5
                     and (top1_score >= expected.get("min_score", 0) if expected.get("min_score") else True)
                     and (len(items) >= expected.get("min_results", 0) if expected.get("min_results", 0) > 0 else True)),
        }

    def run(self, cases: list):
        """逐条执行，打印进度。"""
        total = len(cases)
        for i, case in enumerate(cases):
            cid = case["id"]
            print(f"  [{i+1}/{total}] {cid} ... ", end="", flush=True)
            result = self._run_one(case)
            self.results.append(result)
            if result.get("error"):
                print(_bad(f"ERROR: {result['error'][:80]}"))
            elif result["pass"]:
                print(_ok(f"✓ files={result['files_hit']} kw={result['keyword_coverage']:.0%} score={result['top1_score']}"))
            else:
                parts = []
                if not result["file_hit_pass"]:
                    parts.append(f"files missed={result['files_missed']}")
                if not result["keyword_pass"]:
                    parts.append(f"kw={result['keyword_coverage']:.0%} missed={result['keywords_missed']}")
                if not result["score_pass"]:
                    parts.append(f"score={result['top1_score']} < {result['min_score_expected']}")
                if not result["results_pass"]:
                    parts.append(f"results={result['result_count']} < {result['min_results_expected']}")
                print(_warn(", ".join(parts)))

    # ── 报告生成 ─────────────────────────────────────────────────

    def compute_metrics(self) -> dict:
        valid = [r for r in self.results if "error" not in r]
        errors = [r for r in self.results if "error" in r]

        if not valid:
            return {"error": "no valid results", "total": len(self.results), "errors": len(errors)}

        # ── 文件命中率 ──
        file_hits = sum(1 for r in valid if r["file_hit_pass"])
        file_hit_rate = file_hits / len(valid)

        # 各用例文件命中明细
        file_details = [
            {"id": r["id"], "hit": r["file_hit_pass"],
             "expected": r["files_expected"], "hit_list": r["files_hit"],
             "missed": r["files_missed"]}
            for r in valid
        ]

        # ── 关键词覆盖率 ──
        kw_pass = sum(1 for r in valid if r["keyword_pass"])
        kw_pass_rate = kw_pass / len(valid)
        avg_kw_coverage = sum(r["keyword_coverage"] for r in valid) / len(valid)

        # ── Citation 完整性 ──
        citation_completeness = sum(r["citations_complete"] for r in valid) / max(sum(r["citations_total"] for r in valid), 1)
        cit_full_pass = sum(1 for r in valid if r["citation_pass"])

        # ── Score 分布 ──
        all_top1_scores = [r["top1_score"] for r in valid]
        leaderboard = sorted(valid, key=lambda r: r["top1_score"], reverse=True)
        score_stats = _score_stats(all_top1_scores)

        # ── Precision@K ──
        prec_at_1_list = [r.get("prec_at_1", 0) for r in valid]
        prec_at_3_list = [r.get("prec_at_3", 0) for r in valid]
        prec_at_5_list = [r.get("prec_at_5", 0) for r in valid]

        # ── 延迟 ──
        latencies = [r["elapsed_ms"] for r in valid]

        return {
            "meta": {
                "total_cases": len(self.results),
                "valid": len(valid),
                "errors": len(errors),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "base_url": self.base_url,
            },
            "file_hit": {
                "rate": round(file_hit_rate, 3),
                "hits": file_hits,
                "total": len(valid),
                "details": file_details,
            },
            "keyword_coverage": {
                "pass_rate": round(kw_pass_rate, 3),
                "passes": kw_pass,
                "total": len(valid),
                "avg_coverage": round(avg_kw_coverage, 3),
            },
            "citation": {
                "completeness": round(citation_completeness, 3),
                "complete_count": sum(r["citations_complete"] for r in valid),
                "total_fields": len(CITATION_FIELDS),
                "full_pass_count": cit_full_pass,
                "full_pass_total": len(valid),
            },
            "score_distribution": {
                **score_stats,
                "min_expected_pass": sum(1 for r in valid if r["score_pass"]),
                "min_expected_total": sum(1 for r in valid if r["min_score_expected"] > 0),
                "leaderboard": [
                    {"id": r["id"], "query": r["query"], "top1_score": r["top1_score"]}
                    for r in leaderboard[:5]
                ],
            },
            "precision_at_k": {
                "p@1": round(sum(prec_at_1_list) / len(prec_at_1_list), 3) if prec_at_1_list else 0,
                "p@3": round(sum(prec_at_3_list) / len(prec_at_3_list), 3) if prec_at_3_list else 0,
                "p@5": round(sum(prec_at_5_list) / len(prec_at_5_list), 3) if prec_at_5_list else 0,
            },
            "latency": {
                "min": min(latencies) if latencies else 0,
                "max": max(latencies) if latencies else 0,
                "avg": round(sum(latencies) / len(latencies)) if latencies else 0,
            },
            "overall": {
                "pass_count": sum(1 for r in valid if r["pass"]),
                "pass_rate": round(sum(1 for r in valid if r["pass"]) / len(valid), 3),
            },
        }

    def print_report(self, metrics: dict):
        """终端彩色报告。"""
        m = metrics
        meta = m["meta"]
        print("\n" + "=" * 60)
        print(_hdr("  AIWear RAG Eval 报告"))
        print("  {}  |  {}  |  {}/{} 有效  |  {} 错误".format(
            meta["timestamp"], meta["base_url"], meta["valid"], meta["total_cases"], meta["errors"]))
        print("=" * 60)

        # 综合通过率
        ov = m["overall"]
        ov_rate = ov["pass_rate"]
        tag = _ok if ov_rate >= 0.8 else (_warn if ov_rate >= 0.6 else _bad)
        print("\n" + _hdr("── 综合通过率") + "  " + tag("{:.1%}".format(ov_rate))
              + "  ({}/{})".format(ov["pass_count"], meta["valid"]))

        # 文件命中率
        fh = m["file_hit"]
        fh_rate = fh["rate"]
        tag = _ok if fh_rate >= 0.8 else (_warn if fh_rate >= 0.6 else _bad)
        print("\n" + _hdr("── 文件命中率") + "  " + tag("{:.1%}".format(fh_rate))
              + "  ({}/{})".format(fh["hits"], fh["total"]))
        fails = [d for d in fh["details"] if not d["hit"]]
        if fails:
            for d in fails:
                print("  {} {}: expected={} missed={}".format(
                    _bad("✗"), d["id"], d["expected"], d["missed"]))
        else:
            print("  " + _ok("✓") + " 所有用例均命中预期文件")

        # 关键词覆盖率
        kw = m["keyword_coverage"]
        kw_pass_rate = kw["pass_rate"]
        tag = _ok if kw_pass_rate >= 0.8 else (_warn if kw_pass_rate >= 0.6 else _bad)
        print("\n" + _hdr("── 关键词覆盖率") + "  " + tag("{:.1%}".format(kw_pass_rate))
              + "  ({}/{} 用例 ≥50%)".format(kw["passes"], kw["total"]))
        print("  平均覆盖率: {:.1%}".format(kw["avg_coverage"]))

        # Citation 完整性
        cit = m["citation"]
        cit_comp = cit["completeness"]
        tag = _ok if cit_comp >= 0.9 else (_warn if cit_comp >= 0.7 else _bad)
        cit_total_items = sum(r["citations_total"] for r in self.results if "error" not in r)
        print("\n" + _hdr("── Citation 完整性") + "  " + tag("{:.1%}".format(cit_comp))
              + "  ({}/{} 条结果 {}字段齐全)".format(cit["complete_count"], cit_total_items, cit["total_fields"]))
        print("  全部结果均完整: {}/{} 查询".format(cit["full_pass_count"], cit["full_pass_total"]))

        # Score 分布
        sd = m["score_distribution"]
        print("\n" + _hdr("── Score 分布"))
        print("  min={:.4f}  max={:.4f}  avg={:.4f}".format(sd["min"], sd["max"], sd["avg"]))
        print("  p50={:.4f}  p95={:.4f}  p99={:.4f}".format(sd["p50"], sd["p95"], sd["p99"]))
        if sd["min_expected_total"] > 0:
            print("  min_score 达标: {}/{}".format(sd["min_expected_pass"], sd["min_expected_total"]))
        print("  Top-5 (by score):")
        for entry in sd["leaderboard"]:
            print("    {:.4f}  {}: {}".format(entry["top1_score"], entry["id"], entry["query"]))

        # Precision@K
        pk = m["precision_at_k"]
        print("\n" + _hdr("── Precision@K (文件)"))
        print("  P@1={:.3f}  P@3={:.3f}  P@5={:.3f}".format(pk["p@1"], pk["p@3"], pk["p@5"]))

        # 延迟
        lm = m["latency"]
        print("\n" + _hdr("── 延迟 (ms)") + "  min={}  max={}  avg={}".format(lm["min"], lm["max"], lm["avg"]))

        # 综合评分
        fh_w = 0.30
        kw_w = 0.25
        cit_w = 0.20
        score_w = 0.25
        score_quality = 1.0 - (0.4 - sd["avg"]) / 0.4 if sd["avg"] < 0.4 else 1.0
        if sd["avg"] == 0:
            score_quality = 0
        overall = (
            fh_w * fh_rate +
            kw_w * kw_pass_rate +
            cit_w * cit_comp +
            score_w * score_quality
        )
        tag = _ok if overall >= 0.8 else (_warn if overall >= 0.6 else _bad)
        print("\n" + _hdr("── 综合评分") + "  " + tag("{:.2%}".format(overall))
              + "  (file×{:.0%} + kw×{:.0%} + citation×{:.0%} + score_quality×{:.0%})".format(
                  fh_w, kw_w, cit_w, score_w))
        print("=" * 60 + "\n")

    def compare_baseline(self, metrics: dict, baseline_path: str):
        """与基线 JSON 对比。"""
        if not os.path.exists(baseline_path):
            print(_warn(f"基线文件不存在: {baseline_path}"))
            return
        with open(baseline_path, "r", encoding="utf-8") as f:
            base = json.load(f)

        b_meta = base.get("meta", {})
        b_m = base.get("metrics", base)
        print(f"\n{_hdr('── 基线对比')}  baseline={b_meta.get('timestamp', '?')}  "
              f"cases={b_meta.get('valid', '?')}")

        def _delta(cur, old, fmt=".1%"):
            if old == 0:
                return _ok("NEW") if cur > 0 else "—"
            d = cur - old
            if abs(d) < 0.01:
                return "—"
            return _ok(f"+{d:{fmt}}") if d > 0 else _bad(f"{d:{fmt}}")

        b_fh = b_m.get("file_hit", {})
        print(f"  File Hit:     {b_fh.get('rate', 0):.1%} → {metrics['file_hit']['rate']:.1%}  "
              f"{_delta(metrics['file_hit']['rate'], b_fh.get('rate', 0))}")

        b_kw = b_m.get("keyword_coverage", {})
        print(f"  Keyword Pass: {b_kw.get('pass_rate', 0):.1%} → {metrics['keyword_coverage']['pass_rate']:.1%}  "
              f"{_delta(metrics['keyword_coverage']['pass_rate'], b_kw.get('pass_rate', 0))}")

        b_cit = b_m.get("citation", {})
        print(f"  Citation:     {b_cit.get('completeness', 0):.1%} → {metrics['citation']['completeness']:.1%}  "
              f"{_delta(metrics['citation']['completeness'], b_cit.get('completeness', 0))}")

        sd = metrics["score_distribution"]
        b_sd = b_m.get("score_distribution", {})
        print(f"  Score Avg:    {b_sd.get('avg', 0):.4f} → {sd['avg']:.4f}  "
              f"{_delta(sd['avg'], b_sd.get('avg', 0), '.4f')}")
        print(f"  Score P95:    {b_sd.get('p95', 0):.4f} → {sd['p95']:.4f}  "
              f"{_delta(sd['p95'], b_sd.get('p95', 0), '.4f')}")

    def save_json(self, metrics: dict, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        payload = {"meta": metrics["meta"], "metrics": metrics, "raw_results": self.results}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"报告已保存: {path}")


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AIWear RAG Eval — 统计级评估")
    parser.add_argument("--base-url", default="http://127.0.0.1:5001")
    parser.add_argument("--cases", default=None,
                        help="用例 JSON 文件路径（默认 eval/cases/rag_eval_cases.json）")
    parser.add_argument("--output", default=None,
                        help="输出 JSON 路径（默认 eval/results/rag_eval_<timestamp>.json）")
    parser.add_argument("--baseline", default=None,
                        help="基线 JSON 路径，用于对比")
    parser.add_argument("--timeout", type=int, default=30,
                        help="单条用例超时秒数（默认 30）")
    args = parser.parse_args()

    # 用例路径
    cases_path = args.cases
    if not cases_path:
        cases_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "cases", "rag_eval_cases.json")
    if not os.path.exists(cases_path):
        print(_bad(f"用例文件不存在: {cases_path}"))
        sys.exit(1)

    with open(cases_path, "r", encoding="utf-8") as f:
        case_data = json.load(f)
    cases = case_data.get("cases", [])

    print(_hdr(f"RAG Eval — 加载 {len(cases)} 条用例"))
    print(f"  服务地址: {args.base_url}")
    print(f"  用例文件: {cases_path}")
    print()

    evaluator = RAGEvaluator(base_url=args.base_url, timeout=args.timeout)
    evaluator.run(cases)

    metrics = evaluator.compute_metrics()
    evaluator.print_report(metrics)

    if args.baseline:
        evaluator.compare_baseline(metrics, args.baseline)

    # 输出路径
    output_path = args.output
    if not output_path:
        ts = time.strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "results", f"rag_eval_{ts}.json")
    evaluator.save_json(metrics, output_path)

    # 退出码：综合通过率 < 0.6 返回 1
    overall = metrics["overall"]["pass_rate"]
    sys.exit(0 if overall >= 0.6 else 1)


if __name__ == "__main__":
    main()
