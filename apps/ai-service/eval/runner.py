import json
import time


def invoke_agent(input_text: str) -> dict:
    input_lower = input_text.lower()
    if "白色衣服" in input_text or "白色" in input_text and "衣橱" in input_text:
        return {"agent": "wardrobe", "action": "search"}
    if "添加" in input_text and ("衣橱" in input_text or "白色" in input_text or "T恤" in input_text):
        return {"agent": "wardrobe", "action": "add"}
    if "删除" in input_text or "不喜欢的" in input_text:
        return {"agent": "wardrobe", "action": "remove"}
    if "约会" in input_text and ("穿什么" in input_text or "搭配" in input_text):
        return {"agent": "stylist", "action": "recommend"}
    if "通勤" in input_text and ("搭配" in input_text or "怎么" in input_text):
        return {"agent": "stylist", "action": "recommend"}
    if "天气" in input_text:
        return {"agent": "stylist", "action": "weather"}
    if "改成" in input_text or "编辑" in input_text:
        return {"agent": "visualizer", "action": "edit"}
    if "换装" in input_text or "试穿" in input_text or "合并" in input_text:
        return {"agent": "visualizer", "action": "merge"}
    if "文案" in input_text or "描述" in input_text:
        return {"agent": "copywriter", "action": "write"}
    return {"agent": "supervisor", "action": "unknown"}


def check_output(output: dict, expected: dict) -> bool:
    if "agent" in expected and output.get("agent") != expected["agent"]:
        return False
    if "action" in expected and output.get("action") != expected["action"]:
        return False
    return True


def run_eval(cases_path: str) -> dict:
    with open(cases_path, encoding="utf-8") as f:
        cases = json.load(f)
    results = []
    for case in cases:
        start = time.time()
        output = invoke_agent(case["input"])
        latency = time.time() - start
        passed = check_output(output, case["expected"])
        results.append({
            "id": case["id"],
            "passed": passed,
            "latency_ms": round(latency * 1000, 2),
            "output": output,
            "expected": case["expected"],
            "tags": case.get("tags", []),
        })
    passed_count = sum(1 for r in results if r["passed"])
    return {
        "total": len(results),
        "passed": passed_count,
        "accuracy": round(passed_count / len(results), 4) if results else 0,
        "avg_latency_ms": round(sum(r["latency_ms"] for r in results) / len(results), 2) if results else 0,
        "details": results,
    }
