import threading
import time


PRICING = {
    "deepseek-chat": {"in": 0.14, "out": 0.28},
    "qwen-vl-max": {"in": 0.02, "out": 0.06},
    "wan2.1-imageedit": {"in": 0.0, "out": 0.10},
    "aitryon-plus": {"in": 0.0, "out": 0.071677},
    "qwen-image-edit-plus": {"in": 0.0, "out": 0.10},
}


class SessionStats:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.steps = []
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
            s.steps.append({
                "agent": agent_name,
                "model": model,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency_ms": latency_ms,
                "timestamp": time.time(),
            })
            s.total_tokens_in += tokens_in
            s.total_tokens_out += tokens_out
            s.total_latency_ms += latency_ms
            s.step_count += 1
            s.last_active = time.time()
            pricing = PRICING.get(model, {"in": 0.02, "out": 0.06})
            cost = (tokens_in / 1000.0) * pricing["in"] + (tokens_out / 1000.0) * pricing["out"]
            s.total_cost += cost

    def get_session_stats(self, session_id: str) -> dict:
        with self._session_lock:
            s = self._sessions.get(session_id)
            if not s:
                return {"session_id": session_id, "error": "session not found"}
            return {
                "session_id": s.session_id,
                "total_tokens_in": s.total_tokens_in,
                "total_tokens_out": s.total_tokens_out,
                "total_tokens": s.total_tokens_in + s.total_tokens_out,
                "total_cost_usd": round(s.total_cost, 6),
                "avg_latency_ms": round(s.total_latency_ms / s.step_count, 2) if s.step_count > 0 else 0,
                "step_count": s.step_count,
                "duration_s": round(time.time() - s.started_at, 1),
                "steps": s.steps,
            }

    def get_global_stats(self) -> dict:
        with self._session_lock:
            active_sessions = len([s for s in self._sessions.values() if time.time() - s.last_active < 3600])
            total_tokens_in = sum(s.total_tokens_in for s in self._sessions.values())
            total_tokens_out = sum(s.total_tokens_out for s in self._sessions.values())
            total_cost = sum(s.total_cost for s in self._sessions.values())
            all_latencies = []
            for s in self._sessions.values():
                for step in s.steps:
                    all_latencies.append(step["latency_ms"])
            avg_latency = round(sum(all_latencies) / len(all_latencies), 2) if all_latencies else 0
            return {
                "total_sessions": len(self._sessions),
                "active_sessions": active_sessions,
                "total_tokens_in": total_tokens_in,
                "total_tokens_out": total_tokens_out,
                "total_tokens": total_tokens_in + total_tokens_out,
                "total_cost_usd": round(total_cost, 6),
                "avg_latency_ms": avg_latency,
                "models": list(PRICING.keys()),
            }
