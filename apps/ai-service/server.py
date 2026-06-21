import json
import os
import uuid
import time
import base64
import socket
import html

# Force IPv4 — dashscope DNS resolves to IPv6 on this network but IPv6 is unreachable
_orig_getaddrinfo = socket.getaddrinfo
socket._orig_getaddrinfo = _orig_getaddrinfo
def _getaddrinfo_v4(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _getaddrinfo_v4

import requests
from flask import Flask, request, jsonify, Response, stream_with_context
from dotenv import load_dotenv

# Load .env before any agent imports — DashScope SDK reads DASHSCOPE_API_KEY at import time
_app_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_app_dir))
_dotenv_path = os.path.join(_project_root, ".env")
if not os.path.exists(_dotenv_path):
    _dotenv_path = os.path.join(_app_dir, ".env")
load_dotenv(dotenv_path=_dotenv_path, override=True)

from agent.core import init_models, AgentState
from agent.supervisor import create_supervisor
from agent.agents.wardrobe import create_wardrobe_agent
from agent.agents.stylist import create_stylist_agent
from agent.agents.visualizer import create_visualizer_agent
from agent.agents.copywriter import create_copywriter_agent
from tools.image_tools import edit_image_tool, merge_image_tool, image_description_tool, execute_structured_task, _process_image_to_uri
from tools.image_analyzer import analyze_pair, analyze_image
from tools.task_router import route, route_single
from utils.clip_utils import clip_image_to_512d
from utils.tracing import trace_step, trace_tool_call, trace_error, get_session_trace, get_trace_panel
from utils.cost_tracker import CostTracker
from utils.token_counter import count_tokens
from vector_store.faiss_store import FAISSStore
from memory.wardrobe_store import WardrobeStore
from memory.user_profile import UserProfile
from memory.session_memory import SessionMemory, extract_preferences_from_message
from knowledge.knowledge_service import KnowledgeService
from mcp_servers.tool_registry import mcp_registry

# Register in-process MCP servers
from mcp_servers import weather_server, knowledge_rag_server, body_shape_server, geo_ip_server
weather_server.register()
knowledge_rag_server.register()
body_shape_server.register()
geo_ip_server.register()
print(f"MCP: {len(mcp_registry._tools)} tools registered ({len(mcp_registry._servers)} servers)")

app = Flask(__name__)

FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", os.path.join(_project_root, "data", "faiss_index"))

wardrobe_store = WardrobeStore(index_path=FAISS_INDEX_PATH)
user_profile = UserProfile()
session_memory = SessionMemory()
cost_tracker = CostTracker()

models = init_models()

# ── MCP ──────────────────────────────────────────────────────────
_mcp_tools: list = []
_mcp_manager = None
try:
    from utils.mcp_client import MCPClientManager
    _mcp_config = os.path.join(_app_dir, "config", "mcp_servers.json")
    if os.path.exists(_mcp_config):
        _mcp_manager = MCPClientManager(_mcp_config)
        _mcp_manager.connect_all()
        _mcp_tools = _mcp_manager.get_mcp_tools()
        if _mcp_tools:
            print(f"MCP: {len(_mcp_tools)} tools discovered")
        else:
            print("MCP: connected but no tools discovered (servers may not be running)")
    else:
        print("MCP: config not found, skipping")
except ImportError:
    print("MCP: mcp package not installed, skipping")
except Exception as _exc:
    print(f"MCP: init failed ({_exc}), continuing without MCP tools")
# ── RAG Knowledge ────────────────────────────────────────────────
_knowledge_dir = os.getenv("RAG_KNOWLEDGE_DIR", "") or os.path.join(_project_root, "..", "obsidian", "笔记", "AiwearRag知识库")
_knowledge_index = os.path.join(FAISS_INDEX_PATH, "knowledge")
_knowledge_service = KnowledgeService(_knowledge_dir, _knowledge_index)
if _knowledge_service.load_index():
    print(f"RAG: knowledge index loaded ({_knowledge_service.get_stats()['chunks']} chunks)")
else:
    print("RAG: no existing index found, call /api/rag/build to create")
# Merge external MCP tools with in-process registry tools
_mcp_tools.extend(mcp_registry.get_langchain_tools())
print(f"MCP: {len(_mcp_tools)} total tools available for agents")
# ──────────────────────────────────────────────────────────────────

# Each sub-agent gets ONLY its dedicated tool set — no shared mcp_tools pollution
sub_agents = [
    create_wardrobe_agent(llm=models["planner"], vector_store=wardrobe_store),
    create_stylist_agent(llm=models["planner"], user_profile=user_profile, wardrobe_store=wardrobe_store),
    create_visualizer_agent(llm=models["planner"]),
    create_copywriter_agent(llm=models["planner"], user_profile=user_profile),
]

supervisor_graph = create_supervisor(
    llm=models["planner"], sub_agents=sub_agents, mcp_tools=_mcp_tools,
    knowledge_service=_knowledge_service, mcp_registry=mcp_registry,
    wardrobe_store=wardrobe_store,
    user_profile=user_profile,
)

sessions: dict = {}


def _get_field(name: str, default=None):
    body = request.get_json(silent=True) or {}
    if name in body:
        return body[name]
    if name in request.form:
        return request.form[name]
    if name in request.args:
        return request.args[name]
    return default


def _extract_user_id():
    uid = _get_field("userId") or _get_field("user_id")
    if not uid:
        return "default"
    return str(uid)


def _download_image(url: str) -> bytes:
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    return resp.content


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _collect_image_urls_from_obj(obj):
    urls = []
    if isinstance(obj, dict):
        for key in ("url", "imageUrl", "image_url", "previewUrl", "preview_url", "ossUrl", "oss_url", "filePath", "file_path"):
            val = obj.get(key)
            if isinstance(val, str) and (val.startswith("http") or val.startswith("data:image")):
                urls.append(val)
        for val in obj.values():
            urls.extend(_collect_image_urls_from_obj(val))
    elif isinstance(obj, list):
        for item in obj:
            urls.extend(_collect_image_urls_from_obj(item))
    return urls


def _append_unique(seq, value):
    if value and value not in seq:
        seq.append(value)


def _build_image_id_url_map(result):
    id_to_url = {}

    def walk(obj):
        if isinstance(obj, dict):
            image_id = obj.get("image_id") or obj.get("imageId") or obj.get("id")
            metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
            url = (
                obj.get("url") or obj.get("imageUrl") or obj.get("image_url") or
                obj.get("ossUrl") or obj.get("oss_url") or obj.get("filePath") or
                metadata.get("oss_url") or metadata.get("ossUrl") or metadata.get("url")
            )
            if image_id and isinstance(url, str) and url.startswith("http"):
                id_to_url[str(image_id)] = url
            for val in obj.values():
                walk(val)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(result.get("tool_results", []))
    walk(result.get("sub_agent_results", []))
    return id_to_url


def _outfit_preview_data_url(outfit, idx=0):
    name = html.escape(str(outfit.get("name") or f"Outfit {idx + 1}"))
    items = outfit.get("items") or []
    lines = []
    for item in items[:5]:
        if isinstance(item, dict):
            text = item.get("description") or item.get("name") or item.get("image_id") or ""
        else:
            text = str(item)
        if text:
            lines.append(html.escape(text[:26]))
    palette = [
        ("#884BFF", "#12B76A", "#FDF8F2"),
        ("#2563EB", "#F59E0B", "#F7FBFF"),
        ("#7A4A2B", "#EC4899", "#FFF7ED"),
        ("#027A48", "#6941C6", "#F0FDF4"),
    ][idx % 4]
    y = 150
    item_nodes = []
    for line in lines:
        item_nodes.append(f'<text x="40" y="{y}" font-size="22" fill="#332b24">{line}</text>')
        y += 34
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="480" height="640" viewBox="0 0 480 640">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{palette[2]}"/>
      <stop offset="1" stop-color="#ffffff"/>
    </linearGradient>
  </defs>
  <rect width="480" height="640" rx="32" fill="url(#bg)"/>
  <rect x="28" y="28" width="424" height="584" rx="28" fill="none" stroke="#eadfd2" stroke-width="2"/>
  <circle cx="240" cy="116" r="40" fill="none" stroke="{palette[0]}" stroke-width="10"/>
  <path d="M166 298c8-92 34-140 74-140s66 48 74 140l14 172H152l14-172z" fill="{palette[0]}" opacity=".14"/>
  <path d="M166 298c8-92 34-140 74-140s66 48 74 140" fill="none" stroke="{palette[0]}" stroke-width="10" stroke-linecap="round"/>
  <path d="M116 284c38 4 72 26 94 66M364 284c-38 4-72 26-94 66" fill="none" stroke="{palette[1]}" stroke-width="10" stroke-linecap="round"/>
  <text x="40" y="72" font-size="18" fill="#8b7355" font-family="Arial, sans-serif">AIWear Preview</text>
  <text x="40" y="470" font-size="30" font-weight="700" fill="#2b2118" font-family="Arial, sans-serif">{name}</text>
  <g font-family="Arial, sans-serif">{''.join(item_nodes)}</g>
</svg>'''
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def _build_preview_images(result):
    images = []
    id_to_url = _build_image_id_url_map(result)
    for url in _collect_image_urls_from_obj(result.get("sub_agent_results", [])):
        _append_unique(images, url)

    for agent_result in result.get("sub_agent_results", []):
        if agent_result.get("agent") != "stylist":
            continue
        outfits = agent_result.get("result", {}).get("outfits", [])
        for idx, outfit in enumerate(outfits[:3]):
            for item in outfit.get("items", []) or []:
                if not isinstance(item, dict):
                    continue
                image_id = item.get("image_id") or item.get("imageId")
                _append_unique(images, id_to_url.get(str(image_id)))
            _append_unique(images, _outfit_preview_data_url(outfit, idx))
    for url in _collect_image_urls_from_obj(result.get("tool_results", [])):
        _append_unique(images, url)
    return images[:12]


@app.route("/api/validate-image", methods=["POST"])
def validate_image_api():
    # 消费请求体防止连接重置（后续可接入真实 AI 审核）
    _ = request.get_data()
    return jsonify({"code": 200, "allow": True}), 200


def _classify_wardrobe_item_async(user_id: str, image_data: bytes, image_url: str, pos: int):
    """Background task: use vision LLM to classify wardrobe item and update tags."""
    try:
        # Use structured prompt for classification
        classify_prompt = (
            "分析这张服装图片，返回JSON格式（只返回JSON不要其他内容）：\n"
            '{"category": "上衣/裤子/裙子/外套/鞋子/配饰/其他", '
            '"color": "黑/白/蓝/红/绿/灰/棕/粉/黄/紫/其他", '
            '"style": "休闲/正式/运动/街头/简约/复古/甜美/其他", '
            '"season": "春/夏/秋/冬", '
            '"description": "一句话描述（颜色+品类+风格）"}'
        )
        data_uri = _process_image_to_uri(image_data)
        from langchain_core.messages import HumanMessage
        from langchain_community.chat_models import ChatTongyi
        vl_llm = ChatTongyi(model_name="qwen-vl-max", temperature=0.0)
        human_content = [
            {"image": data_uri},
            {"text": classify_prompt},
        ]
        resp = vl_llm.invoke([HumanMessage(content=human_content)])
        raw = resp.content[0]["text"].strip()
        # Parse JSON response
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        tags = json.loads(raw)
        # Update the item in store
        description = tags.get("description", "")
        wardrobe_store.store.update_metadata(pos, {
            "description": description,
            "tags": {
                "category": tags.get("category", ""),
                "color": tags.get("color", ""),
                "style": tags.get("style", ""),
                "season": tags.get("season", ""),
            },
        })
        wardrobe_store.store.save()
    except Exception as e:
        print(f"[classify] failed for user={user_id}: {e}")


@app.route("/api/upload-image", methods=["POST"])
def upload_image_api():
    try:
        user_id = _extract_user_id()

        if "file" in request.files:
            image_data = request.files["file"].read()
            image_url = ""
        else:
            image_url = _get_field("imageUrl") or _get_field("image_url") or _get_field("ossUrl")
            if not image_url:
                return jsonify({"success": False, "error": "缺少图片"}), 400
            image_data = _download_image(image_url)

        if not image_data:
            return jsonify({"success": False, "error": "图片为空"}), 400

        result = wardrobe_store.add_item(
            user_id=user_id,
            image_data=image_data,
            image_url=image_url,
            description="分类中...",
        )

        # Save FAISS index in background thread
        import threading
        threading.Thread(target=wardrobe_store.store.save, daemon=True).start()

        # Classify item in background (vision LLM takes 2-5s)
        pos = wardrobe_store.store._index.ntotal - 1
        threading.Thread(
            target=_classify_wardrobe_item_async,
            args=(user_id, image_data, image_url, pos),
            daemon=True,
        ).start()

        trace_step("", "upload", {"user_id": user_id, "image_id": result["image_id"]})

        return jsonify({
            "success": True,
            "imageId": result["image_id"],
            "description": "分类中...",
            "embeddingDim": 512,
        }), 200
    except Exception as e:
        trace_error("", "upload-image", str(e))
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/wardrobe/classify", methods=["POST"])
def wardrobe_classify_api():
    """Batch re-classify all wardrobe items for a user using vision LLM."""
    user_id = _extract_user_id()
    items = wardrobe_store.get_user_items(user_id)
    if not items:
        return jsonify({"code": 200, "message": "衣橱为空，无需分类", "total": 0}), 200

    import threading

    def classify_all():
        for item in items:
            oss_url = item["metadata"].get("oss_url", "")
            if not oss_url:
                continue
            try:
                image_data = _download_image(oss_url)
                if not image_data:
                    continue
                classify_prompt = (
                    "分析这张服装图片，返回JSON格式（只返回JSON不要其他内容）：\n"
                    '{"category": "上衣/裤子/裙子/外套/鞋子/配饰/其他", '
                    '"color": "黑/白/蓝/红/绿/灰/棕/粉/黄/紫/其他", '
                    '"style": "休闲/正式/运动/街头/简约/复古/甜美/其他", '
                    '"season": "春/夏/秋/冬", '
                    '"description": "一句话描述（颜色+品类+风格）"}'
                )
                data_uri = _process_image_to_uri(image_data)
                from langchain_core.messages import HumanMessage
                from langchain_community.chat_models import ChatTongyi
                vl_llm = ChatTongyi(model_name="qwen-vl-max", temperature=0.0)
                resp = vl_llm.invoke([HumanMessage(content=[
                    {"image": data_uri},
                    {"text": classify_prompt},
                ])])
                raw = resp.content[0]["text"].strip()
                if "```json" in raw:
                    raw = raw.split("```json")[1].split("```")[0].strip()
                elif "```" in raw:
                    raw = raw.split("```")[1].split("```")[0].strip()
                tags = json.loads(raw)
                metadata = {
                    "description": tags.get("description", ""),
                    "tags": {
                        "category": tags.get("category", ""),
                        "color": tags.get("color", ""),
                        "style": tags.get("style", ""),
                        "season": tags.get("season", ""),
                    },
                }
                # Find position in store and update
                for pos, img_id in enumerate(wardrobe_store.store._image_ids):
                    if img_id == item["image_id"]:
                        wardrobe_store.store.update_metadata(pos, metadata)
                        break
            except Exception as e:
                print(f"[classify] failed for {item['image_id']}: {e}")
        wardrobe_store.store.save()

    threading.Thread(target=classify_all, daemon=True).start()
    return jsonify({
        "code": 200,
        "message": "分类任务已启动，衣橱将在1-2分钟内完成智能分类",
        "total": len(items),
    }), 200


@app.route("/api/search-image", methods=["POST"])
def search_image_api():
    try:
        user_id = _extract_user_id()
        query = _get_field("query")
        file_storage = request.files.get("file")

        is_text = query and str(query).strip()
        is_image = file_storage and getattr(file_storage, "filename", "")

        if not is_text and not is_image:
            return jsonify({"code": 400, "message": "query 或 file 至少需要一个", "data": []}), 400

        if is_image:
            image_data = file_storage.read()
            results = wardrobe_store.search_by_image(user_id=user_id, image_data=image_data)
        else:
            filters = {}
            for key in ["category", "color", "style", "season"]:
                val = _get_field(key)
                if val:
                    filters[key] = val
            results = wardrobe_store.search(user_id=user_id, query=str(query), filters=filters or None)

        data = [
            {
                "filePath": r["metadata"].get("oss_url", ""),
                "imageId": r["image_id"],
                "similarity": round(r["similarity"], 4),
                "description": r["metadata"].get("description", ""),
            }
            for r in results
        ]
        return jsonify({"code": 200, "message": "查询成功", "data": data}), 200
    except Exception as e:
        trace_error("", "search-image", str(e))
        return jsonify({"code": 500, "message": str(e), "data": []}), 500


@app.route("/api/chat", methods=["POST"])
def chat_api():
    try:
        user_id = _extract_user_id()
        message = _get_field("message") or _get_field("query") or ""
        session_id = _get_field("sessionId") or _get_field("session_id") or str(uuid.uuid4())
        image_urls = _get_field("imageUrls") or _get_field("image_urls") or _get_field("imageUrl") or []
        if isinstance(image_urls, str):
            try:
                image_urls = json.loads(image_urls)
            except Exception:
                image_urls = [image_urls] if image_urls else []

        if not message:
            return jsonify({"code": 400, "message": "message 不能为空"}), 400

        from langchain_core.messages import HumanMessage, AIMessage

        # Load session context and user preferences
        session_memory.start_session(session_id, user_id)
        history = session_memory.get_context(session_id, max_turns=3)
        prefs = user_profile.get_preferences(user_id)

        # Get client IP for geo-location
        client_ip = (_get_field("clientIp") or _get_field("client_ip") or
                     request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                     request.remote_addr or "")
        latitude = _get_field("latitude")
        longitude = _get_field("longitude")

        # Build state: pass only new message + mutable fields.
        # MemorySaver checkpoint restores: user_id, session_id, user_preferences,
        # wardrobe_context, and prior messages via add_messages reducer.
        # Transient fields (intent, tool_plan, etc.) are cleared so they recompute.
        state = {
            "messages": [HumanMessage(content=message)],
            "user_id": user_id,
            "session_id": session_id,
            "user_preferences": prefs,
            "image_urls": image_urls,
            "client_ip": client_ip,
            "latitude": latitude,
            "longitude": longitude,
            "intents": [],
            "intent": "",
            "tool_plan": {},
            "tool_results": [],
            "sub_agent_results": [],
            "citations": [],
            "needs_hitl": False,
            "hitl": {},
            "paused": False,
            "user_choice": "",
            "intermediate_steps": [],
        }

        config = {"configurable": {"thread_id": session_id}}
        chat_start = time.time()
        cost_tracker.start_session(session_id)

        try:
            # Wrap invoke in a thread so we can enforce a configurable timeout.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
                _future = _pool.submit(supervisor_graph.invoke, state, config)
                try:
                    chat_timeout = float(os.getenv("CHAT_TIMEOUT_SECONDS", "300"))
                    result = _future.result(timeout=chat_timeout)
                except concurrent.futures.TimeoutError:
                    # Collect whatever steps completed so far
                    partial_steps = state.get("intermediate_steps", [])
                    partial_tools = state.get("tool_results", [])
                    return jsonify({
                        "code": 200,
                        "sessionId": session_id,
                        "reply": "搭配分析需要较长时间，已完成的步骤见下方。请稍后重试或简化需求。",
                        "steps": partial_steps,
                        "toolCalls": partial_tools,
                        "timeout": True,
                        "timeoutSeconds": chat_timeout,
                    }), 200

            # Check for HITL interrupt (LangGraph returns __interrupt__ in state
            # instead of raising GraphInterrupt in this version)
            interrupts = result.get("__interrupt__")
            if interrupts:
                # Handle multiple LangGraph interrupt formats:
                # - List of Interrupt objects (LangGraph >= 0.2)
                # - Single Interrupt object
                # - Dict with type/hitl keys (older versions)
                if isinstance(interrupts, list) and interrupts:
                    interrupt_obj = interrupts[0]
                elif isinstance(interrupts, dict):
                    interrupt_obj = interrupts
                else:
                    interrupt_obj = interrupts

                if hasattr(interrupt_obj, "value"):
                    interrupt_data = interrupt_obj.value
                elif isinstance(interrupt_obj, dict):
                    interrupt_data = interrupt_obj
                else:
                    interrupt_data = {"type": "hitl", "question": str(interrupt_obj)}

                sessions[session_id] = {
                    "config": config,
                    "updated_at": time.time(),
                }
                _hitl_sub_results = interrupt_data.get("candidates", []) if isinstance(interrupt_data, dict) else result.get("sub_agent_results", [])
                if not _hitl_sub_results:
                    _hitl_sub_results = result.get("sub_agent_results", [])
                return jsonify({
                    "code": 200,
                    "sessionId": session_id,
                    "type": "hitl",
                    "hitl": interrupt_data,
                    "intent": result.get("intent", ""),
                    "city": result.get("city", ""),
                    "citySource": result.get("city_source", ""),
                    "steps": result.get("intermediate_steps", []),
                    "subResults": _hitl_sub_results,
                    "toolCalls": result.get("tool_results", []),
                    "citations": result.get("citations", []),
                    "images": _build_preview_images(result),
                    "needsHitl": True,
                    "reply": "需要您的确认才能继续",
                }), 200

            last_msg = result["messages"][-1]
            reply = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

            chat_latency = int((time.time() - chat_start) * 1000)
            cost_tracker.record_step(
                session_id=session_id,
                agent_name="supervisor",
                model="deepseek-chat",
                tokens_in=count_tokens(message),
                tokens_out=count_tokens(reply),
                latency_ms=chat_latency,
            )

            # Persist session memory
            session_memory.add_turn(session_id, message, reply)

            # Extract and persist preferences
            feedback = extract_preferences_from_message(message, reply)
            if feedback:
                user_profile.update_preferences(user_id, feedback)

            sessions[session_id] = {
                "state": result,
                "steps": result.get("intermediate_steps", []),
                "tool_results": result.get("tool_results", []),
                "updated_at": time.time(),
            }

            trace_step(session_id, "chat", {"user_id": user_id, "message": message})

            # Parse final message for structured response
            tool_calls = result.get("tool_results", [])
            citations = result.get("citations", [])
            needs_hitl = result.get("needs_hitl", False)

            return jsonify({
                "code": 200,
                "sessionId": session_id,
                "traceId": session_id,
                "reply": reply,
                "intent": result.get("intent", ""),
                "city": result.get("city", ""),
                "citySource": result.get("city_source", ""),
                "latencyMs": chat_latency,
                "steps": result.get("intermediate_steps", []),
                "subResults": result.get("sub_agent_results", []),
                "toolCalls": tool_calls,
                "citations": citations,
                "images": _build_preview_images(result),
                "needsHitl": needs_hitl,
            }), 200
        except Exception as invoke_err:
            from langgraph.errors import GraphInterrupt
            if isinstance(invoke_err, GraphInterrupt):
                interrupt_data = invoke_err.args[0] if invoke_err.args else {"type": "hitl"}
                sessions[session_id] = {
                    "config": config,
                    "updated_at": time.time(),
                }
                _hitl_sub_results = interrupt_data.get("candidates", []) if isinstance(interrupt_data, dict) else []
                return jsonify({
                    "code": 200,
                    "sessionId": session_id,
                    "type": "hitl",
                    "hitl": interrupt_data,
                    "steps": [],
                    "subResults": _hitl_sub_results,
                    "toolCalls": [],
                    "citations": [],
                    "images": _build_preview_images({"sub_agent_results": _hitl_sub_results}),
                    "needsHitl": True,
                    "reply": "需要您的确认才能继续",
                }), 200
            raise
    except Exception as e:
        trace_error("", "chat", str(e))
        return jsonify({"code": 500, "message": str(e)}), 500


@app.route("/api/chat/resume", methods=["POST"])
def chat_resume_api():
    try:
        session_id = _get_field("sessionId") or _get_field("session_id") or ""
        user_choice = _get_field("choice") or _get_field("userChoice") or "确认继续"

        if not session_id:
            return jsonify({"code": 400, "message": "sessionId 不能为空"}), 400

        session = sessions.get(session_id)
        if not session:
            return jsonify({"code": 404, "message": "session not found"}), 404

        config = session.get("config", {"configurable": {"thread_id": session_id}})

        from langgraph.types import Command

        resume_start = time.time()
        result = supervisor_graph.invoke(Command(resume=user_choice), config)
        last_msg = result["messages"][-1]
        reply = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        resume_latency = int((time.time() - resume_start) * 1000)
        cost_tracker.record_step(
            session_id=session_id,
            agent_name="supervisor",
            model="deepseek-chat",
            tokens_in=50,
            tokens_out=count_tokens(reply),
            latency_ms=resume_latency,
        )

        sessions[session_id] = {
            "state": result,
            "config": config,
            "steps": result.get("intermediate_steps", []),
            "tool_results": result.get("tool_results", []),
            "updated_at": time.time(),
        }

        return jsonify({
            "code": 200,
            "sessionId": session_id,
            "reply": reply,
            "type": "result",
            "userChoice": user_choice,
            "intent": result.get("intent", ""),
            "city": result.get("city", ""),
            "citySource": result.get("city_source", ""),
            "steps": result.get("intermediate_steps", []),
            "subResults": result.get("sub_agent_results", []),
            "toolCalls": result.get("tool_results", []),
            "citations": result.get("citations", []),
            "images": _build_preview_images(result),
            "needsHitl": result.get("needs_hitl", False),
        }), 200
    except Exception as e:
        trace_error("", "chat-resume", str(e))
        return jsonify({"code": 500, "message": str(e)}), 500


@app.route("/api/chat/stream", methods=["GET"])
def chat_stream_api():
    user_id = request.args.get("userId") or request.args.get("user_id") or "default"
    message = request.args.get("message") or request.args.get("query") or ""
    session_id = request.args.get("sessionId") or str(uuid.uuid4())

    if not message:
        return Response("data: {\"error\":\"message required\"}\n\n", mimetype="text/event-stream")

    def generate():
        from langchain_core.messages import HumanMessage

        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or ""
        state = {
            "messages": [HumanMessage(content=message)],
            "user_id": user_id,
            "wardrobe_context": {},
            "session_id": session_id,
            "intermediate_steps": [],
            "client_ip": client_ip,
        }

        cost_tracker.start_session(session_id)
        config = {"configurable": {"thread_id": session_id}}
        stream_start = time.time()

        try:
            # astream_events is async — bridge to sync via thread+queue
            import queue
            import asyncio
            import threading

            event_queue = queue.Queue()

            def _run_async_stream():
                async def _collect():
                    try:
                        async for event in supervisor_graph.astream_events(state, config, version="v2"):
                            event_queue.put(event)
                    except Exception as exc:
                        event_queue.put({"__error__": str(exc)})
                    finally:
                        event_queue.put(None)  # sentinel
                asyncio.run(_collect())

            t = threading.Thread(target=_run_async_stream, daemon=True)
            t.start()

            node_labels = {
                "intent": "意图分析",
                "planning": "工具规划",
                "tool_execution": "调用工具",
                "route": "调用助手",
                "hitl": "HITL 确认",
                "aggregate": "整合结果",
                "final": "生成回复",
            }
            emitted_nodes = set()

            while True:
                event = event_queue.get()
                if event is None:
                    break
                if isinstance(event, dict) and "__error__" in event:
                    yield f"data: {json.dumps({'type': 'error', 'error': event['__error__']}, ensure_ascii=False)}\n\n"
                    break

                kind = event.get("event", "")
                name = event.get("name", "")

                if kind == "on_chain_start" and name in node_labels:
                    if name not in emitted_nodes:
                        yield f"data: {json.dumps({'type': 'node', 'node': name, 'label': node_labels[name], 'status': 'running'}, ensure_ascii=False)}\n\n"
                        emitted_nodes.add(name)

                elif kind == "on_chain_end" and name in node_labels:
                    yield f"data: {json.dumps({'type': 'node', 'node': name, 'label': node_labels[name], 'status': 'done'}, ensure_ascii=False)}\n\n"

                elif kind == "on_chat_model_start":
                    yield f"data: {json.dumps({'type': 'llm_call', 'status': 'running', 'node': event.get('metadata', {}).get('langgraph_node', '')}, ensure_ascii=False)}\n\n"

                elif kind == "on_chat_model_end":
                    yield f"data: {json.dumps({'type': 'llm_call', 'status': 'done'}, ensure_ascii=False)}\n\n"

                elif kind == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    yield f"data: {json.dumps({'type': 'tool', 'tool': tool_name, 'status': 'running'}, ensure_ascii=False)}\n\n"

                elif kind == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    yield f"data: {json.dumps({'type': 'tool', 'tool': tool_name, 'status': 'done'}, ensure_ascii=False)}\n\n"

            # Get final state from checkpointer
            final_state = supervisor_graph.get_state(config)
            if final_state and final_state.values:
                result = final_state.values
                # Check for HITL interrupt in final state
                interrupts = result.get("__interrupt__")
                if interrupts:
                    if isinstance(interrupts, list) and interrupts:
                        interrupt_obj = interrupts[0]
                    elif isinstance(interrupts, dict):
                        interrupt_obj = interrupts
                    else:
                        interrupt_obj = interrupts
                    if hasattr(interrupt_obj, "value"):
                        interrupt_data = interrupt_obj.value
                    elif isinstance(interrupt_obj, dict):
                        interrupt_data = interrupt_obj
                    else:
                        interrupt_data = {"type": "hitl", "question": str(interrupt_obj)}
                    sessions[session_id] = {"config": config, "updated_at": time.time()}
                    yield f"data: {json.dumps({'type': 'hitl', 'sessionId': session_id, 'hitl': interrupt_data, 'reply': '需要您的确认才能继续'}, ensure_ascii=False)}\n\n"
                else:
                    last_msg = result.get("messages", [None])[-1] if result.get("messages") else None
                    reply = last_msg.content if last_msg and hasattr(last_msg, "content") else ""
                    stream_latency = int((time.time() - stream_start) * 1000)
                    cost_tracker.record_step(
                        session_id=session_id,
                        agent_name="supervisor",
                        model="deepseek-chat",
                        tokens_in=count_tokens(message),
                        tokens_out=count_tokens(reply),
                        latency_ms=stream_latency,
                    )
                    yield f"data: {json.dumps({'type': 'result', 'reply': reply, 'sessionId': session_id, 'traceId': session_id, 'steps': result.get('intermediate_steps', []), 'subResults': result.get('sub_agent_results', []), 'toolCalls': result.get('tool_results', []), 'citations': result.get('citations', []), 'needsHitl': result.get('needs_hitl', False)}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'result', 'reply': '处理完成', 'sessionId': session_id}, ensure_ascii=False)}\n\n"

        except Exception as e:
            from langgraph.errors import GraphInterrupt
            if isinstance(e, GraphInterrupt):
                interrupt_data = e.args[0] if e.args else {"type": "hitl"}
                sessions[session_id] = {"config": config, "updated_at": time.time()}
                yield f"data: {json.dumps({'type': 'hitl', 'sessionId': session_id, 'hitl': interrupt_data, 'reply': '需要您的确认才能继续'}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e), 'sessionId': session_id}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/api/session-stats", methods=["GET"])
def session_stats_api():
    session_id = request.args.get("sessionId", "")
    if session_id:
        stats = cost_tracker.get_session_stats(session_id)
        # Merge intermediate_steps from saved session state (agent flow)
        sess = sessions.get(session_id, {})
        flow_steps = sess.get("steps", [])
        if flow_steps:
            stats["flow_steps"] = flow_steps
        flow_tool_results = sess.get("tool_results", [])
        if flow_tool_results:
            stats["flow_tool_results"] = flow_tool_results
    else:
        stats = cost_tracker.get_global_stats()
    return jsonify({"code": 200, "data": stats}), 200


@app.route("/api/wardrobe/<user_id>", methods=["GET"])
def wardrobe_list_api(user_id):
    try:
        items = wardrobe_store.get_user_items(user_id)
        data = [
            {
                "imageId": item["image_id"],
                "ossUrl": item["metadata"].get("oss_url", ""),
                "description": item["metadata"].get("description", ""),
                "tags": item["metadata"].get("tags", {}),
                "uploadTime": item["metadata"].get("created_at", ""),
            }
            for item in items
        ]
        return jsonify({"code": 200, "data": data, "total": len(data)}), 200
    except Exception as e:
        trace_error("", "wardrobe-list", str(e))
        return jsonify({"code": 500, "message": str(e), "data": []}), 500


@app.route("/api/wardrobe/<image_id>", methods=["DELETE"])
def wardrobe_delete_api(image_id):
    try:
        wardrobe_store.delete_item(image_id)
        wardrobe_store.store.save()
        return jsonify({"code": 200, "message": "删除成功"}), 200
    except Exception as e:
        trace_error("", "wardrobe-delete", str(e))
        return jsonify({"code": 500, "message": str(e)}), 500


@app.route("/api/wardrobe", methods=["DELETE"])
def wardrobe_delete_by_url_api():
    """Delete by oss_url query param — used by Java when deleting from my-images."""
    url = request.args.get("url", "")
    if not url:
        return jsonify({"code": 400, "message": "url required"}), 400
    try:
        store = wardrobe_store.store
        with store._lock:
            for idx, mid in enumerate(store._image_ids):
                if mid is None or idx in store._deleted:
                    continue
                meta = store._metadata[idx]
                if meta and meta.get("oss_url") == url:
                    store._image_ids[idx] = None
                    store._metadata[idx] = None
                    store._deleted.add(idx)
                    store.save()
                    return jsonify({"code": 200, "message": "删除成功"}), 200
        return jsonify({"code": 404, "message": "未找到对应图片"}), 404
    except Exception as e:
        trace_error("", "wardrobe-delete-by-url", str(e))
        return jsonify({"code": 500, "message": str(e)}), 500


@app.route("/api/tool/image", methods=["POST"])
def tool_image_api():
    try:
        instruction = request.form.get("instruction", "")
        if not instruction:
            return jsonify({"success": False, "error": "instruction required"}), 400

        if "file1" in request.files and "file2" in request.files:
            data1 = request.files["file1"].read()
            data2 = request.files["file2"].read()
            url1 = request.form.get("image_url1", "")
            url2 = request.form.get("image_url2", "")
            analysis = analyze_pair(data1, data2)
            task = route(analysis, instruction)
            result = execute_structured_task(task)
            result_json = json.dumps(result, ensure_ascii=False)
        elif "file" in request.files:
            data = request.files["file"].read()
            analysis = analyze_image(data)
            task = route_single(analysis, instruction)
            result = execute_structured_task(task)
            result_json = json.dumps(result, ensure_ascii=False)
        else:
            return jsonify({"success": False, "error": "file required"}), 400

        result = json.loads(result_json) if isinstance(result_json, str) else result_json
        if not result.get("success"):
            app.logger.error("tool-image failed: %s", result.get("error", "unknown"))
        return jsonify(result), 200
    except Exception as e:
        trace_error("", "tool-image", str(e))
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tool/image/async", methods=["POST"])
def tool_image_async_api():
    """异步图片任务 — 提交到 RabbitMQ，立即返回 task_id"""
    try:
        instruction = request.form.get("instruction", "")
        if not instruction:
            return jsonify({"success": False, "error": "instruction required"}), 400

        from utils.mq import get_publisher

        if "file1" in request.files and "file2" in request.files:
            data1 = request.files["file1"].read()
            data2 = request.files["file2"].read()
            url1 = request.form.get("image_url1", "")
            url2 = request.form.get("image_url2", "")
            payload = {
                "instruction": instruction,
                "image_url1": url1 or None,
                "image_url2": url2 or None,
                "image_data1_b64": base64.b64encode(data1).decode("utf-8") if not url1 else None,
                "image_data2_b64": base64.b64encode(data2).decode("utf-8") if not url2 else None,
            }
            task_id = get_publisher().publish("merge", payload)
        elif "file" in request.files:
            data = request.files["file"].read()
            url = request.form.get("image_url", "")
            payload = {
                "instruction": instruction,
                "image_url": url or None,
                "image_data_b64": base64.b64encode(data).decode("utf-8") if not url else None,
            }
            task_id = get_publisher().publish("edit", payload)
        else:
            return jsonify({"success": False, "error": "file required"}), 400

        return jsonify({"success": True, "task_id": task_id, "status": "queued"}), 202
    except Exception as e:
        trace_error("", "tool-image-async", str(e))
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tool/image/status/<task_id>", methods=["GET"])
def tool_image_status_api(task_id):
    """查询异步图片任务状态"""
    try:
        from utils.mq import get_task_status
        status = get_task_status(task_id)
        return jsonify({"code": 200, "data": status}), 200
    except Exception as e:
        return jsonify({"code": 500, "message": str(e)}), 500


# ── MCP endpoints ─────────────────────────────────────────────────

@app.route("/api/mcp/status", methods=["GET"])
def mcp_status():
    try:
        # Load server descriptions from config
        cfg_descriptions = {}
        try:
            with open(_mcp_config, "r") as _f:
                _cfg = json.load(_f)
            for sn, sc in _cfg.get("servers", {}).items():
                cfg_descriptions[sn] = {
                    "description": sc.get("description", ""),
                    "transport": sc.get("transport", "in-process"),
                }
        except Exception:
            _cfg = {"servers": {}}

        status_list = []
        # In-process servers (always core, not optional)
        for s in mcp_registry._servers.values():
            cfg = cfg_descriptions.get(s.name, {})
            status_list.append({
                "name": s.name,
                "type": "in-process",
                "status": "connected" if s.connected else "disconnected",
                "transport": s.transport,
                "description": getattr(s, "description", "") or cfg.get("description", ""),
                "toolCount": s.tool_count,
                "optional": False,
                "error": s.error if not s.connected else "",
            })
        # External MCP servers from config (optional if required=false)
        if _mcp_manager:
            ext_names = {st["name"] for st in status_list}
            for sn, sc in _cfg.get("servers", {}).items():
                if sn in ext_names:
                    continue
                is_required = sc.get("required", True)
                connected = _mcp_manager.is_connected(sn)
                status_list.append({
                    "name": sn,
                    "type": "external",
                    "status": "connected" if connected else "disconnected",
                    "transport": sc.get("transport", "stdio"),
                    "description": sc.get("description", ""),
                    "toolCount": 0,
                    "optional": not is_required,
                    "error": "" if connected else ("unreachable（开发辅助能力，不影响核心功能）" if not is_required else "unreachable"),
                })
        return jsonify({"code": 200, "data": status_list}), 200
    except Exception as e:
        return jsonify({"code": 500, "message": str(e)}), 500


@app.route("/api/mcp/tools", methods=["GET"])
def mcp_tools():
    try:
        server = request.args.get("server")
        tools = mcp_registry.get_tools(server=server)
        return jsonify({"code": 200, "data": tools}), 200
    except Exception as e:
        return jsonify({"code": 500, "message": str(e)}), 500


@app.route("/api/mcp/test-call", methods=["POST"])
def mcp_test_call():
    body = request.get_json(silent=True) or {}
    tool_name = body.get("tool", "")
    args = body.get("args", {})
    if not tool_name:
        return jsonify({"code": 400, "message": "tool is required"}), 400
    try:
        result = mcp_registry.call_tool(tool_name, args)
        return jsonify({"code": 200, "data": result}), 200
    except Exception as e:
        return jsonify({"code": 500, "message": str(e)}), 500


# ── RAG endpoints ─────────────────────────────────────────────────

@app.route("/api/rag/search", methods=["POST"])
def rag_search():
    body = request.get_json(silent=True) or {}
    query = body.get("query", "").strip()
    if not query:
        return jsonify({"code": 400, "message": "query is required"}), 400

    gender = body.get("gender")
    occasion = body.get("occasion")
    season = body.get("season")
    category = body.get("category")
    top_k = min(int(body.get("topK", 5)), 20)

    try:
        result = _knowledge_service.search(
            query=query,
            gender=gender,
            occasion=occasion,
            season=season,
            category=category,
            top_k=top_k,
        )
        return jsonify({
            "code": 200,
            "data": {
                "results": result["results"],
                "query": result.get("query", query),
                "rewrittenQuery": result.get("rewritten_query", ""),
                "filters": result.get("filters", {}),
                "topK": result.get("top_k", top_k),
                "totalHits": result.get("total_hits", 0),
                "latencyMs": result.get("latency_ms", 0),
            },
        }), 200
    except Exception as e:
        return jsonify({"code": 500, "message": str(e)}), 500


@app.route("/api/rag/status", methods=["GET"])
def rag_status():
    try:
        stats = _knowledge_service.get_stats()
        return jsonify({"code": 200, "data": stats}), 200
    except Exception as e:
        return jsonify({"code": 500, "message": str(e)}), 500


@app.route("/api/rag/build", methods=["POST"])
def rag_build():
    try:
        n = _knowledge_service.build_index()
        return jsonify({"code": 200, "data": {"chunks_indexed": n}}), 200
    except Exception as e:
        return jsonify({"code": 500, "message": str(e)}), 500


# ── Trace endpoints ──────────────────────────────────────────────

@app.route("/api/traces/<session_id>", methods=["GET"])
def traces_api(session_id):
    try:
        events = get_session_trace(session_id)
        panel = get_trace_panel(session_id)
        # Prefer steps from saved session state, fall back to trace-derived steps
        sess = sessions.get(session_id, {})
        steps = sess.get("steps", []) or panel.get("steps", [])
        tool_calls = [
            e for e in events
            if e.get("type") in ("tool_call", "mcp_call", "rag", "rag_retrieve")
        ]
        model_calls = [e for e in events if e.get("type") == "llm_call"]
        return jsonify({
            "code": 200,
            "data": {
                "sessionId": session_id,
                "events": events,
                "steps": steps,
                "toolCalls": tool_calls,
                "modelCalls": model_calls,
                "timeline": events,
                "summary": {
                    "totalEvents": panel.get("events", len(events)),
                    "toolCalls": len(tool_calls),
                    "modelCalls": len(model_calls),
                    "errors": panel.get("errors", 0),
                    "totalTokensIn": panel.get("total_tokens_in", 0),
                    "totalTokensOut": panel.get("total_tokens_out", 0),
                    "totalLatencyMs": panel.get("total_latency_ms", 0),
                },
            },
        }), 200
    except Exception as e:
        return jsonify({"code": 500, "message": str(e)}), 500


@app.route("/api/traces", methods=["GET"])
def traces_list_api():
    try:
        panel = get_trace_panel()
        return jsonify({"code": 200, "data": panel}), 200
    except Exception as e:
        return jsonify({"code": 500, "message": str(e)}), 500


@app.route("/api/health", methods=["GET"])
def health_api():
    return jsonify({"status": "ok", "build": "codex-agent-fullchain-20260621"}), 200


if __name__ == "__main__":
    os.makedirs(FAISS_INDEX_PATH, exist_ok=True)
    print("AIWear 2.0 服务启动")
    port = int(os.getenv("PORT", os.getenv("FLASK_PORT", "5001")))
    app.run(debug=False, host="0.0.0.0", port=port, threaded=True)
