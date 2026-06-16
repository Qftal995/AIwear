import json
import os
import uuid
import time

import requests
from flask import Flask, request, jsonify, Response, stream_with_context
from dotenv import load_dotenv

from agent.core import init_models, AgentState
from agent.supervisor import create_supervisor
from agent.agents.wardrobe import create_wardrobe_agent
from agent.agents.stylist import create_stylist_agent
from agent.agents.visualizer import create_visualizer_agent
from agent.agents.auditor import create_auditor_agent
from agent.agents.copywriter import create_copywriter_agent
from tools.image_tools import edit_image_tool, merge_image_tool, image_description_tool
from utils.clip_utils import clip_image_to_512d
from utils.tracing import trace_step, trace_tool_call, trace_error
from vector_store.faiss_store import FAISSStore
from memory.wardrobe_store import WardrobeStore
from memory.user_profile import UserProfile

app = Flask(__name__)

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(dotenv_path=os.path.join(_project_root, ".env"))

FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", os.path.join(_project_root, "data", "faiss_index"))

wardrobe_store = WardrobeStore(index_path=FAISS_INDEX_PATH)
user_profile = UserProfile()

models = init_models()

sub_agents = [
    create_wardrobe_agent(llm=models["planner"], vector_store=wardrobe_store),
    create_stylist_agent(llm=models["planner"]),
    create_visualizer_agent(llm=models["planner"]),
    create_auditor_agent(llm=models["planner"]),
    create_copywriter_agent(llm=models["planner"]),
]

supervisor_graph = create_supervisor(llm=models["planner"], sub_agents=sub_agents)

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


@app.route("/api/validate-image", methods=["POST"])
def validate_image_api():
    return jsonify({"code": 200, "allow": True}), 200


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

        description = image_description_tool.invoke({"image_data": image_data})
        if isinstance(description, str) and not description.startswith("{"):
            description = description
        else:
            description = ""

        result = wardrobe_store.add_item(
            user_id=user_id,
            image_data=image_data,
            image_url=image_url,
            description=description,
        )

        wardrobe_store.store.save()
        trace_step("", "upload", {"user_id": user_id, "image_id": result["image_id"]})

        return jsonify({
            "success": True,
            "imageId": result["image_id"],
            "description": description,
            "embeddingDim": 512,
        }), 200
    except Exception as e:
        trace_error("", "upload-image", str(e))
        return jsonify({"success": False, "error": str(e)}), 500


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

        if not message:
            return jsonify({"code": 400, "message": "message 不能为空"}), 400

        from langchain_core.messages import HumanMessage

        state = {
            "messages": [HumanMessage(content=message)],
            "user_id": user_id,
            "wardrobe_context": {},
            "session_id": session_id,
            "intermediate_steps": [],
        }

        result = supervisor_graph.invoke(state)
        last_msg = result["messages"][-1]
        reply = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        sessions[session_id] = {
            "state": result,
            "updated_at": time.time(),
        }

        trace_step(session_id, "chat", {"user_id": user_id, "message": message})

        return jsonify({
            "code": 200,
            "sessionId": session_id,
            "reply": reply,
            "steps": result.get("intermediate_steps", []),
            "subResults": result.get("sub_agent_results", []),
        }), 200
    except Exception as e:
        trace_error("", "chat", str(e))
        return jsonify({"code": 500, "message": str(e)}), 500


@app.route("/api/chat/stream", methods=["GET"])
def chat_stream_api():
    user_id = request.args.get("userId") or request.args.get("user_id") or "default"
    message = request.args.get("message") or request.args.get("query") or ""
    session_id = request.args.get("sessionId") or str(uuid.uuid4())

    if not message:
        return Response("data: {\"error\":\"message required\"}\n\n", mimetype="text/event-stream")

    def generate():
        steps = [
            {"name": "wardrobe", "label": "衣橱检索"},
            {"name": "stylist", "label": "搭配推荐"},
            {"name": "visualizer", "label": "图片生成"},
            {"name": "auditor", "label": "安全审核"},
            {"name": "copywriter", "label": "文案生成"},
        ]

        from langchain_core.messages import HumanMessage

        state = {
            "messages": [HumanMessage(content=message)],
            "user_id": user_id,
            "wardrobe_context": {},
            "session_id": session_id,
            "intermediate_steps": [],
        }

        for i, step in enumerate(steps):
            yield f"data: {json.dumps({'step': step['name'], 'label': step['label'], 'status': 'running', 'progress': round((i) / len(steps) * 100)}, ensure_ascii=False)}\n\n"

        try:
            result = supervisor_graph.invoke(state)
            for i, step in enumerate(steps):
                yield f"data: {json.dumps({'step': step['name'], 'label': step['label'], 'status': 'done', 'progress': round((i + 1) / len(steps) * 100)}, ensure_ascii=False)}\n\n"

            last_msg = result["messages"][-1]
            reply = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
            yield f"data: {json.dumps({'type': 'result', 'reply': reply, 'steps': result.get('intermediate_steps', [])}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"

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
            }
            for item in items
        ]
        return jsonify({"code": 200, "data": data, "total": len(data)}), 200
    except Exception as e:
        trace_error("", "wardrobe-list", str(e))
        return jsonify({"code": 500, "message": str(e), "data": []}), 500


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
            result_json = merge_image_tool.invoke({
                "instruction": instruction,
                "image_data1": data1,
                "image_data2": data2,
                "image_url1": url1 or None,
                "image_url2": url2 or None,
            })
        elif "file" in request.files:
            data = request.files["file"].read()
            result_json = edit_image_tool.invoke({
                "instruction": instruction,
                "image_data": data,
            })
        else:
            return jsonify({"success": False, "error": "file required"}), 400

        result = json.loads(result_json) if isinstance(result_json, str) else result_json
        return jsonify(result), 200
    except Exception as e:
        trace_error("", "tool-image", str(e))
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    os.makedirs(FAISS_INDEX_PATH, exist_ok=True)
    print("AIWear 2.0 服务启动")
    app.run(debug=True, host="0.0.0.0", port=5000)
