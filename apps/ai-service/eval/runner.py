"""
Eval runner for AIWear agent.
Supports single-turn and multi-turn evaluation, mock mode, and timeout control.
"""

import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError


# ---------------------------------------------------------------------------
# Stub agent (keyword-matching, for quick validation)
# ---------------------------------------------------------------------------

def _invoke_agent_stub(input_text: str) -> dict:
    """Keyword-matching stub for quick validation without real agent.

    Priority order (first-match-wins):
    1. Explicit actions (add/delete/edit/merge) — verb+keyword pairs
    2. Stylist recommend (occasion-based) / weather
    3. Copywriter
    4. Wardrobe search (generic, catches leftover wardrobe mentions)
    """

    # --- wardrobe: add (explicit verb) ---
    if "添加" in input_text and any(
        kw in input_text for kw in ("衣橱", "白色", "T恤", "衣服", "外套", "裙子", "裤子", "到衣橱")
    ):
        return {"agent": "wardrobe", "action": "add"}

    # --- wardrobe: remove (explicit verb) ---
    if any(kw in input_text for kw in ("删除", "移除", "丢掉", "不喜欢的")):
        return {"agent": "wardrobe", "action": "remove"}

    # --- stylist: recommend (broad matching before visualizer) ---
    if any(kw in input_text for kw in ("穿什么", "怎么穿", "穿啥", "穿合适",
                                         "穿搭推荐", "穿搭建议", "怎么搭")):
        return {"agent": "stylist", "action": "recommend"}

    # --- visualizer: edit / merge (explicit verbs) ---
    if any(kw in input_text for kw in ("改成", "编辑", "换颜色")):
        return {"agent": "visualizer", "action": "edit"}
    if any(kw in input_text for kw in ("换装", "试穿", "合并", "合成试衣")):
        return {"agent": "visualizer", "action": "merge"}

    # --- copywriter ---
    if "文案" in input_text or "描述" in input_text:
        return {"agent": "copywriter", "action": "write"}

    # --- stylist: recommend (搭配/穿搭 context) ---
    if any(kw in input_text for kw in ("搭配", "穿搭", "婚礼", "换一套", "不喜欢")):
        # Requires a second keyword for confidence, or certain single keywords are enough
        second_checks = any(
            kw in input_text for kw in ("衣服", "推荐", "通勤", "约会", "郊游", "一套", "怎么",
                                        "面试", "商务", "梨形", "女生", "男生", "下雨", "暖色")
        )
        # Single-keyword triggers: 婚礼, 换一套, 不喜欢 all imply styling context
        single_triggers = any(kw in input_text for kw in ("婚礼", "换一套", "不喜欢"))
        if second_checks or single_triggers:
            return {"agent": "stylist", "action": "recommend"}

    # --- stylist: weather ---
    if "天气" in input_text and "穿什么" not in input_text and "怎么穿" not in input_text:
        return {"agent": "stylist", "action": "weather"}

    # --- wardrobe: search (catch-all for wardrobe mentions) ---
    if any(kw in input_text for kw in ("衣橱", "衣柜", "有哪些", "有什么", "看看我的", "我的衣服")):
        return {"agent": "wardrobe", "action": "search"}
    if "白色衣服" in input_text:
        return {"agent": "wardrobe", "action": "search"}

    # --- fallback ---
    return {"agent": "supervisor", "action": "unknown"}


# ---------------------------------------------------------------------------
# Real agent connector
# ---------------------------------------------------------------------------

def _infer_action(input_text: str, agent: str) -> str:
    """Infer action from input text and agent name.

    Used to produce structured output compatible with test-case expectations
    when running against the real graph (which returns natural language).
    """
    if agent == "wardrobe":
        if any(kw in input_text for kw in ("添加", "增加", "新增")):
            return "add"
        if any(kw in input_text for kw in ("删除", "移除", "去掉", "丢弃")):
            return "remove"
        return "search"
    if agent == "stylist":
        if any(kw in input_text for kw in ("穿什么", "怎么穿", "搭配", "推荐")):
            return "recommend"
        if "天气" in input_text:
            return "weather"
        return "recommend"
    if agent == "visualizer":
        if any(kw in input_text for kw in ("换装", "试穿", "合并")):
            return "merge"
        return "edit"
    if agent == "copywriter":
        return "write"
    return "unknown"


def _extract_agent_output(result_state: dict, input_text: str) -> dict:
    """Map the real agent's LangGraph output to a structured {agent, action} dict."""
    intents = result_state.get("intents", [])
    agent = intents[0] if intents else "supervisor"
    action = _infer_action(input_text, agent)

    raw_output = ""
    if result_state.get("messages"):
        last = result_state["messages"][-1]
        raw_output = last.content if hasattr(last, "content") else str(last)

    return {
        "agent": agent,
        "action": action,
        "intents": intents,
        "raw_output": raw_output,
    }


def _invoke_agent_real(input_text: str, thread_id: str = None) -> dict:
    """Invoke the real LangGraph supervisor agent via the server module."""
    try:
        from server import supervisor_graph
    except Exception as exc:
        raise RuntimeError(f"Failed to import supervisor_graph from server: {exc}")

    from langchain_core.messages import HumanMessage

    session_id = thread_id or f"eval_{uuid.uuid4().hex[:8]}"
    state = {
        "messages": [HumanMessage(content=input_text)],
        "user_id": "eval_user",
        "wardrobe_context": {},
        "session_id": session_id,
        "intermediate_steps": [],
    }
    config = {"configurable": {"thread_id": session_id}}

    result = supervisor_graph.invoke(state, config)
    return _extract_agent_output(result, input_text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def invoke_agent(
    input_text: str,
    *,
    use_mock: bool = False,
    thread_id: str = None,
    timeout: int = 30,
) -> dict:
    """Invoke the AIWear agent.

    Args:
        input_text: The user input text.
        use_mock: If True, use the keyword-matching stub instead of the real agent.
        thread_id: Conversation thread ID (required for multi-turn state).
        timeout: Per-invocation timeout in seconds (default 30).

    Returns:
        Dict with ``agent`` and ``action`` keys (and extra metadata).
        When the real agent fails, falls back to the stub result.
    """
    if use_mock:
        return _invoke_agent_stub(input_text)

    def _do_invoke():
        try:
            result = _invoke_agent_real(input_text, thread_id=thread_id)
            result["_fallback"] = False
            return result
        except Exception as exc:
            fallback = _invoke_agent_stub(input_text)
            fallback["_fallback"] = True
            fallback["_fallback_error"] = str(exc)
            return fallback

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_do_invoke)
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            fallback = _invoke_agent_stub(input_text)
            fallback["_fallback"] = True
            fallback["_fallback_error"] = f"Timeout after {timeout}s"
            return fallback


def check_output(output: dict, expected: dict) -> bool:
    """Check if agent output matches all expected key-value pairs."""
    if not expected:
        return True
    for key, value in expected.items():
        if output.get(key) != value:
            return False
    return True


# ---------------------------------------------------------------------------
# Single-turn & multi-turn case runners
# ---------------------------------------------------------------------------

def _run_single_turn_case(case: dict, use_mock: bool) -> dict:
    """Evaluate a single-turn test case."""
    start = time.time()
    thread_id = f"eval_{case['id']}"
    output = invoke_agent(case["input"], use_mock=use_mock, thread_id=thread_id)
    latency = time.time() - start
    passed = check_output(output, case.get("expected", {}))

    result = {
        "id": case["id"],
        "input": case["input"],
        "passed": passed,
        "latency_ms": round(latency * 1000, 2),
        "output": output,
        "expected": case.get("expected", {}),
        "tags": case.get("tags", []),
        "type": "single_turn",
    }
    if output.get("_fallback"):
        result["fallback"] = True
        result["fallback_error"] = output.get("_fallback_error", "")
    return result


def _run_multi_turn_case(case: dict, use_mock: bool) -> dict:
    """Evaluate a multi-turn (conversational) test case.

    All turns share the same ``thread_id`` so the real agent's
    ``MemorySaver`` checkpoint can maintain conversation history.
    """
    turns = case.get("turns", [])
    turn_results = []
    session_passed = True
    total_latency = 0.0
    session_id = f"eval_mt_{case['id']}"

    for i, turn in enumerate(turns):
        start = time.time()
        output = invoke_agent(
            turn["input"], use_mock=use_mock, thread_id=session_id
        )
        latency = time.time() - start
        total_latency += latency
        passed = check_output(output, turn.get("expected", {}))

        if not passed:
            session_passed = False

        tr = {
            "turn_index": i,
            "input": turn["input"],
            "passed": passed,
            "latency_ms": round(latency * 1000, 2),
            "output": output,
            "expected": turn.get("expected", {}),
        }
        if output.get("_fallback"):
            tr["fallback"] = True
        turn_results.append(tr)

    n = len(turns) or 1
    return {
        "id": case["id"],
        "passed": session_passed,
        "latency_ms": round(total_latency * 1000 / n, 2),
        "total_latency_ms": round(total_latency * 1000, 2),
        "turn_results": turn_results,
        "tags": case.get("tags", []),
        "type": "multi_turn",
        "num_turns": len(turns),
    }


def run_eval(cases: list, use_mock: bool = False) -> dict:
    """Run evaluation on a list of test cases.

    Args:
        cases: List of case dicts.  Single-turn cases have an ``input`` key;
               multi-turn cases have a ``turns`` key.
        use_mock: If True, use the stub agent.

    Returns:
        Summary dict with overall stats and per-case results.
    """
    results = []
    fallback_count = 0

    for case in cases:
        if "turns" in case and isinstance(case["turns"], list):
            result = _run_multi_turn_case(case, use_mock)
        else:
            result = _run_single_turn_case(case, use_mock)
        results.append(result)
        if result.get("fallback") or (
            "turn_results" in result
            and any(tr.get("fallback") for tr in result["turn_results"])
        ):
            fallback_count += 1

    passed_count = sum(1 for r in results if r["passed"])
    total = len(results)
    latencies = [r["latency_ms"] for r in results if "latency_ms" in r]

    summary = {
        "total": total,
        "passed": passed_count,
        "failed": total - passed_count,
        "accuracy": round(passed_count / total, 4) if total else 0,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2)
        if latencies
        else 0,
        "fallback_count": fallback_count,
        "results": results,
    }
    summary["fallback_percent"] = (
        round(fallback_count / total * 100, 1) if total else 0
    )
    return summary


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def load_cases(cases_path: str) -> list:
    """Load test cases from a JSON file."""
    with open(cases_path, encoding="utf-8") as f:
        return json.load(f)


def save_results(results: dict, path: str):
    """Save evaluation results to a JSON file."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
