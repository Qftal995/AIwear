import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.tracing import (
    trace_step,
    trace_tool_call,
    trace_error,
    trace_node_start,
    trace_model_call,
    trace_rag_retrieve,
    trace_mcp_call,
    trace_hitl,
    get_session_trace,
    get_trace_panel,
    clear_trace,
)


class TestTracing:
    def setup_method(self):
        clear_trace()

    def teardown_method(self):
        clear_trace()

    def test_trace_step_adds_event(self):
        trace_step("sess-1", "wardrobe", {"action": "search"})
        events = get_session_trace("sess-1")
        assert len(events) == 1
        assert events[0]["type"] == "node_end"
        assert events[0]["source"] == "wardrobe"

    def test_trace_tool_call_records_metadata(self):
        trace_tool_call("sess-1", "weather_api", {"city": "北京"}, "晴 25°C", 340.0)
        events = get_session_trace("sess-1")
        assert len(events) == 1
        assert events[0]["type"] == "tool_call"
        assert events[0]["tool"] == "weather_api"
        assert events[0]["latencyMs"] == 340

    def test_trace_error_records_failure(self):
        trace_error("sess-1", "rag_search", "Connection timeout")
        events = get_session_trace("sess-1")
        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert events[0]["success"] is False

    def test_trace_model_call(self):
        trace_model_call("sess-1", "deepseek-chat", 150, 80, 1200)
        events = get_session_trace("sess-1")
        assert events[0]["type"] == "llm_call"
        assert events[0]["tokensIn"] == 150
        assert events[0]["tokensOut"] == 80

    def test_trace_rag_retrieve(self):
        trace_rag_retrieve("sess-1", "面试穿搭", 5, 250)
        events = get_session_trace("sess-1")
        assert events[0]["type"] == "rag_retrieve"
        assert events[0]["resultCount"] == 5

    def test_trace_mcp_call(self):
        trace_mcp_call("sess-1", "weather", "get_forecast", True, 500)
        events = get_session_trace("sess-1")
        assert events[0]["type"] == "mcp_call"
        assert events[0]["success"] is True

    def test_trace_hitl(self):
        trace_hitl("sess-1", "请选择穿搭风格", "韩式简约")
        events = get_session_trace("sess-1")
        assert events[0]["type"] == "hitl"
        assert events[0]["userChoice"] == "韩式简约"

    def test_multiple_events_per_session(self):
        trace_step("sess-1", "supervisor", {})
        trace_tool_call("sess-1", "clip_search", {"query": "白衬衫"}, "[...]", 100)
        trace_error("sess-1", "merge", "no face detected")
        assert len(get_session_trace("sess-1")) == 3

    def test_sessions_isolated(self):
        trace_step("sess-A", "wardrobe", {})
        trace_step("sess-B", "stylist", {})
        assert len(get_session_trace("sess-A")) == 1
        assert len(get_session_trace("sess-B")) == 1

    def test_get_trace_panel_specific_session(self):
        trace_model_call("sess-1", "deepseek-chat", 100, 50, 500)
        trace_model_call("sess-1", "deepseek-chat", 200, 100, 800)
        panel = get_trace_panel("sess-1")
        assert panel["session_id"] == "sess-1"
        assert panel["model_calls"] == 2
        assert panel["total_tokens_in"] == 300
        assert panel["total_tokens_out"] == 150

    def test_get_trace_panel_all_sessions(self):
        trace_step("sess-A", "wardrobe", {})
        trace_step("sess-B", "stylist", {})
        panel = get_trace_panel()
        assert panel["sessions"] == 2

    def test_clear_single_session(self):
        trace_step("sess-1", "wardrobe", {})
        trace_step("sess-2", "stylist", {})
        clear_trace("sess-1")
        assert get_session_trace("sess-1") == []
        assert len(get_session_trace("sess-2")) == 1

    def test_clear_all_sessions(self):
        trace_step("sess-1", "wardrobe", {})
        clear_trace()
        assert get_session_trace("sess-1") == []

    def test_get_trace_nonexistent_session(self):
        assert get_session_trace("nonexistent") == []

    def test_get_trace_panel_nonexistent_session(self):
        panel = get_trace_panel("nonexistent")
        assert panel["session_id"] == "nonexistent"
        assert panel["events"] == 0
