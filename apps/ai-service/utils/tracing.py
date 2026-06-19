import json
import time
from datetime import datetime, timezone


_trace_store = {}
_trace_lock = __import__('threading').Lock()


def _iso_ms():
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond:06d}"[:3]


def _store_event(session_id: str, event: dict):
    with _trace_lock:
        if session_id not in _trace_store:
            _trace_store[session_id] = []
        _trace_store[session_id].append(event)


def trace_step(session_id: str, step_name: str, data: dict):
    event = {"ts": _iso_ms(), "type": "node_end", "source": step_name, "data": data}
    print(f"[TRACE] {event['ts']} | session:{session_id} | node:{step_name} | {str(data)[:100]}")
    _store_event(session_id, event)

def trace_node_start(session_id: str, node_name: str, input_data: dict = None):
    event = {"ts": _iso_ms(), "type": "node_start", "source": node_name, "input": input_data or {}}
    _store_event(session_id, event)

def trace_tool_call(session_id: str, tool_name: str, args: dict, result: str, duration_ms: float):
    event = {"ts": _iso_ms(), "type": "tool_call", "tool": tool_name, "args": args, "result_preview": str(result)[:200], "latencyMs": int(duration_ms), "success": True}
    print(f"[TRACE] {event['ts']} | session:{session_id} | tool:{tool_name} | duration={duration_ms}ms")
    _store_event(session_id, event)


def trace_error(session_id: str, context: str, error: str):
    event = {"ts": _iso_ms(), "type": "error", "context": context, "error": error, "success": False}
    print(f"[TRACE] {event['ts']} | session:{session_id} | error:{context} | {error}")
    _store_event(session_id, event)


def trace_model_call(session_id: str, model: str, tokens_in: int, tokens_out: int, latency_ms: int):
    event = {"ts": _iso_ms(), "type": "llm_call", "model": model, "tokensIn": tokens_in, "tokensOut": tokens_out, "latencyMs": latency_ms}
    _store_event(session_id, event)

def trace_rag_retrieve(session_id: str, query: str, result_count: int, latency_ms: int):
    event = {"ts": _iso_ms(), "type": "rag_retrieve", "query": query[:200], "resultCount": result_count, "latencyMs": latency_ms}
    _store_event(session_id, event)

def trace_mcp_call(session_id: str, server: str, tool: str, success: bool, latency_ms: int):
    event = {"ts": _iso_ms(), "type": "mcp_call", "server": server, "tool": tool, "success": success, "latencyMs": latency_ms}
    _store_event(session_id, event)

def trace_hitl(session_id: str, question: str, user_choice: str):
    event = {"ts": _iso_ms(), "type": "hitl", "question": question, "userChoice": user_choice}
    _store_event(session_id, event)


def get_session_trace(session_id: str) -> list:
    with _trace_lock:
        return list(_trace_store.get(session_id, []))


def get_trace_panel(session_id: str = None) -> dict:
    with _trace_lock:
        if session_id:
            events = _trace_store.get(session_id, [])
            model_calls = [e for e in events if e["type"] in ("llm_call",)]
            tool_calls = [e for e in events if e["type"] in ("tool_call", "mcp_call")]
            rag_events = [e for e in events if e["type"] == "rag"]
            hitl_events = [e for e in events if e["type"] == "hitl"]
            errors = [e for e in events if e["type"] == "error"]
            node_events = [e for e in events if e["type"] in ("node_start", "node_end")]
            # Sum tokens from llm_call events
            total_tokens_in = sum(e.get("tokensIn", 0) for e in model_calls)
            total_tokens_out = sum(e.get("tokensOut", 0) for e in model_calls)
            # Sum latency from all event types that carry latencyMs
            total_latency = sum(
                e.get("latencyMs", e.get("data", {}).get("latency_ms", 0))
                for e in events
                if e["type"] in ("llm_call", "tool_call", "mcp_call", "rag")
            )
            # Build steps timeline from node_start → node_end pairs
            steps = _build_steps_from_events(events)
            return {
                "session_id": session_id,
                "events": len(events),
                "tool_calls": len(tool_calls),
                "model_calls": len(model_calls),
                "errors": len(errors),
                "total_tokens_in": total_tokens_in,
                "total_tokens_out": total_tokens_out,
                "total_latency_ms": total_latency,
                "steps": steps,
                "timeline": events,
            }
        sessions = {}
        for sid, evts in _trace_store.items():
            sessions[sid] = {"events": len(evts), "last_ts": evts[-1]["ts"] if evts else ""}
        return {"sessions": len(_trace_store), "details": sessions}


def _build_steps_from_events(events: list) -> list:
    """Build a steps timeline from node_start/node_end event pairs with duration."""
    from datetime import datetime, timezone
    node_starts: dict[str, tuple] = {}  # source -> (ts_datetime, event)
    steps = []
    for e in events:
        if e["type"] == "node_start":
            try:
                t = datetime.fromisoformat(e["ts"]).replace(tzinfo=timezone.utc)
            except (ValueError, AttributeError):
                t = None
            node_starts[e["source"]] = (t, e)
        elif e["type"] == "node_end":
            source = e["source"]
            match_key = source.replace("_done", "") if source.endswith("_done") else source
            start_entry = node_starts.pop(match_key, (None, None))
            start_t, start_ev = start_entry[0], start_entry[1]
            duration = 0.0
            if start_t:
                try:
                    end_t = datetime.fromisoformat(e["ts"]).replace(tzinfo=timezone.utc)
                    duration = round((end_t - start_t).total_seconds(), 2)
                except (ValueError, AttributeError):
                    pass
            label_map = {
                "intent": "意图分析", "planning": "工具规划", "tool_execution": "调用工具",
                "dispatch": "调用助手", "hitl": "人工确认", "aggregate": "整合结果",
                "final": "生成回复", "chat": "对话完成",
            }
            steps.append({
                "name": match_key,
                "label": label_map.get(match_key, match_key),
                "status": "done",
                "duration": duration,
                "detail": e.get("data", {}),
            })
    return steps


def clear_trace(session_id: str = None):
    with _trace_lock:
        if session_id:
            _trace_store.pop(session_id, None)
        else:
            _trace_store.clear()
