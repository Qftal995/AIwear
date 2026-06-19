import threading
import time
from collections import defaultdict


PRICING = {
    "deepseek-chat": {"in": 0.14, "out": 0.28},
    "qwen-vl-max": {"in": 0.02, "out": 0.06},
    "wan2.1-imageedit": {"per_image": 0.10},
    "aitryon-plus": {"per_image": 0.071677},
    "qwen-image-edit-plus": {"per_image": 0.10},
}


class SessionStats:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.steps = []
        self.tool_calls = defaultdict(list)
        self.model_calls = defaultdict(list)
        self.total_tokens_in = 0
        self.total_tokens_out = 0
        self.total_cost = 0.0
        self.total_latency_ms = 0
        self.step_count = 0
        self.started_at = time.time()
        self.last_active = time.time()


class CostTracker:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._sessions = {}
                    cls._instance._session_lock = threading.Lock()
        return cls._instance

    def start_session(self, session_id: str):
        with self._session_lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionStats(session_id)

    def record_step(self, session_id: str, agent_name: str, model: str, tokens_in: int, tokens_out: int, latency_ms: int):
        with self._session_lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionStats(session_id)
            s = self._sessions[session_id]
            step = {
                "agent": agent_name,
                "model": model,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency_ms": latency_ms,
                "timestamp": time.time(),
            }
            s.steps.append(step)
            s.model_calls[model].append(step)
            s.total_tokens_in += tokens_in
            s.total_tokens_out += tokens_out
            s.total_latency_ms += latency_ms
            s.step_count += 1
            s.last_active = time.time()
            pricing = PRICING.get(model, {"in": 0.02, "out": 0.06})
            if "per_image" in pricing:
                s.total_cost += pricing["per_image"]
            else:
                s.total_cost += (tokens_in / 1000.0) * pricing["in"] + (tokens_out / 1000.0) * pricing["out"]

    def record_tool_call(self, session_id: str, tool_name: str, model: str, tokens_in: int, tokens_out: int, latency_ms: int):
        with self._session_lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionStats(session_id)
            s = self._sessions[session_id]
            call = {
                "tool": tool_name,
                "model": model,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency_ms": latency_ms,
                "timestamp": time.time(),
            }
            s.tool_calls[tool_name].append(call)
            s.total_tokens_in += tokens_in
            s.total_tokens_out += tokens_out
            s.total_latency_ms += latency_ms
            s.step_count += 1
            s.last_active = time.time()
            pricing = PRICING.get(model, {"in": 0.02, "out": 0.06})
            if "per_image" in pricing:
                s.total_cost += pricing["per_image"]
            else:
                s.total_cost += (tokens_in / 1000.0) * pricing["in"] + (tokens_out / 1000.0) * pricing["out"]

    def get_session_stats(self, session_id: str) -> dict:
        with self._session_lock:
            s = self._sessions.get(session_id)
            if not s:
                return {"session_id": session_id, "error": "session not found"}
            tool_breakdown = {}
            for tool_name, calls in s.tool_calls.items():
                tool_breakdown[tool_name] = {
                    "count": len(calls),
                    "total_latency_ms": sum(c["latency_ms"] for c in calls),
                    "total_tokens_in": sum(c["tokens_in"] for c in calls),
                    "total_tokens_out": sum(c["tokens_out"] for c in calls),
                }
            model_breakdown = {}
            for model_name, calls in s.model_calls.items():
                model_breakdown[model_name] = {
                    "count": len(calls),
                    "total_tokens_in": sum(c["tokens_in"] for c in calls),
                    "total_tokens_out": sum(c["tokens_out"] for c in calls),
                    "avg_latency_ms": round(sum(c["latency_ms"] for c in calls) / len(calls), 2) if calls else 0,
                }
            return {
                "session_id": s.session_id,
                "total_tokens_in": s.total_tokens_in,
                "total_tokens_out": s.total_tokens_out,
                "total_tokens": s.total_tokens_in + s.total_tokens_out,
                "total_cost_usd": round(s.total_cost, 6),
                "avg_latency_ms": round(s.total_latency_ms / s.step_count, 2) if s.step_count > 0 else 0,
                "step_count": s.step_count,
                "duration_s": round(time.time() - s.started_at, 1),
                "tool_breakdown": tool_breakdown,
                "model_breakdown": model_breakdown,
                "steps": s.steps[-20:],
            }

    def get_global_stats(self) -> dict:
        with self._session_lock:
            active = len([s for s in self._sessions.values() if time.time() - s.last_active < 3600])
            total_tokens_in = sum(s.total_tokens_in for s in self._sessions.values())
            total_tokens_out = sum(s.total_tokens_out for s in self._sessions.values())
            total_cost = sum(s.total_cost for s in self._sessions.values())
            all_latencies = []
            for s in self._sessions.values():
                for step in s.steps:
                    all_latencies.append(step["latency_ms"])
            avg_latency = round(sum(all_latencies) / len(all_latencies), 2) if all_latencies else 0
            global_tools = defaultdict(int)
            global_models = defaultdict(int)
            for s in self._sessions.values():
                for t in s.tool_calls:
                    global_tools[t] += len(s.tool_calls[t])
                for m in s.model_calls:
                    global_models[m] += len(s.model_calls[m])
            return {
                "total_sessions": len(self._sessions),
                "active_sessions": active,
                "total_tokens_in": total_tokens_in,
                "total_tokens_out": total_tokens_out,
                "total_tokens": total_tokens_in + total_tokens_out,
                "total_cost_usd": round(total_cost, 6),
                "avg_latency_ms": avg_latency,
                "top_tools": dict(sorted(global_tools.items(), key=lambda x: x[1], reverse=True)[:10]),
                "top_models": dict(sorted(global_models.items(), key=lambda x: x[1], reverse=True)[:10]),
                "models": list(PRICING.keys()),
            }
