from agent.core import init_models, create_aiwear_agent
from tools.rag_tools import get_fashion_knowledge_tool


def _create_user_preferences_tool(user_profile):
    from langchain_core.tools import tool
    import json

    @tool(description="读取用户穿搭偏好，返回用户喜欢的风格、场合、收藏。返回 JSON")
    def get_user_preferences_tool(user_id: str = "default") -> str:
        prefs = user_profile.get_preferences(user_id)
        return json.dumps({"preferences": prefs}, ensure_ascii=False)

    return get_user_preferences_tool


def create_copywriter_agent(llm=None, user_profile=None) -> dict:
    if llm is None:
        llm = init_models()["planner"]
    system_prompt = "你是时尚文案助手，为搭配结果撰写简洁优雅的描述文案。包括穿搭要点、适合场合、风格说明。"
    tools = [get_fashion_knowledge_tool]
    if user_profile:
        tools.append(_create_user_preferences_tool(user_profile))
    agent = create_aiwear_agent(
        tools=tools,
        system_prompt=system_prompt,
    )
    return {"name": "copywriter", "agent": agent, "description": "时尚文案助手"}


def run_copywriter(state: dict) -> dict:
    wardrobe_ctx = state.get("wardrobe_context", "")
    styling_ctx = state.get("styling_context", "")
    combined = f"衣物: {wardrobe_ctx}\n搭配: {styling_ctx}"
    state["copywriting_input"] = combined
    return state
