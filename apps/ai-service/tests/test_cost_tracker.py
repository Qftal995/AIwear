import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.cost_tracker import CostTracker, PRICING


class TestCostTracker:
    def setup_method(self):
        self.tracker = CostTracker()
        # Reset for tests — access internal store directly
        with self.tracker._session_lock:
            self.tracker._sessions.clear()

    def test_singleton(self):
        t1 = CostTracker()
        t2 = CostTracker()
        assert t1 is t2

    def test_start_session(self):
        self.tracker.start_session("sess-1")
        stats = self.tracker.get_session_stats("sess-1")
        assert stats["session_id"] == "sess-1"
        assert stats["total_tokens_in"] == 0

    def test_record_step(self):
        self.tracker.start_session("sess-1")
        self.tracker.record_step("sess-1", "stylist", "deepseek-chat", 200, 150, 800)
        stats = self.tracker.get_session_stats("sess-1")
        assert stats["total_tokens_in"] == 200
        assert stats["total_tokens_out"] == 150
        assert stats["step_count"] == 1
        assert stats["total_cost_usd"] > 0

    def test_record_multiple_steps_accumulates(self):
        self.tracker.start_session("sess-1")
        self.tracker.record_step("sess-1", "supervisor", "deepseek-chat", 100, 50, 300)
        self.tracker.record_step("sess-1", "stylist", "deepseek-chat", 200, 100, 500)
        stats = self.tracker.get_session_stats("sess-1")
        assert stats["total_tokens_in"] == 300
        assert stats["total_tokens_out"] == 150
        assert stats["step_count"] == 2

    def test_record_tool_call(self):
        self.tracker.start_session("sess-1")
        self.tracker.record_tool_call("sess-1", "weather_api", "deepseek-chat", 50, 30, 200)
        stats = self.tracker.get_session_stats("sess-1")
        assert stats["step_count"] == 1
        assert stats["tool_breakdown"]["weather_api"]["count"] == 1

    def test_deepseek_pricing(self):
        self.tracker.start_session("sess-1")
        self.tracker.record_step("sess-1", "stylist", "deepseek-chat", 1000, 500, 1000)
        stats = self.tracker.get_session_stats("sess-1")
        expected_cost = (1000 / 1000.0) * 0.14 + (500 / 1000.0) * 0.28
        assert abs(stats["total_cost_usd"] - expected_cost) < 0.001

    def test_image_model_pricing(self):
        self.tracker.start_session("sess-1")
        self.tracker.record_step("sess-1", "visualizer", "wan2.1-imageedit", 0, 0, 3000)
        stats = self.tracker.get_session_stats("sess-1")
        assert abs(stats["total_cost_usd"] - 0.10) < 0.001

    def test_unknown_model_uses_default_pricing(self):
        self.tracker.start_session("sess-1")
        self.tracker.record_step("sess-1", "unknown_agent", "some-new-model", 1000, 500, 1000)
        stats = self.tracker.get_session_stats("sess-1")
        assert stats["total_cost_usd"] > 0

    def test_nonexistent_session(self):
        stats = self.tracker.get_session_stats("does-not-exist")
        assert "error" in stats

    def test_global_stats(self):
        self.tracker.start_session("sess-1")
        self.tracker.record_step("sess-1", "stylist", "deepseek-chat", 100, 50, 100)
        gs = self.tracker.get_global_stats()
        assert gs["total_sessions"] == 1
        assert gs["total_tokens_in"] == 100

    def test_model_breakdown(self):
        self.tracker.start_session("sess-1")
        self.tracker.record_step("sess-1", "wardrobe", "deepseek-chat", 100, 50, 200)
        self.tracker.record_step("sess-1", "stylist", "deepseek-chat", 200, 100, 400)
        self.tracker.record_step("sess-1", "visualizer", "wan2.1-imageedit", 0, 0, 3000)
        stats = self.tracker.get_session_stats("sess-1")
        assert "deepseek-chat" in stats["model_breakdown"]
        assert "wan2.1-imageedit" in stats["model_breakdown"]
        assert stats["model_breakdown"]["deepseek-chat"]["count"] == 2

    def test_pricing_reference(self):
        assert "deepseek-chat" in PRICING
        assert "qwen-vl-max" in PRICING
        assert PRICING["deepseek-chat"]["in"] == 0.14
        assert PRICING["deepseek-chat"]["out"] == 0.28
