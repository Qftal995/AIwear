import json

from agent.core import init_models
from agent.rag_pipeline import RAGPipeline
from tools.rag_tools import get_fashion_knowledge_tool


def _get_fashion_knowledge(occasion: str = "", style: str = "") -> str:
    """RAG检索器: 时尚知识"""
    try:
        result = get_fashion_knowledge_tool.invoke({"occasion": occasion or "", "style": style or ""})
        return str(result)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _get_user_preferences(user_profile, user_id: str = "default") -> str:
    """RAG检索器: 用户偏好"""
    try:
        prefs = user_profile.get_preferences(user_id)
        return json.dumps({"preferences": prefs}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


class CopywriterAgent:
    """时尚文案助手 — RAG闭环: 检索时尚知识+用户偏好 → 增强prompt → 生成文案"""
    def __init__(self, llm, user_profile=None):
        self.llm = llm
        self.user_profile = user_profile

    def invoke(self, state: dict) -> dict:
        user_id = state.get("user_id", "default")
        msg = state["messages"][-1].content if state.get("messages") else ""
        session_id = state.get("session_id", "")

        # 从上游搭配结果中提取上下文
        sub_results = state.get("sub_agent_results", [])
        styling_context = ""
        for r in sub_results:
            if r.get("agent") == "stylist":
                styling_context = str(r.get("output", ""))[:500]
                break

        copywriter_prompt = (
            "你是AIWear时尚文案撰写助手。基于检索到的时尚知识和上游搭配方案，撰写简洁优雅的描述文案。\n\n"
            "输出JSON格式（只返回JSON不要其他内容）：\n"
            '{\n'
            '  "status": "success|partial|failed",\n'
            '  "confidence": 0.9,\n'
            '  "summary": "一句话总结文案内容",\n'
            '  "result": {\n'
            '    "title": "穿搭主题名称",\n'
            '    "description": "整体风格描述(2-3句)",\n'
            '    "items_highlight": ["单品亮点1", "单品亮点2"],\n'
            '    "occasion": "适合场合",\n'
            '    "tips": "穿搭小贴士"\n'
            '  },\n'
            '  "warnings": []\n'
            '}\n'
        )

        # 从消息和搭配上下文中提取场合/风格
        occasion = ""
        style = ""
        combined = f"{msg} {styling_context}"
        for kw in ["约会", "通勤", "运动", "晚宴", "日常", "出游"]:
            if kw in combined:
                occasion = kw
                break

        retrievers = [
            ("时尚知识", lambda: _get_fashion_knowledge(occasion, style)),
        ]
        if self.user_profile:
            retrievers.append(("用户偏好", lambda: _get_user_preferences(self.user_profile, user_id)))

        pipeline = RAGPipeline(
            llm=self.llm,
            retrievers=retrievers,
            system_prompt=copywriter_prompt,
            session_id=session_id,
        )
        user_message = msg or f"为以下搭配撰写文案:\n{styling_context}"
        result = pipeline.run(user_message)
        raw_output = result["reply"]

        from agent.core import parse_agent_result
        structured = parse_agent_result(raw_output, "copywriter")

        from langchain_core.messages import AIMessage
        return {
            "messages": [AIMessage(content=json.dumps(structured, ensure_ascii=False))],
            "rag_trace": {
                "agent": "copywriter",
                "retrieved": list(pipeline.retrieved_contexts.keys()),
                "generation_len": len(raw_output),
                "structured": True,
            },
        }


def create_copywriter_agent(llm=None, user_profile=None) -> dict:
    if llm is None:
        llm = init_models()["planner"]
    agent = CopywriterAgent(llm=llm, user_profile=user_profile)
    return {"name": "copywriter", "agent": agent, "description": "时尚文案助手（RAG闭环）"}
