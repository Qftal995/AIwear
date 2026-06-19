import json

from agent.core import init_models
from agent.rag_pipeline import RAGPipeline
from tools.wardrobe_tools import search_wardrobe_tool
from tools.rag_tools import get_fashion_knowledge_tool, get_weather_tool


def _search_wardrobe_for_user(user_id: str, query: str = "", occasion: str = "", style: str = "", wardrobe_store=None) -> str:
    """RAG检索器: 衣橱检索 — 向量语义搜索，按场合/风格/查询匹配最相关的单品"""
    try:
        store = wardrobe_store
        # Build semantic query from occasion + style + user query
        search_query = f"{occasion} {style} {query}".strip()
        if not search_query:
            search_query = query or "穿搭"
        # Use vector semantic search (CLIP 512d)
        items = store.search_similar(query=search_query, user_id=user_id, top_k=15)
        if not items:
            # Fallback to all user items
            items = store.get_user_items(user_id)
        data = [
            {
                "image_id": item["image_id"],
                "oss_url": item["metadata"].get("oss_url", ""),
                "description": item["metadata"].get("description", ""),
                "tags": item["metadata"].get("tags", {}),
                "similarity": round(item.get("similarity", 0), 3),
            }
            for item in items
        ]
        return json.dumps({"success": True, "items": data, "total": len(data), "search_method": "vector_semantic"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _get_fashion_knowledge(occasion: str = "", style: str = "") -> str:
    """RAG检索器: 时尚知识"""
    try:
        result = get_fashion_knowledge_tool.invoke({"occasion": occasion or "", "style": style or ""})
        return str(result)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _get_weather(city: str = "北京") -> str:
    """RAG检索器: 天气"""
    try:
        result = get_weather_tool.invoke({"city": city})
        return str(result)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _get_body_shape_advice(gender: str = "", occasion: str = "") -> str:
    """RAG检索器: 身材分析 — 获取所有身材类型的穿搭策略"""
    try:
        from services.body_shape_service import BodyShapeService
        svc = BodyShapeService()
        shapes_detail = {}
        for shape_name in svc.SHAPE_RULES:
            shapes_detail[shape_name] = svc.SHAPE_RULES[shape_name]
        return json.dumps({
            "available_shapes": svc.list_shapes(),
            "styling_rules": shapes_detail,
            "note": "请参考以上身材穿搭策略，在搭配理由中说明推荐的单品适合哪种身材类型及原因",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _get_preferences(user_profile, user_id: str = "default") -> str:
    """RAG检索器: 用户偏好"""
    try:
        prefs = user_profile.get_preferences(user_id)
        history = user_profile.get_history(user_id, limit=5)
        return json.dumps({"preferences": prefs, "recent_history": history}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


class StylistAgent:
    """搭配推荐助手 — RAG闭环: 检索衣橱+天气+时尚知识+偏好 → 增强prompt → 生成搭配"""
    def __init__(self, llm, user_profile=None, wardrobe_store=None):
        self.llm = llm
        self.user_profile = user_profile
        self.wardrobe_store = wardrobe_store

    def invoke(self, state: dict) -> dict:
        user_id = state.get("user_id", "default")
        msg = state["messages"][-1].content if state.get("messages") else ""
        session_id = state.get("session_id", "")

        stylist_prompt = (
            "你是AIWear搭配推荐助手。严格基于衣橱检索、天气、时尚知识和身材分析信息推荐穿搭。\n\n"
            "输出JSON格式（只返回JSON，不要其他内容）：\n"
            '{\n'
            '  "status": "success|partial|failed",\n'
            '  "confidence": 0.85,\n'
            '  "summary": "一句话总结",\n'
            '  "result": {\n'
            '    "outfits": [\n'
            '      {\n'
            '        "name": "搭配主题名称",\n'
            '        "items": [{"image_id": "来自衣橱", "description": "单品描述", "reason": "选择理由"}],\n'
            '        "suitable_occasion": "适用场合",\n'
            '        "body_shape_note": "身材适配说明",\n'
            '        "weather_note": "天气适配说明"\n'
            '      }\n'
            '    ],\n'
            '    "wardrobe_total": 0,\n'
            '    "wardrobe_used": 0\n'
            '  },\n'
            '  "citations": [{"file": "来源文件", "section": "章节"}],\n'
            '  "warnings": []\n'
            '}\n\n'
            "规则：\n"
            "- items 必须从衣橱检索结果中选取，不可编造\n"
            "- 如果衣橱为空或无合适单品，status=partial，在 warnings 中说明\n"
            "- 如果天气数据为 fallback，在 weather_note 中标注'天气数据暂不可用'\n"
            "- body_shape_note 必须提及身材类型及适配原因\n"
            "- confidence: 衣橱充足+天气准确→0.9, 衣橱不足→0.5-0.7, 无衣橱→0.3\n"
            "- 如果用户之前表达过偏好（如'太素了'），在新推荐中体现\n"
        )

        # Read occasion/style/city from state (extracted by supervisor intent node)
        occasion = state.get("occasion", "")
        style = state.get("style", "")
        city = state.get("city", "北京")
        gender = state.get("gender", "")

        retrievers = [
            ("衣橱检索", lambda: _search_wardrobe_for_user(user_id, msg, occasion, style, self.wardrobe_store)),
            ("时尚知识", lambda: _get_fashion_knowledge(occasion, style)),
            ("天气信息", lambda: _get_weather(city)),
            ("身材分析", lambda: _get_body_shape_advice(gender, occasion)),
        ]
        if self.user_profile:
            retrievers.append(("用户偏好", lambda: _get_preferences(self.user_profile, user_id)))

        pipeline = RAGPipeline(
            llm=self.llm,
            retrievers=retrievers,
            system_prompt=stylist_prompt,
            session_id=session_id,
        )
        result = pipeline.run(msg or "推荐搭配")
        raw_output = result["reply"]

        # Parse structured JSON from LLM; fall back to wrapping raw text
        from agent.core import parse_agent_result
        structured = parse_agent_result(raw_output, "stylist")

        # Augment with wardrobe stats
        try:
            wardrobe_data = json.loads(result["retrieved_contexts"].get("衣橱检索", "{}"))
            structured["result"]["wardrobe_total"] = wardrobe_data.get("total", 0)
            structured["result"]["wardrobe_used"] = len(structured.get("result", {}).get("outfits", []))
        except Exception:
            pass

        from langchain_core.messages import AIMessage
        return {
            "messages": [AIMessage(content=json.dumps(structured, ensure_ascii=False))],
            "rag_trace": {
                "agent": "stylist",
                "retrieved": list(pipeline.retrieved_contexts.keys()),
                "generation_len": len(raw_output),
                "structured": True,
            },
        }


def create_stylist_agent(llm=None, user_profile=None, wardrobe_store=None) -> dict:
    if llm is None:
        llm = init_models()["planner"]
    agent = StylistAgent(llm=llm, user_profile=user_profile, wardrobe_store=wardrobe_store)
    return {"name": "stylist", "agent": agent, "description": "搭配推荐助手（RAG闭环，多轮对话）"}
