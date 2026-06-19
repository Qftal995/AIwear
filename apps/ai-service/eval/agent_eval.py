"""
Agent Eval — 统计级评估报告

基于 live /api/chat 调用，对 4 种 intent 分别统计：
  - intent 准确率（混淆矩阵）
  - 工具集合命中率（集合匹配，不要求顺序）
  - HITL 正确率（分类：应触发/不应触发 × 实际触发/未触发）
  - 延迟 P50/P95/P99
  - subResults / steps / toolCalls 完整度

用法:
  py -3 eval/agent_eval.py [--base-url http://127.0.0.1:5001] [--cases eval/cases/agent_eval_cases.json]
                           [--output eval/results/agent_eval.json] [--baseline eval/results/agent_eval_baseline.json]
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


# ── 统计函数（独立于 metrics.py，避免依赖差异） ─────────────────────

def _pct(n: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{n / total * 100:.1f}%"


def _latency_stats(latencies: list) -> dict:
    if not latencies:
        return {"min": 0, "max": 0, "avg": 0, "p50": 0, "p95": 0, "p99": 0}
    s = sorted(latencies)
    n = len(s)
    return {
        "min": s[0],
        "max": s[-1],
        "avg": round(sum(s) / n),
        "p50": s[n // 2],
        "p95": s[int(n * 0.95)],
        "p99": s[int(n * 0.99)],
    }


def _precision_recall(tp: int, fp: int, fn: int) -> dict:
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    return {"precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3)}


# ── 核心逻辑 ─────────────────────────────────────────────────────────

class AgentEvaluator:
    def __init__(self, base_url: str = "http://127.0.0.1:5001", timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.results = []  # 每条用例的原始采集结果

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self.base_url}{path}"
        resp = requests.post(url, json=body, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # ── 单条执行 ──────────────────────────────────────────────────

    def _run_one(self, case: dict) -> dict:
        """执行一条用例，采集完整的响应数据。"""
        session_id = f"ageval_{case['id']}"
        t0 = time.time()
        try:
            r = self._post("/api/chat", {
                "message": case["input"],
                "sessionId": session_id,
            })
            elapsed_ms = int((time.time() - t0) * 1000)
        except Exception as e:
            return {
                "id": case["id"], "input": case["input"],
                "error": str(e), "elapsed_ms": int((time.time() - t0) * 1000),
                "tags": case.get("tags", []),
            }

        # 如果是 HITL 响应，intent 可能未直接返回，从 hitl 对象提取
        intent = r.get("intent", "")
        if not intent and r.get("type") == "hitl":
            hitl_data = r.get("hitl", {})
            intent = hitl_data.get("intent", "")

        tool_names = [tc.get("tool", "") for tc in r.get("toolCalls", [])]
        tool_success = all(tc.get("success", False) for tc in r.get("toolCalls", [])) if tool_names else None

        sub_agents = [sr.get("agent", "") for sr in r.get("subResults", [])]

        return {
            "id": case["id"],
            "input": case["input"],
            "session_id": session_id,
            "intent": intent,
            "intent_expected": case["expected"].get("intent", ""),
            "tools_actual": sorted(tool_names),
            "tools_expected": sorted(case["expected"].get("tools", [])),
            "tool_success_all": tool_success,
            "needs_hitl_actual": bool(r.get("needsHitl") or r.get("type") == "hitl"),
            "needs_hitl_expected": case["expected"].get("needs_hitl", False),
            "latency_ms": r.get("latencyMs", elapsed_ms),
            "sub_agents": sub_agents,
            "sub_agents_count": len(sub_agents),
            "min_sub_agents": case["expected"].get("min_sub_agents", 0),
            "has_steps": bool(r.get("steps")),
            "has_citations": bool(r.get("citations")),
            "max_latency_ms": case["expected"].get("max_latency_ms", 0),
            "tags": case.get("tags", []),
            "reply_preview": r.get("reply", "")[:200],
            "type": r.get("type", "result"),
        }

    def run(self, cases: list):
        """逐条执行，打印进度。"""
        total = len(cases)
        for i, case in enumerate(cases):
            cid = case["id"]
            print(f"  [{i+1}/{total}] {cid} ... ", end="", flush=True)
            result = self._run_one(case)
            self.results.append(result)
            # 快速判断
            intent_ok = result.get("intent") == result.get("intent_expected", "")
            lat_ok = True
            if result.get("max_latency_ms") and result.get("latency_ms"):
                lat_ok = result["latency_ms"] <= result["max_latency_ms"]
            if result.get("error"):
                print(_bad(f"ERROR: {result['error'][:80]}"))
            elif intent_ok and lat_ok:
                print(_ok(f"intent={result.get('intent')} {result.get('latency_ms')}ms"))
            else:
                parts = []
                if not intent_ok:
                    parts.append(f"intent got={result.get('intent')} exp={result.get('intent_expected')}")
                if not lat_ok:
                    parts.append(f"latency {result.get('latency_ms')}ms > {result.get('max_latency_ms')}ms")
                print(_warn(", ".join(parts)))

    # ── 报告生成 ─────────────────────────────────────────────────

    def compute_metrics(self) -> dict:
        """从 self.results 计算所有统计指标。"""
        valid = [r for r in self.results if "error" not in r]
        errors = [r for r in self.results if "error" in r]

        if not valid:
            return {"error": "no valid results", "total": len(self.results), "errors": len(errors)}

        latencies = [r["latency_ms"] for r in valid if r.get("latency_ms")]

        # ── Intent 准确率 ──
        intent_correct = sum(1 for r in valid if r.get("intent") == r.get("intent_expected"))
        intent_by_value = defaultdict(lambda: {"total": 0, "correct": 0})
        for r in valid:
            exp = r.get("intent_expected", "")
            intent_by_value[exp]["total"] += 1
            if r.get("intent") == exp:
                intent_by_value[exp]["correct"] += 1

        # Intent 混淆矩阵
        confusion = defaultdict(lambda: defaultdict(int))
        for r in valid:
            confusion[r.get("intent_expected", "?")][r.get("intent", "?")] += 1

        # ── 工具集合命中率（集合匹配，不绑定顺序） ──
        tool_eval = []
        for r in valid:
            exp_set = set(r.get("tools_expected", []))
            act_set = set(r.get("tools_actual", []))
            if not exp_set:
                continue  # 不检查工具
            hit = exp_set.issubset(act_set)  # 预期工具全部出现即命中
            tool_eval.append({**r, "tool_hit": hit,
                              "tool_missing": list(exp_set - act_set),
                              "tool_extra": list(act_set - exp_set)})
        tool_hits = sum(1 for t in tool_eval if t["tool_hit"])
        tool_total = len(tool_eval)

        # ── HITL 正确率（四象限） ──
        hitl_stats = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
        for r in valid:
            actual = r.get("needs_hitl_actual", False)
            expected = r.get("needs_hitl_expected", False)
            if expected and actual:
                hitl_stats["tp"] += 1
            elif expected and not actual:
                hitl_stats["fn"] += 1
            elif not expected and actual:
                hitl_stats["fp"] += 1
            else:
                hitl_stats["tn"] += 1
        hitl_total = sum(hitl_stats.values())
        hitl_correct = hitl_stats["tp"] + hitl_stats["tn"]

        # ── 延迟 ──
        lat_stats = _latency_stats(latencies)
        latency_ok = sum(1 for r in valid
                         if not r.get("max_latency_ms") or r.get("latency_ms", 0) <= r["max_latency_ms"])

        # ── 完整度 ──
        has_steps = sum(1 for r in valid if r.get("has_steps"))
        has_citations = sum(1 for r in valid if r.get("has_citations"))
        has_sub_agents = sum(1 for r in valid if r.get("sub_agents_count", 0) >= r.get("min_sub_agents", 0))
        sub_agents_total = sum(1 for r in valid if r.get("min_sub_agents", 0) > 0)

        return {
            "meta": {
                "total_cases": len(self.results),
                "valid": len(valid),
                "errors": len(errors),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "base_url": self.base_url,
            },
            "intent": {
                "accuracy": round(intent_correct / len(valid), 3) if valid else 0,
                "correct": intent_correct,
                "total": len(valid),
                "by_value": {k: {"correct": v["correct"], "total": v["total"],
                                  "rate": round(v["correct"] / v["total"], 3) if v["total"] else 0}
                             for k, v in sorted(intent_by_value.items())},
                "confusion_matrix": {str(k): dict(v) for k, v in confusion.items()},
            },
            "tools": {
                "hit_rate": round(tool_hits / tool_total, 3) if tool_total else 0,
                "hits": tool_hits,
                "total": tool_total,
                "details": [
                    {"id": t["id"], "hit": t["tool_hit"],
                     "expected": t.get("tools_expected", []),
                     "actual": t.get("tools_actual", []),
                     "missing": t.get("tool_missing", []),
                     "extra": t.get("tool_extra", [])}
                    for t in tool_eval
                ],
            },
            "hitl": {
                "accuracy": round(hitl_correct / hitl_total, 3) if hitl_total else 0,
                "correct": hitl_correct,
                "total": hitl_total,
                **hitl_stats,
                **_precision_recall(hitl_stats["tp"], hitl_stats["fp"], hitl_stats["fn"]),
            },
            "latency": {
                "violations": len(valid) - latency_ok,
                "total_checked": len(valid),
                **lat_stats,
            },
            "completeness": {
                "steps_present": f"{_pct(has_steps, len(valid))}",
                "citations_present": f"{_pct(has_citations, len(valid))}",
                "sub_agents_sufficient": f"{_pct(has_sub_agents, sub_agents_total)}" if sub_agents_total else "N/A",
            },
        }

    def print_report(self, metrics: dict):
        """终端彩色报告。"""
        m = metrics
        meta = m["meta"]
        print(f"\n{'='*60}")
        print(_hdr("  AIWear Agent Eval 报告"))
        print("  {}  |  {}  |  {}/{} 有效  |  {} 错误".format(
            meta["timestamp"], meta["base_url"], meta["valid"], meta["total_cases"], meta["errors"]))
        print(f"{'='*60}")

        # Intent
        im = m["intent"]
        tag = _ok if im["accuracy"] >= 0.8 else (_warn if im["accuracy"] >= 0.6 else _bad)
        int_acc = im["accuracy"]
        print("\n" + _hdr("── Intent 准确率") + "  " + tag("{:.1%}".format(int_acc))
              + "  ({}/{})".format(im["correct"], im["total"]))
        for val, stats in im["by_value"].items():
            tag2 = _ok if stats["rate"] >= 0.8 else _bad
            sr = stats["rate"]
            print("  {:20s}  {}  ({}/{})".format(val, tag2("{:.1%}".format(sr)), stats["correct"], stats["total"]))

        # 混淆矩阵
        cm = im.get("confusion_matrix", {})
        if len(cm) > 1:
            print(f"\n  混淆矩阵 (行=预期, 列=实际):")
            intents = sorted(set(k for row in cm.values() for k in row))
            header = " " * 20 + "".join(f"{i:>12}" for i in intents)
            print(header)
            for exp in sorted(cm):
                row = "".join(f"{cm[exp].get(act, 0):>12}" for act in intents)
                print(f"  {exp:18s}{row}")

        # 工具
        tm = m["tools"]
        if tm["total"] > 0:
            tag = _ok if tm["hit_rate"] >= 0.8 else (_warn if tm["hit_rate"] >= 0.6 else _bad)
            th = tm["hit_rate"]
            print("\n" + _hdr("── 工具集合命中率") + "  " + tag("{:.1%}".format(th))
                  + "  ({}/{})".format(tm["hits"], tm["total"]))
            # 打印失败项
            fails = [d for d in tm["details"] if not d["hit"]]
            if fails:
                for d in fails:
                    print(f"  {_bad('✗')} {d['id']}: missing={d['missing']} extra={d['extra']}")

        # HITL
        hm = m["hitl"]
        if hm["total"] > 0:
            tag = _ok if hm["accuracy"] >= 0.9 else (_warn if hm["accuracy"] >= 0.7 else _bad)
            ha = hm["accuracy"]
            print("\n" + _hdr("── HITL 正确率") + "  " + tag("{:.1%}".format(ha))
                  + "  ({}/{})".format(hm["correct"], hm["total"]))
            print(f"  TP={hm['tp']}  FP={hm['fp']}  TN={hm['tn']}  FN={hm['fn']}")
            print(f"  Precision={hm['precision']:.2f}  Recall={hm['recall']:.2f}  F1={hm['f1']:.2f}")

        # 延迟
        lm = m["latency"]
        print(f"\n{_hdr('── 延迟 (ms)')}  "
              f"min={lm['min']}  max={lm['max']}  avg={lm['avg']}  "
              f"p50={lm['p50']}  p95={lm['p95']}  p99={lm['p99']}")
        if lm["violations"] > 0:
            lv = lm["violations"]
            print("  {}  (共检查 {} 条)".format(_bad("{} 超时违规".format(lv)), lm["total_checked"]))

        # 完整度
        cm_ = m["completeness"]
        print(f"\n{_hdr('── 响应完整度')}")
        print(f"  steps 存在:     {cm_['steps_present']}")
        print(f"  citations 存在: {cm_['citations_present']}")
        print(f"  subAgents 充足: {cm_['sub_agents_sufficient']}")

        # 总体
        int_w = 0.35
        tool_w = 0.25
        hitl_w = 0.15
        lat_w = 0.25
        score = (
            int_w * im["accuracy"] +
            tool_w * (tm["hit_rate"] if tm["total"] > 0 else 1.0) +
            hitl_w * (hm["accuracy"] if hm["total"] > 0 else 1.0) +
            lat_w * (1.0 - lm["violations"] / max(lm["total_checked"], 1))
        )
        tag = _ok if score >= 0.8 else (_warn if score >= 0.6 else _bad)
        print(f"\n{_hdr('── 综合评分')}  {tag(f'{score:.2%}')}  "
              f"(intent×{int_w:.0%} + tools×{tool_w:.0%} + HITL×{hitl_w:.0%} + latency×{lat_w:.0%})")
        print(f"{'='*60}\n")

    def compare_baseline(self, metrics: dict, baseline_path: str):
        """与基线 JSON 对比，输出变化摘要。"""
        if not os.path.exists(baseline_path):
            print(_warn(f"基线文件不存在: {baseline_path}"))
            return
        with open(baseline_path, "r", encoding="utf-8") as f:
            base = json.load(f)

        b_meta = base.get("meta", {})
        print(f"\n{_hdr('── 基线对比')}  baseline={b_meta.get('timestamp', '?')}  "
              f"cases={b_meta.get('valid', '?')}")

        def _delta(cur, old, fmt=".1%"):
            if old == 0:
                return _ok("NEW") if cur > 0 else "—"
            d = cur - old
            if abs(d) < 0.01:
                return "—"
            return _ok(f"+{d:{fmt}}") if d > 0 else _bad(f"{d:{fmt}}")

        # Intent
        b_im = base.get("intent", {})
        print(f"  Intent:  {b_im.get('accuracy', 0):.1%} → {metrics['intent']['accuracy']:.1%}  "
              f"{_delta(metrics['intent']['accuracy'], b_im.get('accuracy', 0))}")

        # Tools
        b_tm = base.get("tools", {})
        print(f"  Tools:   {b_tm.get('hit_rate', 0):.1%} → {metrics['tools']['hit_rate']:.1%}  "
              f"{_delta(metrics['tools']['hit_rate'], b_tm.get('hit_rate', 0))}")

        # HITL
        b_hm = base.get("hitl", {})
        print(f"  HITL:    {b_hm.get('accuracy', 0):.1%} → {metrics['hitl']['accuracy']:.1%}  "
              f"{_delta(metrics['hitl']['accuracy'], b_hm.get('accuracy', 0))}")

        # Latency
        b_lm = base.get("latency", {})
        print(f"  P95:     {b_lm.get('p95', 0)}ms → {metrics['latency']['p95']}ms  "
              f"{_delta(metrics['latency']['p95'], b_lm.get('p95', 0), '.0f')}")

    def save_json(self, metrics: dict, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        payload = {"meta": metrics["meta"], "metrics": metrics, "raw_results": self.results}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"报告已保存: {path}")


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AIWear Agent Eval — 统计级评估")
    parser.add_argument("--base-url", default="http://127.0.0.1:5001")
    parser.add_argument("--cases", default=None,
                        help="用例 JSON 文件路径（默认 eval/cases/agent_eval_cases.json）")
    parser.add_argument("--output", default=None,
                        help="输出 JSON 路径（默认 eval/results/agent_eval_<timestamp>.json）")
    parser.add_argument("--baseline", default=None,
                        help="基线 JSON 路径，用于对比")
    parser.add_argument("--timeout", type=int, default=90,
                        help="单条用例超时秒数（默认 90）")
    args = parser.parse_args()

    # 用例路径
    cases_path = args.cases
    if not cases_path:
        cases_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "cases", "agent_eval_cases.json")
    if not os.path.exists(cases_path):
        print(_bad(f"用例文件不存在: {cases_path}"))
        sys.exit(1)

    with open(cases_path, "r", encoding="utf-8") as f:
        case_data = json.load(f)
    cases = case_data.get("cases", [])

    print(_hdr(f"Agent Eval — 加载 {len(cases)} 条用例"))
    print(f"  服务地址: {args.base_url}")
    print(f"  用例文件: {cases_path}")
    print()

    evaluator = AgentEvaluator(base_url=args.base_url, timeout=args.timeout)
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
                                   "results", f"agent_eval_{ts}.json")
    evaluator.save_json(metrics, output_path)

    # 退出码：综合评分 < 0.6 返回 1
    im = metrics["intent"]
    tm = metrics["tools"]
    hm = metrics["hitl"]
    lm = metrics["latency"]
    score = (
        0.35 * im["accuracy"] +
        0.25 * (tm["hit_rate"] if tm["total"] > 0 else 1.0) +
        0.15 * (hm["accuracy"] if hm["total"] > 0 else 1.0) +
        0.25 * (1.0 - lm["violations"] / max(lm["total_checked"], 1))
    )
    sys.exit(0 if score >= 0.6 else 1)


if __name__ == "__main__":
    main()
