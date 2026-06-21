import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver
from agent.core import AgentState, init_models, create_aiwear_agent
from utils.tracing import trace_node_start, trace_step, trace_tool_call, trace_hitl, trace_error, trace_model_call
from utils.token_counter import count_tokens
from mcp_servers.tool_registry import mcp_registry


def create_supervisor(llm, sub_agents: list, mcp_tools=None,
                      knowledge_service=None, mcp_registry=mcp_registry, wardrobe_store=None,
                      user_profile=None):
    """Build the AIWear Supervisor with parallel sub-agent dispatch.

    Architecture
    ------------
    START → intent → planning → tool_exec → dispatch → [HITL] → aggregate → final → END

    dispatch runs sub-agents concurrently where possible:
      Group 1 (parallel): wardrobe + weather + RAG + body_shape
      Group 2: stylist → (handoff) visualizer
      Group 3: copywriter
      Optional: auditor (post-visualizer review)
    """

    agent_map = {}
    for sa in sub_agents:
        name = sa["name"] if isinstance(sa, dict) else sa
        agent_map[name] = sa

    # ═══════════════════════════════════════════════════════════════
    # Node 1: Intent classification
    # ═══════════════════════════════════════════════════════════════
    intent_prompt = (
        "分析用户意图并提取关键信息。返回JSON格式，只返回JSON不要其他内容：\n"
        '{"intent": "...", "gender": "...", "occasion": "...", "city": "...", "style": "..."}\n'
        "intent判定规则（按优先级）：\n"
        "1. 提到'衣橱'/'我的衣服'/'穿'/'搭配'/'推荐穿搭' → styling_advice\n"
        "2. 仅查天气无穿搭需求 → weather_only\n"
        "3. 查衣橱不配穿搭 → wardrobe_query\n"
        "4. 修图/生成图 → image_edit\n"
        "gender: male / female / unknown\n"
        "occasion: 面试/约会/通勤/商务/运动/休闲/其他。'上班'→'通勤'\n"
        "city: 提取城市名如'西安''北京''上海'。无城市则''\n"
        "style: 提取风格词，无则''"
    )

    def _add_step(state: AgentState, name: str, label: str, status: str = "done", duration: float = 0, detail: dict = None):
        steps = state.setdefault("intermediate_steps", [])
        steps.append({"name": name, "label": label, "status": status, "duration": round(duration, 2), "detail": detail or {}})
        return steps

    def _save_default_city(state: AgentState, city_name: str):
        """Persist resolved city to user_profile so it overrides IP geolocation."""
        if not city_name or not user_profile:
            return
        try:
            uid = state.get("user_id", "default")
            user_profile.update_preferences(uid, {"default_city": city_name})
        except Exception:
            pass

    def _contains_any(text: str, keywords: list[str]) -> bool:
        return any(kw in text for kw in keywords)

    def _normalize_intent_with_rules(state: AgentState, query: str):
        """Deterministic intent guardrails for obvious fashion requests.

        LLM intent classification can over-focus on words like "tomorrow" or
        weather context. These guards keep explicit wardrobe/body/styling
        requests from being downgraded to weather_only.
        """
        q = query or ""
        styling_hit = _contains_any(q, [
            "穿搭", "搭配", "来一套", "推荐一套", "怎么穿", "穿什么", "约会", "上班", "通勤",
            "面试", "商务", "从衣橱", "衣橱", "我的衣服", "衣服里", "衣柜",
        ])
        body_hit = _contains_any(q, ["身材", "体型", "体态", "梨形", "苹果型", "沙漏", "H型", "倒三角"])
        wardrobe_hit = _contains_any(q, ["衣橱", "我的衣服", "从衣橱", "衣服里", "衣柜"])
        image_edit_hit = _contains_any(q, ["修图", "改图", "生成图", "换背景", "图片编辑", "试衣图", "效果图"])

        if image_edit_hit:
            state["intent"] = "image_edit"
        elif styling_hit or body_hit:
            state["intent"] = "styling_advice"
        elif wardrobe_hit:
            state["intent"] = "wardrobe_query"

        if body_hit:
            state["body_shape_requested"] = True
        if wardrobe_hit:
            state["wardrobe_requested"] = True
        if styling_hit:
            state["styling_requested"] = True

    def intent_node(state: AgentState) -> AgentState:
        sid = state.get("session_id", "")
        trace_node_start(sid, "intent", {"query": state["messages"][-1].content[:100]})
        t0 = time.time()
        msg = state["messages"][-1].content
        result = llm.invoke([
            {"role": "system", "content": intent_prompt},
            {"role": "user", "content": msg},
        ])
        dt = time.time() - t0
        trace_model_call(sid, "intent-llm", count_tokens(msg), count_tokens(str(result.content)), int(dt * 1000))
        try:
            content = result.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {"intent": "styling_advice", "gender": "unknown", "occasion": "", "city": ""}

        state["intent"] = parsed.get("intent", "styling_advice")
        state["gender"] = parsed.get("gender", "unknown")
        state["occasion"] = parsed.get("occasion") or ""
        # Only overwrite city if user explicitly mentioned one; preserve GPS/checkpoint value
        parsed_city = parsed.get("city") or ""
        if parsed_city:
            state["city"] = parsed_city
        elif "city" not in state or not state.get("city"):
            state["city"] = ""
        state["style"] = parsed.get("style") or ""
        state["original_query"] = msg
        _normalize_intent_with_rules(state, msg)
        # If user mentioned a city, persist it as default
        if parsed.get("city"):
            _save_default_city(state, parsed["city"])
        dt = time.time() - t0
        _add_step(state, "intent", "意图分析", "done", dt, {"intent": state["intent"], "gender": state.get("gender","")})
        trace_step(sid, "intent_done", {"intent": state["intent"], "gender": state["gender"], "city": state["city"]})
        return state

    # ═══════════════════════════════════════════════════════════════
    # Node 2: Planning — city resolution + tool plan
    # ═══════════════════════════════════════════════════════════════
    def planning_node(state: AgentState) -> AgentState:
        sid = state.get("session_id", "")
        trace_node_start(sid, "planning", {"intent": state.get("intent", "")})
        t0 = time.time()
        intent = state.get("intent", "styling_advice")
        gender = state.get("gender", "unknown")
        occasion = state.get("occasion", "")
        city = state.get("city", "")

        # City resolution: GPS > user_preference > IP
        # Once resolved, persist city to user_profile so subsequent visits
        # without GPS won't fall back to inaccurate IP geolocation.
        if not city:
            prefs = state.get("user_preferences", {}) or {}
            lat = state.get("latitude")
            lng = state.get("longitude")

            if lat is not None and lng is not None:
                geo_result = mcp_registry.call_tool("aiwear-geo__reverse_geocode", {"lat": lat, "lng": lng})
                if geo_result.get("success"):
                    geo_city = geo_result.get("result", {}).get("city", "")
                    if geo_city:
                        city = geo_city
                        state["city"] = geo_city
                        state["city_source"] = "gps"
                        # Persist to preferences so IP fallback isn't needed next time
                        _save_default_city(state, geo_city)

            if not city:
                default_city = prefs.get("default_city", "")
                if default_city:
                    city = default_city
                    state["city"] = default_city
                    state["city_source"] = "user_preference"

            if not city:
                client_ip = state.get("client_ip", "")
                geo_result = mcp_registry.call_tool("aiwear-geo__get_geolocation", {"ip": client_ip})
                if geo_result.get("success"):
                    geo_city = geo_result.get("result", {}).get("city", "")
                    if geo_city:
                        city = geo_city
                        state["city"] = geo_city
                        state["city_source"] = "ip_geolocation"

        plan = {
            "intent": intent,
            "gender": gender,
            "occasion": occasion,
            "city": city,
            "style": state.get("style", ""),
            "sub_agents": [],
        }

        # Determine sub-agent dispatch plan and risk level
        risk_level = "low"
        requires_hitl = False
        required_tools = []
        estimated_cost = "low"

        if intent == "styling_advice":
            plan["sub_agents"] = ["wardrobe", "stylist", "copywriter"]
            required_tools = ["weather", "rag_search", "wardrobe_search", "body_shape"]
            risk_level = "low"
            requires_hitl = False
            estimated_cost = "low"
        elif intent == "wardrobe_query":
            plan["sub_agents"] = ["wardrobe"]
            required_tools = ["wardrobe_search"]
            risk_level = "low"
            requires_hitl = False
            estimated_cost = "low"
        elif intent == "image_edit":
            plan["sub_agents"] = ["visualizer"]
            required_tools = []
            risk_level = "high"
            requires_hitl = True
            estimated_cost = "high"
        elif intent == "weather_only":
            plan["sub_agents"] = []  # weather handled by tool_execution
            required_tools = ["weather"]
            risk_level = "low"
            requires_hitl = False
            estimated_cost = "low"

        # Guardrails after planning as well, so downstream nodes follow the
        # user's explicit request even if the LLM intent was too narrow.
        if state.get("styling_requested") or state.get("body_shape_requested"):
            plan["intent"] = "styling_advice"
            state["intent"] = "styling_advice"
            plan["sub_agents"] = ["wardrobe", "stylist", "copywriter"]
            required_tools = ["weather", "rag_search", "wardrobe_search", "body_shape"]
            risk_level = "low"
            requires_hitl = False
            estimated_cost = "low"
        elif state.get("wardrobe_requested"):
            plan["intent"] = "wardrobe_query"
            state["intent"] = "wardrobe_query"
            plan["sub_agents"] = ["wardrobe"]
            required_tools = ["wardrobe_search"]

        plan["required_tools"] = required_tools
        plan["risk_level"] = risk_level
        plan["requires_hitl"] = requires_hitl
        plan["estimated_cost"] = estimated_cost

        state["tool_plan"] = plan
        dt = time.time() - t0
        _add_step(state, "planning", "工具规划", "done", dt, {"city": city, "sub_agents": plan.get("sub_agents", [])})
        trace_step(sid, "planning_done", {"plan": plan})
        return state

    # ═══════════════════════════════════════════════════════════════
    # Node 3: Tool execution — shared infra (weather, RAG, body_shape)
    # ═══════════════════════════════════════════════════════════════
    def tool_execution_node(state: AgentState) -> AgentState:
        sid = state.get("session_id", "")
        t0 = time.time()
        plan = state.get("tool_plan", {})
        intent = plan.get("intent", "")
        tool_results = []
        citations = []

        city = state.get("city", "")
        query = state.get("original_query", "")
        gender = state.get("gender", "")
        occasion = state.get("occasion", "")
        body_shape_requested = any(
            kw in query for kw in ["身材", "体型", "体态", "梨形", "苹果型", "H型", "倒三角", "沙漏"]
        ) or bool(state.get("body_shape_requested"))

        trace_node_start(sid, "tool_execution", {"intent": intent, "city": city})

        # Weather — needed for styling_advice and weather_only
        if intent in ("styling_advice", "weather_only") and city:
            _t0 = time.time()
            try:
                wr = mcp_registry.call_tool("aiwear-weather__get_weather", {"city": city})
                ok = wr.get("success", False)
                src = wr.get("result", {}).get("source", "api") if ok else "api"
                latency_ms = int((time.time() - _t0) * 1000)
                tool_results.append({"tool": "weather", "result": wr, "success": ok, "latencyMs": latency_ms, "source": src})
                trace_tool_call(sid, "weather", {"city": city}, str(wr)[:200], latency_ms)
            except Exception as e:
                latency_ms = int((time.time() - _t0) * 1000)
                tool_results.append({"tool": "weather", "error": str(e), "success": False, "latencyMs": latency_ms, "source": "error"})
                trace_tool_call(sid, "weather", {"city": city}, str(e)[:200], latency_ms)

        # RAG Knowledge — for styling intents
        if intent == "styling_advice":
            _t0 = time.time()
            try:
                if knowledge_service:
                    # Build focused search query from intent attributes.
                    # Raw user messages are too long/noisy for the embedding model.
                    parts = []
                    if occasion and occasion != "其他":
                        parts.append(occasion)
                    style_val = plan.get("style", "")
                    if style_val:
                        parts.append(style_val)
                    if gender and gender != "unknown":
                        parts.append(gender)
                    search_query = " ".join(parts).strip() if parts else query
                    rag_result = knowledge_service.search(query=search_query, gender=gender, occasion=occasion, top_k=5)
                    citations = [
                        {"file": h.get("file", ""), "title": h.get("title", ""),
                         "section": h.get("section", ""), "chunkId": h.get("chunkId", ""),
                         "score": round(h.get("score", 0), 4),
                         "content": h.get("content", "")}
                        for h in rag_result.get("results", [])
                    ]
                    latency_ms = int((time.time() - _t0) * 1000)
                    tool_results.append({"tool": "rag_search", "resultCount": len(citations), "success": True, "latencyMs": latency_ms, "source": "rag_index"})
                    trace_tool_call(sid, "rag_search", {"query": search_query, "gender": gender}, f"{len(citations)} citations", latency_ms)
                else:
                    rr = mcp_registry.call_tool("aiwear-knowledge-rag__search_fashion", {"query": query, "gender": gender})
                    ok = rr.get("success", False)
                    latency_ms = int((time.time() - _t0) * 1000)
                    tool_results.append({"tool": "rag_search", "result": rr, "success": ok, "latencyMs": latency_ms, "source": "mcp"})
                    trace_tool_call(sid, "rag_search", {"query": query, "gender": gender}, str(rr)[:200], latency_ms)
            except Exception as e:
                tool_results.append({"tool": "rag_search", "error": str(e), "success": False, "latencyMs": int((time.time() - _t0) * 1000), "source": "error"})

        # Wardrobe — load items for styling / wardrobe query
        if intent in ("styling_advice", "wardrobe_query") and wardrobe_store is not None:
            _t0 = time.time()
            try:
                items = wardrobe_store.get_user_items(state.get("user_id", "default"))
                latency_ms = int((time.time() - _t0) * 1000)
                tool_results.append({"tool": "wardrobe_search", "result": {"items": items, "total": len(items)}, "success": True, "latencyMs": latency_ms, "source": "wardrobe"})
                trace_tool_call(sid, "wardrobe_search", {"user_id": state.get("user_id", "default")}, f"{len(items)} items", latency_ms)
            except Exception as e:
                tool_results.append({"tool": "wardrobe_search", "error": str(e), "success": False, "latencyMs": int((time.time() - _t0) * 1000), "source": "error"})

        # Body Shape — for styling: prefer image-based analysis if user uploaded a photo
        if intent == "styling_advice":
            image_urls = state.get("image_urls", [])
            if image_urls:
                first_url = image_urls[0] if isinstance(image_urls, list) else image_urls
                _t0 = time.time()
                try:
                    br = mcp_registry.call_tool("aiwear-body-shape__analyze_from_image", {"image_url": first_url})
                    ok = br.get("success", False)
                    if ok:
                        br["_image_analyzed"] = True
                    latency_ms = int((time.time() - _t0) * 1000)
                    tool_results.append({"tool": "body_shape", "result": br, "success": ok, "latencyMs": latency_ms, "source": "api"})
                    trace_tool_call(sid, "body_shape", {"image_url": first_url}, str(br)[:200], latency_ms)
                except Exception as e:
                    tool_results.append({"tool": "body_shape", "error": str(e), "success": False, "latencyMs": int((time.time() - _t0) * 1000), "source": "error"})
            elif gender != "unknown":
                _t0 = time.time()
                try:
                    br = mcp_registry.call_tool("aiwear-body-shape__get_styling_advice", {"shape": ""})
                    ok = br.get("success", False)
                    latency_ms = int((time.time() - _t0) * 1000)
                    tool_results.append({"tool": "body_shape", "result": br, "success": ok, "latencyMs": latency_ms, "source": "mcp"})
                    trace_tool_call(sid, "body_shape", {"shape": ""}, str(br)[:200], latency_ms)
                except Exception as e:
                    tool_results.append({"tool": "body_shape", "error": str(e), "success": False, "latencyMs": int((time.time() - _t0) * 1000), "source": "error"})
            elif body_shape_requested:
                _t0 = time.time()
                try:
                    br = mcp_registry.call_tool("aiwear-body-shape__analyze", {"description": query})
                    ok = br.get("success", False)
                    result_payload = br.get("result", {}) if ok else {}
                    if result_payload.get("shape") == "unknown":
                        advice = mcp_registry.call_tool("aiwear-body-shape__get_styling_advice", {"shape": ""})
                        if advice.get("success"):
                            result_payload["general_advice"] = advice.get("result", {})
                            br["result"] = result_payload
                    latency_ms = int((time.time() - _t0) * 1000)
                    tool_results.append({"tool": "body_shape", "result": br, "success": ok, "latencyMs": latency_ms, "source": "mcp"})
                    trace_tool_call(sid, "body_shape", {"description": query}, str(br)[:200], latency_ms)
                except Exception as e:
                    tool_results.append({"tool": "body_shape", "error": str(e), "success": False, "latencyMs": int((time.time() - _t0) * 1000), "source": "error"})

        state["tool_results"] = tool_results
        state["citations"] = citations
        dt = time.time() - t0
        _add_step(state, "tool_execution", "调用工具", "done", dt, {"tools": [t.get("tool") for t in tool_results], "citations": len(citations)})
        trace_step(sid, "tool_execution_done", {"toolCount": len(tool_results), "citationCount": len(citations)})
        return state

    # ═══════════════════════════════════════════════════════════════
    # Node 4: Dispatch — parallel sub-agent execution with handoff
    # ═══════════════════════════════════════════════════════════════
    def dispatch_node(state: AgentState) -> AgentState:
        sid = state.get("session_id", "")
        t0 = time.time()
        plan = state.get("tool_plan", {})
        sub_names = plan.get("sub_agents", [])
        trace_node_start(sid, "dispatch", {"agents": sub_names})

        all_results = []
        context = _format_tool_context(state.get("tool_results", []), state.get("citations", []))
        # Summarize older conversation turns to manage token budget
        summary = _summarize_history(llm, state.get("messages", []), max_turns=4)
        if summary:
            context = summary + "\n\n" + context

        if not sub_names:
            state["sub_agent_results"] = []
            return state

        # Phase 1 — parallel: wardrobe (data-only, fast)
        parallel_group = [n for n in sub_names if n == "wardrobe"]
        sequential = [n for n in sub_names if n != "wardrobe"]

        if parallel_group:
            with ThreadPoolExecutor(max_workers=len(parallel_group)) as pool:
                futures = {
                    pool.submit(_invoke_sub_agent, name, agent_map.get(name), state, context): name
                    for name in parallel_group
                }
                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        all_results.append(future.result())
                    except Exception as exc:
                        all_results.append({"agent": name, "status": "failed", "confidence": 0.0, "summary": str(exc), "result": {}, "error": str(exc)})

        # Phase 2 — sequential with handoff: stylist → visualizer → copywriter
        for name in sequential:
            if name not in agent_map:
                continue
            try:
                # Inject prior agent results as context
                enriched_ctx = context
                if all_results:
                    enriched_ctx += "\n\n## 上游Agent结果\n" + "\n".join(
                        f"[{r['agent']}] ({r.get('status', 'unknown')}): {r.get('summary', '')[:800]}"
                        for r in all_results
                    )
                result = _invoke_sub_agent(name, agent_map[name], state, enriched_ctx)
                all_results.append(result)

                # Handoff: if stylist produced outfit plan, optionally invoke visualizer
                if name == "stylist" and result.get("status") == "success" and "visualizer" in agent_map:
                    _check_handoff(result, "visualizer", agent_map, state, enriched_ctx, all_results)

            except Exception as exc:
                all_results.append({"agent": name, "status": "failed", "confidence": 0.0, "summary": str(exc), "result": {}, "error": str(exc)})

        state["sub_agent_results"] = all_results

        # Determine if HITL needed
        _check_hitl(state)

        dt = time.time() - t0
        _add_step(state, "dispatch", "调用助手", "done", dt, {"agents": [r.get("agent") for r in all_results]})
        trace_step(sid, "dispatch_done", {"agentCount": len(all_results)})
        return state

    # ═══════════════════════════════════════════════════════════════
    # Node 5: HITL
    # ═══════════════════════════════════════════════════════════════
    def hitl_node(state: AgentState) -> AgentState:
        sid = state.get("session_id", "")
        if state.get("needs_hitl", False):
            hitl = state.get("hitl", {})
            question = hitl.get("question", "请确认是否继续？")
            options = hitl.get("options", ["确认", "修改", "取消"])
            trace_hitl(sid, question, "")
            user_choice = interrupt({
                "type": "hitl",
                "question": question,
                "options": options,
                "intent": state.get("intent", ""),
                "candidates": hitl.get("candidates", []),
            })
            state["user_choice"] = user_choice if isinstance(user_choice, str) else json.dumps(user_choice, ensure_ascii=False)
        return state

    # ═══════════════════════════════════════════════════════════════
    # Node 6: Aggregate
    # ═══════════════════════════════════════════════════════════════
    def aggregate_node(state: AgentState) -> AgentState:
        t0 = time.time()
        results = state.get("sub_agent_results", [])
        tool_results = state.get("tool_results", [])
        citations = state.get("citations", [])
        user_choice = state.get("user_choice", "")

        if not results and not tool_results:
            from langchain_core.messages import AIMessage
            state["messages"] = list(state["messages"]) + [
                AIMessage(content="已分析您的需求，请提供更多信息以获得精准搭配建议。")
            ]
            return state

        succeeded = [r for r in results if r.get("status") == "success"]
        failed = [r for r in results if r.get("status") == "failed"]
        partial = [r for r in results if r.get("status") == "partial"]
        state["aggregated_context"] = {
            "succeeded": succeeded,
            "failed": failed,
            "partial": partial,
            "total": len(results),
            "agent_outputs": {r["agent"]: r.get("summary", "") for r in results},
            "tool_results": tool_results,
            "citations": citations,
            "user_choice": user_choice,
        }
        dt = time.time() - t0
        _add_step(state, "aggregate", "整合结果", "done", dt)
        return state

    # ═══════════════════════════════════════════════════════════════
    # Node 7: Final
    # ═══════════════════════════════════════════════════════════════
    def final_node(state: AgentState) -> AgentState:
        sid = state.get("session_id", "")
        t0 = time.time()
        agg = state.get("aggregated_context", {})
        results = state.get("sub_agent_results", [])
        citations = state.get("citations", [])
        tool_results = state.get("tool_results", [])

        trace_node_start(sid, "final", {"agents": len(results), "tools": len(tool_results)})

        if not results and not tool_results:
            from langchain_core.messages import AIMessage
            state["messages"] = list(state["messages"]) + [
                AIMessage(content=f"已根据您的需求进行分析，请提供更多信息以获得精准搭配建议。")
            ]
            return state

        # Build summary from sub-agent structured outputs
        parts = []
        for r in results:
            name = r.get("agent", "unknown")
            status = r.get("status", "unknown")
            label = {"stylist": "搭配推荐", "wardrobe": "衣橱检索", "visualizer": "效果图生成", "copywriter": "文案撰写", "auditor": "内容审核"}.get(name, name)
            result_data = r.get("result", {})
            output_text = json.dumps(result_data, ensure_ascii=False) if result_data else r.get("summary", "")
            parts.append(f"## {label} [{status}]\n{output_text[:1500]}")

        # Degradation note: name which agents failed
        failed_agents = [r for r in results if r.get("status") == "failed"]
        if failed_agents:
            failed_names = [r.get("agent", "unknown") for r in failed_agents]
            parts.append(f"\n注意：以下助手未能正常完成：{', '.join(failed_names)}。以上建议基于可用部分生成。")

        if tool_results:
            parts.append("## 工具调用\n" + json.dumps([{"tool": t.get("tool"), "success": t.get("success")} for t in tool_results], ensure_ascii=False))

            wardrobe_results = [t for t in tool_results if t.get("tool") == "wardrobe_search" and t.get("success")]
            if wardrobe_results:
                wardrobe_payload = wardrobe_results[-1].get("result", {}) or {}
                wardrobe_items = wardrobe_payload.get("items", []) or []
                wardrobe_summary = {
                    "total": wardrobe_payload.get("total", len(wardrobe_items)),
                    "items": [
                        {
                            "image_id": item.get("image_id", ""),
                            "description": (item.get("metadata", {}) or {}).get("description", ""),
                            "tags": (item.get("metadata", {}) or {}).get("tags", {}),
                            "oss_url": (item.get("metadata", {}) or {}).get("oss_url", ""),
                        }
                        for item in wardrobe_items[:12]
                    ],
                }
                parts.append("## Authoritative Wardrobe Search Result\n" + json.dumps(wardrobe_summary, ensure_ascii=False))

            body_shape_results = [t for t in tool_results if t.get("tool") == "body_shape"]
            if body_shape_results:
                parts.append("## Body Shape MCP Result\n" + json.dumps(body_shape_results, ensure_ascii=False)[:1800])

        final_prompt = (
            "你是AIWear虚拟试衣助手。整合以下子助手的结果和工具调用结果，"
            "生成连贯、专业、有具体建议的搭配回复。\n"
            "要求：\n"
            "1. 如果包含搭配推荐，列出每套搭配的具体单品和理由\n"
            "2. 如果包含效果图，描述图片中的搭配效果\n"
            "3. 如果引用知识库，自然提及参考来源\n"
            "4. 使用自然友好的中文，像专业搭配师一样对话\n"
            "5. 如果用户之前有反馈（如'太素了''换一双'），考虑这些偏好调整建议\n"
            "6. Authoritative Wardrobe Search Result 是衣橱真实检索结果；如果 total > 0，禁止说衣橱为空，必须从其中选择单品并说明图片会在前端预览区展示\n"
            "7. Body Shape MCP Result 是身材分析真实结果；如果存在，必须在回复中明确身材类型、穿搭策略和避坑点"
        )
        combined = "\n".join(parts)
        result = llm.invoke([
            {"role": "system", "content": final_prompt},
            {"role": "user", "content": combined},
        ])
        dt = time.time() - t0
        trace_model_call(sid, "final-llm", count_tokens(combined), count_tokens(str(result.content)), int(dt * 1000))
        from langchain_core.messages import AIMessage
        state["messages"] = list(state["messages"]) + [AIMessage(content=result.content)]
        _add_step(state, "final", "生成回复", "done", dt, {"reply_len": len(result.content)})
        trace_step(sid, "final_done", {"replyLen": len(result.content)})
        return state

    # ═══════════════════════════════════════════════════════════════
    # Build graph
    # ═══════════════════════════════════════════════════════════════
    builder = StateGraph(AgentState)
    builder.add_node("intent", intent_node)
    builder.add_node("planning", planning_node)
    builder.add_node("tool_execution", tool_execution_node)
    builder.add_node("dispatch", dispatch_node)
    builder.add_node("hitl", hitl_node)
    builder.add_node("aggregate", aggregate_node)
    builder.add_node("final", final_node)

    builder.add_edge(START, "intent")
    builder.add_edge("intent", "planning")
    builder.add_edge("planning", "tool_execution")
    builder.add_edge("tool_execution", "dispatch")
    builder.add_edge("dispatch", "hitl")
    builder.add_edge("hitl", "aggregate")
    builder.add_edge("aggregate", "final")
    builder.add_edge("final", END)

    memory = MemorySaver()
    compiled = builder.compile(checkpointer=memory)
    return compiled


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _invoke_sub_agent(name: str, agent_def, state: dict, context: str) -> dict:
    """Invoke a single sub-agent and return a structured AgentResult. Timeout: 25s."""
    from langchain_core.messages import HumanMessage
    from agent.core import parse_agent_result

    sub = agent_def
    agent = sub["agent"] if isinstance(sub, dict) else sub

    # Build sub-agent input message
    user_msg = state.get("original_query", state["messages"][-1].content if state.get("messages") else "")
    sub_input = f"用户请求: {user_msg}\n\n{context}"

    # Prepare state for sub-agent (subset of fields)
    sub_state = {
        "messages": [HumanMessage(content=sub_input)],
        "user_id": state.get("user_id", "default"),
        "session_id": state.get("session_id", ""),
        "city": state.get("city", ""),
        "gender": state.get("gender", ""),
        "occasion": state.get("occasion", ""),
        "style": state.get("style", ""),
        "tool_results": state.get("tool_results", []),
        "citations": state.get("citations", []),
        "sub_agent_results": state.get("sub_agent_results", []),
    }

    def _run():
        sub_result = agent.invoke(sub_state)
        last_msg = sub_result["messages"][-1]
        return last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run)
        try:
            output = future.result(timeout=25)
            return parse_agent_result(output, name)
        except Exception as exc:
            return {
                "agent": name, "status": "failed", "confidence": 0.0,
                "summary": "超时或调用失败", "result": {}, "error": str(exc),
            }


def _check_handoff(result: dict, target: str, agent_map: dict, state: dict, context: str, results: list):
    """Check if stylist output warrants a handoff to visualizer.

    Reliable signals (any one triggers handoff):
    1. User uploaded a person photo AND wardrobe has items (strong signal)
    2. Stylist output contains try-on keywords
    3. User explicitly asked for try-on in original query
    """
    summary = str(result.get("summary", "")).lower()
    result_data = result.get("result", {})
    result_text = json.dumps(result_data, ensure_ascii=False) if result_data else summary
    handoff_keywords = ["生成图", "试穿效果", "效果图", "虚拟试衣", "上身效果", "生成图片"]

    # Strong signal: user provided a photo + wardrobe has items
    has_photo = bool(state.get("image_urls"))
    wardrobe_items = [r for r in state.get("tool_results", []) if r.get("tool") == "wardrobe_search"]
    has_wardrobe = any(w.get("result", {}).get("total", 0) > 0 for w in wardrobe_items)

    # Check if user explicitly asked for try-on
    original_query = (state.get("original_query", "") or "").lower()
    asked_tryon = any(kw in original_query for kw in handoff_keywords)

    should_handoff = (has_photo and has_wardrobe) or asked_tryon or any(kw in summary for kw in handoff_keywords)

    if should_handoff and target in agent_map:
        try:
            handoff_result = _invoke_sub_agent(target, agent_map[target], state, context + f"\n\n## 搭配方案\n{result_text[:1000]}")
            results.append(handoff_result)
        except Exception as exc:
            print(f"[WARN] handoff to visualizer failed: {exc}")


def _check_hitl(state: AgentState):
    """Determine if human confirmation is needed.

    Keep HITL only for high-cost or user-visible generation actions. Plain
    styling advice, wardrobe/RAG/weather lookup, low confidence, and multiple
    outfit candidates should continue without blocking the chat UI.
    """
    intent = state.get("intent", "")

    if intent == "image_edit":
        state["needs_hitl"] = True
        state["hitl"] = {
            "question": "即将生成试穿效果图，是否确认继续？",
            "options": ["确认生成", "修改搭配需求", "取消"],
        }
        return

    state["needs_hitl"] = False
    state["hitl"] = {}

def _summarize_history(llm, messages: list, max_turns: int = 4) -> str:
    """Summarize older conversation turns when context exceeds threshold.

    Keeps the last ``max_turns`` messages intact, compresses older ones
    into a concise summary for token budget (system ~500, history ~2000, tools ~2000).
    """
    if len(messages) <= max_turns * 2:  # user+assistant pairs
        return ""

    from langchain_core.messages import SystemMessage
    older = messages[:-(max_turns * 2)]
    older_text = "\n".join(
        f"{'用户' if i % 2 == 0 else '助手'}: {m.content[:200]}"
        for i, m in enumerate(older)
    )
    prompt = (
        "将以下对话历史压缩为简洁摘要，保留关键信息：用户偏好、选择的单品、否决的方案、场合。"
        f"控制在200字以内。\n\n{older_text}"
    )
    try:
        result = llm.invoke([SystemMessage(content=prompt)])
        return f"[对话历史摘要] {result.content.strip()}"
    except Exception:
        return older_text[:500]


def _format_tool_context(tool_results: list, citations: list) -> str:
    """Format tool results as context for sub-agents."""
    parts = []
    if tool_results:
        parts.append("## 工具调用结果")
        for tr in tool_results:
            status = "成功" if tr.get("success") else "失败"
            result_data = tr.get("result", tr.get("error", ""))
            result_str = json.dumps(result_data, ensure_ascii=False) if isinstance(result_data, (dict, list)) else str(result_data)
            parts.append(f"- [{tr.get('tool', 'unknown')}] ({status}): {result_str[:1200]}")
    if citations:
        parts.append("## 知识库检索结果")
        for i, c in enumerate(citations, 1):
            parts.append(f"{i}. [{c.get('title', '未知')}] {c.get('section', '')}: {c.get('content', '')} (相关度: {c.get('score', 0):.2f})")
    return "\n".join(parts)
