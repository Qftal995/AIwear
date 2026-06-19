"""
Scenario verification for AIWear agent behaviour.

Covers:
  1. MCP tool invocation  — does the agent actually call weather/rag/body_shape?
  2. Multi-turn memory     — do preferences persist across turns in a session?
  3. HITL trigger          — does HITL only fire for visualizer/image_edit?
  4. RAG citation quality  — are citations present and well-formed?

Usage:
  py -3 eval/verify_scenarios.py [--base-url http://127.0.0.1:5001] [--suite all|mcp|memory|hitl|rag]
"""
import json
import os
import sys
import time
import uuid
import argparse
from typing import Optional

import requests


class Verifier:
    def __init__(self, base_url: str = "http://127.0.0.1:5001"):
        self.base_url = base_url.rstrip("/")
        self.results = []

    def _post(self, path: str, body: dict, timeout: int = 90) -> dict:
        url = f"{self.base_url}{path}"
        resp = requests.post(url, json=body, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def _record(self, name: str, passed: bool, detail: str, data: dict = None):
        self.results.append({
            "name": name,
            "passed": passed,
            "detail": detail,
            "data": data or {},
        })
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}: {detail}")

    # ------------------------------------------------------------------
    # 1. MCP tool invocation
    # ------------------------------------------------------------------

    def verify_mcp_tools(self):
        print("\n=== MCP Tool Invocation ===")

        # 1a: Weather tool should be called for weather-related queries
        r = self._post("/api/chat", {
            "message": "明天杭州天气怎么样，适合穿什么？",
            "sessionId": f"vrf_mcp_{uuid.uuid4().hex[:8]}",
        })
        tool_names = [tc.get("tool", "") for tc in r.get("toolCalls", [])]
        has_weather = any("weather" in t for t in tool_names)
        self._record("mcp_weather_called", has_weather,
                     f"tools={tool_names}" if tool_names else "no toolCalls in response",
                     {"toolCalls": r.get("toolCalls", []), "reply": r.get("reply", "")[:200]})

        # 1b: RAG tool should be called for styling knowledge queries
        r = self._post("/api/chat", {
            "message": "我是女生，户外婚礼应该怎么穿搭？",
            "sessionId": f"vrf_mcp_{uuid.uuid4().hex[:8]}",
        })
        tool_names = [tc.get("tool", "") for tc in r.get("toolCalls", [])]
        has_rag = any("rag" in t.lower() for t in tool_names)
        self._record("mcp_rag_called", has_rag,
                     f"tools={tool_names}" if tool_names else "no toolCalls in response",
                     {"toolCalls": r.get("toolCalls", []), "citations": r.get("citations", [])})

        # 1c: Body shape tool should be called when body shape is mentioned
        r = self._post("/api/chat", {
            "message": "我是梨形身材女生，适合什么穿搭？",
            "sessionId": f"vrf_mcp_{uuid.uuid4().hex[:8]}",
        })
        tool_names = [tc.get("tool", "") for tc in r.get("toolCalls", [])]
        has_body = any("body" in t.lower() for t in tool_names)
        # Body shape tool may not always trigger if RAG covers it; log as info
        self._record("mcp_body_shape_called", has_body,
                     f"tools={tool_names}" if tool_names else "no toolCalls in response",
                     {"toolCalls": r.get("toolCalls", [])})

        # 1d: All toolCalls should have success=True (when present)
        all_success = all(
            tc.get("success", True) for tc in r.get("toolCalls", [])
        ) if r.get("toolCalls") else None  # None = no tools called, not a failure
        self._record("mcp_all_success", all_success is not False,
                     "all toolCalls success=True" if all_success else
                     "no toolCalls to check" if all_success is None else
                     "some toolCalls have success=False",
                     {"toolCalls": r.get("toolCalls", [])})

    # ------------------------------------------------------------------
    # 2. Multi-turn memory
    # ------------------------------------------------------------------

    def verify_memory(self):
        print("\n=== Multi-turn Memory ===")
        session_id = f"vrf_mem_{uuid.uuid4().hex[:8]}"

        # Turn 1: Set a preference
        r1 = self._post("/api/chat", {
            "message": "我喜欢简约风格的穿搭，不喜欢太花哨的",
            "sessionId": session_id,
        })
        self._record("mem_turn1_set_preference", r1.get("code") == 200,
                     f"reply={r1.get('reply', '')[:120]}")

        # Turn 2: Ask a follow-up that should reference the preference
        r2 = self._post("/api/chat", {
            "message": "帮我推荐一套明天上班穿的",
            "sessionId": session_id,
        })
        has_pref_memory = any(
            kw in r2.get("reply", "").lower()
            for kw in ["简约", "简洁", "简单", "不花哨", "素", "干净"]
        )
        self._record("mem_turn2_recall_preference", has_pref_memory,
                     f"reply={r2.get('reply', '')[:200]}",
                     {"reply": r2.get("reply", "")})

        # Turn 3: Change preference
        r3 = self._post("/api/chat", {
            "message": "我不喜欢简约风格了，换一套更活泼的",
            "sessionId": session_id,
        })
        self._record("mem_turn3_change_preference", r3.get("code") == 200,
                     f"reply={r3.get('reply', '')[:120]}")

        # Check session stats for multi-turn tracking
        stats = requests.get(
            f"{self.base_url}/api/session-stats?sessionId={session_id}"
        ).json()
        has_stats = stats.get("code") == 200
        self._record("mem_session_stats", has_stats,
                     "session stats available" if has_stats else "no session stats",
                     {"data": stats.get("data", {})})

    # ------------------------------------------------------------------
    # 3. HITL trigger
    # ------------------------------------------------------------------

    def verify_hitl(self):
        print("\n=== HITL Trigger ===")

        # 3a: Normal styling query should NOT trigger HITL
        r1 = self._post("/api/chat", {
            "message": "明天面试穿什么好？男生",
            "sessionId": f"vrf_hitl_{uuid.uuid4().hex[:8]}",
        })
        no_hitl = not r1.get("needsHitl") and r1.get("type") != "hitl"
        self._record("hitl_not_for_styling", no_hitl,
                     f"needsHitl={r1.get('needsHitl')} type={r1.get('type', 'result')}",
                     {"needsHitl": r1.get("needsHitl"), "type": r1.get("type")})

        # 3b: Image generation / visualizer should trigger HITL
        r2 = self._post("/api/chat", {
            "message": "帮我生成一张试穿效果图",
            "sessionId": f"vrf_hitl_{uuid.uuid4().hex[:8]}",
        })
        has_hitl = r2.get("needsHitl") or r2.get("type") == "hitl"
        self._record("hitl_for_visualizer", has_hitl,
                     f"needsHitl={r2.get('needsHitl')} type={r2.get('type', 'result')} "
                     f"hitl={json.dumps(r2.get('hitl', {}), ensure_ascii=False)}",
                     {"needsHitl": r2.get("needsHitl"), "type": r2.get("type"),
                      "hitl": r2.get("hitl")})

        # 3c: If HITL returned, verify it has required fields
        if has_hitl and r2.get("hitl"):
            hitl = r2["hitl"]
            valid_hitl = all(k in hitl for k in ("type", "question", "options", "intent"))
            self._record("hitl_fields_valid", valid_hitl,
                         f"hitl keys={list(hitl.keys())}",
                         {"hitl": hitl})
        else:
            self._record("hitl_fields_valid", None,
                         "HITL not triggered, skipping field check")

        # 3d: Resume endpoint should exist and accept choice
        if has_hitl and r2.get("sessionId"):
            r3 = self._post("/api/chat/resume", {
                "sessionId": r2["sessionId"],
                "choice": r2.get("hitl", {}).get("options", ["确认"])[0],
            })
            resume_ok = r3.get("code") == 200
            self._record("hitl_resume_works", resume_ok,
                         f"resume response code={r3.get('code')}",
                         {"code": r3.get("code"), "reply": r3.get("reply", "")[:120]})
        else:
            self._record("hitl_resume_works", None,
                         "HITL not triggered, skipping resume test")

    # ------------------------------------------------------------------
    # 4. RAG citation quality
    # ------------------------------------------------------------------

    def verify_rag_citations(self):
        print("\n=== RAG Citation Quality ===")

        # 4a: Search with gender filter - check citations present
        r = self._post("/api/rag/search", {
            "query": "户外婚礼女生穿搭",
            "gender": "female",
            "topK": 5,
        })
        data = r.get("data", [])
        has_citations = len(data) > 0
        self._record("rag_search_returns_results", has_citations,
                     f"got {len(data)} results",
                     {"resultCount": len(data)})

        # 4b: Each citation should have flat fields (no nested 'citation' key)
        if data:
            first = data[0]
            flat_fields = all(k in first for k in ("file", "title", "section", "chunkId", "score", "content"))
            has_nested = "citation" in first
            self._record("rag_flat_citation_fields", flat_fields and not has_nested,
                         f"keys={list(first.keys())} has_nested_citation={has_nested}",
                         {"first_result_keys": list(first.keys())})

            # 4c: Score should be reasonable
            scores = [d.get("score", 0) for d in data]
            self._record("rag_scores_present", all(s > 0 for s in scores),
                         f"scores={scores}")

            # 4d: Check that the most relevant content matches the query
            top_file = first.get("file", "")
            top_title = first.get("title", "")
            self._record("rag_top_result_relevant", "婚礼" in top_title or "婚礼" in top_file,
                         f"top file={top_file} title={top_title}")

        # 4e: RAG status endpoint
        status = requests.get(f"{self.base_url}/api/rag/status").json()
        status_ok = status.get("code") == 200 and status.get("data", {}).get("indexed")
        self._record("rag_status_ok", status_ok,
                     f"indexed={status.get('data', {}).get('indexed')} "
                     f"chunks={status.get('data', {}).get('chunks')}")

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def print_summary(self):
        passed = sum(1 for r in self.results if r["passed"] is True)
        failed = sum(1 for r in self.results if r["passed"] is False)
        skipped = sum(1 for r in self.results if r["passed"] is None)
        total = len(self.results)

        print(f"\n{'='*50}")
        print(f"SUMMARY: {passed} passed, {failed} failed, {skipped} skipped ({total} total)")
        if failed:
            print("FAILURES:")
            for r in self.results:
                if r["passed"] is False:
                    print(f"  - {r['name']}: {r['detail']}")
        print(f"{'='*50}")

    def save_json(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        print(f"Results saved to {path}")


def main():
    parser = argparse.ArgumentParser(description="AIWear scenario verification")
    parser.add_argument("--base-url", default="http://127.0.0.1:5001",
                        help="Base URL of the AI service")
    parser.add_argument("--suite", default="all",
                        choices=["all", "mcp", "memory", "hitl", "rag"],
                        help="Test suite to run")
    parser.add_argument("--output", default=None,
                        help="Save results to JSON file")
    args = parser.parse_args()

    v = Verifier(base_url=args.base_url)

    suites = {
        "mcp": v.verify_mcp_tools,
        "memory": v.verify_memory,
        "hitl": v.verify_hitl,
        "rag": v.verify_rag_citations,
    }

    if args.suite == "all":
        for fn in suites.values():
            try:
                fn()
            except Exception as e:
                print(f"  [ERROR] Suite failed: {e}")
    else:
        try:
            suites[args.suite]()
        except Exception as e:
            print(f"  [ERROR] Suite failed: {e}")

    v.print_summary()

    if args.output:
        v.save_json(args.output)

    # Exit code: 0 if all passed, 1 otherwise
    has_failures = any(r["passed"] is False for r in v.results)
    sys.exit(1 if has_failures else 0)


if __name__ == "__main__":
    main()
