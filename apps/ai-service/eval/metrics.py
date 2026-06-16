def calculate_accuracy(results: list) -> float:
    if not results:
        return 0.0
    return sum(1 for r in results if r.get("passed")) / len(results)


def calculate_recall(results: list, tag: str) -> float:
    relevant = [r for r in results if tag in r.get("tags", [])]
    if not relevant:
        return 0.0
    passed_relevant = [r for r in relevant if r.get("passed")]
    return len(passed_relevant) / len(relevant)


def calculate_precision(results: list, expected_agent: str) -> float:
    predicted = [r for r in results if r["output"].get("agent") == expected_agent]
    if not predicted:
        return 0.0
    correct = [r for r in predicted if r.get("passed")]
    return len(correct) / len(predicted)


def f1_score(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def latency_stats(results: list) -> dict:
    latencies = [r["latency_ms"] for r in results if "latency_ms" in r]
    if not latencies:
        return {"min_ms": 0, "max_ms": 0, "avg_ms": 0, "p50_ms": 0, "p95_ms": 0}
    sorted_lats = sorted(latencies)
    n = len(sorted_lats)
    return {
        "min_ms": sorted_lats[0],
        "max_ms": sorted_lats[-1],
        "avg_ms": round(sum(latencies) / n, 2),
        "p50_ms": sorted_lats[n // 2],
        "p95_ms": sorted_lats[int(n * 0.95)],
    }


def per_tag_accuracy(results: list) -> dict:
    tags = set()
    for r in results:
        for t in r.get("tags", []):
            tags.add(t)
    return {tag: calculate_accuracy([r for r in results if tag in r.get("tags", [])]) for tag in tags}
